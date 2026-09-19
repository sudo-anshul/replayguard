# Publication status

Updated September 19, 2026. The user resumed the remaining delivery work, including public source, AWS hosting, the demo upload and entry preparation. The previous local-only stop and zero-new-spend constraint have been superseded.

| Deliverable | Confirmed state |
| --- | --- |
| Public source | [sudo-anshul/replayguard](https://github.com/sudo-anshul/replayguard). The audited public source starts with a fresh commit dated when it was actually created. |
| Live AWS URL | [AWS Amplify static lab](https://prod.d2w687q4ucx6dk.amplifyapp.com). **Deployment 3 succeeded** via the Amplify console. [Anonymous HTTPS verification](publication/hosting-video-update/anonymous-https-video-update.json) passed for the root and all 24 exact staged assets; the main pages point to the replacement demo. [Deployment 2 verification](publication/hosting-final/anonymous-https-final.json) remains preserved. |
| YouTube demo | [Revised YouTube demo](https://youtu.be/CGE19upS66A), confirmed **unlisted**. The uploaded source MP4 is 2:43 (163.033333 seconds); the watch player shows 2:43 and Studio rounds to 2:44. Signed-in playback advanced through AWS and local-code scenes. All eight chapters, English (India) transcript/captions and 1080p availability were verified; a custom thumbnail was uploaded. Signed-out playback remains unverified. |
| Hosted CI | **Incomplete: not started.** GitHub blocked the runner before any step; this is not a test failure or a passing CI run. Local checks passed. See the exact observation below. |
| Event entry | Not yet confirmed submitted. See [submission package](submission.md). |

The public tree begins from an explicitly allowlisted local source snapshot, without private development Git history, account configuration, or private research. Recorded AWS evidence and historical test artifacts retain their original dates. The Git author timestamp is not backdated.

AWS work is authorized within a **US$25 cumulative gross project ceiling, with US$5 kept in reserve**. Confirmed gross-spend headroom is required before new billable work. Credits and student eligibility do not remove that accounting requirement. The release gate observed about **$0.23 gross for September 17–18** before credits/refunds, with current-day and billing-lag uncertainty. Allowing **$2 for prior lag and $2 for static hosting** gives about **$4.23 conservative exposure**, below the $20 working envelope. This is an operating budget, not an AWS-enforced hard billing cap. The browser comparison and local repair runner do not call AWS.

The original `replayguard-lab` and `replayguard-hosting` stacks reached `DELETE_COMPLETE` at **2026-09-18 19:13:43 UTC**. The original Amplify attempt did not publish content. Those facts describe the original attempt. The new deployment is **static hosting only**, not a new AWS failure experiment or a public execution endpoint.

Use **September 20, 2026, 09:00 IST (03:30 UTC)** as the earliest observed official cutoff. Exact organizer-approved cutoff remains unresolved because official sources conflict; see [deadline evidence](deadline.md).

## Verification status

The [first public commit](https://github.com/sudo-anshul/replayguard/commit/480a7333954ea3532d9ec3d24cdc4154d212836a) was created at **2026-09-19 05:00:06 UTC**, with no parent commits. GitHub verified the repository is public, its default branch is `main`, and its license is MIT.

[GitHub run 35422824471](https://github.com/sudo-anshul/replayguard/actions/runs/35422824471) did not execute any steps. Its exact annotation was:

> The job was not started because your account is locked due to a billing issue.

The workflow remains available. No account or billing changes were made to force a run. Locally, **33 repair/export tests, 4 source-export tests, 95 JavaScript contract tests and 45 independent-transfer checks passed**. The selected repair exited 0; the full comparison correctly exited 3 for its explicit unresolved control. Those observations are [recorded separately](publication/github-ci-initial.json) and do not substitute for a hosted CI pass.

The [final live-browser review](publication/browser-review.json) passed at verified widths of **1280, 390 and 320 pixels**, including the order counterexample, JSON dialog, incomplete/unresolved states, independent transfer report and final resource links.

The [static video-link update](publication/hosting-video-update/hosting-deployment-video-update.json) was deployed through the existing Amplify console as Deployment 3. The UI displayed “Deployed” and “Deployment SUCCEED,” with a seven-second duration. The uploaded ZIP was 250,304 bytes, SHA-256 `05dce5e449355d0bf7ce5240a179c3b0b03008fefd7834987330345c0cb6cd54`. Independent anonymous HTTPS checks matched every staged asset and verified the replacement demo links on the root, `index.html` and `repair.html`. The deployed root page’s footer link was also confirmed in the browser. This is console UI evidence and public byte verification; no new AWS fault run is claimed.

The [revised video publication record](publication/youtube-publication-v2.json) confirms YouTube Studio's **Video published** state with **Unlisted** visibility, saved English (India) captions and a custom thumbnail. Copyright and Community Guidelines checks completed with no issues. AI use was disclosed; paid promotion was set to No. The signed-in watch page showed the correct title, Unlisted badge, AI label and 2:43 player. Playback advanced through the AWS evidence and local code tutorial, all eight chapters were recognized, and the description's live lab, repository and ElevenLabs links were verified. The full English (India) transcript was visible; enabling CC showed “One receipt. Pass.” at 1:21. 1080p HD was available and selected. Signed-out playback remains unverified. The superseded upload was permanently deleted after explicit user confirmation; its watch page now states “Video unavailable” and “This video has been removed by the uploader.” Its local original master, media evidence and [original publication record](publication/youtube-publication.json) are preserved. [Anonymous public metadata retrieval](publication/youtube-public-metadata-v2.json) for the replacement returned HTTP 200 without credentials; this does not establish signed-out playback.

The revised master passed [19 technical checks](repair-lab/media/revision-2/validation/final-video.json), including full decode and audio levels. An [independent review](repair-lab/media/revision-2/validation/independent-review.json) inspected nine frames from the final encoded MP4 and found no remaining concrete blocker. That sampled review does not claim an end-to-end motion check or perceptual audio listening. Its actual tutorial evidence passed 73/73 checks, with process exits 0 → 1 → 0 and independent receipts 1 → 2 → 1.
