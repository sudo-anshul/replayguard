# Repair-bench demo — verified 2:43

The [YouTube demo](https://youtu.be/2ufAV4Ovat4) uses the companion `replayguard-repair-demo.mp4`, which is **163.064875 seconds (2:43)**. Video decoding and audio checks passed. It combines actual UI captures, recorded local command output, and narration; it is not a continuous live screen recording or a new AWS execution.

The sections below follow the final [spoken transcript](repair-lab/media/transcript.txt). Exact scene timing, source screenshots, and output measurements are recorded in the [render manifest](repair-lab/media/manifest.json) and [capture manifest](repair-lab/media/capture-manifest.json). The [live AWS lab](https://prod.d2w687q4ucx6dk.amplifyapp.com) serves the same static experience; local preview is [127.0.0.1:8088](http://127.0.0.1:8088).

## 0:00–0:21 — A real AWS failure, retained as evidence

**Shown:** The dated AWS experiment and its receipt comparison.

ReplayGuard began with a real Lambda and SQS failure on September eighteenth. A simulated fulfillment succeeded, then the worker crashed.

SQS delivered again. The independently queried DynamoDB ledger recorded two receipts for the vulnerable handler, and one for the repair. These are retained observations.

## 0:21–0:53 — A repair must preserve both orders

**Shown:** The new repair bench and its per-order comparison.

The portable local lab asks a harder question. Two valid orders share one product. Order A commits, loses its response, then retries among deliveries for order B.

Without a key, both orders have duplicate receipts. A product key looks safer, but suppresses order B. Zero receipts is also a failure.

The stable business order key leaves one receipt for each order. The comparison checks both duplicate prevention and valid order preservation.

## 0:53–1:19 — The adapter and effect boundary

**Shown:** The adapter guide and scope explanation.

A small adapter connects your handler to the injected receiver. The handler chooses its key. The receiver owns the atomic receipt contract, and the observer counts effects independently of the handler's return value.

A pass belongs to the observed case and receiver assumptions. It does not promise an external shipment, payment, or safety for arbitrary untrusted code.

## 1:19–1:56 — Execute, break, restore

**Shown:** [Actual command output](repair-lab/media/execution/final/transcript.txt) from the extracted kit: correct candidate, key removed, original source restored.

Here is recorded command output from a fresh kit extraction, with network access denied. The correct adapter produces one receipt and exits zero.

Change the candidate to use no key, and run the same case again. Two receipts appear. The assertion fails, and the process exits one. This is actual execution.

Restore the exact original source, and one receipt returns, with exit zero. The recorded source hashes identify the changed and restored bytes.

For a compact reference run from the extracted kit:

```sh
python3 -I -S scripts/test_repair.py \
  --candidate business-key --case crash-retry --output repaired.json
```

The recorded mutation sequence uses a copied adapter through `--adapter`. The [kit runbook](repair-lab/runbook.md) gives the exact copy/change/restore steps. Command output is retained as evidence; it is not replaced by expected text.

## 1:56–2:20 — A separate application

**Shown:** DispatchDesk and the independently authored five-scenario result.

DispatchDesk uses a different business event and a separate adapter. Its author froze five cases before reading the evaluator implementation. Both authors were AI agents; this is not customer validation.

All five reference cases pass. Removing the business key fails all five. A product-only key fails the two cases with distinct valid orders.

## 2:20–2:43 — Keep the failure, test the repair

**Shown:** The kit/import workflow and explicit incomplete/unsupported states.

Download the kit, run trusted Python locally, change your handler, and import the report. Inputs, fault conditions, assertions, source hashes, and receipt evidence travel together.

Missing observations remain incomplete. Unsupported guarantees remain unresolved. Keep the failure. Test the repair.

## Recording and publication status

The final MP4 is **4,979,581 bytes**, SHA-256 `582537a547ff08a1cfd1118a60b8784a07bfe7d854974aa3abd0a4e2bf580339`. Earlier AWS-only and iteration-04 walkthroughs remain unchanged historical material. The [public results](repair-lab/results.md) distinguish the dated AWS run from new local evidence.

The MP4 is a companion artifact outside this source repository. Publication resumed on September 19, 2026. The video is published **unlisted on YouTube** with English captions. It is under the event's three-minute limit and shows the dated AWS evidence. [Publication status](publication-status.md) records the verified upload link and current event submission state. The video itself remains the measured, unchanged artifact described above.
