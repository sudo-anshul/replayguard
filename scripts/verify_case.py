#!/usr/bin/env python3
"""Derive ReplayGuard's verdict from raw evidence, without AWS credentials.

Evidence is an exported observation, not a cryptographic attestation by AWS.
Stored statuses and the convenience `attempts` array are never trusted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

MODES = ("vulnerable", "repaired")
CLOCK_SKEW_SECONDS = 2  # AWS Lambda hosts have separate wall clocks.
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


def strict_json(data):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant: {value}")))


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(keys))}")


def validate_case(case):
    exact_keys(case, {"schemaVersion", "name", "orders", "fault", "bounds"}, "Case")
    if type(case["schemaVersion"]) is not int or case["schemaVersion"] != 1:
        raise ValueError("Case schemaVersion must be 1")
    if not isinstance(case["name"], str) or not IDENTIFIER.fullmatch(case["name"]):
        raise ValueError("Case name must be 1-64 identifier characters")
    if not isinstance(case["orders"], list) or not 1 <= len(case["orders"]) <= 3:
        raise ValueError("Case requires 1-3 orders")
    identifiers = set()
    for order in case["orders"]:
        exact_keys(order, {"orderId", "sku", "quantity"}, "Order")
        if not isinstance(order["orderId"], str) or not IDENTIFIER.fullmatch(order["orderId"]):
            raise ValueError("orderId must be 1-64 identifier characters")
        if order["orderId"] in identifiers:
            raise ValueError("orderId must be unique within a case")
        identifiers.add(order["orderId"])
        if not isinstance(order["sku"], str) or not SKU.fullmatch(order["sku"]):
            raise ValueError("sku must be 1-128 supported identifier characters")
        if type(order["quantity"]) is not int or not 1 <= order["quantity"] <= 100:
            raise ValueError("quantity must be an integer from 1 to 100")
    exact_keys(case["fault"], {"type"}, "Fault")
    if case["fault"]["type"] != "crash-after-fulfillment":
        raise ValueError("This regression requires fault.type=crash-after-fulfillment")
    exact_keys(case["bounds"], {"maxWaitSeconds", "maxMessages", "drainGraceSeconds"}, "Bounds")
    bounds = case["bounds"]
    for key, low, high in (("maxWaitSeconds", 30, 180), ("maxMessages", 2, 6), ("drainGraceSeconds", 10, 30)):
        if type(bounds[key]) is not int or not low <= bounds[key] <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}")
    if 2 * len(case["orders"]) > bounds["maxMessages"]:
        raise ValueError("maxMessages must allow one message per order in each mode")
    if bounds["maxWaitSeconds"] < bounds["drainGraceSeconds"] + 20:
        raise ValueError("maxWaitSeconds must leave 20 seconds in addition to drain grace")
    return case


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def time_value(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (ValueError, OverflowError):
            pass
    return None


def event_time(event):
    value = event.get("eventTimestamp")
    return value / 1000 if isinstance(value, (int, float)) else time_value(event.get("timestamp"))


def derive_assertions(evidence):
    assertions = []

    def add(identifier, label, status, expected, observed, detail):
        assertions.append({"id": identifier, "label": label, "status": status,
                           "expected": expected, "observed": observed, "detail": detail})

    if not isinstance(evidence, dict):
        add("evidence-schema", "Readable evidence", "incomplete", "JSON object", type(evidence).__name__, "Evidence must be a JSON object.")
        return assertions
    try:
        case = validate_case(evidence.get("case"))
    except (ValueError, TypeError) as error:
        add("case-valid", "Valid bounded case", "incomplete", "strict schemaVersion 1", None, str(error))
        return assertions
    valid_meta = type(evidence.get("schemaVersion")) is int and evidence.get("schemaVersion") == 1 and evidence.get("provenance") == "aws" and bool(IDENTIFIER.fullmatch(str(evidence.get("runId", ""))))
    add("aws-provenance", "AWS run identified", "passed" if valid_meta else "incomplete", "aws provenance, schema 1 and runId", {k: evidence.get(k) for k in ("schemaVersion", "provenance", "runId", "region")}, "Offline verification checks the export's consistency; it cannot authenticate AWS provenance.")
    correct_inputs = evidence.get("inputs") == {"orders": case["orders"]} and evidence.get("fault") == case["fault"]
    hash_matches = evidence.get("artifacts", {}).get("canonicalCaseSha256") == canonical_hash(case)
    add("case-integrity", "Inputs match captured case", "passed" if correct_inputs and hash_matches else "unresolved", "case inputs, fault and canonical hash agree", {"inputsMatch": correct_inputs, "hashMatches": hash_matches}, "The exported case must be the case whose messages were sent.")
    api_errors = list(evidence.get("apiErrors", []))
    if evidence.get("collection", {}).get("unparsedLogEvents", 0):
        api_errors.append({"code": "UnparsedLogEvents", "message": "Some returned run logs could not be decoded"})
    add("collection-complete", "AWS observations collected", "incomplete" if api_errors else "passed", "no collection errors", api_errors, "Any AWS API failure leaves this run incomplete; retry with a fresh run after fixing the reported error.")
    run_id = evidence.get("runId")
    messages = evidence.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    orders = case["orders"]
    expected_pairs = {(mode, order["orderId"]) for mode in MODES for order in orders}
    actual_pairs = [(m.get("mode"), m.get("orderId")) for m in messages if isinstance(m, dict)]
    message_ids = [m.get("messageId") for m in messages if isinstance(m, dict)]
    bad_message_hash = False
    for message in messages:
        if not isinstance(message, dict):
            continue
        order = next((o for o in orders if o["orderId"] == message.get("orderId")), None)
        if order is not None and message.get("mode") in MODES:
            body = {"runId": run_id, "mode": message["mode"], "order": order, "fault": case["fault"]["type"]}
            expected_hash = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            bad_message_hash |= message.get("bodySha256") != expected_hash
    correct_messages = not bad_message_hash and set(actual_pairs) == expected_pairs and len(actual_pairs) == len(expected_pairs) and all(isinstance(m, str) and m for m in message_ids) and len(set(message_ids)) == len(message_ids)
    contradiction = bad_message_hash or len(actual_pairs) > len(expected_pairs) or any(p not in expected_pairs for p in actual_pairs) or len(message_ids) != len(set(message_ids))
    add("bounded-dispatch", "Exact SQS messages recorded", "passed" if correct_messages else "unresolved" if contradiction else "incomplete", len(expected_pairs), len(messages), "Exactly one SendMessage per order per mode; SQS message IDs bind retries to those original messages.")
    events = evidence.get("events", [])
    if not isinstance(events, list):
        events = []
    worker_events = [e for e in events if isinstance(e, dict) and e.get("source") == "worker" and e.get("component") == "worker" and e.get("runId") == run_id]
    receipts_by_mode = evidence.get("receipts", {})
    if not isinstance(receipts_by_mode, dict):
        receipts_by_mode = {}
    completion_times = []
    for mode in MODES:
        raw = receipts_by_mode.get(mode, [])
        raw = raw if isinstance(raw, list) else []
        known_orders = {order["orderId"]: order for order in orders}
        malformed = []
        receipt_ids = []
        for receipt in raw:
            if not isinstance(receipt, dict):
                malformed.append("receipt is not an object")
                continue
            receipt_ids.append(receipt.get("receiptId"))
            order = known_orders.get(receipt.get("orderId"))
            expected_pk = f"RUN#{run_id}#MODE#{mode}"
            submitted = [m for m in messages if isinstance(m, dict) and m.get("mode") == mode and order and m.get("orderId") == order["orderId"]]
            bound_message = submitted[0].get("messageId") if len(submitted) == 1 else None
            consistent = order is not None and receipt.get("runId") == run_id and receipt.get("mode") == mode and receipt.get("PK") == expected_pk and receipt.get("SK") == f"RECEIPT#{receipt.get('receiptId')}" and isinstance(receipt.get("receiptId"), str) and bool(receipt.get("receiptId")) and receipt.get("sku") == order["sku"] and type(receipt.get("quantity")) is int and receipt.get("quantity") == order["quantity"] and time_value(receipt.get("createdAt")) is not None and bool(receipt.get("invocationId")) and type(receipt.get("expiresAt")) is int and receipt.get("messageId") == bound_message and bool(bound_message) and type(receipt.get("receiveCount")) is int and receipt["receiveCount"] >= 1
            if consistent and mode == "repaired":
                expected_key = hashlib.sha256(json.dumps([run_id, order["orderId"]], separators=(",", ":")).encode()).hexdigest()
                consistent = receipt.get("idempotencyKey") == expected_key and receipt.get("receiptId") == expected_key
            matching_successes = [e for e in worker_events if e.get("mode") == mode and e.get("messageId") == bound_message and e.get("receiptId") == receipt.get("receiptId") and e.get("stage") == "fulfillment_succeeded" and event_time(e) is not None]
            if consistent and matching_successes:
                consistent = time_value(receipt["createdAt"]) <= min(event_time(e) for e in matching_successes) + CLOCK_SKEW_SECONDS
            if not consistent:
                malformed.append(receipt.get("receiptId", "missing receiptId"))
        if len(receipt_ids) != len(set(str(i) for i in receipt_ids)):
            malformed.append("duplicate ledger receipt identity")
        add(f"{mode}-ledger-inputs", f"{mode.title()} ledger matches inputs", "unresolved" if malformed else "passed" if raw else "incomplete", "independent ledger receipts for this run and exact order payload", malformed or len(raw), "Receipts are queried directly from DynamoDB with ConsistentRead, separately from worker success logs.")
        for order in orders:
            oid = order["orderId"]
            prefix = f"{mode}-{oid}"
            records = [r for r in raw if isinstance(r, dict) and r.get("orderId") == oid and r.get("runId") == run_id and r.get("mode") == mode]
            ledger_ids = {r.get("receiptId") for r in records if isinstance(r.get("receiptId"), str)}
            count = len(ledger_ids)
            expected_count = ">=2 distinct receipts" if mode == "vulnerable" else "exactly 1 receipt"
            count_status = ("passed" if count >= 2 else "incomplete") if mode == "vulnerable" else ("passed" if count == 1 else "unresolved" if count > 1 else "incomplete")
            add(f"{prefix}-receipt-count", f"{mode.title()}: fulfillment count for {oid}", count_status, expected_count, count, "Each durable receipt represents one simulated fulfillment side effect; retries are counted independently of the worker.")
            sent = [m for m in messages if isinstance(m, dict) and m.get("mode") == mode and m.get("orderId") == oid]
            msgid = sent[0].get("messageId") if len(sent) == 1 else None
            matching = [e for e in worker_events if msgid and e.get("mode") == mode and e.get("orderId") == oid and e.get("messageId") == msgid]
            received = [e for e in matching if e.get("stage") == "received" and type(e.get("receiveCount")) is int and e["receiveCount"] >= 1 and e.get("requestId")]
            first = [e for e in received if e["receiveCount"] == 1]
            retried = [e for e in received if e["receiveCount"] >= 2]
            redelivery = any(a["requestId"] != b["requestId"] and event_time(a) is not None and event_time(b) is not None and event_time(b) > event_time(a) for a in first for b in retried)
            add(f"{prefix}-redelivery", f"{mode.title()}: SQS redelivered {oid}", "passed" if redelivery else "incomplete", "same sent messageId, receiveCount 1 then >=2, distinct invocations", [{k: e.get(k) for k in ("messageId", "receiveCount", "requestId")} for e in received], "Two separately observed worker invocations must handle the exact SQS message originally sent.")
            faults = [e for e in matching if e.get("stage") == "fault_injected"]
            good_faults = []
            for fault in faults:
                succeeded = [e for e in matching if e.get("stage") == "fulfillment_succeeded" and e.get("requestId") == fault.get("requestId") and e.get("receiptId") == fault.get("receiptId") and event_time(e) is not None and event_time(fault) is not None and event_time(e) <= event_time(fault) and any(event_time(r) is not None and event_time(r) <= event_time(e) and r.get("requestId") == e.get("requestId") for r in first)]
                failed = [e for e in matching if e.get("stage") == "failed" and e.get("requestId") == fault.get("requestId") and event_time(e) is not None and event_time(fault) is not None and event_time(e) >= event_time(fault)]
                started = any(e.get("requestId") == fault.get("requestId") and event_time(e) is not None and event_time(fault) is not None and event_time(e) <= event_time(fault) for e in first)
                durable_receipt = next((r for r in records if r.get("receiptId") == fault.get("receiptId")), None)
                durable_before_fault = durable_receipt is not None and durable_receipt.get("receiveCount") == 1 and time_value(durable_receipt.get("createdAt")) is not None and event_time(fault) is not None and time_value(durable_receipt["createdAt"]) <= event_time(fault) + CLOCK_SKEW_SECONDS
                if succeeded and failed and started and durable_before_fault and fault.get("receiveCount") == 1 and fault.get("fault") == case["fault"]["type"] and fault.get("receiptId") in ledger_ids:
                    good_faults.append(fault)
            bad_fault = any(f.get("receiveCount") != 1 or f.get("fault") != case["fault"]["type"] for f in faults)
            add(f"{prefix}-fault-after-fulfillment", f"{mode.title()}: crash followed a durable fulfillment", "unresolved" if bad_fault else "passed" if good_faults else "incomplete", "received → success → injected crash → failed; receipt exists in ledger", [f.get("receiptId") for f in faults], "The injected failure must occur after a separately verified durable receipt, on receiveCount 1. Receipt clock comparisons permit 2 seconds of cross-Lambda clock skew.")
            completed = [e for e in matching if e.get("stage") == "completed" and type(e.get("receiveCount")) is int and e["receiveCount"] >= 2 and e.get("receiptId") in ledger_ids and any(r.get("requestId") == e.get("requestId") and r.get("receiveCount") == e.get("receiveCount") for r in retried) and any(s.get("stage") == "fulfillment_succeeded" and s.get("requestId") == e.get("requestId") and s.get("receiptId") == e.get("receiptId") and event_time(s) is not None and event_time(e) is not None and event_time(s) <= event_time(e) and any(r.get("requestId") == e.get("requestId") and r.get("receiveCount") == e.get("receiveCount") and event_time(r) is not None and event_time(r) <= event_time(s) for r in retried) for s in matching)]
            add(f"{prefix}-completed", f"{mode.title()}: retry completed", "passed" if completed else "incomplete", "retry returned success referencing an independent receipt", [e.get("receiptId") for e in completed], "Successful completion is required for both handlers, not just a receipt appearing.")
            completion_times.extend(event_time(e) for e in completed if event_time(e) is not None)
            if mode == "repaired":
                retry_successes = [s for s in matching if s.get("stage") == "fulfillment_succeeded" and type(s.get("receiveCount")) is int and s["receiveCount"] >= 2 and any(s.get("requestId") == e.get("requestId") and s.get("receiptId") == e.get("receiptId") for e in completed)]
                reuse_contract = bool(retry_successes) and all(s.get("accepted") is False and s.get("reused") is True for s in retry_successes)
                contradictory_reuse = any(("accepted" in s and s["accepted"] is not False) or ("reused" in s and s["reused"] is not True) for s in retry_successes)
                reused = bool(good_faults and completed and good_faults[0].get("receiptId") == completed[-1].get("receiptId") and reuse_contract)
                add(f"{prefix}-same-receipt", "Repaired retry reused the durable receipt", "passed" if reused else "unresolved" if count > 1 or contradictory_reuse else "incomplete", "same receiptId, retry accepted=false and reused=true", {"fault": [e.get("receiptId") for e in good_faults], "completed": [e.get("receiptId") for e in completed]}, "Receiver-side idempotency must preserve one receipt for the logical order across redelivery.")
    snapshots = evidence.get("queueObservations", [])
    snapshots = [s for s in snapshots if isinstance(s, dict)] if isinstance(snapshots, list) else []
    latest_completion = max(completion_times, default=float("inf"))
    zero_since = None
    drain_seconds = 0
    dlq_messages = False
    last_observed = None
    for snapshot in sorted(snapshots, key=lambda s: time_value(s.get("observedAt")) or 0):
        observed_at = time_value(snapshot.get("observedAt"))
        attributes = [snapshot.get(q, {}).get(k) for q in ("queue", "dlq") for k in ("visible", "notVisible", "delayed") if isinstance(snapshot.get(q), dict)]
        dlq_messages |= any(type(snapshot.get("dlq", {}).get(k)) is int and snapshot["dlq"][k] > 0 for k in ("visible", "notVisible", "delayed")) if isinstance(snapshot.get("dlq"), dict) else False
        if observed_at is not None and observed_at >= latest_completion and len(attributes) == 6 and all(type(v) is int and v == 0 for v in attributes):
            zero_since = observed_at if zero_since is None else zero_since
            drain_seconds = observed_at - zero_since
            last_observed = observed_at
        else:
            zero_since, drain_seconds, last_observed = None, 0, None
    grace = case["bounds"]["drainGraceSeconds"]
    reads = evidence.get("collection", {}).get("lastLedgerReadAt", {})
    final_reads = [time_value(reads.get(mode)) for mode in MODES] if isinstance(reads, dict) else []
    closed = len(final_reads) == 2 and last_observed is not None and all(t is not None and t >= last_observed for t in final_reads)
    drained = drain_seconds >= grace and closed
    add("queues-drained", "Queues stayed drained after completed retries", "unresolved" if dlq_messages else "passed" if drained else "incomplete", f"source + DLQ empty for >= {grace}s, followed by final ledger reads", {"stableDrainSeconds": round(drain_seconds, 3), "deadLetterObserved": dlq_messages, "ledgerReadAfterFinalObservation": closed}, "SQS counts are approximate. This bounded grace observation supports this run only, not a global exactly-once guarantee.")
    return assertions


def verdict(assertions):
    statuses = {a["status"] for a in assertions}
    return "unresolved" if "unresolved" in statuses else "incomplete" if "incomplete" in statuses or not assertions else "passed"


def verify(evidence):
    try:
        assertions = derive_assertions(evidence)
    except (AttributeError, TypeError, ValueError, KeyError, OverflowError) as error:
        assertions = [{"id": "evidence-schema", "label": "Well-formed raw evidence", "status": "incomplete", "expected": "schemaVersion 1 evidence", "observed": type(error).__name__, "detail": "Malformed evidence cannot establish a passing run."}]
    return {"schemaVersion": 1, "runId": evidence.get("runId") if isinstance(evidence, dict) else None,
            "status": verdict(assertions), "assertions": assertions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--case", type=Path, help="Also verify the original case file's SHA-256")
    parser.add_argument("--json", action="store_true", help="Print the full recomputed assertion report")
    parser.add_argument("--output", type=Path, help="Write the recomputed assertion report")
    args = parser.parse_args()
    try:
        evidence = strict_json(args.evidence.read_text())
        result = verify(evidence)
        if args.case:
            data = args.case.read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            matching = actual == evidence.get("artifacts", {}).get("caseSha256") and validate_case(strict_json(data)) == evidence.get("case")
            result["assertions"].append({"id": "original-case-sha256", "label": "Original case bytes match", "status": "passed" if matching else "unresolved", "expected": evidence.get("artifacts", {}).get("caseSha256"), "observed": actual, "detail": "SHA-256 binds the original case file to this export."})
            result["status"] = verdict(result["assertions"])
    except (ValueError, OSError, TypeError, AttributeError) as error:
        result = {"schemaVersion": 1, "status": "incomplete", "error": str(error), "assertions": []}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"ReplayGuard: {result['status'].upper()}")
        for assertion in result["assertions"]:
            print(f"  {assertion['status']:10} {assertion['label']}")
        if result.get("error"):
            print(result["error"])
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
