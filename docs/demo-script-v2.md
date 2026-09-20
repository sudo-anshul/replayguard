# ReplayGuard tutorial — current 2:43 demo

[Watch the revised demo](https://youtu.be/CGE19upS66A). The final `replayguard-demo-neha.mp4` is **163.033333 seconds**, 13,108,071 bytes, SHA-256 `f59eeaf60918c0be3b98cdbfae39db474bc3909604f463751ddd0274994c8621`. It is published unlisted. [Publication status](publication-status.md) records verified signed-in playback, captions, chapters and 1080p availability; signed-out playback remains unverified.

The [exact 309-word spoken script](repair-lab/media/revision-2/script.txt) and [post-edit English captions](repair-lab/media/revision-2/narration.srt) are public. Synthetic English narration uses ElevenLabs' **Neha - Messy and Relatable**, in an Indian accent. The video follows genuine browser interactions, actual adapter changes, Python execution and report imports, with deliberate reading holds and explanatory motion.

## Chapters

| Start | What the viewer sees |
| --- | --- |
| 00:00 | The missing-order hook and retained September 18 AWS evidence |
| 00:30 | Compare three fulfillment keys against the same valid orders |
| 00:57 | Understand the local commit/response fault and download the kit |
| 01:11 | Edit and run the real Python handler |
| 01:23 | Remove the key, rerun and inspect the failed report |
| 01:47 | Restore the business key and verify the repaired report |
| 01:59 | Test a separate synthetic worker |
| 02:18 | Export evidence and inspect incomplete/unresolved states |

The real tutorial's baseline, key-removed and restored executions produced **0 → 1 → 0 process exits** and **1 → 2 → 1 receipts**. Their reports, actual stdout, source snapshots and hashes are retained in [revision 2](repair-lab/media/revision-2/README.md). A read-only evidence check passed 73/73 conditions. The [portable workbench source](repair-lab/media/revision-2/recording/README.md) shows how the recording UI genuinely saves and executes that disposable adapter.

## What the footage establishes

The historical AWS worker crashed after simulated fulfillment returned success. The current portable test instead interrupts the response immediately after the receiver commits a receipt. The dated AWS evidence and new local execution remain separate. The synthetic DispatchDesk transfer has five frozen cases; it does not claim customer validation or adoption.

Browser frames were captured during real interaction at approximately 3–12 fps and composited into a 30 fps video. This is not native 30 fps screen recording. The [production notes](repair-lab/media/revision-2/PRODUCTION.md) describe the exact method, Neha settings, audio edit map and source hashes.

All [19 technical checks](repair-lab/media/revision-2/validation/final-video.json) passed, including full audio/video decode and final loudness. The [independent reviewer](repair-lab/media/revision-2/validation/independent-review.json) visually inspected nine frames extracted from the completed MP4. No remaining concrete evidence-visibility blocker was found. This is a sampled visual check, not a complete motion watch-through or perceptual listening certification.

## Preserved earlier version

The [previous walkthrough script](demo-script-v1.md) is retained byte-for-byte. Its original media manifests, transcript, command evidence, hashes and publication record remain preserved. The replacement upload has a new URL. The superseded YouTube upload was permanently deleted after explicit user confirmation, and its watch page confirms removal by the uploader. Its local original master and evidence remain preserved.
