# Validation record

## September 20 release checkpoint

The [current release record](releases/2026-09-20.md) documents the accepted interface's local browser checks and the [fresh key-scope tutorial](repair-lab/key-scope-tutorial/README.md): actual identical-case executions changed the order-ID key to SKU and restored it, producing 1/1 → 1/0 → 1/1 receipts. The UI imported all three reports with their expected business states and downloaded the restored report byte-for-byte unchanged.

The current browser review covered 1280×800, 390×844 and 320×568 layouts without observed horizontal overflow; keyboard candidate activation retained focus. Contradictory and invalid-UTF-8 imports preserved the preceding report/bytes. Scroll forward, reverse and manual ownership checks passed, with no console warnings/errors observed during reviewed states. A 200% zoom run and an operating-system reduced-motion preference check were **not performed**; source fallback is not runtime verification of that preference.

The first new six-original-message AWS attempt, `85500aff-3d08-483e-9e63-78a9723eb67a`, ended **unresolved**: provider JSON logging failed on DynamoDB `Decimal` values, so SKU-key ORDER-B lacked terminal rejection evidence and reached the DLQ. Its [original report](../evidence/key-scope-20260920.json) and [captured-source archive](../web/aws-key-scope-attempt-1.zip) remain preserved. The SKU candidate is incomplete; receipt counts alone did not establish the intended comparison. Cleanup was unconfirmed in that report because of a separate optional-error-metadata parsing defect; a [later exact-ARN read](../evidence/key-scope-20260920-cleanup-followup.json) verified deletion at 2026-09-19 19:07:27 UTC. It changes neither the original record nor the business failure.

The corrected [second run](../evidence/key-scope-20260920-r2.json), `366eeb3b-3258-474b-8136-792f1587ffa5`, **passed with verified cleanup**, observing 2/2, 1/0 and 1/1 receipts with the required terminal evidence. Independent audit subsequently found two checker acceptance gaps using deliberately tampered reports: absent required source hashes and contradictory terminal events. Targeted fixes reject those cases and preserve valid distinct-invocation retries. The second run's raw evidence still derives a pass; its original stored assertions and [archive](../web/aws-key-scope-attempt-2.zip) remain tied to their original verifier.

The final [third run](../evidence/key-scope-20260920-r3.json), `82a1155f-c729-4b56-a32f-b4bc9a70a3ad`, **passed 22/22 experiment checks** with the captured hardened verifier and unchanged worker/provider behavior. It observed no-key 2/2 receipts (violation), SKU-key 1/0 with terminal rejection (violation), and order-key 1/1 (passed). Collection used **114 API calls**; cleanup used a separate 31 and verified deletion at **2026-09-19 19:36:17.789 UTC**, with no cleanup errors. The [site report](../web/aws-key-scope-report.json) is byte-identical to the final raw record, and the [regression archive](../web/aws-key-scope-regression.zip) retains its captured sources. [Exact versions, hashes and historical attempts](releases/2026-09-20.md#aws-evidence). The current checkpoint also confirms 144 SDK-free Python and 112 JavaScript tests passing; publication verification remains separate.

The current site is **published in Amplify Deployment 4**. [Anonymous HTTPS checks](releases/2026-09-20-anonymous-https.json) matched the root and all 37 staged assets. [Live-browser checks](releases/2026-09-20-browser.json) confirmed main/AWS navigation, order-key selection with focus retained, exact final AWS report identity, SKU terminal rejection, expected business/cleanup states and no observed horizontal overflow at 390×844. The initial checker's local trust-store failure is retained separately; its successful rerun used the installed botocore CA bundle with TLS certificate/hostname validation enabled. Zoom, runtime reduced motion and a new native kit-save completion were not tested.

The completed silent local MP4 is **154.000 seconds**, 1920×1080 H.264/30 fps, with 4,620 video frames and zero audio streams. Its 9,472,219 bytes hash to `bf6af0ae5585a044ce58eae3dafedc64374ddd86362710fdf6d7d8f8f79f120c`. Full decode and all [14 technical checks](releases/2026-09-20-silent-video.json) passed. [Visual review](releases/2026-09-20-silent-video-review.json) covered 28 sampled encoded frames across every scene; it does not establish a full real-time watch-through. Actual captured sequences are composed with animation and reading holds, not presented as a native 30 fps screencast. The [static source verification](../demo/silent-20260920/source-verification.json) rebuilt 16 capture clips byte-identically in the same installed runtime; it did not perform another full-master render or a fresh npm install. [Artifact and production details](releases/2026-09-20.md#media-and-publication).

The final source commit/export/publication remain pending. The new local video does not replace the earlier published YouTube upload, and no new voice or YouTube upload was performed. The dated AWS and media records below remain unchanged in scope.

## September 18 AWS comparison

The real AWS comparison **passed all 16 recomputed assertions** in `us-east-1` for run `dec1c369-e85d-442f-8a12-af0f4d2ac718`. The run started at **2026-09-18 18:56:16.240 UTC** and finished at **18:58:34.825 UTC** (138.585 seconds). Raw evidence is in [evidence/latest.json](../evidence/latest.json); the downloadable, self-contained regression is [web/regression-case.zip](../web/regression-case.zip).

One synthetic order, `ORDER-1042`, requested one `FIELD-NOTES-3PACK`. The runner sent exactly two SQS messages: one per handler mode. Both received the same `crash-after-fulfillment` condition.

| Observation (UTC, 2026-09-18) | Vulnerable | Repaired |
| --- | --- | --- |
| First worker receive | 18:56:19.966 | 18:56:20.249 |
| Independent provider accepted first receipt | 18:56:22.992 | 18:56:23.216 |
| Worker logged success, then injected failure | 18:56:22.995 | 18:56:23.221 |
| Same SQS message redelivered | 18:57:31.756 | 18:57:32.029 |
| Time between worker receives | 71.790 seconds | 71.780 seconds |
| Retry completed | 18:57:31.809 | 18:57:32.086 |
| Independent durable receipt count | **2** | **1** |

CloudWatch records `ApproximateReceiveCount` values 1 and 2 with distinct Lambda request IDs for each original SQS message. The vulnerable message ID is `0f2a113a-7dc7-4201-afcc-c26b2476bf9b`; the repaired message ID is `e0ad7ed4-9092-4745-8faa-aaae8dc0ce06`. The verifier binds receipts and log events to those IDs and the exact case payload.

The independent provider accepted three effects across the comparison and reused the repaired receipt on its retry. The repaired worker reported `accepted=false` and `reused=true`, preserving receipt `3b035b6e19eed379be4248f17b81c6b95075099176e38f0698d90f1822023cb9`. Receipt counts came from strongly consistent DynamoDB queries, not worker success claims.

Both queues remained observed empty for **18.967 seconds**, exceeding the 15-second requirement. Final queue observation was at 18:58:30.930 UTC, followed by ledger reads at 18:58:31.777 and 18:58:32.141 UTC. No DLQ messages or collection errors were observed. Collection used **123 AWS API calls** against its 300-call limit and recorded 18 structured events: 14 worker and 4 provider events.

## Reproduction and checks

- `python3 -m unittest discover -s tests`: **51 tests passed** on the final source, covering the handler crash/retry behavior, input limits, contradictory or incomplete evidence, and collection bounds.
- `python3 scripts/verify_case.py evidence/latest.json --case cases/crash-after-fulfillment.json`: **passed, exit 0**. The verifier recomputes from raw observations rather than trusting saved assertion results.
- Both exported ZIPs were extracted separately; every `SHA256SUMS` entry matched and the extracted verifier returned **passed, exit 0**. Each archive contains 14 files, including deployment source, case, evidence, assertions, pinned Python requirements, replay/verification scripts and cleanup instructions.
- Regression archive SHA-256: `fbc7ba0a3fe4efa6bf26dbc76a0380ff1c96abcd23c4524662e4e618fd5290ef`.

## Earlier real failure retained

The first run, `3ca94e3d-2985-4c90-8d05-62a72d683127`, is preserved in [evidence/initial-cold-start.json](../evidence/initial-cold-start.json). Cold SDK initialization exceeded the initial 128 MB functions' short timeouts before any fulfillment succeeded. Three receives per message produced zero receipts and two DLQ messages. Its recomputed state remains **unresolved**, exit 2; it is not presented as the intended post-fulfillment failure demonstration.

The initial evidence and matching source were archived before modification. The successful deployment increased both functions to 512 MB, set worker/provider timeouts to 12/6 seconds, bounded SDK timeouts, and used 72-second queue visibility. A fresh run UUID then produced the passed evidence above.

## Limits of the result

This is a simulated fulfillment: the durable receipt itself is the side effect. The repair requires a receiver that atomically owns the effect and its idempotency decision. No payment, shipment, email or real customer order was created. SQS queue counts are approximate, and a finite grace observation cannot prove the absence of every future duplicate. Cross-Lambda timestamp comparisons permit two seconds of clock skew; this run's provider acceptance preceded its fault without requiring that allowance. The export's hashes detect changed bytes and bind source versions, but are not AWS-signed attestations. Replaying the archive creates a fresh independent observation.

## September 18 local UI and demo checks

The static site renders the actual captured run as 2 vulnerable receipts versus 1 repaired receipt and 16/16 assertions. Browser checks exercised the handler toggle, JSON dialog, Escape dismissal, invalid-file import rejection without changing the prior view, terminal command copy, and regression ZIP download. The 390×844 mobile viewport had no horizontal overflow. Imported evidence is labeled unauthenticated, and the ZIP button explicitly remains bound to the published/original case when viewing a different import.

The local MP4 is **135.967 seconds** (2:16), 1280×800, H.264 video with AAC system-voice narration. It records the actual UI and AWS evidence page. No YouTube upload or live content publication occurred. Screen recording, narration and editing were performed locally with Playwright, macOS system speech and FFmpeg.

The September 18 hosting publisher did not complete an upload before work paused. That historical attempt remains incomplete. Publication resumed on September 19; [current publication status](publication-status.md) records any subsequently verified deployment.
