# First Commit submission package

Updated September 20, 2026. **Prepared, not submitted.**

Project title: **ReplayGuard — Keep the failure. Test the repair.**

[Current form answers and missing owner fields](submission-form.md). Intended track: **Ship it**. The official form configuration changed on September 19; the draft now includes the required leader profiles, track, contributions and positive/negative AWS feedback.

## Short writeup

ReplayGuard helps developers test whether a retry repair preserves one correct fulfillment receipt for every valid business order under declared faults.

A worker can fulfill an order, crash and fulfill it again on retry. A hasty repair can introduce another failure: using a SKU as the idempotency key stops duplicates but rejects another valid order for the same product. The order-and-receipts comparison makes both failures visible. In the recorded local interleaved case, no key produces two receipts per order, a SKU key leaves the second order without a receipt, and the business-order key preserves one receipt for each order.

The project began with a real AWS experiment on September 18. Standard SQS redelivered a message after a Lambda worker crashed following a successful fulfillment response. A separate fulfillment Lambda persisted receipts in DynamoDB; an independent observer queried the ledger and correlated CloudWatch evidence. The unsafe path produced two receipts and the repaired path one; the recorded run passed 16 recomputed assertions. CloudFormation, finite sends, low concurrency, short retention and explicit cleanup made the experiment reproducible and bounded.

The final September 20 AWS comparison extends that proof to two valid orders and all three key choices. It passed **22/22 experiment checks**, observing no-key 2/2 receipts, SKU-key 1/0 with terminal rejection, and order-key 1/1. The first two candidates are business violations; the order-key candidate passed for the declared run. The [final evidence and captured-source regression](releases/2026-09-20.md#aws-evidence) bind this observation to the hardened verifier. Stack deletion was verified without cleanup errors. Earlier attempts, including an unresolved provider-logging failure, remain preserved rather than rewritten.

The repair bench turns that lesson into a runnable local regression workflow. A trusted Python adapter connects application code to a receiver-owned effect contract. The harness supplies inputs and bounded deliveries, interrupts the response immediately after a simulated receipt commits, and checks the receipts independently of handler returns. The portable kit contains executable source, fault conditions and assertions. Reports retain observations and captured source fingerprints; the browser recomputes states from those observations.

On September 20, a clean extraction of the kit executed the stronger repair counterexample using the same inputs and faults throughout: order-ID key → SKU key → restored original source. Receipts were **1/1 → 1/0 → 1/1**, and actual process exits were **0 → 1 → 0**. ORDER-B's payload conflict explains its missing receipt. [Execution records, source snapshots and reports](repair-lab/key-scope-tutorial/README.md) are retained. This is local execution with network access denied, not a new AWS run.

DispatchDesk provides a separate synthetic application and five frozen scenarios. Its reference repair passed all five; removing its key caused duplicate effects, while a SKU-only mutation suppressed valid orders in two multi-order cases. A separate AI agent in this project authored the application and cases. This supports transfer within the stated adapter contract; it is not outside-developer validation, customer adoption or an organically discovered customer defect.

The main lesson was that eliminating duplicates is only half of the repair: every valid order must survive, and the effect must be observed independently. The first AWS attempt also taught us to distinguish an intended post-fulfillment crash from a cold-start timeout that never fulfilled anything. [What we learned](what-we-learned.md) records the observed quota, timeout, visibility and hosting constraints.

The receipt is the complete simulated fulfillment effect. A pass covers declared supported cases with a receiver that atomically owns the effect and its key decision. The project does not establish exactly-once SQS delivery, arbitrary third-party payment/shipping safety, process-restart coverage or all possible interleavings. Missing observation remains incomplete; unsupported contracts remain unresolved. Source hashes identify captured bytes, not authenticated report origin.

AI disclosure: **OpenAI Codex** assisted with research, implementation, testing, UI and demo preparation. **ElevenLabs** generated Neha's English narration for the current 2:34 demo. Leader/team contribution statements remain for their owners to confirm.

## Delivery and evidence status

| Item | Confirmed state / remaining gate |
| --- | --- |
| Public repository | **Published** at [`0d0ec11ef4e3ba30ad03f2bd623f4e116d7ce664`](https://github.com/sudo-anshul/replayguard/commit/0d0ec11ef4e3ba30ad03f2bd623f4e116d7ce664). [Anonymous pinned-file checks](releases/2026-09-20-github-public.json) passed; [network-denied source validation](releases/2026-09-20-source-validation.json) passed 149 Python tests, 112 JavaScript tests, 45 transfer checks and 19 release checks with identical re-export. The ZIP is a local companion; later docs-only updates are separate from the tested source. |
| Live AWS URL | [AWS Amplify static lab](https://prod.d2w687q4ucx6dk.amplifyapp.com). **Deployment 4 published the accepted interface and AWS comparison**; anonymous checks matched the root and all 37 staged assets, followed by scoped live-browser checks. [Verification](releases/2026-09-20.md#deployed-website-verification). Static hosting does not execute regressions or expose a cloud fault endpoint. |
| Original AWS evidence | **Passed, dated September 18.** Two unsafe receipts versus one repaired receipt, 16 recomputed assertions. The original stacks were subsequently deleted; that cleanup does not describe a new stack. |
| New three-candidate AWS experiment | Final third run **passed 22/22 experiment checks with verified cleanup**, observing 2/2 violation, 1/0 violation and 1/1 passed. Exact report and captured hardened verifier/archive retained. First two attempts remain unchanged. [Chronology and artifacts](releases/2026-09-20.md#aws-evidence). |
| New local repair tutorial | **Passed.** A clean kit extraction executed order-ID → SKU → restored source, with 1/1 → 1/0 → 1/1 receipts. [Evidence](repair-lab/key-scope-tutorial/README.md). |
| Current YouTube demo | [September 20 narrated video](https://youtu.be/coCDLSyU8AY), **unlisted, 2:34 (154.000 seconds)**. Publication and the watch-page duration were verified; copyright and Community Guidelines checks reported no issues. It shows the recorded AWS comparison and actual local order-ID → SKU → order-ID tutorial. [Script and verification scope](demo-script.md). The previous upload's captions, quality and signed-out checks do not establish those states for this new upload. |
| Preserved silent master | **Completed local artifact**, 154.000 seconds, 1920×1080 H.264/30 fps with zero audio streams. Full decode and 14 technical checks passed; 28 sampled encoded frames reviewed. [Metadata and limits](releases/2026-09-20.md#media-and-publication). Its picture is retained unchanged in the current narrated film; the silent source record remains historical. |
| Outside-developer validation | **Not obtained.** [Trial protocol and status](first-user-trial.md); no outreach or participant outcome is claimed. |
| Hosted CI | **Incomplete: did not start.** [Run 35466519733 at the published source commit](releases/2026-09-20-github-ci.json) executed no steps because of the account billing block. This is not a test failure; recorded local checks are separate. |
| Event submission | **Not submitted.** Required owner fields and actual submission confirmation remain outstanding. |

## Video and submission boundary

The rules require a public repository, a short writeup, and a public or unlisted **YouTube video under three minutes showing AWS use**. Ship it requires a live AWS deployment URL. The selected [2:34 narrated YouTube film](https://youtu.be/coCDLSyU8AY) is published unlisted and replaces the earlier selected demo. It presents recorded AWS evidence and explicitly changes to the actual local tutorial at 00:34. The [current form draft](submission-form.md) uses this new URL. Publication of the film does not establish event submission.

Confirm the leader's registered WeMakeDevs username, GitHub and LinkedIn profiles, actual contribution, team membership and any member contributions. Student verification is user-reported; applicable Builder Center/SheerID, registration and First Commit check-in still require account-owner confirmation. Resume sharing is an optional owner decision, with separate fast-track interview requirements. No personal profile or contribution has been invented to fill the form.

## Deadline and spending boundary

The current official submission cutoff is **September 20, 2026, 20:00 IST (14:30 UTC)**. The [fresh API read at 2026-09-20 07:05:26 UTC](publication/deadline-current-20260920.json) returned `end_date: "2026-09-20T14:30:00Z"`, with configuration updated at `2026-09-20T04:57:05.393246Z`. Submit before this cutoff. It supersedes the earlier 09:00 IST boundary and 07:30 target; the [prior API snapshot](releases/2026-09-20-deadline.json) and [deadline history](deadline.md) remain preserved as historical evidence.

AWS work remains bounded by a **US$25 cumulative gross project ceiling with US$5 reserved**. Confirmed headroom is required before further billable work. Credits, expiry and alerts are not hard spending caps. Historical spending observations are dated, not current billing readings. [Publication record](publication-status.md) and [operating limits](repair-lab/results.md#aws-evidence-and-present-limits).

## Supporting artifacts

- [Actual order-ID → SKU → order-ID tutorial](repair-lab/key-scope-tutorial/README.md).
- [Repair results and synthetic transfer](repair-lab/results.md).
- [Portable regression kit](../web/replayguard-repair-lab.zip) and [runbook](repair-lab/runbook.md).
- [Final three-candidate AWS report](../web/aws-key-scope-report.json), [captured-source regression](../web/aws-key-scope-regression.zip) and [dated attempt chronology](releases/2026-09-20.md#aws-evidence).
- [Original AWS viewer](../web/aws-run.html), [September 18 validation](validation.md) and [unchanged original AWS archive](../web/regression-case.zip).
- [Adapter contract](repair-lab/adapter.md), [report schema](repair-lab/schema.md) and [learning/feedback](what-we-learned.md).
- [Current video script and verification scope](demo-script.md), [historical September 19 script](demo-script-v2.md) and [that earlier upload's signed-out check](publication/youtube-signed-out-v2.json).
