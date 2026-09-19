# First Commit submission package

Project title: **ReplayGuard — a retry repair should protect every order**

Intended track: **Ship It**. Publication and AWS hosting resumed on September 19, 2026. The confirmed live URL and YouTube link are recorded below as they are verified; no event submission is claimed until confirmed.

## Short writeup

A queued worker can fulfill an order, crash, and fulfill it again on retry. A hasty repair can introduce another bug: using a SKU as the idempotency key stops duplicates but rejects a different valid order for the same product.

ReplayGuard tests both sides of the repair: one correct fulfillment receipt for every valid business order. Its order-and-receipts comparison shows the counterexample directly. Across two interleaved orders, no key produces two receipts each; a SKU key produces one receipt and leaves the second order unfulfilled; the business-order key produces one receipt each.

The project began with a real AWS failure loop. On September 18, standard SQS redelivered messages after a Lambda worker crashed following successful simulated fulfillment. A separate fulfillment Lambda persisted receipts in DynamoDB; an independent observer queried the ledger and correlated CloudWatch evidence. The vulnerable handler produced two receipts, the repaired handler one, and the recorded run satisfied 16 assertions. CloudFormation made deployment and cleanup reproducible; the lab used no VPC or NAT gateway, low concurrency, short retention, and finite runs.

The new repair bench turns that lesson into an executable local regression workflow. A trusted Python adapter connects application code to a receiver-owned effect contract. The harness supplies bounded deliveries, injects failure after receipt commit and before the response, and checks receipts independently of handler returns. The portable kit contains runnable code, inputs, fault conditions, and assertions; execution exports receipt evidence and captured source fingerprints. The browser compares candidates and recomputes imported report states from their observations.

An independently authored synthetic application and five scenarios were frozen before the first run. Its correct repair passed all five; removing the key caused duplicate effects, while the SKU-only mutation suppressed valid orders in two multi-order cases. This is application-transfer evidence, not customer validation. The contribution is a focused workflow for detecting both duplicate fulfillment and an overbroad repair, with a regression case developers can run against changed code.

The receipt is the complete simulated fulfillment effect. The project does not claim exactly-once SQS delivery, protection for arbitrary third-party APIs, or exhaustive interleaving coverage. The current bench runs locally. The dated AWS evidence, original infrastructure cleanup, and current delivery status remain explicit.

AI disclosure: **OpenAI Codex** assisted with research, implementation, tests, UI, and demo preparation.

## Submission fields and current status

| Field | Status |
| --- | --- |
| Repository | [sudo-anshul/replayguard](https://github.com/sudo-anshul/replayguard): audited public source with a fresh history recording actual publication time. |
| Live AWS URL | [Live AWS Amplify lab](https://prod.d2w687q4ucx6dk.amplifyapp.com). New static hosting; the original failure experiment remains recorded evidence. |
| Demo | [Revised YouTube demo](https://youtu.be/CGE19upS66A), confirmed **unlisted**. The source video is **2:43 (163.033333 seconds)**, under three minutes; the watch player shows 2:43 and Studio rounds to 2:44. Signed-in playback, all eight chapters, the English (India) transcript, enabled captions and 1080p availability were verified. Signed-out playback remains unverified. |
| Event submission | **Not submitted.** The [official form](https://www.wemakedevs.org/aws/first-commit/submit) has not been used to publish this entry. |
| Eligibility | The user reports verified student status. Required Builder Center/SheerID verification, individual registration, and First Commit check-in were not independently verified in this work. |

The rules require a **public repository**, short writeup, and a **public or unlisted YouTube video under three minutes showing AWS use**. Ship It also requires a live AWS deployment URL. A local MP4 and loopback preview do not satisfy those publication requirements. [Official requirement evidence](deadline.md).

## Deadline and spending boundary

Use **September 20, 2026, 09:00 IST (03:30 UTC)** as the earliest observed official cutoff and finish before it. The submission form uses that API timestamp; the event countdown points to 20:00 IST. The exact organizer-approved cutoff remains **unresolved** because official sources conflict. No organizer confirmation or later deadline assumption is claimed.

A [read-only refresh on September 19 at 04:12 UTC](deadline-refresh-20260919.json) confirmed that the API still returns `2026-09-20T03:30:00Z`. The refreshed overview response did not expose an end time, so it does not resolve the earlier discrepancy.

Publication, video upload, and completion of the entry are authorized. AWS work is bounded by a **US$25 cumulative gross project ceiling with US$5 reserved**. Confirmed gross-spend headroom is required before further billable work; credits alone do not establish that headroom. See [publication status](publication-status.md) and [public operating limits](repair-lab/results.md#aws-evidence-and-present-limits).

## Evidence for the entry

- [Repair outcomes and validation](repair-lab/results.md), including the two-order counterexample and independent five-scenario transfer.
- [Portable regression kit](../web/replayguard-repair-lab.zip) and its [clean extraction validation](repair-lab/validation/README.md).
- [Recorded AWS run](../web/aws-run.html) and [September 18 AWS validation](validation.md), shown with their dates and provenance.
- [Adapter API](repair-lab/adapter.md), [report schema](repair-lab/schema.md), and the new [order comparison](../web/index.html).
