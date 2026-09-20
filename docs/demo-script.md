# ReplayGuard tutorial — current 2:34 demo

[Watch the September 20 narrated demo](https://youtu.be/coCDLSyU8AY), published **unlisted**. The source `replayguard-demo-neha.mp4` is **154.000 seconds**, **12,647,916 bytes**, SHA-256 `ea4a94ad6c48aa4866954d0702d45fce15e9fd02fa1f12cf2589499906d2d327`. Publication and the watch-page 2:34 duration were verified; YouTube's copyright and Community Guidelines checks reported no issues. [Publication status](publication-status.md) keeps source/site deployment and event submission separate.

The film pairs the reviewed animated browser captures with ElevenLabs' **Neha - Messy and Relatable**, speaking English in an Indian accent. The recorded September 20 AWS comparison uses real Lambda/SQS/DynamoDB infrastructure and simulated fulfillment. Its provider fails after committing a receipt, before returning success. The first failed attempt remains unresolved in its original evidence. At 00:34, the film explicitly changes to the actual recorded local Python tutorial: **order ID → SKU → order ID**, with **1/1 → 1/0 → 1/1 receipts** and unchanged inputs and faults. [AWS chronology](releases/2026-09-20.md#aws-evidence) and [local execution evidence](repair-lab/key-scope-tutorial/README.md) retain the full records.

## Chapters

| Start | What the viewer sees |
| --- | --- |
| 00:00 | A receipt survives failure on AWS |
| 00:16 | Keep failed experiments visible |
| 00:34 | Two valid orders, one dangerous key |
| 00:54 | Run the regression in Python |
| 01:08 | Change the key and inspect the missing order |
| 01:39 | Restore order ID and rerun |
| 02:00 | Three actual local executions |
| 02:13 | Export evidence and inspect result states |

These are the chapter timings prepared for this 154-second film; they do not inherit the previous upload's chapter or caption verification.

## Exact narration text

The generated narration uses this 314-word text, with acronym letters spaced for speech. The transcript preserves the supplied text; it is not a claim of word-perfect automatic transcription.

A receipt exists. The response fails. Then S Q S retries. Can the same order fulfill twice?

This is real A W S, with simulated fulfillment. The provider fails after committing the receipt, before returning success.

Our first run caught our own bug. The experiment stayed unresolved.

Different keys give us duplicates, a missing order, or one receipt each.

The receipt survives failure. The product key then rejects the other order.

Now look at the recorded local comparison. These are two distinct orders for the same product. Both need a receipt.

A product key mixes up those orders. We need a key that stays stable across retries, while keeping these two business orders distinct.

Take the regression kit into Python. This local fault interrupts after commit.

Let’s run the local adapter. With the order ID as the key, both orders get one receipt.

Now change only the key to S K U. Save that change, then run the exact same case again.

The retry no longer duplicates A, but B gets no receipt.

Import the actual result. Its original receipts and source evidence let us inspect exactly what happened.

B needed one receipt. We observed zero.

A's receipt survives the crash. Its retry reuses it. B stays rejected.

Now restore the order ID and save the adapter. Keep the same orders and the same fault.

Run it again. One receipt for A, and one for B.

Import the repaired report. Both valid orders have a matching receipt. This case passes.

Three real executions: a pass, a failure, then a pass. Only the key changed.

Keep the inputs, the fault, the assertions, and the original evidence together.

Export the original JSON evidence, and keep the runnable kit beside your handler.

Missing receipt data stays incomplete. Unknown isn't zero.

Unsupported effects stay unresolved. There's no pass.

ReplayGuard. Keep the failure. Test the repair. Follow the evidence.

## Production and verification scope

The narrated master passed **17 technical and edit checks**. It retains all **4,620 compressed video frames** of the 154-second silent master, adds 48 kHz AAC audio, and passes full decode. The final audio measured **−16.04 LUFS** and **−1.38 dBTP**. Narration remains at its generated speaking rate; only measured quiet gaps were shortened. Independent waveform inspection and transcription found no concrete cutting or scene-order blocker. Direct perceptual listening was unavailable, so naturalness and pronunciation were not certified.

The picture combines timestamped browser captures, genuine adapter edits/executions/imports, explanatory animation and documented reading holds. It is not a continuous native 30 fps screen recording or the real elapsed duration of the executions. The preserved [silent rendering source](../demo/silent-20260920/README.md), [14-check silent technical record](releases/2026-09-20-silent-video.json) and [28-sample visual review](releases/2026-09-20-silent-video-review.json) remain unchanged. Adding narration did not run another AWS experiment.

The [new publication record](publication/youtube-publication-v3.json) confirms the player reached the end without an error at 1920×1080 and anonymous oEmbed metadata resolved. It does not inherit the old upload's English captions or signed-out playback check. A passing declared case does not establish arbitrary payment/shipping safety or every possible retry schedule. Missing observations remain incomplete; unsupported effects remain unresolved.

## Preserved earlier versions

The [September 19 2:43 script snapshot](demo-script-v2.md) is retained byte-for-byte, with its original source hash, tutorial chronology and validation. Its [production evidence](repair-lab/media/revision-2/README.md) and [publication record](publication/youtube-publication-v2.json) describe that earlier film, not this upload. The [first walkthrough script](demo-script-v1.md) is also preserved. Retirement of an earlier YouTube upload is a separate publication action and does not remove its local evidence.
