"""Explicit local seams implementing only APIs actually used by the provider."""
import copy
import io
import json
import threading
import types
import uuid


class ConditionalCheckFailed(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Local conditional receipt already exists"}}


class MemoryLedger:
    """An atomic local receipt store; no AWS or persistence is implied."""
    CONDITION = "attribute_not_exists(PK) AND attribute_not_exists(SK)"

    def __init__(self):
        self._rows = {}
        self._lock = threading.Lock()
        self.operations = []

    def put_item(self, *, Item, ConditionExpression):
        if ConditionExpression != self.CONDITION:
            raise ValueError("Local ledger only supports the declared atomic create condition")
        if not isinstance(Item, dict) or not isinstance(Item.get("PK"), str) or not isinstance(Item.get("SK"), str):
            raise ValueError("Receipt must contain string PK/SK")
        key = (Item["PK"], Item["SK"])
        with self._lock:
            if key in self._rows:
                self.operations.append({"operation": "conditional-create", "outcome": "conflict"})
                raise ConditionalCheckFailed()
            self._rows[key] = copy.deepcopy(Item)
            self.operations.append({"operation": "conditional-create", "outcome": "created"})
        return {}

    def get_item(self, *, Key, ConsistentRead):
        if ConsistentRead is not True:
            raise ValueError("Local receiver requires a consistent read")
        with self._lock:
            item = self._rows.get((Key["PK"], Key["SK"]))
            self.operations.append({"operation": "get-receipt", "outcome": "found" if item else "missing"})
            return {"Item": copy.deepcopy(item)} if item else {}

    def independent_snapshot(self):
        """Observer-owned read: never use the worker's return value as the ledger."""
        with self._lock:
            return copy.deepcopy([value for _, value in sorted(self._rows.items())])


class LocalLambdaTransport:
    """Call the real provider handler, preserving synchronous FunctionError shape."""
    FUNCTION_NAME = "local-only-fulfillment-provider"

    def __init__(self, provider):
        self.provider = provider
        self.invocations = []

    def invoke(self, *, FunctionName, InvocationType, Payload):
        if FunctionName != self.FUNCTION_NAME or InvocationType != "RequestResponse":
            raise ValueError("Local transport accepts only the explicitly injected synchronous provider")
        payload = json.loads(Payload)
        request_id = "local-provider-" + uuid.uuid4().hex
        invocation = {"requestId": request_id, "payload": copy.deepcopy(payload)}
        self.invocations.append(invocation)
        context = types.SimpleNamespace(aws_request_id=request_id)
        try:
            result = self.provider.handler(payload, context)
        except Exception as error:
            encoded = {"errorType": type(error).__name__, "errorMessage": str(error)}
            invocation.update({"functionError": "Unhandled", "error": encoded})
            return {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": io.BytesIO(json.dumps(encoded).encode())}
        invocation.update({"functionError": None, "returned": copy.deepcopy(result)})
        return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(result).encode())}
