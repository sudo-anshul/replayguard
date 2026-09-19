# What the AWS run taught us

The first deployment exposed a small-account constraint: the account's regional Lambda quota was 10. Reserved concurrency requires preserving AWS's unreserved pool, so reserving two slots was rejected. The deployment now detects that situation and keeps experiment concurrency bounded by the private SQS mapping's maximum of two workers.

The first actual experiment then failed before reaching the intended fault. Both 128 MB functions repeatedly timed out while starting the AWS SDK/fulfillment call (worker 6 seconds, provider 3 seconds). SQS did redeliver the exact messages, but there were no fulfillment receipts and no injected post-fulfillment failures. After three deliveries, both messages reached the DLQ. The observer correctly produced **unresolved**, not passed. Raw evidence is preserved in `evidence/initial-cold-start.json`; supplemental Lambda REPORT entries are in the initial timeout JSON files.

The lab now uses 512 MB functions, a 12-second worker timeout, a 6-second receiver timeout, and a 72-second visibility timeout (six times the worker timeout). SDK requests have bounded timeouts and automatic request retries are disabled; SQS owns the experiment's retries. These are practical execution settings, separate from the application repair: a stable idempotency key enforced at the receiver.

A separate AWS account restriction prevented creation of a new CloudFront distribution. An AWS Amplify hosting template was prepared instead, but no content deployment succeeded. The failed CloudFront stack and its empty retained bucket were removed; the later Amplify stack was also deleted. No live project URL, weakened account-wide security setting, or purchased support plan is claimed.

The final exported evidence and offline verifier, rather than these design intentions, determine whether the corrected real-AWS experiment passed. Public views distinguish recorded AWS observations from new executions. The downloadable bundle is self-contained so another developer can deploy and test the same case.
