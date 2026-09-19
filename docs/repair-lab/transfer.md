# Independent transfer: DispatchDesk

## Status

**Passed on the first independent execution:** all five reference cases passed;
both deliberate defects produced the expected material violations. The transfer
driver passed **44/44 checks** at **2026-09-19 03:58:15 UTC**, without evaluator
edits, fixture changes or a retry. Those 44 checks include artifact integrity and
execution checks; they are not 44 independent application scenarios.

After the core owner completed generic runtime hardening, a regression run
passed **45/45 checks**, adding before/after hashes of the bounded runtime
source files. That run is retained in
[`transfer-results/final-runtime/`](transfer-results/final-runtime/).
The current regression, after the numeric payload-equivalence fix, passed
**45/45 checks** at **2026-09-19 04:08:29 UTC**. It produced the same application
outcomes and preserved every frozen byte. These are reruns of already exposed
cases, not additional unseen holdouts. Current evidence is
[`transfer-results/final-numeric-runtime/summary.json`](transfer-results/final-numeric-runtime/summary.json).

The fixture and plans were frozen at **2026-09-19 03:50:08 UTC**, before
the independent fixture author read any repair-engine implementation or ran
an engine test. The author received only the public adapter and plan schemas.

The manifest is `tests/repair_holdout/freeze.json`, SHA-256:

```text
f9979ca9217a40f72c521ca901e7cf902966bc0134b5626fffb386b7359ae85d
```

It records hashes for the independently authored application, adapter, README,
five-case plan and mutation expectations. Run
`python3 tests/repair_holdout/verify_freeze.py` to check the retained bytes.

## The application boundary

DispatchDesk is a small stationery dispatch example with its own nested
`dispatch.ready.v1` business event. `examples/dispatchdesk/worker.py` receives
an injected fulfillment gateway; it has no ReplayGuard imports, stage names,
fault information, assertion labels or access to an evaluator receipt store.
Its stable business reference remains unchanged across transport retries.
Separate references may purchase the same product and quantity.

Only `examples/dispatchdesk/adapter.py` knows `build(effects)` and the public
delivery shape. It maps a delivery to the application's event, and maps the
application's normalized gateway call back to the public effect boundary. It
does not catch a committed-crash exception or suppress a payload conflict.

This establishes independence of authorship and application shape from the
engine implementation. Both authors are AI agents working in one project;
this is **not human developer validation, customer adoption or an external
production integration**. The app and its inputs are synthetic. The simulated
gateway's atomic-key contract is explicit; an external non-idempotent provider
is outside this evidence.

## Frozen scenarios and expected outcomes

`tests/repair_holdout/dispatchdesk-plan.json` declares five cases and 18
deliveries. Expected receipt counts are authored separately from candidate
returns:

| Case | Held-out condition | Required outcome |
|---|---|---|
| Response loss | Commit, crash before response, retry, then a new transport message for the same order | One receipt for the stable business reference |
| Interleaved orders | Crash after order A commits; order B shares its SKU; then repeat both | One receipt each; B must not be suppressed by an overbroad key |
| Distinct references | Two shops reuse the same human order-number suffix with identical product/shipping details | Two separate valid receipts, preserved across retries |
| Quantity conflict | Same reference changes quantity after success, followed by the original payload | Conflict surfaces; original receipt remains the only effect |
| Shipping conflict after crash | Destination changes after a committed crash, then exact original payload retries | Changed destination is rejected and original receipt reused |

`tests/repair_holdout/mutations.json` freezes two deliberate defects. Test runs
must copy the app/adapter to temporary directories, mutate only the copies,
and retain the pristine reference hashes:

- **No business key:** retries create additional receipts and conflicts are
  not rejected.
- **SKU-only key:** separate valid business orders sharing a SKU collide.

Passing the reference plus rejecting these two mutations is a bounded API
transfer result. It does not establish arbitrary application support or
production reliability. Evaluator failures must be reported to its owner;
the transfer author does not edit the evaluator to make the fixture pass.

## Execution evidence

The driver used fresh temporary copies for the reference and each mutation,
with no bytecode caches. It invoked the public CLI in isolated/no-site Python
mode and checked raw receipts independently of the report's headline status.
An import failure, timeout or arbitrary non-passing status could not earn
mutation-detection credit.

| Frozen case | Reference | No business key | SKU-only key |
|---|---|---|---|
| Response loss | Pass; one receipt | Violation; three receipts | Pass; one receipt |
| Interleaved orders | Pass; one receipt each | Violation; three for A, two for B | Violation; B has no receipt and its deliveries conflict |
| Distinct references | Pass; one receipt each | Violation; two receipts each | Violation; the second shop's valid order has no receipt |
| Quantity conflict | Pass; conflict surfaced, one original receipt | Violation; changed payload accepted, three receipts | Pass; conflict surfaced, one original receipt |
| Shipping conflict after crash | Pass; conflict surfaced, one original receipt | Violation; changed payload accepted, three receipts | Pass; conflict surfaced, one original receipt |

The SKU-only defect is the useful counterexample: it passes the simple
crash/retry case, yet prevents a second legitimate order from being fulfilled.
This demonstrates the value of checking both duplicate prevention and valid
order preservation for these inputs.

The first execution is retained under
[`transfer-results/first-execution/`](transfer-results/first-execution/):

- [`summary.json`](transfer-results/first-execution/summary.json): all 44 checks,
  invocation arguments, Python version, exit codes, source hashes and freeze
  integrity before/after.
- [`reference.json`](transfer-results/first-execution/reference.json): five
  passing application cases.
- [`no-business-key.json`](transfer-results/first-execution/no-business-key.json):
  five violations with independently recorded duplicate effects.
- [`sku-only-key.json`](transfer-results/first-execution/sku-only-key.json): two
  violations and three passing single-order cases.

The frozen original plan SHA-256 is
`5dd459a726de3d74926a7e1bbcb5c16937822d9fd1f108ebced7fa55acbef8d5`.
The first runner entrypoint (`scripts/test_repair.py`) SHA-256 was
`a83fda10ae59a1d93fd2cc3d11fb578915ca460a1feebd67ee750d812d11cc3b`.
The candidate snapshot includes `adapter.py`, `worker.py` and `__init__.py`,
and its reported hashes matched the actual copied bytes. That is a bounded
source snapshot, not an attestation of arbitrary dependencies or the entire
Python environment.

The final runtime report additionally records hashes of the entry script,
`repair_lab` Python files and imported `local_lab/guard.py` before and after
execution. They matched. The Python interpreter and standard library remain
outside that source-hash scope. Current per-candidate reports are
[`reference.json`](transfer-results/final-numeric-runtime/reference.json),
[`no-business-key.json`](transfer-results/final-numeric-runtime/no-business-key.json),
and [`sku-only-key.json`](transfer-results/final-numeric-runtime/sku-only-key.json).

After the input plan was frozen, the public report vocabulary was finalized
(`id` → `deliveryId`, `after-commit-before-response` → `after-commit`,
`atomic-receipt` → `receiver-owned-receipt`, `complete` → `independent-ledger`).
The parser accepted the original draft aliases generically. The test driver
verified the canonical report preserves every frozen case's semantics. No
application source, plan condition or mutation expectation was changed.

To reproduce the full transfer check with a new evidence directory:

```sh
python3 tests/repair_holdout/run_transfer.py --output-dir /tmp/dispatchdesk-transfer-new
```

To run only the reference through the public API:

```sh
python3 -I -S scripts/test_repair.py \
  --adapter examples/dispatchdesk/adapter.py \
  --case-file tests/repair_holdout/dispatchdesk-plan.json \
  --output /tmp/dispatchdesk-reference.json
```

## Separate browser verification

The first browser import test used the actual reference and no-key reports.
It passed 18/20 checks, with no remote request or JavaScript page error. It
found two issues sent to the UI owner: an unconfigured fault marked as
injected was accepted, and the imported report overflowed a 390-pixel page.
Other tested contradictions were rejected and preserved the prior comparison
and exact original downloaded bytes. See
[`import-tampering-results/first-execution/results.json`](import-tampering-results/first-execution/results.json).
These browser findings are separate from the passing application transfer;
the first run remains retained. After the UI owner fixed the fault-consistency
check and narrow layout, the same suite passed **20/20**, with all four UI
source files unchanged during the test, no remote request/page error, and a
390-pixel document at a 390-pixel viewport. See
[`import-tampering-results/after-ui-fixes/results.json`](import-tampering-results/after-ui-fixes/results.json).
No tampering-test expectation was changed to obtain that pass.

After the repaired comparison became the main `index.html` route and numeric
attribute validation was finalized, the required main-route rerun again passed
**20/20**. All five checked UI source files stayed unchanged during the test;
there were no remote requests or page errors. Rejected reports preserved the
previous comparison and exact imported bytes. A syntactically valid altered
source hash was correctly accepted as an **unauthenticated claim**, with that
limitation displayed: the browser validates report consistency, not publisher
identity or actual source execution. Current evidence is
[`import-tampering-results/final-main/results.json`](import-tampering-results/final-main/results.json).

Nine untouched runtime edge reports also passed **9/9** browser import checks,
preserving their actual verdicts and original downloadable bytes without
390-pixel overflow, remote requests or page errors. These cover wrong payloads,
repeated reuse, a manual crash on conflict, call exhaustion, timeout, a caught
protocol error, wide/empty-description values, numeric equivalence and the
distinction between numbers and booleans. See
[`native-browser-results/final/results.json`](native-browser-results/final/results.json).
The runtime owner authored these edge cases; their import verification is
separate from the independently frozen DispatchDesk transfer.

The retained AWS/reference journey at `recorded-lab.html` passed **14/14**
preservation checks, including historical evidence/download bytes, rejected
import rollback and narrow layouts. This was a loopback browser check, not a
new AWS execution. See
[`legacy-preservation/browser-reference-results.json`](legacy-preservation/browser-reference-results.json).

Current desktop/narrow views and comparison, adapter, incomplete, transfer and
historical AWS views are captured in [`media/`](media/). Their
[`capture-manifest.json`](media/capture-manifest.json) records routes, source
hashes, dimensions and crop provenance. These are actual rendered product
states; no displayed DOM content was replaced for the captures.
