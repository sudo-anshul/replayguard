#!/usr/bin/env python3
"""Six-message private AWS comparison; unconditionally clean up its tagged stack."""
import argparse
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time
import uuid

from verify_key_case import CANDIDATES, REPORT_KIND, canonical, digest, first_order_gate, message_body, strict_json, validate_case, verify

MAX_API_CALLS = 400
MAX_PAGES = 5
POLL_SECONDS = 10
REQUIRED_OUTPUTS = ("QueueUrl", "DlqUrl", "LedgerTable", "WorkerLogGroup", "ProviderLogGroup", "Region", "Expiry", "MappingId", "Experiment")
SOURCE_PATHS = ("src/key_provider.py", "src/key_worker.py", "infra/build_template.py", "scripts/deploy.py", "scripts/destroy.py",
                "scripts/run_key_case.py", "scripts/verify_key_case.py", "scripts/export_key_case.py", "requirements.txt")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def aws_error_details(error):
    """Transport exceptions may expose response=None or malformed metadata."""
    response = getattr(error, "response", None)
    details = response.get("Error") if isinstance(response, dict) else None
    return details if isinstance(details, dict) else {}


def safe_error(error, operation):
    aws = aws_error_details(error)
    message = str(aws.get("Message", str(error)))
    message = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[redacted]", message)
    message = re.sub(r"(?i)(authorization|x-amz-security-token|aws_secret_access_key|aws_session_token|secretaccesskey|sessiontoken)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", message)
    return {"operation": operation, "code": str(aws.get("Code", type(error).__name__)), "message": message[:400], "recordedAt": now()}


class Stopped(RuntimeError):
    pass


class Collector:
    def __init__(self, session, outputs, evidence, deadline, clock=time.monotonic):
        from botocore.config import Config
        config = Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1}, user_agent_extra="ReplayGuard/key-scope-v2")
        self.sqs = session.client("sqs", config=config)
        self.logs = session.client("logs", config=config)
        self.table = session.resource("dynamodb", config=config).Table(outputs["LedgerTable"])
        self.outputs, self.evidence, self.deadline, self.clock = outputs, evidence, deadline, clock
        self.calls, self.seen = 0, set()

    def call(self, operation, function, **kwargs):
        if self.deadline - self.clock() < 7:
            raise Stopped("Collection deadline reached")
        if self.calls >= MAX_API_CALLS:
            raise Stopped("Collector API budget exhausted")
        self.calls += 1
        try:
            return function(**kwargs)
        except Exception as error:
            self.evidence["apiErrors"].append(safe_error(error, operation))
            raise Stopped("AWS operation failed: " + operation) from error

    def queues(self):
        snapshot = {"observedAt": now()}
        names = {"visible": "ApproximateNumberOfMessages", "notVisible": "ApproximateNumberOfMessagesNotVisible", "delayed": "ApproximateNumberOfMessagesDelayed"}
        for target, output in (("queue", "QueueUrl"), ("dlq", "DlqUrl")):
            response = self.call("sqs.GetQueueAttributes." + target, self.sqs.get_queue_attributes, QueueUrl=self.outputs[output], AttributeNames=list(names.values()))
            attributes = response.get("Attributes", {})
            if any(name not in attributes for name in names.values()):
                raise Stopped("Incomplete queue attributes")
            snapshot[target] = {key: int(attributes[name]) for key, name in names.items()}
        self.evidence["queueObservations"].append(snapshot)
        return snapshot

    def receipts(self):
        from boto3.dynamodb.conditions import Key
        for candidate in CANDIDATES:
            items, token = [], None
            for _ in range(MAX_PAGES):
                args = {"KeyConditionExpression": Key("PK").eq(f"RUN#{self.evidence['runId']}#CANDIDATE#{candidate}") & Key("SK").begins_with("RECEIPT#"), "ConsistentRead": True, "Limit": 100}
                if token:
                    args["ExclusiveStartKey"] = token
                response = self.call("dynamodb.Query." + candidate, self.table.query, **args)
                if not isinstance(response.get("Items"), list):
                    raise Stopped("Incomplete receipt query")
                items.extend(response["Items"])
                token = response.get("LastEvaluatedKey")
                if not token:
                    plain = json.loads(json.dumps(items, default=json_default))
                    at = now()
                    self.evidence["receipts"][candidate] = plain
                    self.evidence["ledgerObservations"].append({"candidate": candidate, "observedAt": at, "consistent": True, "items": plain})
                    self.evidence["collection"]["lastLedgerReadAt"][candidate] = at
                    break
            else:
                raise Stopped("Receipt pagination exceeded its bound; no partial snapshot committed")

    def log_events(self):
        for source, output in (("worker", "WorkerLogGroup"), ("provider", "ProviderLogGroup")):
            token = None
            for _ in range(MAX_PAGES):
                args = {"logGroupName": self.outputs[output], "filterPattern": '{ $.runId = "' + self.evidence["runId"] + '" }',
                        "startTime": self.evidence["collection"]["logsStartTime"], "limit": 100}
                if token:
                    args["nextToken"] = token
                response = self.call("logs.FilterLogEvents." + source, self.logs.filter_log_events, **args)
                for raw in response.get("events", []):
                    identity = (source, raw.get("eventId"))
                    if identity in self.seen:
                        continue
                    try:
                        event = strict_json(raw.get("message", ""))
                    except (ValueError, TypeError):
                        self.evidence["collection"]["unparsedLogEvents"] += 1
                        continue
                    if not isinstance(event, dict) or event.get("runId") != self.evidence["runId"]:
                        self.evidence["collection"]["unparsedLogEvents"] += 1
                        continue
                    event.update(source=source, eventId=raw.get("eventId"), eventTimestamp=raw.get("timestamp"), ingestionTime=raw.get("ingestionTime"),
                                 logStreamName=raw.get("logStreamName"), sourceLogGroup=self.outputs[output], collectedAt=now())
                    self.evidence["events"].append(event)
                    self.seen.add(identity)
                following = response.get("nextToken")
                if not following or following == token:
                    break
                token = following
            else:
                raise Stopped("Log pagination exceeded its bound")
        self.evidence["events"].sort(key=lambda e: (e.get("eventTimestamp") or 0, e.get("eventId") or ""))
        self.evidence["collection"]["lastLogReadAt"] = now()

    def send(self, candidate, order, phase):
        if time.time() + 15 >= int(self.outputs["Expiry"]):
            raise Stopped("Processing window expired before dispatch")
        if len(self.evidence["messages"]) >= 6:
            raise Stopped("Original-message bound reached")
        if any(m["candidate"] == candidate and m["orderId"] == order["orderId"] for m in self.evidence["messages"]):
            raise Stopped("Duplicate original dispatch refused")
        if phase == 2 and not self.evidence.get("phaseGate"):
            raise Stopped("Phase 2 requires the recorded A commit/failure gate")
        if phase == 2 and first_order_gate(self.evidence, self.evidence["phaseGate"]["recordedAt"]) != self.evidence["phaseGate"]:
            raise Stopped("Phase gate does not match current raw evidence")
        body = message_body(self.evidence["runId"], candidate, order)
        serialized = canonical(body)
        response = self.call("sqs.SendMessage", self.sqs.send_message, QueueUrl=self.outputs["QueueUrl"], MessageBody=serialized)
        if not response.get("MessageId"):
            raise Stopped("Ambiguous send: no message ID; refusing retry")
        self.evidence["messages"].append({"candidate": candidate, "orderId": order["orderId"], "messageId": response["MessageId"],
                                          "phase": phase, "sentAt": now(), "bodySha256": hashlib.sha256(serialized.encode()).hexdigest()})


def capture_sources(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCE_PATHS}


def blank_evidence(case, case_bytes, region, stack, root):
    return {"schemaVersion": 2, "kind": REPORT_KIND, "provenance": "aws", "runId": str(uuid.uuid4()),
        "recordedAt": now(), "region": region, "requestedStack": stack, "case": case,
        "messages": [], "receipts": {c: None for c in CANDIDATES}, "events": [], "ledgerObservations": [],
        "queueObservations": [], "phaseGate": None, "apiErrors": [],
        "collection": {"startedAt": now(), "logsStartTime": int(time.time() * 1000) - 5000, "lastLedgerReadAt": {}, "lastLogReadAt": None,
                       "unparsedLogEvents": 0, "apiCalls": 0, "maxApiCalls": MAX_API_CALLS, "maxPagesPerRead": MAX_PAGES, "stopReason": None},
        "cleanup": {"status": "not-started", "verified": False, "errors": []},
        "artifacts": {"caseSha256": hashlib.sha256(case_bytes).hexdigest(), "canonicalCaseSha256": digest(case), "sourceFiles": capture_sources(root)},
        "limitations": ["A receipt is the entire simulated effect; no real payment, shipment or email is attempted.",
            "Standard SQS may redeliver beyond the observed grace period; no exactly-once claim is made.",
            "Faults occur only after a new receipt on receiveCount=1; late first acceptance can leave fault evidence incomplete.",
            "The fault is a failed provider response and worker invocation, not an OS process termination.",
            "Offline consistency and source fingerprints are not AWS-signed attestations.",
            "A matched experiment intentionally includes two candidates with business violations."]}


def write_evidence(evidence, path):
    evidence["recordedAt"] = now()
    evidence["result"] = verify(evidence, check_claims=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def verified_target(stack, outputs):
    tags = {t["Key"]: t["Value"] for t in stack.get("Tags", [])}
    if tags.get("Project") != "ReplayGuard" or tags.get("Experiment") != "key-scope" or outputs.get("Experiment") != "key-scope":
        raise ValueError("Refusing untagged/non-key-scope stack; no cleanup target accepted")
    arn = stack.get("StackId", "")
    if not arn.startswith("arn:") or ":cloudformation:" not in arn or ":stack/" not in arn:
        raise ValueError("Expected an exact CloudFormation stack ARN")
    return {"stackArn": arn, "mappingId": outputs.get("MappingId")}


def cleanup_stack(session, target, record, clock=time.monotonic, sleep=time.sleep):
    """Independent of evidence writes and collector budget; always attempt deletion."""
    from botocore.config import Config
    record.update(status="unconfirmed", verified=False, startedAt=now(), stackArn=target["stackArn"], apiCalls=0)
    record.setdefault("errors", [])
    config = Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1})
    deadline = clock() + 300
    cf = session.client("cloudformation", config=config)
    try:
        if target.get("mappingId"):
            record["apiCalls"] += 1
            session.client("lambda", config=config).update_event_source_mapping(UUID=target["mappingId"], Enabled=False)
            record["mappingDisableRequested"] = True
    except Exception as error:
        record["errors"].append(safe_error(error, "cleanup.DisableMapping"))
    try:
        record["apiCalls"] += 1
        cf.delete_stack(StackName=target["stackArn"])
        record["deleteRequested"] = True
    except Exception as error:
        record["errors"].append(safe_error(error, "cleanup.DeleteStack"))
    while clock() < deadline and record["apiCalls"] < 70:
        try:
            record["apiCalls"] += 1
            stacks = cf.describe_stacks(StackName=target["stackArn"]).get("Stacks", [])
            current = stacks[0].get("StackStatus") if len(stacks) == 1 else None
            record["lastStackStatus"] = current
            if current == "DELETE_COMPLETE":
                record.update(status="deleted", verified=True, finishedAt=now())
                return
            if current == "DELETE_FAILED":
                record.update(status="failed", finishedAt=now())
                return
        except Exception as error:
            aws = aws_error_details(error)
            if aws.get("Code") == "ValidationError" and "does not exist" in str(aws.get("Message", "")):
                record.update(status="deleted", verified=True, lastStackStatus="absent", finishedAt=now())
                return
            record["errors"].append(safe_error(error, "cleanup.VerifyDeletion"))
        sleep(min(5, max(0, deadline - clock())))
    record["finishedAt"] = now()


def collect_run(collector, evidence, path, sleep=time.sleep, clock=time.monotonic):
    initial = collector.queues()
    if any(value != 0 for name in ("queue", "dlq") for value in initial[name].values()):
        raise Stopped("Source/DLQ not empty; no messages sent")
    a, b = evidence["case"]["orders"]
    write_evidence(evidence, path)
    for candidate in CANDIDATES:
        collector.send(candidate, a, 1)
        write_evidence(evidence, path)
    print("Phase 1 submitted; observing three independent A commit/failure chains.", flush=True)
    while clock() < collector.deadline:
        collector.queues()
        collector.receipts()
        collector.log_events()
        if evidence["phaseGate"] is None:
            gate = first_order_gate(evidence, now())
            if gate:
                evidence["phaseGate"] = gate
                write_evidence(evidence, path)  # A failed durable checkpoint prevents B dispatch.
                for candidate in CANDIDATES:
                    collector.send(candidate, b, 2)
                    write_evidence(evidence, path)
                print("A gate recorded; phase 2 submitted. Observing SQS redelivery and per-order receipts.", flush=True)
        result = verify(evidence, check_claims=False)
        if result["experimentStatus"] in ("passed", "unresolved"):
            evidence["collection"]["stopReason"] = "Experiment evidence complete" if result["experimentStatus"] == "passed" else "Contradictory evidence; no more sends"
            return
        write_evidence(evidence, path)
        sleep(min(POLL_SECONDS, max(0, collector.deadline - clock())))
    raise Stopped("Observation window exhausted; missing evidence remains incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack", default="replayguard-keys")
    parser.add_argument("--case", type=Path, default=Path("cases/aws-key-scope.json"))
    parser.add_argument("--output", type=Path, default=Path("evidence/aws-key-scope.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        case_bytes = args.case.read_bytes()
        if len(case_bytes) > 16384:
            raise ValueError("Case exceeds 16 KiB")
        case = validate_case(strict_json(case_bytes))
        if args.output.exists():
            raise ValueError("Output already exists; select a fresh path to preserve prior evidence")
        evidence = blank_evidence(case, case_bytes, args.region, args.stack, root)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    session, target, collector = None, None, None
    try:
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        config = Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1})
        cf = session.client("cloudformation", config=config)
        description = cf.describe_stacks(StackName=args.stack)
        stacks = description.get("Stacks", [])
        if len(stacks) != 1:
            raise ValueError("Expected one stack")
        stack = stacks[0]
        outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
        target = verified_target(stack, outputs)
        evidence["deployment"] = {"stackArn": target["stackArn"], "stackStatus": stack.get("StackStatus"), "expiry": outputs.get("Expiry"), "experiment": outputs.get("Experiment")}
        if stack.get("StackStatus") not in ("CREATE_COMPLETE", "UPDATE_COMPLETE") or any(not outputs.get(k) for k in REQUIRED_OUTPUTS):
            raise ValueError("Stack is not ready or outputs are incomplete")
        if outputs["Region"] != args.region or time.time() + case["bounds"]["maxWaitSeconds"] + 30 >= int(outputs["Expiry"]):
            raise ValueError("Wrong region or processing expiry too close")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(args.output.parent).free < 32 * 1024 * 1024:
            raise OSError("Less than 32 MiB free for evidence; refusing dispatch")
        template = cf.get_template(StackName=target["stackArn"], TemplateStage="Original")["TemplateBody"]
        if isinstance(template, str):
            template = strict_json(template)
        deployed = {"src/key_worker.py": template["Resources"]["WorkerFunction"]["Properties"]["Code"]["ZipFile"],
                    "src/key_provider.py": template["Resources"]["ProviderFunction"]["Properties"]["Code"]["ZipFile"]}
        hashes = {name: hashlib.sha256(source.encode()).hexdigest() for name, source in deployed.items()}
        evidence["deployment"]["templateSourceSha256"] = hashes
        if any(evidence["artifacts"]["sourceFiles"][name] != value for name, value in hashes.items()):
            raise ValueError("Deployed CloudFormation source does not match the captured code")
        collector = Collector(session, outputs, evidence, time.monotonic() + case["bounds"]["maxWaitSeconds"])
        collect_run(collector, evidence, args.output)
    except BaseException as error:
        if isinstance(error, (SystemExit, GeneratorExit)):
            raise
        evidence["apiErrors"].append(safe_error(error, "run"))
        evidence["collection"]["stopReason"] = "Stopped: " + type(error).__name__
    finally:
        evidence["collection"].update(apiCalls=collector.calls if collector else 0, finishedAt=now())
        try:
            if capture_sources(root) != evidence["artifacts"]["sourceFiles"]:
                evidence["apiErrors"].append({"operation": "source-stability", "code": "ChangedSource", "message": "Captured source changed during the run"})
            write_evidence(evidence, args.output)
        except Exception as error:
            print("Evidence write failed before cleanup:", type(error).__name__, file=sys.stderr, flush=True)
        finally:
            # Never make cloud shutdown conditional on successful export or free disk.
            if target and session:
                try:
                    cleanup_stack(session, target, evidence["cleanup"])
                except BaseException as error:
                    evidence["cleanup"].update(status="unconfirmed", verified=False)
                    evidence["cleanup"]["errors"].append(safe_error(error, "cleanup"))
            else:
                evidence["cleanup"].update(status="unconfirmed", verified=False, reason="No exact tagged experimental stack was verified; no resource was selected for deletion")
            try:
                write_evidence(evidence, args.output)
            except Exception as error:
                print("Final evidence write failed:", type(error).__name__, file=sys.stderr, flush=True)
                print(json.dumps({"runId": evidence["runId"], "cleanup": evidence["cleanup"]}), file=sys.stderr, flush=True)
    result = verify(evidence)
    print("Experiment:", result["experimentStatus"], "| cleanup:", evidence["cleanup"]["status"], "| evidence:", args.output)
    return 0 if result["experimentStatus"] == result["operationalStatus"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
