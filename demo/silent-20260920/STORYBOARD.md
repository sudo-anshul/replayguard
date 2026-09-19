# Silent English storyboard

Final assembly: 154 seconds. Frozen r3 AWS evidence and verified destination URLs. No voice or audio.

| Time | Main on-screen text | Supporting line | Source |
|---|---|---|---|
| 000.00–008.00s | Committed. Failed. Retried. | The receipt persisted. The invocation failed. SQS retried. | Recorded AWS run · recorded |
| 008.00–016.00s | A failed response does not undo fulfillment. | AWS experiment: the provider fails after receipt commit, before success returns. | Explanation · fault |
| 016.00–022.00s | Our first run caught our own provider defect. | Plausible counts were not enough. The experiment stayed unresolved. | Recorded AWS run · recorded |
| 022.00–028.00s | Same two orders. Three keys. One fault. | Count each order’s receipts independently of the worker. | Recorded AWS run · recorded |
| 028.00–031.00s | The receiver commits before the response fails. | First delivery: a durable receipt exists before the worker reports failure. | Recorded AWS run · recorded |
| 031.00–034.00s | The worker fails. The receipt remains. | Then ORDER-B reaches the same product key and is rejected. | Recorded AWS run · recorded |
| 034.00–038.00s | A passing retry test can hide a broken key. | Two valid orders. One shared product. | Local regression · recorded |
| 038.00–044.00s | Check both valid orders. | A product key prevents the retry—and loses the other order. | Local regression · recorded |
| 044.00–054.00s | Same product ≠ same order. | The fulfillment key must identify the business order. | Explanation · scope |
| 054.00–060.00s | Take the case to your handler. | Local regression: interrupt after commit, before the response returns. | Local regression · recorded |
| 060.00–068.00s | Start with the order ID. | Same two orders. Same local fault. Actual Python execution. | Local regression · recorded |
| 068.00–072.40s | Change only the key: orderId → sku. | Save the real adapter, then run the same case. | Local regression · recorded |
| 072.40–076.00s | Change only the key: orderId → sku. | Saved to the actual adapter. The next action runs this source. | Local regression · recorded |
| 076.00–082.00s | A green retry can hide a missing order. | Read each order’s receipt count, not only the worker’s return. | Local regression · recorded |
| 082.00–089.00s | Import the actual result. | The report carries its original receipt and source evidence. | Local regression · recorded |
| 089.00–093.00s | Open the assertion. Inspect the receipts. | ORDER-B expected one receipt. The observed count is zero. | Local regression · recorded |
| 093.00–096.00s | The receipt survived the crash. | ORDER-A committed. The product key then rejects ORDER-B. | Local regression · recorded |
| 096.00–099.00s | The retry reuses A. B is still rejected. | One shared product key cannot represent two business orders. | Local regression · recorded |
| 099.00–103.60s | Restore orderId. Run the same case. | Only the fulfillment key changes. | Local regression · recorded |
| 103.60–107.00s | Restore orderId. Run the same case. | Saved to the actual adapter. The next action runs this source. | Local regression · recorded |
| 107.00–113.00s | Test the repair against the same fault. | Actual Python execution · same two orders, same fault. | Local regression · recorded |
| 113.00–120.00s | Check every valid business order. | Import the repaired report and inspect the observed receipts. | Local regression · recorded |
| 120.00–128.00s | One line. Three recorded executions. | Same case and fault. Source restored exactly. | Recorded report comparison · report |
| 128.00–133.00s | Keep the failure with your code. | A runnable regression case, with the evidence needed to inspect it. | Explanation · package |
| 133.00–140.00s | Export the original report. | Inputs · fault conditions · assertions · receipts | Local regression · recorded |
| 140.00–144.13s | Incomplete: the receipt snapshot is missing. | Unknown is not zero. A missing snapshot cannot establish a pass. | Local regression · recorded |
| 144.13–148.00s | Unresolved: the effect contract is unsupported. | This external effect was not tested. No passing result is claimed. | Local regression · recorded |
| 148.00–154.00s | A failure you can replay. A repair you can verify. |  | Explanation · close |

The three-report insert reads actual before/broken/restored JSON files and verifies their hashes, reported state, and receipt counts against execution metadata. The SKU mutation suppresses a second valid order; it is not the missing-key duplicate case.

AWS and local execution remain separately labeled. The frozen AWS provider fails after receipt commit, before success returns. The historical first attempt is unresolved and explicitly labels its origin and later cleanup confirmation. The successful r3 experiment preserves two faulty business outcomes and one passing repair.

Unsaved edits exclude stale saved-key footers and previous results. Saved edits show the real source and enabled next run action. The delivery trail preserves observed receipt commit, fault, conflict, and receipt reuse.

Captured-action scenes include explicit editorial reading holds. Original timestamps, retained intervals, omitted elapsed gaps, source-file hashes, and clip hashes remain in provenance. The earlier complete local comparison is a labeled return to an earlier recorded final snapshot, not a second execution.
