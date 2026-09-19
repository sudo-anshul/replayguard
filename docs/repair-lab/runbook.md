# ReplayGuard repair lab

Run a trusted Python candidate against bounded delivery schedules, inspect the
independent simulated receipts, and retain the counterexample when a repair
fails. **Python 3.11+ on macOS or Linux/POSIX is required.** Windows is unsupported
because bounded execution uses POSIX timers. No install, third-party package,
AWS credential, network connection, or paid service is needed.

Start in this extracted archive's root. A known repair should pass the crash
and retry case:

```sh
python3 -I -S scripts/test_repair.py --candidate business-key --case crash-retry --output repaired.json
```

The command executes candidate source; it does not load a stored successful
result. Exit `0` means this selected candidate passed this selected case. The
receipt itself is the simulated fulfillment effect.

## A repair can stop duplicates and still lose an order

Make an editable copy, leaving the reference source intact:

```sh
mkdir -p candidate
cp repair_lab/adapters/business_key.py candidate/adapter.py
python3 -I -S scripts/test_repair.py --adapter candidate/adapter.py --case interleaved-retries --output before.json
```

Two valid orders share the same product. Expect **PASSED / exit 0**, with one
receipt for ORDER-A and one for ORDER-B. In `candidate/adapter.py`, replace
`key=order["orderId"]` with `key=order["sku"]`.
Run the same test again:

```sh
python3 -I -S scripts/test_repair.py --adapter candidate/adapter.py --case interleaved-retries --output broken.json
```

Expect **VIOLATION / exit 1**: ORDER-A has one receipt, but valid ORDER-B has
none. The receiver rejected the different payload under the reused product
key. Stopping duplicates did not protect the other order. Restore the candidate
and rerun:

```sh
cp repair_lab/adapters/business_key.py candidate/adapter.py
python3 -I -S scripts/test_repair.py --adapter candidate/adapter.py --case interleaved-retries --output restored.json
```

Expect **PASSED / exit 0**, one receipt for each order. Import `before.json`,
`broken.json` and `restored.json` into the companion lab. The browser checks and
displays supplied observations; these terminal commands execute Python.
The JSON reports include the executed source
fingerprints, case inputs, fault conditions, observations, and assertions.
Keep the failed report with its source when diagnosing a later change.

For the simpler duplicate failure, replace the key with `None` and run
`--case crash-retry`. One receipt becomes two and the result is a violation.
Restore the reference source afterwards. Neither exercise makes real shipments.

## Compare the full controls

```sh
python3 -I -S scripts/test_repair.py --output repair-results.json
```

This compares no key, a business key, and an overbroad key across the fixed
cases. An overbroad key can suppress a second legitimate order; avoiding a
duplicate is not enough. Missing observations stay **INCOMPLETE**. An unsupported
external effect stays **UNRESOLVED**. The full comparison intentionally includes
these controls and is **not expected to exit 0**, even for the business-key
candidate selected across all cases. It is not an expected-outcomes suite that
turns known bad behavior into an overall green result.

| Exit | Selected execution outcome |
| --- | --- |
| 0 | Passed: the required invariants held in this bounded local execution. |
| 1 | Violation: observed behavior broke an invariant. |
| 2 | Incomplete: required execution or observations were missing. |
| 3 | Unresolved: the model or evidence did not support a resolved conclusion. |

For a multi-result report, the overall precedence is unresolved, violation,
incomplete, then pass; inspect the individual case outcomes. Use the full comparison JSON with the
companion repair UI. The static UI reads reports; it does not execute Python.

## Run the independent application example

```sh
python3 -I -S scripts/test_repair.py --adapter examples/dispatchdesk/adapter.py --case-file examples/dispatchdesk/cases.json --output dispatchdesk-results.json
```

DispatchDesk is a separately authored synthetic stationery-dispatch worker with
its own event shape and an injected fulfillment gateway. Its adapter bridges
that application to the public lab contract. It is not a customer deployment,
user-adoption result, commercial shipping integration, or real shipment. Its
worker, bridge, and independently specified case plan are included.

To integrate trusted code, read `docs/repair-lab/adapter.md` and
`docs/repair-lab/schema.md`. The public boundary is `build(effects)` returning a
delivery handler. The candidate must preserve valid orders as well as deduplicate
retries; the receiver's atomic effect contract remains essential.

## Verify and reproduce the package

`SHA256SUMS` covers every other archive file. `PACKAGE.json` lists source hashes,
requirements, commands, and the evidence boundary. Verify before editing:

```sh
# macOS
shasum -a 256 -c SHA256SUMS
# Linux
sha256sum -c SHA256SUMS
```

From the unmodified extraction, recreate the deterministic archive:

```sh
python3 -I -S scripts/export_repair.py --output recreated.zip
```

Temporary candidates and generated reports are not included by the exporter.
Hashes establish byte consistency; they do not authenticate the execution
origin or make a JSON report an AWS-signed attestation.

## Scope

This is a **local simulation with bounded calls and an in-memory receipt store**.
It does not reproduce AWS SQS visibility timing, concurrency, durability,
throttling, deployment, or service failure behavior. ReplayGuard's dated AWS
failure evidence is a separate historical artifact and is not bundled here.
These commands create **no new cloud evidence** and neither verify nor recreate
an AWS deployment.

The guard blocks ordinary Python networking, AWS SDK, subprocess, and native-FFI
paths before candidate import. It is defense in depth for **trusted candidate
code**, not a sandbox for hostile Python/native code. Do not run unknown code
merely because this guard is present. A separate payment/shipping action cannot
be made exactly once by an unrelated local receipt; that external atomicity
problem remains outside this model.
