#!/usr/bin/env python3
"""Run one bounded ReplayGuard comparison against an already deployed AWS stack."""
from __future__ import annotations

import argparse
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid

from verify_case import MODES, canonical_hash, strict_json, validate_case, verify

REQUIRED_OUTPUTS = ("QueueUrl", "DlqUrl", "LedgerTable", "WorkerLogGroup", "ProviderLogGroup", "Region", "Expiry")
MAX_API_CALLS = 300
MAX_PAGES = 5
POLL_SECONDS = 5
SOURCE_PATHS = ("src/provider.py", "src/worker.py", "infra/build_template.py", "scripts/deploy.py", "scripts/destroy.py", "scripts/run_case.py", "scripts/verify_case.py", "scripts/export_case.py", "requirements.txt")
LIMITATIONS = [
    "The receipt is the simulated fulfillment side effect. No payment, shipment, email or real customer order is created.",
    "The repaired mode uses receiver-side atomic idempotency. This does not guarantee exactly once for arbitrary external APIs.",
    "SQS queue counts are approximate; the result covers this bounded run and the recorded drain grace, not all future deliveries.",
    "Logs can arrive late. Missing logs, partial API reads, expiry or deadline exhaustion produce incomplete evidence.",
    "Offline exports are integrity-checked observations, not AWS-signed attestations. A fresh AWS replay provides independent confirmation.",
]


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def sanitized_error(error, operation):
    response = getattr(error, "response", {})
    aws_error = response.get("Error", {}) if isinstance(response, dict) else {}
    message = str(aws_error.get("Message", str(error)))
    message = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[redacted-access-key]", message)
    message = re.sub(r"(?i)(authorization|x-amz-security-token|aws_secret_access_key|aws_session_token|secretaccesskey|sessiontoken)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", message)
    message = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", message)
    return {"operation": operation, "code": str(aws_error.get("Code", type(error).__name__)), "message": message[:600], "recordedAt": utc_now()}


class CollectionStopped(RuntimeError):
    pass


class Collector:
    def __init__(self, session, outputs, evidence, deadline, clock=time.monotonic):
        from botocore.config import Config
        # Disable automatic retries, especially for SendMessage: ambiguous send failures
        # must never turn into unrecorded duplicate submissions by this runner.
        config = Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1}, user_agent_extra="ReplayGuard/1")
        self.sqs = session.client("sqs", config=config)
        self.logs = session.client("logs", config=config)
        self.table = session.resource("dynamodb", config=config).Table(outputs["LedgerTable"])
        self.outputs = outputs
        self.evidence = evidence
        self.deadline = deadline
        self.clock = clock
        self.calls = 0
        self.seen_events = set()

    def call(self, operation, function, **kwargs):
        if self.deadline - self.clock() < 7:
            raise CollectionStopped("Observation deadline reached; reserving seven seconds for the final bounded API response")
        if self.calls >= MAX_API_CALLS:
            raise CollectionStopped(f"Read budget reached ({MAX_API_CALLS} AWS API calls)")
        self.calls += 1
        try:
            return function(**kwargs)
        except Exception as error:
            self.evidence["apiErrors"].append(sanitized_error(error, operation))
            raise CollectionStopped(f"AWS {operation} failed; see apiErrors in evidence") from error

    def queues(self):
        snapshot = {"observedAt": utc_now()}
        names = {"visible": "ApproximateNumberOfMessages", "notVisible": "ApproximateNumberOfMessagesNotVisible", "delayed": "ApproximateNumberOfMessagesDelayed"}
        for target, output in (("queue", "QueueUrl"), ("dlq", "DlqUrl")):
            response = self.call(f"sqs.GetQueueAttributes.{target}", self.sqs.get_queue_attributes, QueueUrl=self.outputs[output], AttributeNames=list(names.values()))
            attributes = response.get("Attributes", {})
            if any(name not in attributes for name in names.values()):
                raise CollectionStopped(f"SQS returned incomplete {target} queue attributes")
            snapshot[target] = {key: int(attributes[name]) for key, name in names.items()}
        self.evidence["queueObservations"].append(snapshot)
        return snapshot

    def receipts(self):
        from boto3.dynamodb.conditions import Key
        for mode in MODES:
            items = []
            token = None
            for page in range(MAX_PAGES):
                args = {"KeyConditionExpression": Key("PK").eq(f"RUN#{self.evidence['runId']}#MODE#{mode}") & Key("SK").begins_with("RECEIPT#"), "ConsistentRead": True, "Limit": 100}
                if token:
                    args["ExclusiveStartKey"] = token
                result = self.call(f"dynamodb.Query.{mode}", self.table.query, **args)
                items.extend(result.get("Items", []))
                token = result.get("LastEvaluatedKey")
                if not token:
                    self.evidence["receipts"][mode] = json.loads(json.dumps(items, default=json_default))
                    self.evidence["collection"]["lastLedgerReadAt"][mode] = utc_now()
                    break
            else:
                raise CollectionStopped(f"Ledger pagination exceeded {MAX_PAGES} pages; refusing a partial receipt count")

    def log_events(self):
        start_time = self.evidence["collection"]["logsStartTime"]
        for source, output in (("worker", "WorkerLogGroup"), ("provider", "ProviderLogGroup")):
            token = None
            for page in range(MAX_PAGES):
                args = {"logGroupName": self.outputs[output], "filterPattern": '{ $.runId = "' + self.evidence["runId"] + '" }', "startTime": start_time, "limit": 100}
                if token:
                    args["nextToken"] = token
                result = self.call(f"logs.FilterLogEvents.{source}", self.logs.filter_log_events, **args)
                for raw in result.get("events", []):
                    key = (source, raw.get("eventId"))
                    if key in self.seen_events:
                        continue
                    try:
                        event = strict_json(raw.get("message", ""))
                    except (ValueError, TypeError):
                        self.evidence["collection"]["unparsedLogEvents"] += 1
                        continue
                    if not isinstance(event, dict) or event.get("runId") != self.evidence["runId"]:
                        continue
                    event.update({"source": source, "eventId": raw.get("eventId"), "eventTimestamp": raw.get("timestamp"), "ingestionTime": raw.get("ingestionTime"), "logStreamName": raw.get("logStreamName"), "sourceLogGroup": self.outputs[output]})
                    self.evidence["events"].append(event)
                    self.seen_events.add(key)
                next_token = result.get("nextToken")
                if not next_token or next_token == token:
                    break
                token = next_token
            else:
                raise CollectionStopped(f"CloudWatch pagination exceeded {MAX_PAGES} pages; refusing partial log evidence")
        self.evidence["events"].sort(key=lambda e: (e.get("eventTimestamp") or 0, e.get("eventId") or ""))
        self.evidence["attempts"] = {mode: [dict(e) for e in self.evidence["events"] if e.get("source") == "worker" and e.get("component") == "worker" and e.get("mode") == mode and e.get("stage") == "received"] for mode in MODES}
        self.evidence["collection"]["lastLogReadAt"] = utc_now()

    def send(self, mode, order):
        if time.time() >= int(self.outputs["Expiry"]):
            raise CollectionStopped("Deployed lab expired before message dispatch; refusing further sends")
        body = {"runId": self.evidence["runId"], "mode": mode, "order": order, "fault": self.evidence["fault"]["type"]}
        serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
        result = self.call("sqs.SendMessage", self.sqs.send_message, QueueUrl=self.outputs["QueueUrl"], MessageBody=serialized)
        if not result.get("MessageId"):
            raise CollectionStopped("SQS SendMessage returned no message ID; refusing to retry ambiguous submission")
        self.evidence["messages"].append({"mode": mode, "orderId": order["orderId"], "messageId": result["MessageId"], "sentAt": utc_now(), "bodySha256": hashlib.sha256(serialized.encode()).hexdigest()})


def blank_evidence(case, case_bytes, region, stack):
    script_path = Path(__file__).resolve()
    source_hashes = {name: hashlib.sha256((script_path.parent.parent / name).read_bytes()).hexdigest() for name in SOURCE_PATHS if (script_path.parent.parent / name).is_file()}
    return {"schemaVersion": 1, "provenance": "aws", "runId": str(uuid.uuid4()), "recordedAt": utc_now(), "region": region, "stack": stack, "status": "incomplete", "case": case, "inputs": {"orders": case["orders"]}, "fault": case["fault"], "messages": [], "receipts": {mode: [] for mode in MODES}, "attempts": {mode: [] for mode in MODES}, "events": [], "assertions": [], "queueObservations": [], "apiErrors": [], "limitations": LIMITATIONS, "collection": {"logsStartTime": int(time.time() * 1000) - 5000, "startedAt": utc_now(), "lastLedgerReadAt": {}, "lastLogReadAt": None, "unparsedLogEvents": 0, "apiCalls": 0, "maxApiCalls": MAX_API_CALLS, "maxPagesPerRead": MAX_PAGES, "stopReason": None}, "artifacts": {"sourceFiles": source_hashes, "caseSha256": hashlib.sha256(case_bytes).hexdigest(), "canonicalCaseSha256": canonical_hash(case), "runnerSha256": hashlib.sha256(script_path.read_bytes()).hexdigest(), "verifierSha256": hashlib.sha256(script_path.with_name("verify_case.py").read_bytes()).hexdigest()}}


def finalize(evidence, path):
    evidence["recordedAt"] = utc_now()
    result = verify(evidence)
    evidence["status"] = result["status"]
    evidence["assertions"] = result["assertions"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(evidence, indent=2, default=json_default) + "\n")
    temporary.replace(path)
    print(f"ReplayGuard: {evidence['status'].upper()} — {path}")
    print(f"Run {evidence['runId']}: {len(evidence['messages'])} submitted messages; receipts vulnerable={len(evidence['receipts']['vulnerable'])}, repaired={len(evidence['receipts']['repaired'])}")
    if evidence["collection"]["stopReason"]:
        print(evidence["collection"]["stopReason"])
    for error in evidence["apiErrors"]:
        print(f"{error['operation']}: {error['code']}: {error['message']}", file=sys.stderr)
    return 0 if evidence["status"] == "passed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="AWS profile; otherwise use the standard credential chain")
    parser.add_argument("--region", help="AWS region, falling back to profile configuration")
    parser.add_argument("--stack", default="replayguard-lab", help="Already deployed CloudFormation stack name")
    parser.add_argument("--case", type=Path, default=Path("cases/crash-after-fulfillment.json"))
    parser.add_argument("--output", type=Path, default=Path("evidence/latest.json"))
    args = parser.parse_args()
    try:
        case_bytes = args.case.read_bytes()
        if len(case_bytes) > 16384:
            raise ValueError("Case file exceeds 16 KiB")
        case = validate_case(strict_json(case_bytes))
    except (OSError, ValueError, TypeError) as error:
        parser.error(f"Invalid case; no AWS calls made: {error}")
    evidence = blank_evidence(case, case_bytes, args.region, args.stack)
    deadline = time.monotonic() + case["bounds"]["maxWaitSeconds"]
    collector = None
    operation = "aws.Session"
    try:
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        evidence["region"] = session.region_name
        if not session.region_name:
            raise ValueError("Set --region or configure a region in your AWS profile")
        operation = "cloudformation.DescribeStacks"
        cf = session.client("cloudformation", config=Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1}))
        description = cf.describe_stacks(StackName=args.stack)
        stacks = description.get("Stacks", [])
        if len(stacks) != 1:
            raise ValueError("Expected exactly one deployed stack")
        outputs = {item["OutputKey"]: item["OutputValue"] for item in stacks[0].get("Outputs", [])}
        missing = [name for name in REQUIRED_OUTPUTS if not outputs.get(name)]
        if missing:
            raise ValueError("Deployed stack is missing outputs: " + ", ".join(missing))
        if outputs["Region"] != session.region_name:
            raise ValueError("Stack Region output disagrees with the selected AWS region")
        evidence["deployment"] = {"stackStatus": stacks[0].get("StackStatus"), "expiry": outputs["Expiry"], "workerLogGroup": outputs["WorkerLogGroup"], "providerLogGroup": outputs["ProviderLogGroup"], "ledgerTable": outputs["LedgerTable"]}
        if stacks[0].get("StackStatus") not in ("CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"):
            raise ValueError("Stack is not in a stable deployed state")
        expiry = int(outputs["Expiry"])
        if time.time() + case["bounds"]["maxWaitSeconds"] + 30 >= expiry:
            raise ValueError("Lab expiry is missing, expired, or too close to finish this case. Deploy a fresh short-lived lab; no messages sent.")
        collector = Collector(session, outputs, evidence, deadline)
        initial = collector.queues()
        if any(value != 0 for key in ("queue", "dlq") for value in initial[key].values()):
            raise CollectionStopped("Source queue or DLQ is not empty. Finish or inspect the prior run before starting another case; no messages sent.")
        for order in case["orders"]:
            for mode in MODES:
                collector.send(mode, order)
        print(f"Submitted {len(evidence['messages'])} messages for run {evidence['runId']}; observing for up to {case['bounds']['maxWaitSeconds']}s.", flush=True)
        while time.monotonic() < deadline:
            # Observe queue emptiness first, then perform strongly consistent ledger reads.
            # Passing therefore includes reads AFTER the last queue grace observation.
            collector.queues()
            collector.receipts()
            collector.log_events()
            interim = verify(evidence)
            if interim["status"] in ("passed", "unresolved"):
                evidence["collection"]["stopReason"] = "Assertions satisfied within the observation window" if interim["status"] == "passed" else "Contradictory evidence requires investigation"
                break
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(POLL_SECONDS, remaining))
        else:
            evidence["collection"]["stopReason"] = "Observation deadline reached; missing evidence remains incomplete"
    except CollectionStopped as error:
        evidence["collection"]["stopReason"] = str(error)
        if not evidence["apiErrors"]:
            evidence["apiErrors"].append(sanitized_error(error, "collection.BoundOrPrecondition"))
    except KeyboardInterrupt:
        evidence["collection"]["stopReason"] = "Interrupted; submitted messages may still be processing. Exported partial observations."
        evidence["apiErrors"].append({"operation": "collection", "code": "Interrupted", "message": evidence["collection"]["stopReason"], "recordedAt": utc_now()})
    except Exception as error:
        evidence["apiErrors"].append(sanitized_error(error, operation))
        evidence["collection"]["stopReason"] = "Preflight failed; see apiErrors. No AWS success evidence has been invented."
    finally:
        evidence["collection"]["apiCalls"] = (collector.calls if collector else 0) + 1
        evidence["collection"]["finishedAt"] = utc_now()
    return finalize(evidence, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
