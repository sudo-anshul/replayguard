# The repair that loses a valid order

Executed September 20, 2026 IST (September 19 UTC), from a clean extraction of
the public regression kit. These are actual local Python executions with
networking denied by macOS `sandbox-exec`, using the kit's own runner and source.
The receiver's receipts are simulated fulfillment; this is not an AWS run or
outside-user validation.

| Source change | Process exit | ORDER-A | ORDER-B | Business result |
|---|---:|---:|---:|---|
| Original order-ID key | 0 | 1 receipt | 1 receipt | Passed |
| Key changed to SKU | 1 | 1 receipt | 0 receipts | Violation |
| Original source bytes restored | 0 | 1 receipt | 1 receipt | Passed |

All three executions selected `interleaved-retries` with exactly the same
inputs, deliveries and fault conditions. The broken run contains the receiver's
payload-conflict evidence for ORDER-B. Removing duplicate fulfillment is not
sufficient when a legitimate order is rejected.

Each folder contains the original report bytes, stdout/stderr, actual source
before and after execution, and a timestamped execution record. The summary
checks source fingerprints against the executed candidate, independent receipt
counts, actual process exits, fault evidence, identical cases, exact source
restoration, and a byte-identical re-export of the kit.

Archive SHA-256 at execution:

```text
6c25d254c8f53216ae7e82a46d8102b7508d8d83a4ad7933487a3541260654e5
```

Reproduce the sequence with the [runbook](../runbook.md). Open the live lab and
import `before/report.json`, `broken/report.json` and `restored/report.json` to
inspect the receipts. Imported-file origin is not authenticated; hashes identify
bytes and do not establish authorship. The kit and observed contract remain
bounded trusted-Python tests with an in-memory atomic receiver.
