#!/usr/bin/env python3
"""Compare public HTTPS bytes with the staged manifest after deployment completes.

Run from any directory with Python 3 (standard library only):
  python3 verify_anonymous_https.py --deployment-job-id <confirmed-job-id>
This performs 25 bounded, read-only requests and never reads AWS credentials.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request


HERE = Path(__file__).resolve().parent
LIVE_URL = "https://prod.d2w687q4ucx6dk.amplifyapp.com/"
NEW_VIDEO = "https://youtu.be/CGE19upS66A"
OLD_VIDEO_ID = "2ufAV4Ovat4"
MAX_BYTES = 16 * 1024 * 1024


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(item, timeout):
    relative, expected = item
    url = urllib.parse.urljoin(LIVE_URL, relative)
    result = {"path": relative, "expectedSha256": expected, "url": url}
    request = urllib.request.Request(url, headers={
        "User-Agent": "ReplayGuard-Anonymous-Asset-Verifier/2",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
    })
    # No proxy credentials, cookies, authentication handlers, or redirects.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        NoRedirects(),
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            result.update(httpStatus=response.status,
                          contentType=response.headers.get_content_type())
        if len(body) > MAX_BYTES:
            return dict(result, status="incomplete", error="response-size-limit")
        observed = hashlib.sha256(body).hexdigest()
        result.update(bytes=len(body), sha256=observed,
                      matchesStagedSource=observed == expected)
        if relative in ("/", "index.html", "repair.html"):
            text = body.decode("utf-8")
            links = Links()
            links.feed(text)
            result["videoLinks"] = {
                "replacementHrefPresent": NEW_VIDEO in links.hrefs,
                "supersededVideoIdAbsent": OLD_VIDEO_ID not in text,
            }
        checks = [response.status == 200, observed == expected]
        checks.extend(result.get("videoLinks", {}).values())
        result["status"] = "passed" if all(checks) else "violation"
    except urllib.error.HTTPError as error:
        result.update(httpStatus=error.code, status="violation", error="http-error")
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as error:
        # Exception messages can expose system paths; retain only the class.
        result.update(status="incomplete", error=type(error).__name__)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=HERE / "site-stage-manifest.json")
    parser.add_argument("--output", type=Path, default=HERE / "anonymous-https-video-update.json")
    parser.add_argument("--deployment-job-id", required=True)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+", args.deployment_job_id):
        parser.error("deployment job ID must be numeric")
    if not 1 <= args.timeout <= 30:
        parser.error("timeout must be between 1 and 30 seconds")
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    files = manifest["files"]
    if len(files) != 24 or not {"index.html", "repair.html"}.issubset(files):
        parser.error("expected the exact 24-asset staged manifest")
    for name, sha in files.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not re.fullmatch(r"[a-f0-9]{64}", sha):
            parser.error("invalid manifest filename or SHA-256")
    targets = [("/", files["index.html"])] + sorted(files.items())
    started = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda item: fetch(item, args.timeout), targets))
    failures = [result for result in results if result["status"] != "passed"]
    status = ("violation" if any(r["status"] == "violation" for r in failures)
              else "incomplete" if failures else "passed")
    report = {
        "kind": "anonymous-https-video-link-deployment-verification",
        "startedAt": started,
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": LIVE_URL,
        "deploymentJobId": args.deployment_job_id,
        "scope": "Static site bytes and replacement demo links; no AWS failure run or YouTube playback check.",
        "method": "Anonymous HTTPS GET with certificate/hostname verification; no cookies, authentication, AWS credentials, proxy, signed URL or redirects.",
        "manifestFile": "site-stage-manifest.json",
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "requestCount": len(results),
        "assetsPassed": sum(r["status"] == "passed" for r in results[1:]),
        "assetCount": len(files),
        "root": results[0],
        "assets": results[1:],
        "status": status,
        "passed": status == "passed",
        "limitations": "Byte/link verification only; no rendered interaction review, signed-out video playback, or cloud execution claimed.",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": status, "root": results[0]["status"],
                      "assetsPassed": report["assetsPassed"], "assetCount": len(files)}))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
