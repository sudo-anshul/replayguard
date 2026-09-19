"""Strict, bounded public plan parser and reference schedules."""
import copy
import json
import math
from pathlib import Path

MAX_PLAN_BYTES = 65536
MAX_CASES = 16
MAX_DELIVERIES = 8
MAX_SAFE_INTEGER = 9007199254740991


class PlanError(ValueError):
    pass


def normalize_json_numbers(value, depth=0, budget=None, max_depth=32):
    """JSON value equality shared with browsers, not lexical number equality.

    CPython preserves int/float distinctions that JSON.parse does not. Keep
    booleans distinct, normalize integral floats and reject unsafe integers.
    """
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if budget[0] < 0 or depth > max_depth:
        raise PlanError("JSON value exceeds supported structural bounds")
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int:
        if abs(value) > MAX_SAFE_INTEGER:
            raise PlanError("JSON integers must be within the JavaScript safe integer range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise PlanError("JSON numbers must be finite")
        if value.is_integer():
            if abs(value) > MAX_SAFE_INTEGER:
                raise PlanError("Integral JSON numbers must be within the JavaScript safe integer range")
            return int(value)
        return value
    if isinstance(value, list):
        return [normalize_json_numbers(item, depth + 1, budget, max_depth) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise PlanError("JSON object keys must be strings")
        return {key: normalize_json_numbers(item, depth + 1, budget, max_depth) for key, item in value.items()}
    raise PlanError("Values must use supported JSON types")


def object_keys(value, required, optional=(), label="object"):
    if not isinstance(value, dict):
        raise PlanError(f"{label} must be an object")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing or unknown:
        raise PlanError(f"{label}: missing {sorted(missing)}, unknown {sorted(unknown)}")


def bounded_string(value, label, maximum=160):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PlanError(f"{label} must be a nonempty string of at most {maximum} characters")
    return value


def validate_order(order):
    object_keys(order, ("orderId", "sku", "quantity"), ("attributes",), "order")
    bounded_string(order["orderId"], "orderId")
    bounded_string(order["sku"], "sku")
    if type(order["quantity"]) is not int or not 1 <= order["quantity"] <= 1000000:
        raise PlanError("quantity must be an integer from 1 to 1000000")
    if "attributes" in order:
        if not isinstance(order["attributes"], dict):
            raise PlanError("attributes must be an object")
        try:
            normalize_json_numbers(order["attributes"])
            encoded = json.dumps(order["attributes"], allow_nan=False, sort_keys=True)
        except (TypeError, ValueError, RecursionError) as exc:
            raise PlanError("attributes must be bounded JSON") from exc
        if len(encoded) > 4096:
            raise PlanError("attributes exceeds 4096 characters")
    return copy.deepcopy(order)


def canonical(value):
    return json.dumps(normalize_json_numbers(value, budget=[8192], max_depth=64), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def validate_plan(plan):
    object_keys(plan, ("schemaVersion", "kind", "cases"), label="plan")
    if type(plan["schemaVersion"]) is not int or plan["schemaVersion"] != 2 or plan["kind"] != "replayguard-repair-plan":
        raise PlanError("expected replayguard-repair-plan schemaVersion 2")
    if not isinstance(plan["cases"], list) or not 1 <= len(plan["cases"]) <= MAX_CASES:
        raise PlanError("plan must contain 1–16 cases")
    result = copy.deepcopy(plan)
    ids = set()
    for case in result["cases"]:
        object_keys(case, ("id", "title", "description", "effectModel", "observation", "expectedOrders", "deliveries"), label="case")
        bounded_string(case["id"], "case id")
        bounded_string(case["title"], "case title", 240)
        if not isinstance(case["description"], str) or len(case["description"]) > 2000:
            raise PlanError("case description must be a string of at most 2000 characters")
        if case["id"] in ids:
            raise PlanError("duplicate case id")
        ids.add(case["id"])
        case["effectModel"] = {"atomic-receipt": "receiver-owned-receipt"}.get(case["effectModel"], case["effectModel"])
        case["observation"] = {"complete": "independent-ledger", "withheld": "missing"}.get(case["observation"], case["observation"])
        if case["effectModel"] not in ("receiver-owned-receipt", "unsupported-external"):
            raise PlanError("unknown effectModel")
        if case["observation"] not in ("independent-ledger", "missing"):
            raise PlanError("unknown observation")
        unsupported = case["effectModel"] == "unsupported-external"
        expected = case["expectedOrders"]
        if not isinstance(expected, list) or not (0 if unsupported else 1) <= len(expected) <= MAX_DELIVERIES:
            raise PlanError("expectedOrders must contain 1–8 orders (or zero for unsupported controls)")
        order_ids = set()
        for item in expected:
            object_keys(item, ("order", "count"), label="expected order")
            item["order"] = validate_order(item["order"])
            if type(item["count"]) is not int or item["count"] != 1:
                raise PlanError("expected count must be exactly 1")
            if item["order"]["orderId"] in order_ids:
                raise PlanError("duplicate expected business order id")
            order_ids.add(item["order"]["orderId"])
        deliveries = case["deliveries"]
        if not isinstance(deliveries, list) or not (0 if unsupported else 1) <= len(deliveries) <= MAX_DELIVERIES:
            raise PlanError("deliveries must contain 1–8 items (or zero for unsupported controls)")
        delivery_ids = set()
        for delivery in deliveries:
            if isinstance(delivery, dict) and "id" in delivery:
                if "deliveryId" in delivery:
                    raise PlanError("delivery cannot supply both id and deliveryId")
                delivery["deliveryId"] = delivery.pop("id")
            object_keys(delivery, ("deliveryId", "messageId", "receiveCount", "order", "fault", "expect"), label="delivery")
            bounded_string(delivery["deliveryId"], "deliveryId")
            bounded_string(delivery["messageId"], "messageId")
            if delivery["deliveryId"] in delivery_ids:
                raise PlanError("duplicate delivery id")
            delivery_ids.add(delivery["deliveryId"])
            if type(delivery["receiveCount"]) is not int or not 1 <= delivery["receiveCount"] <= 1000000:
                raise PlanError("receiveCount must be a positive bounded integer")
            delivery["order"] = validate_order(delivery["order"])
            if delivery["fault"] == "after-commit-before-response":
                delivery["fault"] = "after-commit"
            if delivery["fault"] not in ("none", "after-commit") or delivery["expect"] not in ("complete", "crash", "conflict"):
                raise PlanError("unknown delivery fault or expectation")
            if (delivery["fault"] == "after-commit") != (delivery["expect"] == "crash"):
                raise PlanError("after-commit fault and crash expectation must be paired")
    return result


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_plan(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_PLAN_BYTES + 1)
    if len(data) > MAX_PLAN_BYTES:
        raise PlanError("plan exceeds 64 KiB")
    try:
        plan = json.loads(data, object_pairs_hook=_unique_pairs, parse_constant=lambda value: (_ for _ in ()).throw(PlanError(f"invalid JSON number {value}")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PlanError(f"invalid plan JSON: {exc}") from exc
    return validate_plan(plan)


def default_plan():
    a = {"orderId": "ORDER-A", "sku": "FIELD-NOTES", "quantity": 1}
    b = {"orderId": "ORDER-B", "sku": "FIELD-NOTES", "quantity": 1}
    c = {"orderId": "ORDER-C", "sku": "TOTE", "quantity": 2}
    changed = dict(a, quantity=3)
    def delivery(did, order, mid=None, receive=1, fault="none", expect="complete"):
        return {"deliveryId": did, "messageId": mid or did, "receiveCount": receive, "order": copy.deepcopy(order), "fault": fault, "expect": expect}
    def case(cid, title, orders, deliveries, observation="independent-ledger", effect="receiver-owned-receipt"):
        return {"id": cid, "title": title, "description": title + ". Receiver receipts define the business outcome.", "effectModel": effect, "observation": observation, "expectedOrders": [{"order": copy.deepcopy(o), "count": 1} for o in orders], "deliveries": deliveries}
    return validate_plan({"schemaVersion": 2, "kind": "replayguard-repair-plan", "cases": [
        case("clean-orders", "Two clean orders", [a, c], [delivery("d1", a), delivery("d2", c)]),
        case("crash-retry", "Committed effect, lost response", [a], [delivery("d1", a, "m-a", fault="after-commit", expect="crash"), delivery("d2", a, "m-a", 2)]),
        case("different-message", "One order, different messages", [a], [delivery("d1", a, "m-a"), delivery("d2", a, "m-b")]),
        case("two-orders-same-sku", "Different orders share a SKU", [a, b], [delivery("d1", a), delivery("d2", b)]),
        case("interleaved-retries", "Interleaved committed orders and retries", [a, b], [delivery("d1", a, "m-a", fault="after-commit", expect="crash"), delivery("d2", b, "m-b"), delivery("d3", a, "m-a", 2), delivery("d4", b, "m-c")]),
        case("payload-conflict", "Changed payload must be rejected", [a], [delivery("d1", a, "m-a"), delivery("d2", changed, "m-b", expect="conflict")]),
        case("missing-snapshot", "Receiver observation unavailable", [a], [delivery("d1", a)], observation="missing"),
        case("unsupported-effect", "External effect has no atomic receipt contract", [], [], effect="unsupported-external"),
    ]})
