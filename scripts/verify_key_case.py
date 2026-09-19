#!/usr/bin/env python3
"""Verify bounded v2 AWS observations offline; consistency is not AWS attestation."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

CANDIDATES = ("no-key", "sku-key", "order-key")
FAULT = "after-commit-first-receive"
CASE_KIND = "replayguard-aws-key-scope-case"
REPORT_KIND = "replayguard-aws-key-scope-report"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
PRECEDENCE = ("passed", "incomplete", "violation", "unresolved")


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def event_time(event):
    value = event.get("eventTimestamp")
    return value / 1000 if type(value) is int else timestamp(event.get("timestamp"))


def ordered(*events):
    times = [event_time(e) for e in events]
    return all(t is not None for t in times) and times == sorted(times)


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label + " has unexpected or missing fields")


def validate_order(order):
    exact(order, ("orderId", "sku", "quantity"), "order")
    if not isinstance(order["orderId"], str) or not ID.fullmatch(order["orderId"]):
        raise ValueError("Invalid order ID")
    if not isinstance(order["sku"], str) or not SKU.fullmatch(order["sku"]):
        raise ValueError("Invalid SKU")
    if type(order["quantity"]) is not int or not 1 <= order["quantity"] <= 100:
        raise ValueError("Invalid quantity")


def validate_case(case):
    exact(case, ("schemaVersion", "kind", "name", "orders", "candidates", "fault", "sequence", "bounds"), "case")
    if type(case["schemaVersion"]) is not int or case["schemaVersion"] != 2 or case["kind"] != CASE_KIND:
        raise ValueError("Expected AWS key-scope case v2")
    if not isinstance(case["name"], str) or not ID.fullmatch(case["name"]):
        raise ValueError("Invalid case name")
    if case["candidates"] != list(CANDIDATES) or not isinstance(case["orders"], list) or len(case["orders"]) != 2:
        raise ValueError("Exactly three fixed candidates and two orders required")
    for order in case["orders"]:
        validate_order(order)
    a, b = case["orders"]
    if a["orderId"] == b["orderId"] or a["sku"] != b["sku"]:
        raise ValueError("Two distinct orders must share a SKU")
    if case["fault"] != {"type": FAULT} or case["sequence"] != "first-order-commit-and-failure-before-second-order-send":
        raise ValueError("Unsupported fault or sequencing contract")
    exact(case["bounds"], ("maxWaitSeconds", "maxMessages", "drainGraceSeconds"), "bounds")
    bounds = case["bounds"]
    if type(bounds["maxWaitSeconds"]) is not int or not 180 <= bounds["maxWaitSeconds"] <= 420:
        raise ValueError("maxWaitSeconds must be 180–420")
    if type(bounds["maxMessages"]) is not int or bounds["maxMessages"] != 6:
        raise ValueError("Exactly six original sends allowed")
    if type(bounds["drainGraceSeconds"]) is not int or not 15 <= bounds["drainGraceSeconds"] <= 30:
        raise ValueError("drainGraceSeconds must be 15–30")
    return case


def key_for(run_id, candidate, order):
    if candidate == "no-key":
        return None
    field = "sku" if candidate == "sku-key" else "orderId"
    return hashlib.sha256(json.dumps([run_id, field, order[field]], separators=(",", ":")).encode()).hexdigest()


def message_body(run_id, candidate, order):
    return {"schemaVersion": 2, "runId": run_id, "candidate": candidate, "order": order, "fault": FAULT}


def status(assertions):
    return max((a["status"] for a in assertions), key=PRECEDENCE.index, default="incomplete")


def raw_context(evidence):
    case = validate_case(evidence["case"])
    messages = evidence.get("messages", [])
    events = evidence.get("events", [])
    receipts = evidence.get("receipts", {})
    reads = evidence.get("ledgerObservations", [])
    if (not isinstance(messages, list) or len(messages) > 6 or not all(isinstance(m, dict) for m in messages)
            or not isinstance(events, list) or len(events) > 2000 or not all(isinstance(e, dict) for e in events)
            or not isinstance(receipts, dict) or not isinstance(reads, list) or len(reads) > 400
            or not all(isinstance(r, dict) for r in reads)):
        raise ValueError("Malformed or oversized observations")
    return case, messages, events, receipts, reads


def delivery_facts(evidence, candidate, order):
    """Correlate message, worker, provider and ledger facts; never use summaries."""
    case, messages, events, receipts, reads = raw_context(evidence)
    run_id = evidence["runId"]
    sent = [m for m in messages if m.get("candidate") == candidate and m.get("orderId") == order["orderId"]]
    message_id = sent[0].get("messageId") if len(sent) == 1 else None
    scoped = [e for e in events if e.get("runId") == run_id and e.get("candidate") == candidate
              and e.get("messageId") == message_id and message_id and e.get("order") == order
              and e.get("orderId") == order["orderId"]]
    worker = [e for e in scoped if e.get("source") == "worker" and e.get("component") == "worker"]
    provider = [e for e in scoped if e.get("source") == "provider" and e.get("component") == "provider"]
    raw = receipts.get(candidate)
    ledger = raw if isinstance(raw, list) else []
    records = [r for r in ledger if r.get("order") == order]
    received = [e for e in worker if e.get("stage") == "received" and type(e.get("receiveCount")) is int and e["receiveCount"] >= 1 and e.get("requestId")]
    faults, fulfilled, rejected, unclosed = [], [], [], []
    for start in received:
        wid, count = start["requestId"], start["receiveCount"]
        we = [e for e in worker if e.get("requestId") == wid and e.get("receiveCount") == count]
        pe = [e for e in provider if e.get("workerRequestId") == wid and e.get("receiveCount") == count]
        terminals = []
        for commit in [e for e in pe if e.get("stage") == "accepted" and e.get("accepted") is True and e.get("reused") is False]:
            receipt = next((r for r in records if r.get("receiptId") == commit.get("receiptId")
                            and r.get("invocationId") == commit.get("requestId") and r.get("workerRequestId") == wid
                            and r.get("messageId") == message_id and r.get("receiveCount") == count), None)
            injected = [e for e in pe if e.get("stage") == "fault_injected" and e.get("requestId") == commit.get("requestId")
                        and e.get("receiptId") == commit.get("receiptId") and e.get("fault") == FAULT and ordered(commit, e)]
            provider_failed = [e for e in we if e.get("stage") == "provider_failed" and e.get("errorType") == "InjectedAfterCommit"]
            failed = [e for e in we if e.get("stage") == "failed" and any(ordered(start, p, e) for p in provider_failed)]
            durable_before_fault = (receipt is not None and timestamp(receipt.get("createdAt")) is not None
                and event_time(commit) is not None and timestamp(receipt["createdAt"]) <= event_time(commit) + 2)
            if durable_before_fault and count == 1 and injected and failed and not any(e.get("stage") == "fulfillment_succeeded" for e in we):
                faults.append({"receiptId": receipt["receiptId"], "messageId": message_id, "workerRequestId": wid,
                    "providerRequestId": commit["requestId"], "faultEventId": injected[0].get("eventId"),
                    "failureEventId": failed[0].get("eventId"), "fault": injected[0], "failure": failed[0]})
                terminals.extend(failed)
        for end in [e for e in we if e.get("stage") == "completed" and e.get("outcome") == "fulfilled"]:
            rid = end.get("receiptId")
            successes = [e for e in we if e.get("stage") == "fulfillment_succeeded" and e.get("receiptId") == rid and ordered(start, e, end)]
            receipt = next((r for r in records if r.get("receiptId") == rid), None)
            expected_key = key_for(run_id, candidate, order)
            providers = [e for e in pe if e.get("receiptId") == rid and e.get("key") == expected_key and
                         ((e.get("stage") == "accepted" and e.get("accepted") is True and e.get("reused") is False)
                          or (e.get("stage") == "reused" and e.get("accepted") is False and e.get("reused") is True))]
            if receipt and any(s.get("key") == expected_key and type(s.get("accepted")) is bool
                               and s.get("accepted") != s.get("reused") and any(p.get("accepted") == s.get("accepted") and p.get("reused") == s.get("reused") for p in providers) for s in successes):
                fulfilled.append(end)
                terminals.append(end)
        for end in [e for e in we if e.get("stage") == "completed" and e.get("outcome") == "rejected"]:
            rid = end.get("receiptId")
            receipt = next((r for r in ledger if r.get("receiptId") == rid), None)
            rejected_logs = [e for e in we if e.get("stage") == "business_rejected" and e.get("reason") == "payload-conflict" and e.get("receiptId") == rid and ordered(start, e, end)]
            conflicts = [e for e in pe if e.get("stage") == "payload_conflict" and e.get("receiptId") == rid
                         and receipt and e.get("existingOrder") == receipt.get("order") and e.get("existingOrder") != order
                         and e.get("key") == receipt.get("key") == key_for(run_id, candidate, order)]
            if conflicts and rejected_logs:
                rejected.append(end)
                terminals.append(end)
        if not terminals:
            unclosed.append(wid)
    return {"sent": sent, "messageId": message_id, "received": received, "faults": faults, "fulfilled": fulfilled,
            "rejected": rejected, "unclosed": unclosed, "records": records}


def first_order_gate(evidence, recorded_at):
    """The runner may open phase 2 only from already collected, linked raw facts."""
    case, _, events, _, reads = raw_context(evidence)
    at = timestamp(recorded_at)
    if at is None:
        return None
    proofs = []
    for candidate in CANDIDATES:
        facts = delivery_facts(evidence, candidate, case["orders"][0])
        proof = None
        for fault in facts["faults"]:
            committed = next(r for r in facts["records"] if r["receiptId"] == fault["receiptId"])
            matching_reads = [r for r in reads if r.get("candidate") == candidate and r.get("consistent") is True
                and timestamp(r.get("observedAt")) is not None and timestamp(r["observedAt"]) <= at
                and any(canonical(item) == canonical(committed) for item in (r.get("items") or []))]
            collected = [timestamp(fault[e].get("collectedAt")) for e in ("fault", "failure")]
            if matching_reads and all(t is not None and t <= at for t in collected):
                proof = {k: fault[k] for k in ("receiptId", "messageId", "workerRequestId", "providerRequestId", "faultEventId", "failureEventId")}
                proof.update(candidate=candidate, ledgerObservedAt=matching_reads[0]["observedAt"])
                break
        if proof is None:
            return None
        proofs.append(proof)
    return {"recordedAt": recorded_at, "proofs": proofs}


def conflicting_invocations(events):
    """A qualifying terminal cannot erase a contradictory fact in its invocation."""
    groups = {}
    for event in events:
        groups.setdefault((event.get("source"), event.get("requestId")), []).append(event)
    conflicts = []
    for (source, request_id), group in groups.items():
        stages = {event.get("stage") for event in group}
        bad = False
        if source == "worker":
            ends = [e for e in group if e.get("stage") == "completed"]
            outcomes = {e.get("outcome") for e in ends}
            bad = bool(ends and "failed" in stages) or len(outcomes) > 1 or bool(outcomes - {"fulfilled", "rejected"})
            markers = stages & {"fulfillment_succeeded", "business_rejected", "provider_failed"}
            bad |= len(markers) > 1
            bad |= ("fulfilled" in outcomes and bool(stages & {"business_rejected", "provider_failed"}))
            bad |= ("rejected" in outcomes and bool(stages & {"fulfillment_succeeded", "provider_failed"}))
            successes = [e for e in group if e.get("stage") == "fulfillment_succeeded"]
            flags = {(e.get("accepted"), e.get("reused")) for e in successes}
            bad |= len(flags) > 1 or any(type(e.get("accepted")) is not bool or type(e.get("reused")) is not bool
                                       or e["accepted"] == e["reused"] for e in successes)
        elif source == "provider":
            outcomes = stages & {"accepted", "reused", "payload_conflict"}
            bad = len(outcomes) > 1 or ("fault_injected" in stages and bool(outcomes - {"accepted"}))
            for event in group:
                if event.get("stage") in ("accepted", "reused"):
                    accepted = event["stage"] == "accepted"
                    bad |= event.get("accepted") is not accepted or event.get("reused") is not (not accepted)
        receipt_ids = {event.get("receiptId") for event in group if event.get("receiptId") is not None}
        bad |= len(receipt_ids) > 1
        if bad:
            conflicts.append({"source": source, "requestId": request_id})
    return conflicts


def derive(evidence):
    case, messages, events, receipts, reads = raw_context(evidence)
    assertions, candidate_results = [], []
    def add(aid, passed, detail, bad=False):
        assertions.append({"id": aid, "status": "passed" if passed else "unresolved" if bad else "incomplete", "detail": detail})
    run_id = evidence.get("runId")
    add("envelope", type(evidence.get("schemaVersion")) is int and evidence["schemaVersion"] == 2 and evidence.get("kind") == REPORT_KIND
        and evidence.get("provenance") == "aws" and isinstance(run_id, str) and bool(ID.fullmatch(run_id)), "V2 exported AWS observation; origin is not authenticated offline.")
    add("case-fingerprint", evidence.get("artifacts", {}).get("canonicalCaseSha256") == digest(case), "Case inputs and fault match their captured canonical hash.", True)
    source_hashes = evidence.get("artifacts", {}).get("sourceFiles", {})
    deployed = evidence.get("deployment", {}).get("templateSourceSha256", {})
    source_names = ("src/key_worker.py", "src/key_provider.py")
    hashes_present = (isinstance(source_hashes, dict) and isinstance(deployed, dict)
        and all(isinstance(mapping.get(name), str) and re.fullmatch(r"[a-f0-9]{64}", mapping[name])
                for mapping in (source_hashes, deployed) for name in source_names))
    sources_match = bool(hashes_present) and all(deployed[name] == source_hashes[name] for name in source_names)
    add("deployed-template-sources", sources_match, "Both exact worker/receiver paths require present SHA-256 hashes matching the deployed template; hashes are not signatures.", bool(hashes_present) and not sources_match)
    add("collection-errors", not evidence.get("apiErrors") and evidence.get("collection", {}).get("unparsedLogEvents", 0) == 0, "No API failures or undecodable run logs.")
    expected_pairs = {(c, o["orderId"]) for c in CANDIDATES for o in case["orders"]}
    pairs = [(m.get("candidate"), m.get("orderId")) for m in messages]
    ids = [m.get("messageId") for m in messages]
    contradiction = len(set(ids)) != len(ids) or len(set(pairs)) != len(pairs) or any(p not in expected_pairs for p in pairs)
    for message in messages:
        order = next((o for o in case["orders"] if o["orderId"] == message.get("orderId")), None)
        if order and message.get("candidate") in CANDIDATES:
            contradiction |= message.get("bodySha256") != digest(message_body(run_id, message["candidate"], order))
            contradiction |= message.get("phase") != 1 + case["orders"].index(order)
        contradiction |= not isinstance(message.get("messageId"), str) or not ID.fullmatch(message.get("messageId", "")) or timestamp(message.get("sentAt")) is None
    add("exact-dispatch", not contradiction and set(pairs) == expected_pairs, "Six recorded original SQS sends; an ambiguous send is never retried.", contradiction)
    gate = evidence.get("phaseGate")
    rebuilt = first_order_gate(evidence, gate.get("recordedAt")) if isinstance(gate, dict) else None
    gate_good = rebuilt is not None and gate == rebuilt
    if gate_good:
        gate_good = all(timestamp(m["sentAt"]) >= timestamp(gate["recordedAt"]) if m.get("phase") == 2
                        else timestamp(m["sentAt"]) <= timestamp(gate["recordedAt"]) for m in messages)
    add("causal-phase-gate", gate_good, "Every A receipt and post-commit worker failure were collected before any B send.", bool(gate) and not gate_good)
    event_ids = [(e.get("source"), e.get("eventId")) for e in events]
    bad_events = len(set(event_ids)) != len(event_ids)
    received_events = [e for e in events if e.get("source") == "worker" and e.get("stage") == "received"]
    invocations = {"worker": {}, "provider": {}}
    for event in events:
        pair = (event.get("candidate"), event.get("orderId"))
        message = next((m for m in messages if (m.get("candidate"), m.get("orderId")) == pair), None)
        order = next((o for o in case["orders"] if o["orderId"] == event.get("orderId")), None)
        bad_events |= (event.get("runId") != run_id or event.get("schemaVersion") != 2 or not event.get("eventId")
            or event.get("source") not in ("worker", "provider") or event.get("source") != event.get("component")
            or not message or event.get("messageId") != message.get("messageId") or event.get("order") != order
            or type(event.get("receiveCount")) is not int or event.get("receiveCount", 0) < 1
            or event_time(event) is None or timestamp(event.get("collectedAt")) is None or not event.get("requestId"))
        try:
            validate_order(event.get("order"))
        except (ValueError, TypeError):
            bad_events = True
        source = event.get("source")
        if source in invocations:
            identity = (event.get("candidate"), event.get("messageId"), event.get("receiveCount"), event.get("workerRequestId") if source == "provider" else None)
            previous = invocations[source].setdefault(event.get("requestId"), identity)
            bad_events |= previous != identity
            allowed = ("received", "provider_failed", "failed", "business_rejected", "fulfillment_succeeded", "completed") if source == "worker" else ("accepted", "reused", "fault_injected", "payload_conflict")
            bad_events |= event.get("stage") not in allowed
            wid = event.get("workerRequestId") if source == "provider" else event.get("requestId")
            bad_events |= not any(r.get("requestId") == wid and r.get("candidate") == event.get("candidate") and r.get("messageId") == event.get("messageId") and r.get("receiveCount") == event.get("receiveCount") for r in received_events)
    add("event-bindings", not bad_events, "All collected run events bind to the exact submitted order/message and have unique source IDs.", bad_events)
    conflicts = conflicting_invocations(events)
    add("invocation-consistency", not conflicts, "No single worker/provider invocation reports contradictory terminal outcomes or receipt facts.", bool(conflicts))
    terminal_times = []
    for candidate in CANDIDATES:
        raw = receipts.get(candidate)
        candidate_assertions = []
        ledger_reads = [r for r in reads if r.get("candidate") == candidate and r.get("consistent") is True]
        latest_read = ledger_reads[-1] if ledger_reads else {}
        recorded_read = evidence.get("collection", {}).get("lastLedgerReadAt", {}).get(candidate)
        ledger_complete = (isinstance(raw, list) and len(raw) <= 500 and bool(ledger_reads)
            and canonical(latest_read.get("items")) == canonical(raw) and timestamp(recorded_read) is not None
            and latest_read.get("observedAt") == recorded_read)
        add(candidate + ":independent-snapshot", ledger_complete, "Latest complete strongly consistent receipt query supplies the count.")
        malformed = False
        known_ids = set()
        for receipt in raw if isinstance(raw, list) else []:
            if not isinstance(receipt, dict):
                malformed = True
                continue
            try:
                validate_order(receipt.get("order"))
            except (ValueError, TypeError):
                malformed = True
            order = next((o for o in case["orders"] if o == receipt.get("order")), None)
            message = next((m for m in messages if m.get("candidate") == candidate and order and m.get("orderId") == order["orderId"]), None)
            rid = receipt.get("receiptId")
            key = key_for(run_id, candidate, order) if order else None
            valid_id = bool(re.fullmatch(r"[a-f0-9]{32}", str(rid))) if key is None else rid == hashlib.sha256(key.encode()).hexdigest()
            malformed |= (not order or not message or receipt.get("messageId") != message.get("messageId") or receipt.get("runId") != run_id
                or receipt.get("candidate") != candidate or receipt.get("PK") != f"RUN#{run_id}#CANDIDATE#{candidate}"
                or receipt.get("SK") != "RECEIPT#" + str(rid) or receipt.get("key") != key or not valid_id
                or rid in known_ids or type(receipt.get("receiveCount")) is not int or receipt.get("receiveCount", 0) < 1
                or timestamp(receipt.get("createdAt")) is None or not receipt.get("invocationId") or not receipt.get("workerRequestId"))
            known_ids.add(rid)
            accepts = [e for e in events if e.get("source") == "provider" and e.get("stage") == "accepted" and e.get("candidate") == candidate
                and e.get("receiptId") == rid and e.get("order") == order and e.get("requestId") == receipt.get("invocationId")
                and e.get("workerRequestId") == receipt.get("workerRequestId") and e.get("messageId") == receipt.get("messageId")
                and e.get("receiveCount") == receipt.get("receiveCount") and e.get("key") == key]
            if not accepts:
                add(candidate + ":receipt-acceptance:" + str(rid), False, "Receipt requires its independent provider acceptance event.")
        provider_receipt_ids = {e.get("receiptId") for e in events if e.get("source") == "provider" and e.get("candidate") == candidate and e.get("stage") == "accepted"}
        if ledger_complete:
            malformed |= bool(provider_receipt_ids - known_ids)
        add(candidate + ":receipt-integrity", not malformed, "Receipts match full inputs, chosen keys and original message identities.", malformed)
        if malformed:
            candidate_assertions.append({"id": "receipt-integrity", "status": "unresolved"})
        counts = {}
        for index, order in enumerate(case["orders"]):
            facts = delivery_facts(evidence, candidate, order)
            count = len(facts["records"]) if ledger_complete else None
            counts[order["orderId"]] = count
            business = "incomplete" if count is None or (count == 0 and not facts["rejected"]) else "passed" if count == 1 else "violation"
            candidate_assertions.append({"id": "order:" + order["orderId"], "status": business, "expected": 1, "observed": count})
            rejected_case = candidate == "sku-key" and index == 1
            retry = any(e.get("receiveCount", 0) >= 2 and any(f["workerRequestId"] != e.get("requestId") for f in facts["faults"]) for e in facts["fulfilled"])
            trace_good = bool(facts["rejected"]) and not facts["fulfilled"] and not facts["faults"] if rejected_case else bool(facts["faults"]) and retry and not facts["rejected"]
            trace_good = trace_good and not facts["unclosed"]
            add(candidate + ":trace:" + order["orderId"], trace_good, "Terminal payload rejection is correlated." if rejected_case else "A committed first-receive failure and same-message successful SQS retry are correlated.")
            if not trace_good:
                candidate_assertions.append({"id": "delivery:" + order["orderId"], "status": "incomplete"})
            terminal_times.extend(event_time(e) for e in facts["fulfilled"] + facts["rejected"] + [f["failure"] for f in facts["faults"]] if event_time(e) is not None)
        candidate_results.append({"candidate": candidate, "status": status(candidate_assertions), "receiptCounts": counts, "assertions": candidate_assertions})
    latest = max(terminal_times, default=float("inf"))
    zero_since, last_zero, dlq_seen = None, None, False
    for observation in evidence.get("queueObservations", []):
        at = timestamp(observation.get("observedAt"))
        values = [observation.get(q, {}).get(k) for q in ("queue", "dlq") for k in ("visible", "notVisible", "delayed")]
        dlq_seen |= any(type(observation.get("dlq", {}).get(k)) is int and observation["dlq"][k] > 0 for k in ("visible", "notVisible", "delayed"))
        if at is not None and at >= latest and all(type(v) is int and v == 0 for v in values):
            zero_since = at if zero_since is None else zero_since
            last_zero = at
        else:
            zero_since, last_zero = None, None
    final_reads = evidence.get("collection", {}).get("lastLedgerReadAt", {})
    closed = last_zero is not None and all(timestamp(final_reads.get(c)) is not None and timestamp(final_reads[c]) >= last_zero for c in CANDIDATES)
    closed = closed and timestamp(evidence.get("collection", {}).get("lastLogReadAt")) is not None and timestamp(evidence["collection"]["lastLogReadAt"]) >= last_zero
    drained = closed and zero_since is not None and last_zero - zero_since >= case["bounds"]["drainGraceSeconds"]
    add("bounded-drain", drained and not dlq_seen, "Source and DLQ observed empty after terminal outcomes, then final ledger/log reads; no claim about all future deliveries.", dlq_seen)
    expected = {"no-key": "violation", "sku-key": "violation", "order-key": "passed"}
    add("expected-business-findings", all(r["status"] == expected[r["candidate"]] for r in candidate_results), "Both faulty keys are detected and the business-order key preserves both valid orders.")
    cleanup = evidence.get("cleanup", {})
    cleanup_confirmed = (cleanup.get("status") == "deleted" and cleanup.get("verified") is True
        and cleanup.get("lastStackStatus") in ("DELETE_COMPLETE", "absent") and cleanup.get("stackArn")
        and cleanup.get("stackArn") == evidence.get("deployment", {}).get("stackArn"))
    operational = "passed" if cleanup_confirmed else "unresolved" if cleanup.get("status") in ("deleted", "failed", "unconfirmed") else "incomplete"
    return {"schemaVersion": 2, "kind": "replayguard-aws-key-scope-verdict", "runId": run_id,
        "experimentStatus": status(assertions), "operationalStatus": operational, "candidateResults": candidate_results, "assertions": assertions}


def verify(evidence, check_claims=True):
    try:
        result = derive(evidence)
        if check_claims and "result" in evidence and evidence["result"] != result:
            result["assertions"].append({"id": "stored-verdict", "status": "unresolved", "detail": "Stored verdict disagrees with recomputed observations."})
            result["experimentStatus"] = "unresolved"
        return result
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as error:
        return {"schemaVersion": 2, "kind": "replayguard-aws-key-scope-verdict", "experimentStatus": "incomplete",
            "operationalStatus": "incomplete", "candidateResults": [], "assertions": [{"id": "well-formed-evidence", "status": "incomplete", "detail": type(error).__name__ + ": malformed observations cannot establish a pass"}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        evidence = strict_json(args.evidence.read_bytes())
        result = verify(evidence)
        if args.case:
            data = args.case.read_bytes()
            if validate_case(strict_json(data)) != evidence.get("case") or hashlib.sha256(data).hexdigest() != evidence.get("artifacts", {}).get("caseSha256"):
                result["experimentStatus"] = "unresolved"
                result["assertions"].append({"id": "original-case", "status": "unresolved", "detail": "Original case bytes differ."})
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("Experiment:", result["experimentStatus"].upper(), "| cleanup:", result["operationalStatus"].upper())
            for candidate in result["candidateResults"]:
                print(candidate["candidate"], candidate["status"], candidate["receiptCounts"])
            for assertion in result["assertions"]:
                if assertion["status"] != "passed":
                    print(assertion["status"], assertion["id"])
        return 0 if result["experimentStatus"] == result["operationalStatus"] == "passed" else 2
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
