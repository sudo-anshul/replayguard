# What ReplayGuard taught us

Updated September 20, 2026. The AWS observations below distinguish the preserved September 18 experiment, September 19 hosting and the September 20 three-candidate attempts. The first attempt ended **unresolved**. The corrected second attempt and the final third attempt using the hardened verifier **passed with verified cleanup**.

## A repair must preserve the next valid order

The useful question is not only “did the retry duplicate an effect?” It is also “did every legitimate order get its correct effect?” A SKU key can eliminate duplicates while causing the receiver to reject a different order for the same product.

The [September 20 local tutorial](repair-lab/key-scope-tutorial/README.md) executed the same two-order case with an order-ID key, changed it to SKU, then restored the original source. Independent receipt counts were 1/1 → 1/0 → 1/1. This made the missing-order failure visible without trusting the worker's return value. These are simulated receiver effects under declared local faults, not a production fulfillment guarantee or a new AWS observation.

## The intended fault must actually happen

The first AWS attempt failed before reaching the intended post-fulfillment crash. Both 128 MB functions timed out during SDK/fulfillment initialization under their initial worker/provider timeouts of six/three seconds. SQS redelivered the messages, but there were no receipts and no injected post-fulfillment failures. After three deliveries, both messages reached the DLQ. The observer returned **unresolved**, not passed. [Raw initial evidence](../evidence/initial-cold-start.json) and the [validation record](validation.md#earlier-real-failure-retained) preserve the failure.

The successful original experiment used 512 MB functions, a 12-second worker timeout, a six-second receiver timeout and 72-second SQS visibility. SDK requests had bounded timeouts and automatic request retries were disabled so SQS drove the experiment's retries. Observed redelivery was approximately 71.8 seconds after the first receive. These settings made the experiment execute; they were separate from the business repair of enforcing a stable key at the receiver.

## A failure in our evidence path must not become a passing experiment

The first three-candidate AWS run, `85500aff-3d08-483e-9e63-78a9723eb67a`, exposed a defect in our provider's conflict logging. A receipt returned through boto3 contained DynamoDB `Decimal` values. Serializing that receipt into a JSON conflict event raised `TypeError` before the expected terminal rejection could be recorded. The SKU-key delivery for ORDER-B repeatedly failed and reached the DLQ.

The [final first-attempt record](../evidence/key-scope-20260920.json) remains **unresolved**, not passed. Although the receipt counts looked like the intended 2/2, 1/0 and 1/1 comparison, the SKU candidate remained **incomplete** because its terminal rejection evidence was missing; the nonempty DLQ made the overall experiment unresolved. Counts alone were insufficient. The [captured source and first-attempt archive](../web/aws-key-scope-attempt-1.zip) preserve the implementation that actually ran. This is a defect found during our own engineering experiment, not outside-user validation or a customer bug discovery.

Cleanup had a separate reporting defect: optional AWS error metadata was `None`, and the parser tried to call `.get()` on it. The original cleanup record therefore says unconfirmed. A [separate exact-stack-ARN follow-up](../evidence/key-scope-20260920-cleanup-followup.json) verified `DELETE_COMPLETE` at **2026-09-19 19:07:27 UTC**. That resolves operational cleanup only; the original record is unchanged and the business experiment remains unresolved. After tested Decimal normalization and optional-error handling fixes, the [second run](../evidence/key-scope-20260920-r2.json) passed with the expected 2/2, 1/0 and 1/1 receipts plus the required terminal evidence, and verified its own cleanup.

## Test the verifier with bad evidence

An independent audit then found two acceptance gaps in the AWS checker: deliberately altered reports without required source hashes or with contradictory terminal events could still pass. The targeted fixes now reject those cases, while independent rechecking confirmed that valid retries with distinct invocation IDs still pass. The SDK-free Python and JavaScript checks reported 144 and 112 passing tests at this checkpoint.

The second run's raw AWS observations still derive a pass under the stronger checker. Its stored assertions and [archive](../web/aws-key-scope-attempt-2.zip) retain their original verifier version. The [third fresh run](../evidence/key-scope-20260920-r3.json) then passed all 22 experiment checks with the hardened verifier captured alongside its observation and generated assertions. It observed no-key 2/2 receipts, SKU-key 1/0 with rejection evidence, and order-key 1/1. Cleanup was verified at **2026-09-19 19:36:17.789 UTC** without errors. No worker/provider behavior changed between the second and third attempts. [Release chronology and exact artifacts](releases/2026-09-20.md#aws-evidence). These are engineering checks inside this project, not outside-user validation.

## Small-account deployment needs a quota preflight

The tested region's Lambda concurrency quota was 10. Reserving two slots was rejected because AWS requires preserving the unreserved pool. The deployment added a fallback that kept the private SQS event-source mapping at a maximum of two workers. A mapping limit bounds that source; it is not an account-wide concurrency or spending cap.

Our negative AWS feedback is specific: surface the relationship between the account's concurrency quota and reserved-concurrency requirements before the stack fails. A combined preflight for worker/provider/visibility timeouts and cold initialization would also make small experimental deployments easier to diagnose. These are observations from this account and workload, not a claim that every small AWS deployment behaves the same way.

## Check receipts separately from worker status

CloudWatch let the observer correlate message IDs, receive counts, Lambda request IDs and the injected failure. Strongly consistent DynamoDB queries supplied durable receipt counts separately from the worker's success claim. In the [successful September 18 run](validation.md), the unsafe path had two receipts and the repaired path one; all 16 assertions recomputed from the recorded evidence passed.

This is the strongest positive AWS feedback: SQS redelivery plus independent ledger reads made the failure inspectable, while CloudFormation and explicit teardown made the small experiment reproducible. Queue counts remain approximate and finite observation does not rule out every future delivery. An absent observation must stay unknown rather than become an empty ledger.

## Hosting history is distinct from current hosting

During the original September 18 attempt, an account restriction prevented CloudFront distribution creation. An Amplify template was prepared, but that attempt did not publish content. The failed hosting resources and original lab stacks were subsequently removed. Those are historical outcomes.

Publication resumed on September 19. A later **AWS Amplify static deployment succeeded**, and anonymous HTTPS checks matched the root and all 24 staged assets. The latest accepted interface and AWS viewer were then published in **Deployment 4 on September 20 IST**; the root and all 37 staged assets matched their expected hashes. The [live lab](https://prod.d2w687q4ucx6dk.amplifyapp.com/) is current. [Deployment and verification evidence](releases/2026-09-20.md#deployed-website-verification) keeps both publication dates and their checks distinct.

The first check of Deployment 4 failed locally because its verifier lacked the needed trust-store configuration. That incomplete record remains retained. Repeating the check with the installed botocore CA bundle succeeded while certificate and hostname checks stayed enabled. Fixing a local trust-store configuration is different from disabling TLS validation; no TLS checks were disabled.

Amplify provided a workable static-hosting path after the earlier restriction. The hosted interface displays and validates evidence; it does not execute Python or launch AWS faults. Gross spending, short retention, expiry and verified deletion have different roles: credits and expiry do not replace cost observation or cleanup.

## What remains unproven

The current local receiver atomically owns the simulated receipt effect. The local harness interrupts a response after commit; the original AWS worker crashed after receiving a successful response. Neither result proves arbitrary external payment/shipping safety, actual process-restart behavior or exhaustive concurrent interleavings. DispatchDesk is a separate synthetic fixture, and [outside-developer validation has not been recorded](first-user-trial.md). These boundaries guide the next work rather than becoming success claims.
