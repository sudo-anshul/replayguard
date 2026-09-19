/* Read-only repair reference at the named source commit. Not imported execution evidence.
 * Excerpts preserve source bytes, indentation and final LF; ranges are one-based, inclusive.
 * tests/test_reference_repair.cjs detects full-source and excerpt drift.
 */
(function (root, factory) {
  'use strict';
  const reference = factory();
  if (typeof module === 'object' && module.exports) module.exports = reference;
  else Object.defineProperty(root, 'ReplayGuardReferenceRepair', {
    value: reference, enumerable: true, writable: false, configurable: false
  });
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function freeze(value) {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
    return value;
  }
  return freeze({
  "schemaVersion": 1,
  "version": "63bc428117f9df20427f2aa789c78ca61348845e",
  "files": {
    "worker": {
      "path": "src/worker.py",
      "sha256": "de7873c61f4d140e7229d7ae4eb1c03aaf0f2ec34b22d00291c25c7a3cea5b4f"
    },
    "provider": {
      "path": "src/provider.py",
      "sha256": "0c053a5cbf7f57da3aeb0fef2c2ddf6312682a70cdeccd9618bcbdccaeb91a8a"
    }
  },
  "excerpts": {
    "workerRepair": {
      "file": "worker",
      "start": 105,
      "end": 108,
      "text": "        if payload[\"mode\"] == \"repaired\":\n            # The repair is a stable key supplied by the caller to an idempotent\n            # receiver. An attempt UUID would create another fulfillment.\n            invocation_payload[\"idempotencyKey\"] = idempotency_key(payload[\"runId\"], payload[\"order\"][\"orderId\"])\n"
    },
    "workerKey": {
      "file": "worker",
      "start": 65,
      "end": 67,
      "text": "def idempotency_key(run_id, order_id):\n    identity = json.dumps([run_id, order_id], separators=(\",\", \":\")).encode(\"utf-8\")\n    return hashlib.sha256(identity).hexdigest()\n"
    },
    "providerWrite": {
      "file": "provider",
      "start": 109,
      "end": 129,
      "text": "    accepted = True\n    try:\n        ledger().put_item(Item=receipt, ConditionExpression=\"attribute_not_exists(PK) AND attribute_not_exists(SK)\")\n    except Exception as error:\n        code = getattr(error, \"response\", {}).get(\"Error\", {}).get(\"Code\")\n        if not keyed or code != \"ConditionalCheckFailedException\":\n            raise\n        existing = ledger().get_item(Key={\"PK\": receipt[\"PK\"], \"SK\": receipt[\"SK\"]}, ConsistentRead=True).get(\"Item\")\n        if not existing:\n            raise RuntimeError(\"Conditional write conflicted but no durable receipt was found\") from error\n        expected = {\"runId\": payload[\"runId\"], \"mode\": payload[\"mode\"], \"orderId\": order[\"orderId\"], \"sku\": order[\"sku\"], \"quantity\": order[\"quantity\"], \"idempotencyKey\": stable_key}\n        if any(existing.get(key) != value for key, value in expected.items()):\n            emit(\"payload_conflict\", payload, context, existing)\n            raise PayloadConflict(\"Idempotency key already used with different fulfillment inputs\") from error\n        receipt = existing\n        accepted = False\n    emit(\"accepted\" if accepted else \"reused\", payload, context, receipt, accepted=accepted, reused=not accepted)\n    return {\n        \"receiptId\": receipt[\"receiptId\"], \"accepted\": accepted, \"reused\": not accepted,\n        \"idempotencyKey\": receipt[\"idempotencyKey\"], \"createdAt\": receipt[\"createdAt\"],\n    }\n"
    },
    "providerSelection": {
      "file": "provider",
      "start": 86,
      "end": 94,
      "text": "def handler(event, context):\n    payload = validate_payload(event)\n    require_active_lab()\n    order = payload[\"order\"]\n    stable_key = idempotency_key(payload[\"runId\"], order[\"orderId\"])\n    # Mode separates the comparison's ledgers; only the receiver contract's\n    # optional key controls idempotency. Both handlers use the same provider.\n    keyed = \"idempotencyKey\" in payload\n    receipt_id = stable_key if keyed else uuid.uuid4().hex\n"
    },
    "providerValidation": {
      "file": "provider",
      "start": 44,
      "end": 46,
      "text": "    if \"idempotencyKey\" in payload and payload[\"idempotencyKey\"] != idempotency_key(payload[\"runId\"], order[\"orderId\"]):\n        raise ValueError(\"idempotencyKey must be the SHA-256 of the compact JSON [runId,orderId] tuple\")\n    return payload\n"
    }
  }
});
});
