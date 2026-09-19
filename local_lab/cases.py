"""Strict case declarations frozen to the supervisor's pre-implementation plan."""
import hashlib
import json
import re

ITERATION = "RG-SUP-001-9c7acfba"
PLAN_SHA256 = "0a16692d69cb7b9a066eb9ba20c774cfd3b022f36aec243c304f0b71a59db26e"
CASE_IDS = ("no-fault", "crash-after-fulfillment", "different-message-ids", "missing-observation", "ambiguous-side-effect")
EXPECTED = {
    "no-fault": {"vulnerable": "pass", "repaired": "pass"},
    "crash-after-fulfillment": {"vulnerable": "violation", "repaired": "pass"},
    "different-message-ids": {"vulnerable": "violation", "repaired": "pass"},
    "missing-observation": {"vulnerable": "incomplete", "repaired": "incomplete"},
    "ambiguous-side-effect": {"vulnerable": "unresolved", "repaired": "unresolved"},
}
DELIVERIES = {
    "no-fault": [{"messageKey": "message-a", "receiveCount": 1}],
    "crash-after-fulfillment": [{"messageKey": "message-a", "receiveCount": 1}, {"messageKey": "message-a", "receiveCount": 2}],
    "different-message-ids": [{"messageKey": "message-a", "receiveCount": 1}, {"messageKey": "message-b", "receiveCount": 1}],
    "missing-observation": [{"messageKey": "message-a", "receiveCount": 1}],
    "ambiguous-side-effect": [],
}


def load_case(path):
    data = path.read_bytes()
    if len(data) > 16384:
        raise ValueError("Local case exceeds 16 KiB")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    case = json.loads(data, object_pairs_hook=pairs)
    expected_keys = {"schemaVersion", "id", "title", "order", "fault", "deliveries", "observation", "effectModel", "expectedStatus", "maxDeliveries"}
    if not isinstance(case, dict) or set(case) != expected_keys:
        raise ValueError("Local case has unexpected or missing fields")
    if type(case["schemaVersion"]) is not int or case["schemaVersion"] != 1 or case["id"] not in CASE_IDS:
        raise ValueError("Unsupported local case schema/id")
    case_id = case["id"]
    if path.stem != case_id or case["expectedStatus"] != EXPECTED[case_id] or case["deliveries"] != DELIVERIES[case_id]:
        raise ValueError("Case differs from frozen scenario/expectations; do not tune cases to pass")
    if not isinstance(case["title"], str) or not 1 <= len(case["title"]) <= 120:
        raise ValueError("Case title must be 1–120 characters")
    if type(case["maxDeliveries"]) is not int or case["maxDeliveries"] != len(DELIVERIES[case_id]) or case["maxDeliveries"] > 2:
        raise ValueError("Finite delivery limit differs from frozen scenario")
    for delivery in case["deliveries"]:
        if type(delivery.get("receiveCount")) is not int:
            raise ValueError("Receive count must be an integer, not a boolean")
    fault = "crash-after-fulfillment" if case_id == "crash-after-fulfillment" else "none"
    observation = "withhold-ledger" if case_id == "missing-observation" else "independent-ledger"
    model = "ambiguous-external-effect" if case_id == "ambiguous-side-effect" else "receiver-owned-receipt"
    if case["fault"] != fault or case["observation"] != observation or case["effectModel"] != model:
        raise ValueError("Case fault/observation/model differs from frozen scenario")
    order = case["order"]
    if not isinstance(order, dict) or set(order) != {"orderId", "sku", "quantity"}:
        raise ValueError("Order requires orderId, sku and quantity")
    if not isinstance(order["orderId"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", order["orderId"]):
        raise ValueError("Invalid orderId")
    if not isinstance(order["sku"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", order["sku"]):
        raise ValueError("Invalid SKU")
    if type(order["quantity"]) is not int or not 1 <= order["quantity"] <= 100:
        raise ValueError("Invalid quantity")
    return case, hashlib.sha256(data).hexdigest()
