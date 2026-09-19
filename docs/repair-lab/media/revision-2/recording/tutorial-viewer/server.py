#!/usr/bin/env python3
"""Loopback-only UI for the real disposable ReplayGuard tutorial adapter."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
TUTORIAL = (HERE.parent / "tutorial").resolve()
ADAPTER = TUTORIAL / "candidate/adapter.py"
BASELINE = TUTORIAL / ".recording/baseline-adapter.py"
PORT = 8767
STAGES = ("baseline", "broken", "repaired")
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ORIGINS = {f"http://{host}" for host in HOSTS}
LOCK = threading.Lock()


def code_kind(code):
    baseline = BASELINE.read_text()
    if code == baseline:
        return "business-key"
    if code == baseline.replace('key=order["orderId"]', "key=None"):
        return "no-key"
    return "unsupported"


def state():
    code = ADAPTER.read_text()
    runs = {}
    for stage in STAGES:
        record = TUTORIAL / ".recording/runs" / stage / "execution.json"
        if record.is_file():
            data = json.loads(record.read_text())
            runs[stage] = {key: data.get(key) for key in (
                "stage", "startedAt", "completedAt", "processExitCode",
                "reportedStatus", "observedReceipts", "report", "reportSha256",
                "sourceBeforeSha256", "sourceAfterSha256",
            )}
    return {"code": code, "kind": code_kind(code), "runs": runs}


class Handler(BaseHTTPRequestHandler):
    server_version = "ReplayGuardLocal/1.0"

    def log_message(self, fmt, *args):
        print("Local viewer:", fmt % args, flush=True)

    def send_bytes(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def json(self, status, value):
        self.send_bytes(status, (json.dumps(value) + "\n").encode(), "application/json; charset=utf-8")

    def valid_host(self):
        if self.headers.get("Host") not in HOSTS:
            self.json(403, {"error": "This workbench accepts only its loopback Host."})
            return False
        return True

    def do_GET(self):
        if not self.valid_host():
            return
        route = urlsplit(self.path)
        if route.query or route.fragment:
            self.json(404, {"error": "Unknown route."})
            return
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if route.path in assets:
            name, content_type = assets[route.path]
            self.send_bytes(200, (HERE / name).read_bytes(), content_type)
        elif route.path == "/api/state":
            self.json(200, state())
        else:
            self.json(404, {"error": "Unknown route."})

    def do_POST(self):
        if not self.valid_host():
            return
        origin = self.headers.get("Origin")
        expected_origin = "http://" + self.headers.get("Host", "")
        if origin not in ORIGINS or origin != expected_origin:
            self.json(403, {"error": "A same-origin loopback request is required."})
            return
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            self.json(403, {"error": "Cross-site requests are not accepted."})
            return
        if self.headers.get("Transfer-Encoding"):
            self.json(400, {"error": "A bounded Content-Length is required."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= 4096:
            self.json(413, {"error": "Request body must be 1–4096 bytes."})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self.json(415, {"error": "JSON is required."})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self.json(400, {"error": "Invalid JSON."})
            return
        if not isinstance(payload, dict):
            self.json(400, {"error": "A JSON object is required."})
            return
        if self.path not in ("/api/save", "/api/run"):
            self.json(404, {"error": "Unknown route."})
            return
        if not LOCK.acquire(blocking=False):
            self.json(409, {"error": "An execution or save is already active."})
            return
        try:
            if self.path == "/api/save":
                if set(payload) != {"code"} or not isinstance(payload["code"], str) or code_kind(payload["code"]) == "unsupported":
                    self.json(400, {"error": 'Save exactly the documented adapter, with key=order["orderId"] or key=None and its final newline.'})
                    return
                if ADAPTER.is_symlink() or ADAPTER.parent.resolve() != TUTORIAL / "candidate":
                    self.json(409, {"error": "The fixed candidate path changed."})
                    return
                with tempfile.NamedTemporaryFile(dir=ADAPTER.parent, prefix=".adapter-save-", delete=False) as handle:
                    temp_path = Path(handle.name)
                    handle.write(payload["code"].encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, ADAPTER)
                self.json(200, {"saved": True, **state()})
            else:
                if set(payload) != {"stage"} or payload.get("stage") not in STAGES:
                    self.json(400, {"error": "Choose baseline, broken or repaired."})
                    return
                stage = payload["stage"]
                if (TUTORIAL / f"{stage}.json").exists() or (TUTORIAL / ".recording/runs" / stage).exists():
                    self.json(409, {"error": "This take already has evidence. It will not be overwritten."})
                    return
                argv = [sys.executable, str(TUTORIAL / "record_run.py"), stage]
                try:
                    result = subprocess.run(argv, cwd=TUTORIAL, capture_output=True, text=True, timeout=75)
                except subprocess.TimeoutExpired as exc:
                    self.json(504, {"error": "The actual command exceeded 75 seconds. Inspect the retained take before retrying.", "stdout": (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""})
                    return
                current = state()
                self.json(200, {"stage": stage, "stdout": result.stdout, "stderr": result.stderr,
                                "processExitCode": result.returncode, "evidence": current["runs"].get(stage), **current})
        except Exception as exc:
            self.json(500, {"error": type(exc).__name__ + ": " + str(exc)})
        finally:
            LOCK.release()


if __name__ == "__main__":
    if not ADAPTER.is_file() or not BASELINE.is_file():
        raise SystemExit("Prepare the disposable tutorial first.")
    print(f"ReplayGuard local adapter workbench: http://127.0.0.1:{PORT}", flush=True)
    print("No case executes until a Run button is clicked.", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
