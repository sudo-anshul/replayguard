"""Execute existing Python handler code and assess independently observed effects."""
import contextlib
import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import time
import types
import uuid

from .adapters import LocalLambdaTransport, MemoryLedger
from .cases import CASE_IDS, ITERATION, PLAN_SHA256, load_case

EXIT_CODES = {"pass": 0, "violation": 1, "incomplete": 2, "unresolved": 3}
INJECTED_ERROR = "Injected crash AFTER successful simulated fulfillment; SQS must redeliver"
DELIVERY_TIMEOUT_SECONDS = 2
BOUNDARIES = [
    "Actual existing worker.py and provider.py execute through explicit local adapters; this is not AWS execution or stored-evidence verification.",
    "The observer independently snapshots a process-local MemoryLedger. It models atomic receiver-owned receipt creation only, not DynamoDB durability or service behavior.",
    "Delivery schedules are declared finite inputs (maximum two deliveries); they do not model SQS timing, visibility, concurrency, redrive or all possible interleavings.",
    "No external payment, shipment, email or customer order is attempted. An external effect without an atomic idempotency contract is explicitly unresolved.",
    "A suite pass means observed outcomes match the frozen expectations, including expected buggy-handler violations. It does not mean every handler is safe.",
    "The guard blocks normal Python network, SDK, process and FFI APIs. This trusted-code lab is not a sandbox for adversarial native code.",
]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _load_source(path, label, source_bytes):
    # Compile the same captured bytes whose SHA-256 is reported. Import loaders
    # can otherwise execute a timestamp-valid stale .pyc for different source.
    name = "replayguard_local_" + label + "_" + uuid.uuid4().hex
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    code = compile(source_bytes, str(path), "exec", dont_inherit=True)
    exec(code, module.__dict__)
    if not callable(getattr(module, "handler", None)):
        raise ValueError(label + " has no callable handler")
    return module


@contextlib.contextmanager
def _local_environment():
    local = {"LAB_EXPIRES_AT": str(int(time.time()) + 60), "PROVIDER_FUNCTION_ARN": LocalLambdaTransport.FUNCTION_NAME}
    previous = {key: os.environ.get(key) for key in local}
    os.environ.update(local)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class DeliveryDeadline(TimeoutError):
    pass


@contextlib.contextmanager
def _delivery_deadline():
    if not hasattr(signal, "setitimer") or not hasattr(signal, "SIGALRM"):
        raise RuntimeError("This runner requires POSIX delivery deadline support")
    def timeout(signum, frame):
        raise DeliveryDeadline("Local handler exceeded the two-second delivery bound")
    previous = signal.signal(signal.SIGALRM, timeout)
    old_timer = signal.setitimer(signal.ITIMER_REAL, DELIVERY_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if old_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, *old_timer)


def _error(error):
    return {"type": type(error).__name__, "message": str(error)[:1000]}


def _read_events(buffer, delivery, events, errors):
    for line in buffer.getvalue().splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            errors.append({"type": "UnparsedHandlerLog", "message": line[:300]})
            continue
        if not isinstance(value, dict):
            errors.append({"type": "UnparsedHandlerLog", "message": "Handler log is not a JSON object"})
            continue
        value["localObservationIndex"] = len(events)
        value["localDeliveryIndex"] = delivery
        events.append(value)


def _assess(result, case, guard_attempts):
    assertions = []
    def add(identifier, status, expected, observed, detail):
        assertions.append({"id": identifier, "status": status, "expected": expected, "observed": observed, "detail": detail})
    if case["effectModel"] != "receiver-owned-receipt":
        add("supported-effect-model", "unresolved", "receiver atomically owns effect and idempotency", case["effectModel"], "Unsupported external side effect rejected before handler import/execution; no external outcome is invented.")
        return assertions
    add("source-executed", "pass" if result["execution"]["sourcesLoaded"] else "incomplete", "existing worker and provider modules loaded", result["execution"]["sourcesLoaded"], "The runner executes the captured handler source bytes at their existing entry points; the reported SHA-256 fingerprints those exact bytes.")
    add("no-forbidden-operations", "unresolved" if guard_attempts else "pass", 0, guard_attempts, "Any handler network, SDK, subprocess or native FFI attempt is blocked and invalidates this local result.")
    deliveries = result["deliveries"]
    add("finite-schedule-executed", "pass" if len(deliveries) == len(case["deliveries"]) else "incomplete", len(case["deliveries"]), len(deliveries), "Only the fixed declared deliveries execute; there are no automatic retries.")
    events = result["events"]
    incomplete_deliveries = []
    fault_proven = case["fault"] == "none"
    for index, delivery in enumerate(deliveries):
        worker_events = [e for e in events if e.get("component") == "worker" and e.get("requestId") == delivery["requestId"] and e.get("messageId") == delivery["messageId"] and e.get("receiveCount") == delivery["receiveCount"]]
        def stage(name):
            return [e for e in worker_events if e.get("stage") == name]
        received, succeeded, completed = stage("received"), stage("fulfillment_succeeded"), stage("completed")
        expected_fault = case["fault"] == "crash-after-fulfillment" and delivery["receiveCount"] == 1
        if expected_fault:
            faults, failures = stage("fault_injected"), stage("failed")
            error = delivery.get("error") or {}
            sequence = bool(received and succeeded and faults and failures and received[0]["localObservationIndex"] < succeeded[0]["localObservationIndex"] < faults[0]["localObservationIndex"] < failures[0]["localObservationIndex"])
            receipt_id = faults[0].get("receiptId") if faults else None
            receipts = result["ledgerSnapshot"] or []
            provider_accept = any(e.get("component") == "provider" and e.get("stage") == "accepted" and e.get("workerRequestId") == delivery["requestId"] and e.get("receiptId") == receipt_id and succeeded and e["localObservationIndex"] < succeeded[0]["localObservationIndex"] for e in events)
            durable = any(r.get("receiptId") == receipt_id and r.get("receiveCount") == 1 and r.get("messageId") == delivery["messageId"] for r in receipts)
            fault_proven = sequence and provider_accept and durable and error.get("type") == "RuntimeError" and error.get("message") == INJECTED_ERROR and faults[0].get("fault") == case["fault"] and not completed
            if not fault_proven:
                incomplete_deliveries.append(index + 1)
        else:
            sequence = bool(received and succeeded and completed and received[0]["localObservationIndex"] < succeeded[0]["localObservationIndex"] < completed[0]["localObservationIndex"])
            if delivery.get("error") or not delivery.get("returnedNormally") or not sequence:
                incomplete_deliveries.append(index + 1)
    add("required-completions", "incomplete" if incomplete_deliveries else "pass" if deliveries else "incomplete", "all non-fault deliveries return normally after a completed event", incomplete_deliveries, "An immediate exception or missing completion cannot pass. Only a fully evidenced configured first-delivery crash is expected.")
    if case["fault"] != "none":
        add("post-fulfillment-fault", "pass" if fault_proven else "incomplete", "provider acceptance → worker success → injected error → same-message retry", fault_proven, "The known exception text alone is insufficient: ordered real logs and an independently observed receipt are required.")
    receipts = result["ledgerSnapshot"]
    if receipts is None:
        add("independent-receipt-observation", "incomplete", "observer reads the ledger independently", None, "The case deliberately withholds the snapshot; worker responses and logs cannot fill this evidence gap.")
        return assertions
    add("independent-receipt-observation", "pass", "observer snapshot after execution", len(receipts), "Receipt counts come directly from MemoryLedger state, never a worker returned result.")
    invalid_receipts = []
    order = case["order"]
    message_ids = {delivery["messageId"] for delivery in deliveries}
    for receipt in receipts:
        valid = (receipt.get("runId") == result["runId"] and receipt.get("mode") == result["mode"] and all(receipt.get(key) == value for key, value in order.items()) and receipt.get("PK") == f"RUN#{result['runId']}#MODE#{result['mode']}" and receipt.get("SK") == "RECEIPT#" + str(receipt.get("receiptId")) and receipt.get("messageId") in message_ids)
        if not valid:
            invalid_receipts.append(receipt.get("receiptId"))
    add("receipt-input-integrity", "unresolved" if invalid_receipts else "pass", "all receipts belong to the executed logical order", invalid_receipts, "The same logical order identity spans the declared deliveries, including different message IDs.")
    count = len({receipt.get("receiptId") for receipt in receipts})
    add("single-fulfillment", "pass" if count == 1 else "violation" if count > 1 else "incomplete", 1, count, "One durable local receipt is the only modeled fulfillment effect. More than one is a directly observed safety violation.")
    if result["errors"] and not all(error.get("expectedInjectedFault") for error in result["errors"]):
        add("execution-errors", "incomplete", "no unexplained execution errors", [error["type"] for error in result["errors"] if not error.get("expectedInjectedFault")], "Unexpected import, provider, parse or handler failures prevent a pass.")
    return assertions


def _status(assertions):
    statuses = {item["status"] for item in assertions}
    for status in ("unresolved", "violation", "incomplete"):
        if status in statuses:
            return status
    return "pass" if assertions else "incomplete"


def execute_case(case, mode, source_dir, source_bytes, guard, run_id):
    result = {"caseId": case["id"], "title": case["title"], "mode": mode, "runId": run_id, "provenance": "local-execution", "expectedStatus": case["expectedStatus"][mode], "observedStatus": "incomplete", "exitCode": 2, "expectationMatched": False, "case": copy.deepcopy(case), "execution": {"performed": False, "sourcesLoaded": False, "handlerInvocations": 0, "providerInvocations": 0, "maxDeliveries": case["maxDeliveries"], "maximumDeliveryRuntimeSeconds": DELIVERY_TIMEOUT_SECONDS}, "deliveries": [], "providerInvocations": [], "events": [], "ledgerSnapshot": None, "ledgerOperations": [], "errors": [], "assertions": []}
    blocked_before = guard.snapshot()["handlerBlockedOperationCount"]
    ledger = MemoryLedger()
    transport = None
    if case["effectModel"] == "receiver-owned-receipt":
        imported = io.StringIO()
        try:
            with contextlib.redirect_stdout(imported), _delivery_deadline():
                provider = _load_source(source_dir / "provider.py", "provider", source_bytes["provider.py"])
                worker = _load_source(source_dir / "worker.py", "worker", source_bytes["worker.py"])
            _read_events(imported, None, result["events"], result["errors"])
            result["execution"]["sourcesLoaded"] = True
            provider._table = ledger
            transport = LocalLambdaTransport(provider)
            worker._lambda_client = transport
            with _local_environment():
                for index, scheduled in enumerate(case["deliveries"]):
                    message_id = run_id + "-" + scheduled["messageKey"]
                    request_id = "local-worker-" + uuid.uuid4().hex
                    payload = {"runId": run_id, "mode": mode, "order": copy.deepcopy(case["order"]), "fault": case["fault"]}
                    event = {"Records": [{"messageId": message_id, "body": json.dumps(payload, separators=(",", ":")), "attributes": {"ApproximateReceiveCount": str(scheduled["receiveCount"])}}]}
                    delivery = {"index": index + 1, "messageId": message_id, "receiveCount": scheduled["receiveCount"], "requestId": request_id, "input": copy.deepcopy(event), "startedAt": utc_now(), "returnedNormally": False, "returned": None, "error": None}
                    result["deliveries"].append(delivery)
                    result["execution"]["performed"] = True
                    result["execution"]["handlerInvocations"] += 1
                    captured = io.StringIO()
                    try:
                        with contextlib.redirect_stdout(captured), _delivery_deadline():
                            returned = worker.handler(event, types.SimpleNamespace(aws_request_id=request_id))
                        delivery["returned"] = returned
                        delivery["returnedNormally"] = True
                    except Exception as error:
                        delivery["error"] = _error(error)
                        expected = case["fault"] == "crash-after-fulfillment" and scheduled["receiveCount"] == 1 and type(error) is RuntimeError and str(error) == INJECTED_ERROR
                        result["errors"].append({**_error(error), "deliveryIndex": index + 1, "expectedInjectedFault": expected})
                    finally:
                        delivery["finishedAt"] = utc_now()
                        _read_events(captured, index + 1, result["events"], result["errors"])
        except Exception as error:
            result["errors"].append({**_error(error), "phase": "source-import-or-adapter-setup", "expectedInjectedFault": False})
        finally:
            if case["observation"] == "independent-ledger":
                result["ledgerSnapshot"] = ledger.independent_snapshot()
            result["ledgerOperations"] = copy.deepcopy(ledger.operations)
            if transport:
                result["providerInvocations"] = copy.deepcopy(transport.invocations)
                result["execution"]["providerInvocations"] = len(transport.invocations)
    else:
        result["execution"]["reasonNotExecuted"] = "Unsupported external side effect: no atomic receiver contract to model."
    blocked = guard.snapshot()["handlerBlockedOperationCount"] - blocked_before
    result["assertions"] = _assess(result, case, blocked)
    result["observedStatus"] = _status(result["assertions"])
    result["exitCode"] = EXIT_CODES[result["observedStatus"]]
    result["expectationMatched"] = result["observedStatus"] == result["expectedStatus"]
    return result


def run(root, source_dir, guard, selected_case=None, selected_mode=None):
    started = utc_now()
    plan_path = root / "docs/iteration-01/plan.json"
    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest() if plan_path.exists() else None
    if plan_hash != PLAN_SHA256:
        raise ValueError("Frozen pre-implementation plan is absent or changed; refusing execution")
    source_bytes = {name: (source_dir / name).read_bytes() for name in ("worker.py", "provider.py")}
    source_hashes = {"src/" + name: hashlib.sha256(data).hexdigest() for name, data in source_bytes.items()}
    selected_ids = [selected_case] if selected_case else CASE_IDS
    loaded = [(case_id, *load_case(root / "cases/local" / (case_id + ".json"))) for case_id in selected_ids]
    case_hashes = {"cases/local/" + case_id + ".json": digest for case_id, _, digest in loaded}
    results = []
    for _, case, _ in loaded:
        run_id = "local-" + uuid.uuid4().hex
        for mode in ([selected_mode] if selected_mode else ("vulnerable", "repaired")):
            results.append(execute_case(case, mode, source_dir, source_bytes, guard, run_id))
    matched = all(result["expectationMatched"] for result in results)
    single = selected_case is not None and selected_mode is not None
    command_exit = results[0]["exitCode"] if single else (0 if matched else 1)
    return {"schemaVersion": 1, "provenance": "local-execution", "supervisorIteration": ITERATION, "startedAt": started, "recordedAt": utc_now(), "boundaries": BOUNDARIES, "noNetworkGuard": guard.snapshot(), "runtime": {"python": sys.version.split()[0], "isolated": bool(sys.flags.isolated), "noSitePackages": bool(sys.flags.no_site), "sdkImported": any(name == "boto3" or name.startswith("boto3.") or name == "botocore" or name.startswith("botocore.") for name in sys.modules)}, "sourceSha256": source_hashes, "caseSha256": case_hashes, "plan": {"path": "docs/iteration-01/plan.json", "sha256": plan_hash, "frozenBeforeImplementation": True}, "results": results, "suite": {"status": "passed" if matched else "failed", "exitCode": 0 if matched else 1, "expectationsMatched": matched, "matchedCount": sum(result["expectationMatched"] for result in results), "totalCount": len(results), "allHandlersSafe": all(result["observedStatus"] == "pass" for result in results), "meaning": "Suite passed means all declared outcomes matched, including expected vulnerable violations and explicit incomplete/unresolved cases."}, "command": {"kind": "single-handler" if single else "expectation-suite", "exitCode": command_exit}}


def write_report(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)
