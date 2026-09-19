# ReplayGuard demo revision 2

This media handoff contains the actual local failure-and-repair executions used in the new narrated tutorial. The baseline passed with one receipt, removing the key produced two receipts and a violation, and restoring the original adapter bytes restored one receipt and a pass. A read-only validation of the retained evidence passed **73/73 checks**.

The final master is **2:43 (163.033333 seconds)**, 1920×1080 H.264 at 30 container fps with AAC 48 kHz mono narration. All **19 technical checks passed**, including full decode, under-three-minute duration, unchanged rendered video packets and final audio level. The MP4 is 13,108,071 bytes, SHA-256 `f59eeaf60918c0be3b98cdbfae39db474bc3909604f463751ddd0274994c8621`.

[Watch the replacement on YouTube](https://youtu.be/CGE19upS66A), published **unlisted**. Signed-in playback advanced through the AWS evidence and local code tutorial; all eight chapters, the English (India) transcript and an enabled caption were verified on the watch page. 1080p HD was available and selected. A custom thumbnail was uploaded. Nine sampled frames from the final MP4 passed independent visual review. Signed-out playback, deletion of the superseded upload and deployment of the revised site link remain unverified or pending. See [`provenance.json`](provenance.json) for explicit verification states. The original Neha narration (152.044263 seconds) and edited audio master (163.044263 seconds) remain distinct from the final video container duration.

| Recorded stage | Actual process exit | Independent receipts | Result |
| --- | --- | --- | --- |
| [Baseline](execution/baseline/report.json) | 0 | 1 | Passed |
| [Key removed](execution/broken/report.json) | 1 | 2 | Violation |
| [Original source restored](execution/repaired/report.json) | 0 | 1 | Passed |

Each execution folder contains the unchanged generated report, raw stdout/stderr, adapter snapshots before and after the command, and the original execution record. Original evidence bytes were copied without alteration; SHA-256 values are included in the provenance. Source restoration and identical case inputs/faults are among the validation checks. These are three real recorded executions, not fabricated output or simulated typing.

The five-line adapter is a small copy of the public contract, with the reference docstring and blank lines omitted. Its actual source hashes are captured; it is not mislabeled with the reference file's hash. The public regression archive used for the recording has SHA-256 `e01bdcaef59a813f56c96a4ba9e10c25175d41dd33c56d7e9b29b5b29d9d2555`.

- [Final spoken script](script.txt)
- [Post-edit English captions](narration.srt) and [caption structure validation](validation/captions.json)
- [Production method and narration settings](PRODUCTION.md)
- [Sanitized source-capture catalog](capture-provenance.json)
- [Execution validation](validation/summary.json)
- [Final video technical validation](validation/final-video.json) and [video-preserving audio mux](validation/final-mux.json)
- [Portable recording workbench source](recording/README.md)
- [Thumbnail](youtube-thumbnail.png), [data provenance](youtube-thumbnail.json) and [reproduction source](create_youtube_thumbnail.py)

The included captions are the final **post-hold** SRT, copied byte-for-byte from the final output companion. They follow the audio's four-second and five-second action holds. All 47 cues are non-overlapping and the last cue ends at 160.754 seconds, within the final video. Nine sampled final frames passed [independent visual review](validation/independent-review.json). The watch page displayed the full English (India) transcript, and enabling CC showed “One receipt. Pass.” at 1:21. This does not claim a complete motion watch-through or perceptual listening review.

The September 18 AWS experiment is retained separately in the [AWS evidence viewer](../../../../web/aws-run.html). In that experiment the worker crashed after simulated fulfillment returned success. These new local executions interrupt the response immediately after the receiver commits a receipt. They do not run a new AWS experiment or establish an external shipment/payment guarantee.
