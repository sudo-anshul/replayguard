# Repair plan and report v2

Plans use `schemaVersion: 2`, `kind: "replayguard-repair-plan"`, and a nonempty `cases` array. Unknown fields, duplicate JSON keys, invalid values, duplicate case/delivery IDs, and oversized input are rejected. Case fields are `id`, `title`, `description`, `effectModel`, `observation`, `expectedOrders`, and `deliveries`.

```json
{
  "schemaVersion": 2,
  "kind": "replayguard-repair-plan",
  "cases": [{
    "id": "crash-retry", "title": "Committed effect, lost response", "description": "Retry after fulfillment commits.",
    "effectModel": "receiver-owned-receipt", "observation": "independent-ledger",
    "expectedOrders": [{"order": {"orderId": "A", "sku": "BOOK", "quantity": 1}, "count": 1}],
    "deliveries": [
      {"deliveryId": "d1", "messageId": "m1", "receiveCount": 1, "order": {"orderId": "A", "sku": "BOOK", "quantity": 1}, "fault": "after-commit", "expect": "crash"},
      {"deliveryId": "d2", "messageId": "m1", "receiveCount": 2, "order": {"orderId": "A", "sku": "BOOK", "quantity": 1}, "fault": "none", "expect": "complete"}
    ]
  }]
}
```

`effectModel` is `receiver-owned-receipt` or `unsupported-external`. `observation` is `independent-ledger` or `missing`. Expected orders have unique business order IDs and `count: 1`. Orders contain exactly `orderId`, `sku`, `quantity`, and optional `attributes` object. Delivery IDs are unique per case; repeated message IDs and business order IDs are allowed. Fault is `none` or `after-commit`; expected outcome is `complete`, `crash`, or `conflict`. Only crash expectations may configure `after-commit`, and every crash expectation must configure it. Supported cases need at least one expected order and delivery. Unsupported controls may have empty arrays.

Attribute numbers use semantic JSON equality: `1` equals `1.0`, and `-0.0` equals `0`. Booleans remain distinct from numbers. All numbers must be finite; integer-valued numbers must be in the JavaScript safe integer range (−9007199254740991 through 9007199254740991). The runner rejects values outside that range instead of silently rounding them in the browser. Attribute objects are limited to 4096 serialized characters, nesting depth 32, and 4096 values. These rules apply both to plans and candidate-submitted effect payloads.

For compatibility with the first public draft, the parser generically accepts delivery `id` instead of `deliveryId`, fault `after-commit-before-response` instead of `after-commit`, effect model `atomic-receipt` instead of `receiver-owned-receipt`, and observations `complete` instead of `independent-ledger` and `withheld` instead of `missing`. Supplying both ID names is rejected. Reports always use the canonical vocabulary above. These are input aliases for every plan, not exceptions for particular cases.

Reports use `schemaVersion: 2`, `kind: "replayguard-repair-report"`, `provenance: "local-execution"`, `startedAt`, `recordedAt`, `candidates`, canonical `cases`, `results`, `summary`, `boundaries`, and `guard`. Each candidate has `id`, `title`, `adapter` (relative source filename), `sourceSha256` (relative `.py` filename to SHA-256), and `sourceHashScope`.

Each result contains `candidateId`, `caseId`, `status`, `expectedOrders`, `receipts` (array or null when observation is unavailable), `deliveries`, `events`, `assertions`, `errors`, `execution`, and `blockedOperationCount`. `execution` contains `imported`, `built`, `sourceUnchanged`, `snapshotComplete`, `completedSchedule`, `console`, and `consoleTruncated`. Errors contain `phase`, `type`, and `message`.

Receipt fields: `receiptId`, `order`, `key` (string or null), `createdAt`, and `acceptedDeliveryId`. Delivery fields: `deliveryId`, `messageId`, `receiveCount`, `order`, `fault`, `expect`, `attempted`, `outcome`, `error` (object or null), `returned` (diagnostic JSON or null), `faultInjected`, `effectCalls`, `acceptedReceiptIds`, `reusedReceiptIds`, `conflictObserved`, `startedAt`, and `finishedAt`. Outcomes are `completed`, `crashed`, `conflict`, `error`, `timeout`, `not-run`.

Accepted receipt IDs are unique within the receiver ledger. Reused receipt IDs may repeat within a delivery when a candidate calls `fulfill` with the same key more than once; each reuse has a corresponding `receipt-reused` event. `effectCalls` saturates at 9 (eight allowed calls and the first denied call). Event `index` starts at zero. `sourceUnchanged` requires both copied source integrity and unchanged original files through the run.

Events are receiver/harness records with monotonic `index`, `type`, and `deliveryId`; type is `delivery-start`, `receipt-accepted`, `receipt-reused`, `payload-conflict`, `fault-injected`, or `delivery-end`. Effect events include `receiptId`, `order`, and `key` where applicable. Assertions are `{id,status,message}` with status `pass`, `violation`, `incomplete`, or `unresolved`. UI consumers must recompute conclusions from cases, receipts, outcomes and execution facts; supplied status/summary/assertion labels are not authority. Imported JSON is unauthenticated evidence.

Assessment rules, in order of severity:

1. Unsupported effects or any guard-blocked operation are `unresolved`.
2. Given a complete independent snapshot, each expected business order must have exactly one receipt with the complete expected payload. Duplicate, missing, wrong-payload, or unrequested receipts are `violation`. Legitimate deliveries ending in conflict are `violation`. An expected conflict returning normally or accepting a new effect is `violation`.
3. Missing snapshot, failed import/build, changed source, unrun schedule, or unexpected errors/timeouts are `incomplete` unless a stronger result above exists. Expected crash requires outcome `crashed`, a harness-recorded injection, and a matching committed receipt plus accepted/injected events for that delivery. Unmet failpoint is `incomplete`. Expected conflict requires outcome `conflict` and no new accepted effect; other unexplained failure is `incomplete`.
4. `pass` requires the supported observed business invariant and every required outcome. Candidate return values cannot supply receipt truth or satisfy rejected/conflicted requests.

Per-result and aggregate severity is `unresolved > violation > incomplete > pass`. `summary` has `status`, `exitCode`, and `counts` keyed by all four statuses. A preflight input failure produces no fabricated case results: it records a top-level `errors` list, summary `incomplete`, and exit 2.
