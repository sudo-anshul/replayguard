# Final submission fields

Prepared September 19, 2026. **Not submitted.**

Form: https://www.wemakedevs.org/aws/first-commit/submit

## Project title

ReplayGuard — Keep the failure. Test the repair.

## Description

ReplayGuard turns a real AWS retry failure into a regression test you can keep.

A worker can fulfill an order, crash, and fulfill it again when SQS retries. But a repair using a product-level idempotency key can silently discard another customer's valid order. ReplayGuard checks the actual outcome: one correct fulfillment receipt for every business order.

We reproduced this failure using standard Amazon SQS, AWS Lambda and DynamoDB. A separate observer checked persisted receipts and CloudWatch evidence: the unsafe handler produced two receipts; the repaired handler produced one. The recorded AWS run passed 16 assertions.

The interactive lab compares three handlers on two orders for the same product: no key creates duplicates, a SKU key loses an order, and an order-ID key preserves both. Export a runnable Python regression kit containing inputs, fault conditions and assertions. Change the handler, rerun it, and import receipt evidence and source fingerprints to verify the repair. Missing evidence stays incomplete or unresolved.

The 2:43 demo shows an actual code edit, failing run and restored passing run. CloudFormation reproduces the AWS lab, with finite runs, low concurrency and short retention. The UI is live on AWS Amplify; regression execution runs locally, and the original AWS experiment is preserved as dated evidence. Fulfillment is simulated.

AI tools: OpenAI Codex for research, implementation, testing, UI and demo preparation; ElevenLabs for narration.

## Repository

https://github.com/sudo-anshul/replayguard

## Demo video

https://youtu.be/CGE19upS66A

## Live demo or deployment

https://prod.d2w687q4ucx6dk.amplifyapp.com/

## Readiness

- Public repository, live pages and regression ZIP checked anonymously on September 19 at approximately 16:03 IST.
- The 2:43 unlisted YouTube video played in a fresh signed-out Firefox private window; playback advanced through the recorded AWS evidence to 0:33. This check verifies access, not a fresh end-to-end audio review.
- Required student verification is user-reported. Each team member's WeMakeDevs registration/check-in and Builder Center/SheerID state still require account-owner confirmation.
- Hosted GitHub Actions did not start because of a billing block. Local tests passed; no hosted CI pass is claimed.
- Current official API cutoff remains September 20, 2026, **09:00 IST**. Use that earlier boundary; conflicting official deadline information remains unresolved.
