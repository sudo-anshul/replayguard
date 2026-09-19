#!/usr/bin/env python3
"""Export a portable regression with original inputs, observations and checksums."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from verify_case import strict_json, validate_case, verify
from run_case import SOURCE_PATHS

README = """# ReplayGuard regression case

This archive captures a bounded real AWS SQS/Lambda failure comparison.
`evidence.json` reports the observed run; `assertions.json` is independently
recomputed at export. PASSED requires the exact original SQS messages to retry,
a durable receipt before each injected failure, eventual success, duplicate
vulnerable receipts, a single repaired receipt, and stable queue drainage.
INCOMPLETE means required observations are missing; UNRESOLVED means observations
contradict the case. Neither state is a successful AWS validation.

Verify the unmodified archive locally (no AWS credentials needed):

```sh
python3 scripts/verify_case.py evidence.json --case case.json --json
```

Check every file's integrity with `shasum -a 256 -c SHA256SUMS` (macOS) or
`sha256sum -c SHA256SUMS` (Linux). Checksums detect changed bytes; these exports
are not cryptographically signed by AWS and do not independently prove origin.

Deploy the included source, then replay against a short-lived AWS stack. Prerequisites:
Python 3.10+, AWS CLI v2 on PATH, and an authenticated AWS profile authorized to
create the scoped CloudFormation/IAM/Lambda/SQS/DynamoDB/CloudWatch lab resources.
Deployment creates billable AWS resources; credits are not a spending cap.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/deploy.py --profile YOUR_PROFILE --region YOUR_REGION --stack replayguard-lab --hours 1
python scripts/run_case.py --profile YOUR_PROFILE --region YOUR_REGION --stack replayguard-lab --case case.json --output new-evidence.json
python scripts/verify_case.py new-evidence.json --case case.json
python scripts/export_case.py --case case.json --evidence new-evidence.json --output new-regression.zip
python scripts/destroy.py --profile YOUR_PROFILE --region YOUR_REGION --stack replayguard-lab
```

If a matching active stack already exists, skip deployment. The runner only
submits to an existing stack and refuses expired deployments or nonempty queues.
Deployment source is included under src/, infra/ and scripts/ and its SHA-256
fingerprints are captured in evidence.json. Each replay gets a new run UUID and
sends one message per mode per order (maximum six), with a maximum 180-second
observation window, a 300-call collector budget and five-page per-read limit.
Delete the lab when done; expiry stops fulfillment but does not delete resources.

Fault: the worker invokes the independent simulated fulfillment provider,
then throws on SQS receiveCount 1 after the provider has durably written a receipt.
SQS redelivers the same message. Vulnerable mode accepts another receipt; repaired
mode uses receiver-side atomic idempotency and reuses the original receipt.
No real payment, shipment, email or customer order is generated. The repair
models a receiver that atomically owns the effect and idempotency decision.

Artifact source fingerprints and sanitized AWS API errors (if any) are retained
inside evidence.json. CloudWatch logs can arrive late; missing evidence stays
incomplete. SQS queue counts are approximate. This bounded demonstration is not
a general exactly-once guarantee for distributed systems or external APIs.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=Path("cases/crash-after-fulfillment.json"))
    parser.add_argument("--evidence", type=Path, default=Path("evidence/latest.json"))
    parser.add_argument("--output", type=Path, default=Path("evidence/replayguard-case.zip"))
    args = parser.parse_args()
    try:
        case_bytes = args.case.read_bytes()
        case = validate_case(strict_json(case_bytes))
        evidence_bytes = args.evidence.read_bytes()
        evidence = strict_json(evidence_bytes)
        if evidence.get("case") != case or evidence.get("artifacts", {}).get("caseSha256") != hashlib.sha256(case_bytes).hexdigest():
            raise ValueError("Original case does not match evidence; refusing to export mixed inputs")
        report = verify(evidence)
        here = Path(__file__).resolve().parent
        for name, key in (("run_case.py", "runnerSha256"), ("verify_case.py", "verifierSha256")):
            if hashlib.sha256((here / name).read_bytes()).hexdigest() != evidence.get("artifacts", {}).get(key):
                raise ValueError(f"{name} changed after the run; preserve the matching script version or replay before exporting")
        source_files = {}
        for name in SOURCE_PATHS:
            data = (here.parent / name).read_bytes()
            expected = evidence.get("artifacts", {}).get("sourceFiles", {}).get(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"{name} no longer matches the recorded source; replay before exporting")
            source_files[name] = data
        requirements_path = here.parent / "requirements.txt"
        requirements = requirements_path.read_bytes() if requirements_path.exists() else b"boto3>=1.35,<2\n"
        files = {"case.json": case_bytes, "evidence.json": evidence_bytes,
                 "assertions.json": (json.dumps(report, indent=2) + "\n").encode(),
                 "README.md": README.encode(), "requirements.txt": requirements,
                 "scripts/run_case.py": (here / "run_case.py").read_bytes(),
                 "scripts/verify_case.py": (here / "verify_case.py").read_bytes(),
                 "scripts/export_case.py": (here / "export_case.py").read_bytes()}
        files.update(source_files)
        files["SHA256SUMS"] = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items())).encode()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
        temporary.replace(args.output)
        print(f"Exported {report['status'].upper()} regression: {args.output}")
        return 0
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
