#!/usr/bin/env python3
"""Publish read-only web/ assets through AWS Amplify's manual ZIP deployment."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import ssl
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack", default="replayguard-hosting")
    parser.add_argument("--infra-only", action="store_true", help="Create app and production branch without uploading assets")
    parser.add_argument("--web-dir", type=Path, default=ROOT / "web", help="Static asset directory; may be an immutable staged copy")
    parser.add_argument("--evidence", type=Path, help="Write sanitized deployment evidence; signed upload URLs are never included")
    args = parser.parse_args()
    # Finish local validation before creating chargeable hosting resources.
    import boto3
    from botocore.config import Config
    from botocore.httpsession import get_cert_path
    tls_context = ssl.create_default_context(cafile=get_cert_path(True))
    web = args.web_dir.resolve()
    if not (web / "index.html").is_file():
        raise SystemExit("Static index.html is missing; finish the UI before publishing")
    buffer = io.BytesIO()
    assets = {}
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(web.rglob("*")):
            relative = path.relative_to(web)
            if path.is_file() and not path.is_symlink() and not any(part.startswith(".") for part in relative.parts) and path.suffix != ".map":
                data = path.read_bytes()
                info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 9, 19, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
                assets[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    bundle = buffer.getvalue()
    if len(bundle) > MAX_UPLOAD_BYTES:
        raise SystemExit("Static upload exceeds this publisher's 25 MiB limit")
    record = {"startedAt": datetime.now(timezone.utc).isoformat(), "region": args.region, "stack": args.stack,
              "status": "preflight-passed", "bundleBytes": len(bundle), "bundleSha256": hashlib.sha256(bundle).hexdigest(),
              "assetSha256": assets, "tlsCertificateAndHostnameVerification": True, "signedUploadURLRecorded": False,
              "scope": "Manual static Amplify hosting only; no new failure experiment or execution endpoint."}
    def save():
        if args.evidence:
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    save()
    base = ["aws", "--no-cli-pager", "--region", args.region]
    if args.profile:
        base += ["--profile", args.profile]
    subprocess.run(base + ["cloudformation", "deploy", "--stack-name", args.stack,
        "--template-file", str(ROOT / "infra/site.json"), "--tags", "Project=ReplayGuard",
        "--no-fail-on-empty-changeset"], check=True)
    result = subprocess.run(base + ["cloudformation", "describe-stacks", "--stack-name", args.stack,
        "--query", "Stacks[0].Outputs", "--output", "json"], check=True, capture_output=True, text=True)
    outputs = {item["OutputKey"]: item["OutputValue"] for item in json.loads(result.stdout)}
    record["outputs"] = outputs
    record["status"] = "infrastructure-ready"
    save()
    if args.infra_only:
        print("Hosting infrastructure ready; no content uploaded yet.")
        print(outputs["LiveUrl"])
        return 0
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    client = session.client("amplify", config=Config(connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 2}))
    deployment = client.create_deployment(appId=outputs["AppId"], branchName=outputs["BranchName"])
    record["jobId"] = deployment["jobId"]
    record["status"] = "uploading"
    save()
    def stop_pending_job():
        try:
            stopped = client.stop_job(appId=outputs["AppId"], branchName=outputs["BranchName"], jobId=deployment["jobId"])
            record["cleanupJobStatus"] = stopped.get("jobSummary", {}).get("status", "stop-requested")
        except Exception as error:
            record["cleanupErrorType"] = type(error).__name__
    # Treat this signed URL as a credential: it stays in memory and is never logged.
    request = urllib.request.Request(deployment["zipUploadUrl"], data=bundle, method="PUT", headers={"Content-Type": "application/zip"})
    try:
        with urllib.request.urlopen(request, timeout=60, context=tls_context) as response:
            if response.status not in (200, 201):
                raise RuntimeError("Amplify upload was not accepted")
        client.start_deployment(appId=outputs["AppId"], branchName=outputs["BranchName"], jobId=deployment["jobId"])
    except Exception as error:
        stop_pending_job()
        record["status"] = "upload-or-start-failed"
        record["error"] = {"type": type(error).__name__, "httpStatus": getattr(error, "code", None)}
        save()
        raise SystemExit(f"Amplify asset upload failed ({type(error).__name__}, HTTP {getattr(error, 'code', 'n/a')}); signed upload URL omitted") from None
    print(f"Uploaded {len(bundle):,} bytes. Waiting for hosting deployment {deployment['jobId']}.", flush=True)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            job = client.get_job(appId=outputs["AppId"], branchName=outputs["BranchName"], jobId=deployment["jobId"])["job"]
        except Exception as error:
            stop_pending_job()
            record["status"] = "poll-failed-stop-requested"
            record["error"] = {"type": type(error).__name__}
            save()
            print("Hosting status check failed; stop requested for the exact pending job.", file=sys.stderr)
            return 2
        status = job["summary"]["status"]
        record["status"] = status
        record["checkedAt"] = datetime.now(timezone.utc).isoformat()
        save()
        if status == "SUCCEED":
            print("Static site deployment succeeded.")
            print(outputs["LiveUrl"])
            return 0
        if status in ("FAILED", "CANCELLED"):
            print(f"Hosting deployment {status.lower()}; inspect the Amplify console for this app.", file=sys.stderr)
            return 2
        print(f"Hosting deployment: {status.lower()}.", flush=True)
        time.sleep(10)
    print("Hosting deployment still pending after ten minutes; no success claimed.", file=sys.stderr)
    stop_pending_job()
    record["status"] = "poll-timeout-stop-requested"
    save()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
