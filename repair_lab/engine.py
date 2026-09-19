"""Bounded trusted-code runner with a harness-owned receipt observer."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from datetime import datetime, timezone

from local_lab.guard import ForbiddenLocalOperation, LocalExecutionGuard
from repair_lab.plans import canonical, validate_order

STATUSES = ("pass", "incomplete", "violation", "unresolved")
EXIT_CODES = {"pass": 0, "violation": 1, "incomplete": 2, "unresolved": 3}
MAX_EFFECT_CALLS = 32
MAX_DELIVERY_CALLS = 8
PHASE_SECONDS = 2.0
SUITE_SECONDS = 60.0


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Conflict(Exception):
    """A request was rejected because its business identity already exists."""


class CrashAfterCommit(BaseException):
    """Simulated process loss after the receiver accepted an effect."""


class ExecutionTimeout(BaseException):
    pass


class EffectLimitExceeded(BaseException):
    pass


class BoundedGuard(LocalExecutionGuard):
    """Reuse the local guard, bounding diagnostics for repeated denied calls."""
    def __init__(self):
        super().__init__()
        self.total_blocked = 0
        self.handler_blocked = 0

    def reject(self, event, detail=""):
        self.total_blocked += 1
        self.handler_blocked += not self.probing
        if len(self.blocked) < 64:
            self.blocked.append({"event": event, "detail": str(detail)[:240], "duringSelfTest": self.probing})
        raise ForbiddenLocalOperation(f"Local execution guard blocked {event}")

    def snapshot(self):
        result = super().snapshot()
        result["blockedOperationCount"] = self.total_blocked
        result["handlerBlockedOperationCount"] = self.handler_blocked
        result["diagnosticsTruncated"] = self.total_blocked > len(self.blocked)
        return result


class CappedConsole(io.TextIOBase):
    def __init__(self):
        self.parts = []
        self.size = 0
        self.truncated = False

    def write(self, value):
        if not isinstance(value, str):
            value = str(value)
        remaining = max(0, 16384 - self.size)
        kept = value[:remaining]
        if kept:
            self.parts.append(kept)
            self.size += len(kept)
        self.truncated |= len(value) > remaining
        return len(value)

    def getvalue(self):
        return "".join(self.parts)


@contextlib.contextmanager
def bounded_phase(deadline):
    seconds = min(PHASE_SECONDS, deadline - time.monotonic())
    if seconds <= 0:
        raise ExecutionTimeout("suite exceeded its 60 second budget")
    def timeout_handler(signum, frame):
        raise ExecutionTimeout("execution phase exceeded its time budget")
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    old_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *old_timer)
        signal.signal(signal.SIGALRM, old_handler)


def diagnostic_return(value):
    """Bound diagnostics without serializing an arbitrary large object graph."""
    remaining = [128]
    def visit(item, depth):
        remaining[0] -= 1
        if remaining[0] < 0 or depth > 8:
            return "<truncated>"
        if item is None or type(item) in (bool, int):
            return item if not isinstance(item, int) or item.bit_length() < 256 else "<large integer>"
        if isinstance(item, str):
            return item[:512]
        if type(item) is float:
            return item if item == item and abs(item) != float("inf") else "<nonfinite>"
        if isinstance(item, (list, tuple)):
            return [visit(v, depth + 1) for v in item[:32]]
        if isinstance(item, dict):
            result = {}
            for index, (key, val) in enumerate(item.items()):
                if index == 32:
                    break
                result[str(key)[:160]] = visit(val, depth + 1)
            return result
        return f"<{type(item).__name__}>"
    return visit(value, 0)


def error_record(phase, exc):
    try:
        message = str(exc)[:1000]
    except BaseException:
        message = "exception message unavailable"
    return {"phase": phase, "type": type(exc).__name__, "message": message}


class Effects:
    Conflict = Conflict
    CrashAfterCommit = CrashAfterCommit

    def __init__(self, events):
        self._receipts = []
        self._keys = {}
        self._active = None
        self._events = events
        self._total_calls = 0
        self.protocol_errors = []

    def _event(self, kind, **fields):
        self._events.append({"index": len(self._events), "type": kind, "deliveryId": self._active["deliveryId"] if self._active else None, **copy.deepcopy(fields)})

    def fulfill(self, order, *, key=None):
        if self._active is None:
            if len(self.protocol_errors) < 8:
                self.protocol_errors.append("fulfill called outside an active delivery")
            raise RuntimeError("fulfill is only available during handle(delivery)")
        delivery = self._active
        self._total_calls = min(self._total_calls + 1, MAX_EFFECT_CALLS + 1)
        delivery["effectCalls"] = min(delivery["effectCalls"] + 1, MAX_DELIVERY_CALLS + 1)
        if self._total_calls > MAX_EFFECT_CALLS or delivery["effectCalls"] > MAX_DELIVERY_CALLS:
            raise EffectLimitExceeded("effect call bound exceeded (8 per delivery, 32 per case)")
        order = validate_order(order)
        if key is not None and (not isinstance(key, str) or not key.strip() or len(key) > 256):
            raise ValueError("effect key must be None or a nonempty string of at most 256 characters")
        if key is not None and key in self._keys:
            receipt = self._keys[key]
            if canonical(receipt["order"]) != canonical(order):
                delivery["conflictObserved"] = True
                self._event("payload-conflict", receiptId=receipt["receiptId"], order=order, key=key)
                raise Conflict("idempotency key already belongs to a different order payload")
            delivery["reusedReceiptIds"].append(receipt["receiptId"])
            self._event("receipt-reused", receiptId=receipt["receiptId"], order=order, key=key)
            return {"receiptId": receipt["receiptId"], "accepted": False, "reused": True, "order": copy.deepcopy(receipt["order"])}
        receipt = {"receiptId": f"receipt-{len(self._receipts) + 1:03d}", "order": order, "key": key, "createdAt": now(), "acceptedDeliveryId": delivery["deliveryId"]}
        self._receipts.append(receipt)
        if key is not None:
            self._keys[key] = receipt
        delivery["acceptedReceiptIds"].append(receipt["receiptId"])
        self._event("receipt-accepted", receiptId=receipt["receiptId"], order=order, key=key)
        if delivery["fault"] == "after-commit" and not delivery["faultInjected"]:
            delivery["faultInjected"] = True
            self._event("fault-injected", receiptId=receipt["receiptId"], fault="after-commit")
            raise CrashAfterCommit("receiver committed fulfillment; response was lost")
        return {"receiptId": receipt["receiptId"], "accepted": True, "reused": False, "order": copy.deepcopy(order)}

    def snapshot(self):
        return copy.deepcopy(self._receipts)


def capture_source(path):
    original = Path(path).expanduser().absolute()
    if original.is_symlink() or original.suffix != ".py" or not original.is_file():
        raise ValueError("adapter must be an existing regular .py source file, not a symlink")
    root = original.parent.resolve()
    sources = {}
    total = 0
    visited_directories = 0
    for current, directories, filenames in os.walk(root, followlinks=False):
        visited_directories += 1
        if visited_directories > 128:
            raise ValueError("adapter source folder exceeds 128 directories; use a dedicated folder")
        directories[:] = sorted(d for d in directories if d != "__pycache__")
        for directory in directories:
            if (Path(current) / directory).is_symlink():
                raise ValueError("adapter source folder cannot contain directory symlinks")
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            source = Path(current) / filename
            if source.is_symlink():
                raise ValueError("adapter source folder cannot contain Python source symlinks")
            if len(sources) >= 64:
                raise ValueError("adapter source folder exceeds 64 Python files; use a dedicated folder")
            with source.open("rb") as stream:
                data = stream.read(262145)
            total += len(data)
            if total > 262144:
                raise ValueError("adapter source folder exceeds 256 KiB of Python; use a dedicated folder")
            sources[source.relative_to(root).as_posix()] = data
    relative = original.resolve().relative_to(root).as_posix()
    if relative not in sources:
        raise ValueError("adapter source could not be captured")
    return {"root": root, "relative": relative, "sources": sources, "hashes": {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}}


def sources_unchanged(capture):
    try:
        updated = capture_source(capture["root"] / capture["relative"])
        return updated["hashes"] == capture["hashes"]
    except (OSError, ValueError):
        return False


def blank_delivery(plan):
    return {**copy.deepcopy(plan), "attempted": False, "outcome": "not-run", "error": None, "returned": None, "faultInjected": False, "effectCalls": 0, "acceptedReceiptIds": [], "reusedReceiptIds": [], "conflictObserved": False, "startedAt": None, "finishedAt": None}


def blank_result(candidate_id, case):
    return {"candidateId": candidate_id, "caseId": case["id"], "status": "incomplete", "expectedOrders": copy.deepcopy(case["expectedOrders"]), "receipts": None, "deliveries": [blank_delivery(d) for d in case["deliveries"]], "events": [], "assertions": [], "errors": [], "execution": {"imported": False, "built": False, "sourceUnchanged": True, "snapshotComplete": False, "completedSchedule": False, "console": "", "consoleTruncated": False}, "blockedOperationCount": 0}


def assess(case, result):
    """Derive conclusions from observer/harness facts; ignore supplied statuses."""
    assertions = []
    def add(aid, status, message):
        assertions.append({"id": aid, "status": status, "message": message})
    if case["effectModel"] == "unsupported-external":
        add("supported-effect", "unresolved", "The external effect does not expose the atomic receipt contract.")
    if result["blockedOperationCount"]:
        add("local-boundary", "unresolved", "Candidate attempted an operation blocked by the local execution guard.")
    execution = result["execution"]
    if case["effectModel"] != "unsupported-external":
        if not execution["imported"] or not execution["built"]:
            add("adapter-ready", "incomplete", "Adapter import/build did not complete.")
        if not execution["sourceUnchanged"]:
            add("source-stability", "incomplete", "Original or copied Python source changed during execution.")
        if not execution["completedSchedule"]:
            add("schedule-complete", "incomplete", "The bounded delivery schedule did not finish.")
        receipts = result["receipts"]
        if receipts is None or not execution["snapshotComplete"] or case["observation"] != "independent-ledger":
            add("receipt-observation", "incomplete", "Independent receiver snapshot is unavailable.")
        else:
            expected = {item["order"]["orderId"]: item for item in case["expectedOrders"]}
            for oid, item in expected.items():
                actual = [r for r in receipts if r["order"]["orderId"] == oid]
                valid = len(actual) == item["count"] and all(canonical(r["order"]) == canonical(item["order"]) for r in actual)
                add(f"order:{oid}", "pass" if valid else "violation", f"Order {oid}: expected {item['count']} receipt with the full expected payload; observed {len(actual)}.")
            unexpected = [r for r in receipts if r["order"]["orderId"] not in expected]
            if unexpected:
                add("no-unrequested-effects", "violation", f"Observed {len(unexpected)} receipt(s) for unrequested business orders.")
        for delivery in result["deliveries"]:
            did = delivery["deliveryId"]
            outcome = delivery["outcome"]
            expectation = delivery["expect"]
            status = "incomplete"
            if expectation == "complete":
                status = "pass" if outcome == "completed" else "violation" if outcome == "conflict" else "incomplete"
            elif expectation == "conflict":
                if outcome == "completed" or delivery["acceptedReceiptIds"]:
                    status = "violation"
                elif outcome == "conflict":
                    status = "pass"
            elif expectation == "crash":
                ids = set(delivery["acceptedReceiptIds"])
                committed = {r["receiptId"] for r in (result["receipts"] or []) if r["acceptedDeliveryId"] == did}
                accepted = {e.get("receiptId") for e in result["events"] if e["type"] == "receipt-accepted" and e["deliveryId"] == did}
                injected = {e.get("receiptId") for e in result["events"] if e["type"] == "fault-injected" and e["deliveryId"] == did and e.get("fault") == "after-commit"}
                if outcome == "crashed" and delivery["faultInjected"] and ids & committed & accepted & injected:
                    status = "pass"
            add(f"delivery:{did}", status, f"Delivery {did}: required {expectation}, observed {outcome}.")
        if result["errors"]:
            add("execution-errors", "incomplete", "Execution recorded an import, build, protocol, timeout, or handler error.")
    status = max((a["status"] for a in assertions), key=STATUSES.index, default="incomplete")
    result["assertions"] = assertions
    result["status"] = status
    return status


def execute_case(candidate_id, case, capture, guard, deadline):
    result = blank_result(candidate_id, case)
    if case["effectModel"] == "unsupported-external":
        assess(case, result)
        return result
    blocked_before = guard.handler_blocked
    effects = Effects(result["events"])
    console = CappedConsole()
    phase = "import"
    module_name = f"_replayguard_adapter_{candidate_id.replace('-', '_')}_{case['id'].replace('-', '_')}"
    modules_before = set(sys.modules)
    try:
        with tempfile.TemporaryDirectory(prefix="replayguard-adapter-") as temporary:
            root = Path(temporary)
            for name, data in capture["sources"].items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            adapter_path = root / capture["relative"]
            with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
                with bounded_phase(deadline):
                    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    result["execution"]["imported"] = True
                phase = "build"
                with bounded_phase(deadline):
                    build = getattr(module, "build", None)
                    if not callable(build):
                        raise TypeError("adapter must export callable build(effects)")
                    handle = build(effects)
                    if not callable(handle):
                        raise TypeError("build(effects) must return a callable handler")
                    result["execution"]["built"] = True
                for delivery in result["deliveries"]:
                    if time.monotonic() >= deadline:
                        result["errors"].append({"phase": "schedule", "type": "ExecutionTimeout", "message": "suite exceeded its 60 second budget"})
                        break
                    delivery["attempted"] = True
                    delivery["startedAt"] = now()
                    effects._active = delivery
                    effects._event("delivery-start")
                    phase = "delivery"
                    try:
                        with bounded_phase(deadline):
                            public_delivery = {key: copy.deepcopy(delivery[key]) for key in ("deliveryId", "messageId", "receiveCount", "order")}
                            delivery["returned"] = diagnostic_return(handle(public_delivery))
                        delivery["outcome"] = "completed"
                    except CrashAfterCommit as exc:
                        delivery["outcome"] = "crashed"
                        delivery["error"] = error_record("delivery", exc)
                    except Conflict as exc:
                        delivery["outcome"] = "conflict"
                        delivery["conflictObserved"] = True
                        delivery["error"] = error_record("delivery", exc)
                    except ExecutionTimeout as exc:
                        delivery["outcome"] = "timeout"
                        delivery["error"] = error_record("delivery", exc)
                        result["errors"].append(delivery["error"])
                    except BaseException as exc:
                        delivery["outcome"] = "error"
                        delivery["error"] = error_record("delivery", exc)
                        result["errors"].append(delivery["error"])
                    finally:
                        delivery["finishedAt"] = now()
                        effects._event("delivery-end", outcome=delivery["outcome"])
                        effects._active = None
                result["execution"]["completedSchedule"] = all(d["attempted"] for d in result["deliveries"])
                try:
                    with bounded_phase(deadline):
                        result["execution"]["sourceUnchanged"] = capture_source(adapter_path)["hashes"] == capture["hashes"]
                except (OSError, ValueError):
                    result["execution"]["sourceUnchanged"] = False
    except BaseException as exc:
        result["errors"].append(error_record(phase, exc))
    finally:
        # Do not leak fixture modules/state into the next case. Modules imported
        # from stdlib remain cached; only temporary candidate modules are removed.
        for name in list(set(sys.modules) - modules_before):
            loaded = sys.modules.get(name)
            source = getattr(loaded, "__file__", None)
            if name == module_name or (source and "replayguard-adapter-" in str(source)):
                sys.modules.pop(name, None)
        result["execution"]["console"] = console.getvalue()
        result["execution"]["consoleTruncated"] = console.truncated
        result["blockedOperationCount"] = guard.handler_blocked - blocked_before
        for message in effects.protocol_errors:
            result["errors"].append({"phase": "protocol", "type": "AdapterProtocolError", "message": message})
        if result["execution"]["built"] and case["observation"] == "independent-ledger":
            result["receipts"] = effects.snapshot()
            result["execution"]["snapshotComplete"] = True
    assess(case, result)
    return result


def summarize(results, errors=()):
    counts = {status: sum(r["status"] == status for r in results) for status in EXIT_CODES}
    status = max((r["status"] for r in results), key=STATUSES.index, default="incomplete")
    if errors and STATUSES.index(status) < STATUSES.index("incomplete"):
        status = "incomplete"
    return {"status": status, "exitCode": EXIT_CODES[status], "counts": counts}


def run(plan, candidate_specs):
    report = {"schemaVersion": 2, "kind": "replayguard-repair-report", "provenance": "local-execution", "startedAt": now(), "recordedAt": None, "candidates": [], "cases": copy.deepcopy(plan["cases"]), "results": [], "summary": {}, "errors": [], "boundaries": ["Trusted local Python adapters only; defense-in-depth guard is not a hostile-code sandbox.", "Receiver-owned simulated effects and bounded explicit schedules; no real AWS execution or cloud equivalence claimed.", "Independent local receipts establish effects; handler returns do not.", "Source hashes cover captured .py files in each adapter folder only; not signatures or dependency attestation."], "guard": {}}
    captures = {}
    capture_errors = {}
    deadline = time.monotonic() + SUITE_SECONDS
    for spec in candidate_specs:
        candidate = {"id": spec["id"], "title": spec["title"], "adapter": Path(spec["path"]).name, "sourceSha256": {}, "sourceHashScope": "Captured .py files recursively within adapter directory; excludes dependencies and non-Python files."}
        try:
            with bounded_phase(deadline):
                capture = capture_source(spec["path"])
            captures[spec["id"]] = capture
            candidate["adapter"] = capture["relative"]
            candidate["sourceSha256"] = capture["hashes"]
        except (OSError, ValueError, ExecutionTimeout) as exc:
            capture_errors[spec["id"]] = error_record("source-capture", exc)
        report["candidates"].append(candidate)
    sys.dont_write_bytecode = True
    guard = BoundedGuard().install()
    guard.self_test()
    for spec in candidate_specs:
        for case in plan["cases"]:
            if spec["id"] in capture_errors and case["effectModel"] != "unsupported-external":
                result = blank_result(spec["id"], case)
                result["errors"].append(capture_errors[spec["id"]])
                assess(case, result)
            else:
                result = execute_case(spec["id"], case, captures.get(spec["id"]), guard, deadline)
            report["results"].append(result)
    for spec in candidate_specs:
        capture = captures.get(spec["id"])
        try:
            with bounded_phase(deadline):
                unchanged = capture is not None and sources_unchanged(capture)
        except ExecutionTimeout:
            unchanged = False
        for case, result in zip(plan["cases"], [r for r in report["results"] if r["candidateId"] == spec["id"]]):
            result["execution"]["sourceUnchanged"] = result["execution"]["sourceUnchanged"] and unchanged
            assess(case, result)
    report["guard"] = guard.snapshot()
    report["recordedAt"] = now()
    report["summary"] = summarize(report["results"], report["errors"])
    return report
