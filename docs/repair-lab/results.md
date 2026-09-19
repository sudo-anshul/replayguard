# Repair-bench results

## September 20 release checkpoint

The [new key-scope tutorial](key-scope-tutorial/README.md) was executed from a clean extraction of the kit, using its own runner with network access denied. With the same two-order inputs and faults, the order-ID key passed with 1/1 receipts, the SKU mutation produced a violation with 1/0, and exact source restoration passed with 1/1. Reports, process exits, source snapshots and the archive hash at execution are retained in that record. This is local simulated fulfillment, not a cloud run or outside-user trial.

The accepted interface imported those three actual reports, preserved the prior view/bytes after contradictory and invalid-UTF-8 files, and downloaded the restored report byte-for-byte unchanged. The [release record](../releases/2026-09-20.md) lists the specific responsive, keyboard and scroll checks and the untested zoom/reduced-motion states. The first new AWS attempt remains unresolved; the corrected second attempt passed and retains its original verifier/assertions. The final third run with the hardened verifier **passed 22/22 experiment checks and verified cleanup**, observing no-key 2/2 violation, SKU-key 1/0 violation and order-key 1/1 passed. Its [exact report](../../web/aws-key-scope-report.json) and [captured-source archive](../../web/aws-key-scope-regression.zip) are now published with the accepted interface in **Amplify Deployment 4**. [All attempts and verifier chronology](../releases/2026-09-20.md#aws-evidence).

[Anonymous HTTPS checks](../releases/2026-09-20-anonymous-https.json) matched the root and all 37 staged assets, and [scoped live-browser checks](../releases/2026-09-20-browser.json) covered the main/AWS interactions and 390-pixel layouts. The [silent local video is complete](../releases/2026-09-20.md#media-and-publication): 154.000 seconds, zero audio streams, full decode and 14 technical checks passed. The visual review covered 28 sampled encoded frames. Source commit [`0d0ec11ef4e3ba30ad03f2bd623f4e116d7ce664`](https://github.com/sudo-anshul/replayguard/commit/0d0ec11ef4e3ba30ad03f2bd623f4e116d7ce664) is published and [anonymously verified](../releases/2026-09-20-github-public.json). [Network-denied clean-source validation](../releases/2026-09-20-source-validation.json) passed 149 Python tests, 112 JavaScript tests, 45 transfer checks and 19 release checks, with byte-identical re-export. The source ZIP is local, and later docs-only records are separate from the tested source. [Hosted CI](../releases/2026-09-20-github-ci.json) remains incomplete because no steps started under the billing block. No new narration or YouTube upload occurred; the existing 2:43 film remains the older published video.

## September 19 reference evidence

The reference results below were recorded September 19, 2026. These tests execute trusted Python adapters locally and do not perform AWS calls. [Current delivery status](../publication-status.md) distinguishes later release work from these dated observations.

## A repair must preserve both orders

The reference interleaved schedule submits two valid orders for the same SKU, crashes after the first order's receipt commits, then retries and redelivers the orders. The observer expects one correct receipt for each business order.

| Candidate | ORDER-A receipts | ORDER-B receipts | Derived result |
| --- | ---: | ---: | --- |
| `no-key` | 2 | 2 | Violation: both orders were duplicated |
| `overbroad-key` (SKU) | 1 | 0 | Violation: the second valid order was suppressed |
| `business-key` | 1 | 1 | Passed |

Source: [native reference report](../../web/repair-example.json). This is the core product result: a repair can eliminate duplicates while still breaking fulfillment. The observer checks each expected order and its full payload instead of trusting successful worker returns or an aggregate receipt count.

Across the eight reference cases and three candidates, the report contains **24 candidate/case results: 12 passed, 6 violations, 3 incomplete, and 3 unresolved**. The business-key adapter passes all six supported, observed cases. Missing-snapshot controls remain incomplete; unsupported external effects remain unresolved. Consequently, the default full-suite CLI exits **3**, including when selecting the business-key candidate across all eight cases.

## Independent application transfer

A separate AI agent authored DispatchDesk's worker, adapter, five-scenario plan, and two mutations, then froze them before reading the engine implementation. The engine author did not inspect the frozen scenario files before their first execution. Both authors worked in the same project. The plan contains **18 deliveries** and uses an application-specific dispatch event and fulfillment gateway payload, mapped through the public adapter contract.

| Actual application candidate | Five-scenario outcome |
| --- | --- |
| Reference business key | 5 passed |
| Key removed | 5 violations, including actual duplicate receipts |
| SKU-only key | 2 multi-order violations; 3 single-order cases passed |

The [first unseen run](transfer-results/first-execution/summary.json), completed at **03:58:15 UTC**, passed **44 integrity and execution checks**. These checks cover five scenarios and their mutations; they are not 44 separate scenarios. No fixture edits or retry tuning preceded that successful first run.

The [final numeric-runtime run](transfer-results/final-numeric-runtime/summary.json), completed at **04:08:29 UTC**, passed **45 checks**, including before/after runtime-source fingerprints. It reruns already exposed cases and does not claim a second unseen evaluation. Original frozen inputs and application bytes remained unchanged. The evidence is synthetic application transfer, not human-customer validation or adoption.

The source-repository command uses `--case-file tests/repair_holdout/dispatchdesk-plan.json`. The portable kit packages the same plan at `examples/dispatchdesk/cases.json`.

## Native execution and browser agreement

The engine's **26 focused tests** cover receipt preservation, cross-order collisions, changed payloads, fake crashes, reused receipts, missing observation, unsupported effects, caught guard violations, source capture, stale bytecode, protocol misuse, timeouts, call bounds, strict input parsing, and JSON numeric semantics.

```sh
python3 -m unittest discover -s tests -p test_repair_lab.py
python3 tests/repair_holdout/native_parity.py --output-directory /tmp/replayguard-native-parity-check
```

The [native parity integration](validation/native-parity/summary.json) passed **70 checks over nine real reports**. It runs adapters that submit wrong payloads, reuse a receipt repeatedly, manually raise a crash during an expected rejection, exhaust allowed calls, time out after a committed effect, and catch an out-of-delivery protocol error. Additional cases cover supported million-unit quantities/receive counts, empty descriptions, `1` versus `1.0`, `-0.0` versus `0`, and boolean/number distinction. The test never rewrites report states.

The [separate browser pass](native-browser-results/final/results.json) imported all nine native reports, rendered the expected status, and downloaded each file byte-for-byte unchanged. At 390 CSS pixels, the document did not overflow the viewport. That pass recorded no page errors or remote requests and preserved the tested UI source hashes. These checks do not claim full cross-browser or screen-reader certification.

The [current-page import checks](import-tampering-results/final-main/results.json) rejected contradictory receipt, input, fault, and summary claims while preserving the previous view and imported bytes. The [legacy comparison check](legacy-preservation/browser-reference-results.json) verifies the retained original experience separately.

## September 19 portable-kit reproduction

The September 19 validated regression kit contained **22 files / 32,330 bytes**. Its recorded SHA-256 was:

```text
e01bdcaef59a813f56c96a4ba9e10c25175d41dd33c56d7e9b29b5b29d9d2555
```

The [current kit download](../../web/replayguard-repair-lab.zip) may be a later release. Do not apply this historical hash to it; the [September 20 tutorial summary](key-scope-tutorial/summary.json) identifies the exact newer archive executed there.

[Final clean extraction validation](validation/numeric-parity-final/package-validation.json) completed at **04:08:15 UTC**. Four actual CLI executions used the archive's own sources, Python `-I -S`, a sanitized environment, the local guard, and macOS network denial:

1. A copied business-key adapter passed the crash/retry case, exit 0.
2. Changing that same copied source to `key=None` produced a violation, exit 1.
3. Restoring its original bytes restored the pass, exit 0.
4. DispatchDesk's five-scenario plan passed, exit 0.

Source fingerprints matched the files actually executed. Re-export was byte-identical; archive manifests and checksums matched; **50 previously fingerprinted historical evidence/archive files remained unchanged**. Those 50 files are preservation checks, not new application scenarios. The [validation guide](validation/README.md) records the complete transcript, earlier attempts, and reproducible command.

## AWS evidence and present limits

The original AWS run remains dated **September 18, 2026**: real SQS redelivery, a Lambda worker, a separate fulfillment Lambda, DynamoDB receipts, and CloudWatch evidence. It observed two vulnerable receipts versus one repaired receipt and satisfied **16 recorded assertions**. The initial cold-start failure remains separate. See [recorded AWS validation](../validation.md), [dated viewer](../../web/aws-run.html), and [preserved original comparison](../../web/recorded-lab.html).

The original AWS crash followed a successful fulfillment response. The new local harness injects immediately after receipt commit and before the response returns. Local execution does not establish AWS queue timing, durability, throttling behavior, or exactly-once delivery. The receiver receipt is the entire simulated effect; external payments, emails, and shipments require their own supported effect contract.

Both original AWS stacks reached `DELETE_COMPLETE` on **September 18 at 19:13:43 UTC**. That cleanup is historical evidence. Publication and hosting resumed on September 19 under a **US$25 cumulative gross project ceiling, with US$5 reserved**. Gross-spend headroom must be confirmed before new billable work; AWS credits do not establish it. The release gate observed about **$0.23 gross for September 17–18** before credits/refunds, with current-day and billing-lag uncertainty. Allowing **$2 for prior lag and $2 for static hosting** gives about **$4.23 conservative exposure**, below the $20 working envelope. This is an operating budget, not an AWS-enforced hard billing cap. Current hosting, repository, video and submission links are recorded in [publication status](../publication-status.md).

The [September 19 published demo](https://youtu.be/CGE19upS66A) is **163.033333 seconds (2:43)** and 13,108,071 bytes, SHA-256 `f59eeaf60918c0be3b98cdbfae39db474bc3909604f463751ddd0274994c8621`. It uses Neha's synthetic Indian-English narration, real adapter edits/executions/imports and explanatory motion. All [19 technical checks](media/revision-2/validation/final-video.json) passed; an independent review of nine final-output frames found no remaining concrete blocker. The [September 19 tutorial evidence](media/revision-2/README.md) passed 73/73 checks and preserved the observed 1 → 2 → 1 receipt sequence. These facts describe the earlier video; the completed silent local revision has its own metadata and checks above. Earlier MP4s and their [original render evidence](media/manifest.json) remain preserved. [Publication status](../publication-status.md) distinguishes the versions and their checks.

The earliest observed official deadline is **September 20, 09:00 IST**. Exact organizer confirmation remains unresolved because the form configuration and countdown conflict. See [deadline evidence](../deadline.md).

The [September 19, 04:12 UTC read-only refresh](../deadline-refresh-20260919.json) confirmed the same earlier API cutoff. The refreshed overview response supplied no end time, leaving the discrepancy unresolved. No AWS API was used for this check.
