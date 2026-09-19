#!/usr/bin/env python3
"""Verify the published static bytes against sanitized Amplify deployment evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import ssl
import urllib.request

LIVE_URL = "https://prod.d2w687q4ucx6dk.amplifyapp.com/"


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(item):
    name, expected = item
    result = {"path": name, "expectedSha256": expected}
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirects(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    request = urllib.request.Request(LIVE_URL + name, headers={
        "Accept-Encoding": "identity", "Cache-Control": "no-cache",
        "User-Agent": "ReplayGuard-Anonymous-Release-Verifier/1",
    })
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(16 * 1024 * 1024 + 1)
            result["httpStatus"] = response.status
        if len(body) > 16 * 1024 * 1024:
            raise ValueError("response-size-limit")
        digest = hashlib.sha256(body).hexdigest()
        result.update(bytes=len(body), sha256=digest,
                      status="passed" if result["httpStatus"] == 200 and digest == expected else "violation")
    except Exception as error:
        result.update(status="incomplete", error=type(error).__name__)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deployment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or args.output.resolve() == args.deployment.resolve():
        parser.error("Output must be a new file, distinct from deployment evidence")
    deployment_bytes = args.deployment.read_bytes()
    deployment = json.loads(deployment_bytes)
    files = deployment["assetSha256"]
    if deployment["status"] != "SUCCEED" or not 1 <= len(files) <= 50 or "index.html" not in files:
        parser.error("Expected successful deployment with 1–50 static assets")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", n) or not re.fullmatch(r"[a-f0-9]{64}", h) for n, h in files.items()):
        parser.error("Invalid asset filename or hash")
    targets = [("", files["index.html"])] + sorted(files.items())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, targets))
    passed = all(r["status"] == "passed" for r in results)
    record = {
        "kind": "anonymous-static-release-byte-verification",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": LIVE_URL, "deploymentJobId": deployment["jobId"],
        "deploymentEvidenceSha256": hashlib.sha256(deployment_bytes).hexdigest(),
        "method": "Anonymous HTTPS GET; certificate and hostname checked; no credentials, cookies, proxies or redirects.",
        "requestCount": len(results), "assetCount": len(files),
        "assetsPassed": sum(r["status"] == "passed" for r in results[1:]),
        "root": results[0], "assets": results[1:], "passed": passed,
        "scope": "Static bytes only; rendered interactions, video playback and AWS execution are separate checks.",
    }
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: record[k] for k in ("passed", "assetCount", "assetsPassed", "deploymentJobId")}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
