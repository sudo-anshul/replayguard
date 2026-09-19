# First Commit submission fields

Updated September 20, 2026. **Prepared, not submitted.** Owner fields below remain incomplete.

Form: https://www.wemakedevs.org/aws/first-commit/submit

The official API configuration refreshed during the September 19 planning review was updated at `2026-09-19T16:04:09.889984Z`. It adds track selection, leader profiles, contributions and AWS feedback to the earlier project fields. Recheck the signed-in form before submitting; the older API snapshot in this repository does not contain these additions.

## Leader and team information — owner input required

| Field | Value / state |
| --- | --- |
| Leader's WeMakeDevs username | **MISSING — owner to provide the registered username.** |
| Leader's GitHub profile | **MISSING — owner to confirm the profile URL.** The project repository below does not establish the leader's identity. |
| Leader's LinkedIn profile | **MISSING — owner to provide the profile URL.** |
| Solo or team membership | **UNCONFIRMED — owner to confirm actual members.** AI tools are disclosed separately and are not team members. |
| Leader's contribution | **MISSING — owner to describe and confirm their actual work.** Do not attribute all generated implementation to the leader. |
| Other members' profiles and contributions | **PENDING IF APPLICABLE — provide the actual members and each person's work using the current form fields.** |
| Registration, check-in and student requirements | Student verification is user-reported; required account registration/check-in and each member's applicable Builder Center/SheerID state still require confirmation. |
| Resume link | Optional in the form; described as needed for fast-track interview consideration. Supply only if the owner chooses to share one. |

## Track selection

**Ship it.** The project used Lambda, standard SQS, DynamoDB and CloudWatch in the recorded AWS experiment, and its static interface is hosted on AWS Amplify. Select the matching checkbox in the current form. Do not also select `Built it` merely because the regression runner uses local Python.

## Project title

ReplayGuard — Keep the failure. Test the repair.

## What the project does and who it is for

ReplayGuard helps developers test whether a retry repair preserves every valid order.

A queued worker can fulfill an order, crash and fulfill it again on retry. Adding an idempotency key may stop duplicates but still reject another customer's valid order if the key identifies the product instead of the business order. ReplayGuard compares the actual fulfillment receipts for each expected order, including missing and incorrect effects.

The lab compares no key, a SKU key and an order-ID key. Developers can export a runnable Python regression kit, change an adapter, rerun the same inputs and fault conditions, and import the resulting evidence. The browser recomputes outcomes from observations; a handler's successful return is not receipt truth. Missing evidence stays incomplete and unsupported effects stay unresolved.

The September 20 local tutorial runs the same two-order case with an order-ID key, changes it to SKU, then restores the original source. Observed receipts are 1/1 → 1/0 → 1/1, with process exits 0 → 1 → 0. These are actual local executions from a clean kit extraction, with network access denied. Fulfillment is simulated. The pass covers the declared cases and a receiver that atomically owns its effect and key decision; it does not certify arbitrary payment or shipping APIs.

## How AWS was used

The project began with a real AWS failure experiment on September 18. Standard SQS delivered an order to a Lambda worker. A separate fulfillment Lambda wrote a durable receipt to DynamoDB; the worker then crashed after the successful response. SQS redelivered the message. An independent observer queried the receipt ledger and correlated CloudWatch events: the unsafe handler produced two receipts, the repaired handler one. That recorded run passed 16 recomputed assertions.

CloudFormation makes the original lab reproducible. Low concurrency, finite sends, bounded collection, short retention and explicit teardown keep the experiment small. The public interface is static AWS Amplify hosting; it does not execute Python or launch cloud faults. The current regression bench runs locally and also tests response interruption immediately after a simulated receipt commits. This local fault is distinct from the original AWS crash after a successful response.

The final September 20 three-candidate AWS run **passed 22/22 experiment checks with verified cleanup**. Across two valid orders, it observed no-key 2/2 receipts, SKU-key 1/0 with terminal rejection, and order-key 1/1. The two faulty candidates remain business violations; the order-key candidate passed for this declared run. The exact report and captured-source regression include the hardened verifier. Earlier attempts and their original sources/assertions remain preserved. This is our own engineering validation, not outside-user evidence. [Final result and chronology](releases/2026-09-20.md#aws-evidence).

## Positive AWS feedback

SQS redelivery, CloudWatch request/receive records and strongly consistent DynamoDB queries let us check the business effect independently of the worker. In the successful recorded run we could bind the original message, injected failure, retry and durable receipt rather than rely on a green Lambda response. CloudFormation made the lab and teardown reproducible. After an earlier hosting attempt failed, a later Amplify deployment served the static viewer successfully; anonymous checks matched the deployed assets to the release files.

## Negative AWS feedback / what could improve

Small-account limits were a practical obstacle. The tested region had a Lambda concurrency quota of 10, and reserving two slots was rejected because of the unreserved-pool requirement. We added a preflight fallback to the SQS mapping's two-worker limit. Our initial 128 MB functions and short timeouts also expired during SDK/fulfillment initialization before the intended fault could happen; larger memory, explicit request bounds and aligned worker/provider/visibility timeouts made the experiment usable. We would value a clearer deployment preflight that surfaces these quota and timeout relationships together. A separate account restriction blocked CloudFront distribution creation; a later Amplify deployment provided a workable static-hosting path.

These comments describe observed project experience and specific requested improvements, not a general AWS reliability benchmark. See [what we learned](what-we-learned.md).

## Repository

https://github.com/sudo-anshul/replayguard

## YouTube demo

https://youtu.be/CGE19upS66A

This is the **previously published September 19 video**, 2:43 (163.033333 seconds), unlisted. It shows the older interface, the original recorded AWS evidence and the local key-removal/restoration tutorial. It does not show the September 20 interface, the new order-ID → SKU → order-ID code execution or the final three-candidate AWS run. Signed-out playback was verified on September 19; this document does not claim a new playback check.

A new **silent local video is complete**: 154.000 seconds, 1920×1080 H.264/30 fps, zero audio streams. Full decode and 14 technical checks passed, with a 28-frame sampled visual review. [Exact metadata and production limits](releases/2026-09-20.md#media-and-publication). No new voice or YouTube upload occurred. The local video must not be described as published or supplied as though it were a YouTube URL. If the existing upload remains the submitted video, rely only on the capabilities it actually demonstrates in the judged pitch.

## Live demo or deployment

https://prod.d2w687q4ucx6dk.amplifyapp.com/

The accepted interface and three-candidate AWS viewer are **published in Amplify Deployment 4**. Anonymous HTTPS checks matched the root and all 37 staged assets. Live-browser checks confirmed the main/AWS navigation, expected results, control focus and 390-pixel layouts. [Deployment and verification records](releases/2026-09-20.md#deployed-website-verification). The current Git source revision still has its separate commit/export/publication gate; the new silent video is complete locally.

## AI disclosure

OpenAI Codex assisted with research, implementation, tests, interface design and demo preparation. ElevenLabs generated narration for the earlier published video. The current video revision is silent; no new voice generation is planned. The leader and any teammates must confirm their own contributions separately.

## Remaining submission checks

- Fill and confirm the leader/team fields; verify registration/check-in and applicable student requirements.
- Confirm the exact source release, deployed interface and selected video. Link the [new local tutorial evidence](repair-lab/key-scope-tutorial/README.md) without implying that the existing video shows it.
- Retain the completed final AWS report/archive and verified cleanup alongside both earlier attempts. Their exact published bytes passed Deployment 4's anonymous verification.
- Hosted GitHub Actions previously did not start because of a billing block. Local checks do not establish a hosted CI pass.
- No outside-developer trial has been recorded. [Trial protocol and status](first-user-trial.md).
- The [latest official API read](releases/2026-09-20-deadline.json) still gives September 20, 2026, **09:00 IST**. Target submission by 07:30 IST; conflicting official countdown information remains unresolved. See [earlier deadline evidence](deadline.md).
- Retain the actual successful submission screen/receipt. Prepared answers and an accessible form are not proof of submission.
