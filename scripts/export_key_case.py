#!/usr/bin/env python3
"""Export the v2 case without altering historical archives or inventing a pass."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from run_key_case import SOURCE_PATHS
from verify_key_case import strict_json, validate_case, verify

README = """# ReplayGuard AWS key-scope regression

This is a versioned, bounded AWS observation. Check `assertions.json` for the
experiment's completeness, each candidate's business result, and cleanup state.
Two intentionally faulty candidates should violate the valid-order invariant.
An experiment pass does not turn their business results into passes.

Verify without AWS credentials or third-party packages:

```sh
python3 scripts/verify_key_case.py evidence.json --case case.json --json
shasum -a 256 -c SHA256SUMS
```

Checksums identify changed bytes; they are not AWS signatures or trusted origin
attestation. The independent observer queries the DynamoDB receipt ledger. A
receipt is the entire simulated effect, not a real payment or shipment.

To run again, use Python 3.10+, AWS CLI v2 and a trusted AWS profile authorized
for the small private CloudFormation/Lambda/SQS/DynamoDB/CloudWatch lab. First
check current gross spending and allow for billing lag; credits are not a cap.
This creates billable resources. There is no public execution endpoint.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/deploy.py --experiment key-scope --hours 1 --stack replayguard-key-replay --profile YOUR_PROFILE --region us-east-1
python scripts/run_key_case.py --stack replayguard-key-replay --profile YOUR_PROFILE --region us-east-1 --case case.json --output new-evidence.json
python scripts/verify_key_case.py new-evidence.json --case case.json
python scripts/export_key_case.py --case case.json --evidence new-evidence.json --output new-regression.zip
```

The runner ALWAYS attempts to disable and delete the exact verified stack tagged
Project=ReplayGuard and Experiment=key-scope, including if observation/export
fails. It does not delete the separate Amplify host. Check the cleanup record;
unconfirmed deletion remains an unresolved operational task. If deployment
succeeded but the runner could not start, clean up the named lab explicitly:

```sh
python scripts/destroy.py --stack replayguard-key-replay --profile YOUR_PROFILE --region us-east-1
```

Three original A messages are sent, one per fixed key choice. Only after every
A receipt and correlated post-commit failure has been observed are three B
messages sent. A and B share a SKU. The provider conditionally writes a receipt,
then deliberately fails its response after a NEW first-receive commit. The
worker fails and standard SQS redelivers it. Recognized payload conflicts are
acknowledged as terminal business rejections, not counted as fulfillment.

No key must expose at least two receipts per order, SKU key must expose one A
receipt and an evidenced rejected B, and order key must retain one per order.
Actual extra SQS deliveries stay in the evidence. There is no total-order,
exactly-two-deliveries or universal exactly-once claim. This is a response and
function failure, not an OS process kill. Missing first-receive/fault evidence
prevents an experiment pass.

Bounds: six original sends, 420-second collection, 400 collector API calls,
five pages per read, mapping concurrency two, one-hour processing expiry.
Cleanup has a separate bounded verification budget. Expiry and TTL do not
delete the lab and are not dollar-exact billing limits. Source fingerprints
cover the packaged sources and match the CloudFormation inline worker/provider
template inspected before dispatch. They are not a dependency attestation.
"""


def export(case_path, evidence_path, output, root):
    if output.exists():
        raise ValueError("Output exists; select a fresh archive path")
    case_bytes, evidence_bytes = case_path.read_bytes(), evidence_path.read_bytes()
    case = validate_case(strict_json(case_bytes))
    evidence = strict_json(evidence_bytes)
    if evidence.get("case") != case or evidence.get("artifacts", {}).get("caseSha256") != hashlib.sha256(case_bytes).hexdigest():
        raise ValueError("Case bytes do not match the captured input")
    sources = {}
    for name in SOURCE_PATHS:
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != evidence.get("artifacts", {}).get("sourceFiles", {}).get(name):
            raise ValueError("Source changed after capture: " + name)
        sources[name] = data
    protected = {case_path.resolve(), evidence_path.resolve()} | {(root / name).resolve() for name in SOURCE_PATHS}
    if output.resolve() in protected:
        raise ValueError("Refusing to replace input")
    report = verify(evidence)
    files = {**sources, "README.md": README.encode(), "case.json": case_bytes, "evidence.json": evidence_bytes,
             "assertions.json": (json.dumps(report, indent=2) + "\n").encode()}
    files["SHA256SUMS"] = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in sorted(files.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    temporary.replace(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=Path("cases/aws-key-scope.json"))
    parser.add_argument("--evidence", type=Path, default=Path("evidence/aws-key-scope.json"))
    parser.add_argument("--output", type=Path, default=Path("evidence/aws-key-scope.zip"))
    args = parser.parse_args()
    try:
        report = export(args.case, args.evidence, args.output, Path(__file__).resolve().parents[1])
        print("Exported", report["experimentStatus"], "experiment:", args.output)
        return 0
    except (ValueError, OSError, TypeError, AttributeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
