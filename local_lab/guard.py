"""Fail-closed guard for normal Python network, SDK and child-process APIs.

This is defense in depth for trusted local handler execution, not a sandbox for
hostile native code. Install before importing the handlers. The hook cannot be
removed by ordinary Python code and rejects the operation before it occurs.
"""
import sys


class ForbiddenLocalOperation(PermissionError):
    pass


class LocalExecutionGuard:
    BLOCKED_MODULES = frozenset({"boto3", "botocore", "subprocess", "ctypes"})
    BLOCKED_EVENTS = frozenset({"os.system", "os.fork", "os.forkpty", "os.posix_spawn", "os.exec", "os.spawn", "subprocess.Popen", "pty.spawn", "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function"})

    def __init__(self):
        self.installed = False
        self.audit_events_seen = 0
        self.blocked = []
        self.probing = False
        self.probes = []

    def reject(self, event, detail=""):
        self.blocked.append({"event": event, "detail": detail, "duringSelfTest": self.probing})
        raise ForbiddenLocalOperation(f"Local execution guard blocked {event}")

    def audit(self, event, args):
        self.audit_events_seen += 1
        if event.startswith("socket.") or event in self.BLOCKED_EVENTS:
            self.reject(event)
        if event == "import" and args and str(args[0]).split(".", 1)[0] in self.BLOCKED_MODULES:
            self.reject("import", str(args[0]))

    def find_spec(self, fullname, path=None, target=None):
        # Meta-path interception also covers importlib imports whose audit import
        # event differs across CPython versions.
        if fullname.split(".", 1)[0] in self.BLOCKED_MODULES:
            self.reject("import", fullname)
        return None

    def install(self):
        if not self.installed:
            sys.addaudithook(self.audit)
            sys.meta_path.insert(0, self)
            self.installed = True
        return self

    def self_test(self):
        """Attempt a socket constructor and imports; no network packets or process."""
        import socket
        self.probing = True
        try:
            for name, operation in (
                ("socket-construction", lambda: socket.socket()),
                ("aws-sdk-import", lambda: __import__("boto3")),
                ("child-process-import", lambda: __import__("subprocess")),
                ("native-ffi-import", lambda: __import__("ctypes")),
            ):
                try:
                    operation()
                except ForbiddenLocalOperation:
                    self.probes.append({"probe": name, "blocked": True})
                else:
                    self.probes.append({"probe": name, "blocked": False})
        finally:
            self.probing = False
        if not all(probe["blocked"] for probe in self.probes):
            raise RuntimeError("Local guard self-test failed; refusing handler execution")

    def snapshot(self):
        return {
            "installedBeforeHandlerImport": self.installed,
            "mechanism": "CPython audit hook plus SDK/process/FFI import blocker",
            "auditEventsSeen": self.audit_events_seen,
            "blockedOperationCount": len(self.blocked),
            "handlerBlockedOperationCount": sum(not event["duringSelfTest"] for event in self.blocked),
            "blockedOperations": list(self.blocked),
            "selfTests": list(self.probes),
            "passed": self.installed and bool(self.probes) and all(probe["blocked"] for probe in self.probes),
            "boundary": "Blocks normal Python socket, SDK, subprocess and ctypes paths; not a hostile-native-code sandbox.",
        }
