# How this tutorial was made

The tutorial records genuine product interactions: inspect the retained AWS run, compare three candidate keys, download the kit, edit a real disposable adapter, execute the selected case, import the resulting JSON, restore the code, rerun, and inspect the repaired result. The locally hosted recording workbench writes the actual candidate file and invokes the public Python runner. It is a recording aid, separate from the published product viewer.

## Narration

The synthetic narration uses ElevenLabs' exact catalog voice **Neha - Messy and Relatable**, speaking English with an Indian accent. The generation settings were:

| Setting | Value |
| --- | --- |
| Model | Eleven Multilingual v2 |
| Speed | 0.86 |
| Stability | 0.45 |
| Similarity boost | 0.75 |
| Style | 0.15 |
| Speaker boost | Enabled |

The voice was selected from the provider's catalog, not cloned from a private recording. The source narration is 152.044263 seconds and contains the 309-word [spoken script](script.txt). Its original SHA-256 is retained in `provenance.json`. The [audio edit map](audio-edit-map.json) inserts four seconds at source time 84.75 and five seconds at 105.077, both within quiet gaps, plus a two-second tail. The resulting master audio is 163.044263 seconds; speaking speed and pitch were unchanged during this edit. Neither source nor audio-master duration should be reported as the final container duration without probing the video.

Captions were prepared using an existing local tiny Whisper model: independent ASR first, followed by alignment of the known script and measured pauses. No transcription API or new model download was used for that alignment. The automated pass detected no whole-sentence omission, but it is not a manual pronunciation certification. The included `narration.srt` is the post-edit master version, with the same silence-insertion map applied: 47 non-overlapping cues, at most two lines and 42 characters per line. Its final cue ends at 160.754 seconds. The audio master measured −16.11 LUFS integrated and −1.47 dBTP. The final encoded video measured **−16.12 LUFS and −1.40 dBTP**, with successful full audio/video decode. The caption ranges fit its 163.033333-second runtime, and nine sampled frames from the final encoded video passed independent visual review. The published watch page displayed the full English (India) transcript and the expected caption “One receipt. Pass.” at 1:21 when CC was enabled. Neither check claims complete manual timing validation or perceptual listening.

## Capture and composition

Browser frames were sampled through CUA during actual interaction at approximately **3–12 captured frames per second**. At handoff, per-clip mean rates span roughly 2.72–12.15 fps; exact rates, gaps, frame counts and source video hashes are in the source-capture catalog. Frames were converted into a **30 fps container by holding/repeating captured pixels according to their wall-clock timestamps**.

This is **not native 30 fps screen recording**. The composition adds deliberate cuts, restrained motion and explanatory overlays to real captures. It does not manufacture terminal output, receipt counts, report imports or source edits. A labeled conceptual fault sequence explains commit → response loss → retry; it is not AWS infrastructure footage. The final montage can trim source clips and hold a real recorded frame while a point is explained.

The source catalog lists all encoded clips retained at handoff, not a claim that every frame appears in the final montage. Original frame-path and local-user-path details are omitted from the public catalog; original metadata hashes and source-video hashes are retained. The private production originals were not altered for this export.

The final cut uses approximately **130.17 seconds of genuine captured footage**, about **79.84%** of the 163.033333-second film. The remaining time is explanatory motion or titles. Two short reading holds show genuine edited/restored source frames. The final mux preserves all H.264 video packets and encodes the exact mastered mono narration as AAC; only about 11 ms of the added closing silence is trimmed. [Technical validation](validation/final-video.json) records 19 passing checks, including the input fingerprints and full decode.

## Real execution provenance

The actual baseline, broken and repaired commands were recorded on September 19. Each selected `crash-retry`, used the public trusted-Python adapter, and wrote an independently observed receipt report. The macOS wrapper denied network during the child command; the Python harness also applied its local execution guard.

The evidence establishes **0 → 1 → 0 process exits** and **1 → 2 → 1 receipts**. The recorder saved source bytes before/after, original stdout/stderr and report hashes. Restoring the baseline restored the exact original candidate bytes. The read-only validator checked 73 integrity, source, execution, fault and receipt conditions; they are not 73 separate application scenarios.

Source fingerprints identify captured bytes. They do not authenticate an arbitrary report publisher or certify Python dependencies, the OS, or an external fulfillment provider. The current product browser checks report consistency; it does not execute Python or start cloud fault injection.

## AWS and application scope

The historical AWS use remains the September 18 Lambda/SQS/DynamoDB experiment. Its worker crashed after successful simulated fulfillment returned. It is shown as dated retained evidence. No new AWS failure experiment was run for this revision.

The new portable test has a different, explicit boundary: the simulated receiver commits a receipt, then the response is interrupted before it returns. The receipt is the simulated effect. External shipments, payments and emails need their own supported effect contract.

DispatchDesk is a separately authored synthetic application with five frozen cases. Both fixture and evaluator authors were AI agents working in this project. Its transfer results do not claim customer adoption, human validation or production deployment.

## Publication state

[The replacement video](https://youtu.be/CGE19upS66A) is published **unlisted**. YouTube Studio confirmed publication, saved English (India) captions, the custom thumbnail and the AI disclosure. Copyright and Community Guidelines checks completed with no issues. The signed-in watch page showed the correct title, Unlisted badge, AI label and 2:43 runtime; Studio rounds the runtime to 2:44. Playback advanced through both the AWS evidence and local code tutorial, all eight chapters were recognized, the full transcript and a caption were visible, and 1080p HD was available and selected. The description's live lab, repository and ElevenLabs links were verified.

The [independent review](validation/independent-review.json) inspected nine frames from the final MP4 and found no remaining concrete visibility blocker. It was a sampled review, without end-to-end motion or perceptual audio certification. Signed-out playback remains unverified. The superseded upload was permanently deleted after explicit user confirmation; its watch page states “Video unavailable” and “This video has been removed by the uploader.” Its local original master and historical evidence remain preserved. [Anonymous public metadata](../../../publication/youtube-public-metadata-v2.json) for the replacement returned HTTP 200 without credentials, which does not establish signed-out playback. Deployment of the revised site link remains pending.
