# Trusted Python repair adapters

Run Python 3.11+ on macOS/Linux, using only the standard library:

```sh
python3 -I -S scripts/test_repair.py --candidate business-key --case crash-retry --output report.json
python3 -I -S scripts/test_repair.py --adapter path/to/adapter.py --case-file plan.json --output report.json
```

Without candidate options, all three reference candidates run. An external adapter receives ID `external-1` (additional `--adapter` values are numbered). A selected case must exist in the selected plan. `--case-file` uses the public plan format in [schema.md](schema.md).

An adapter exports `build(effects)`, returning a callable `handle(delivery)`. Build runs afresh for each candidate × case. State persists between that case's deliveries. The delivery is a deep copy containing only `deliveryId`, `messageId`, `receiveCount`, and `order`. It does not contain the fault schedule, expected outcome, or assertions.

```python
def build(effects):
    def handle(delivery):
        order = delivery["order"]
        return effects.fulfill(order, key=order["orderId"])
    return handle
```

The order has nonempty string `orderId` and `sku`, positive integer `quantity`, and optionally a JSON object `attributes`. Full canonical order payload equality matters. `effects.fulfill(order, *, key=None)` atomically owns the simulated external effect and its receipt. No key accepts a fresh receipt each call. A new nonempty string key accepts a receipt. Reusing a key for an identical order returns the original receipt; reusing it for a different payload raises `effects.Conflict`. The return value has `receiptId`, `accepted`, `reused`, and a copied `order`. An adapter can expose a domain-level rejection by raising `effects.Conflict`; an ordinary return does not prove rejection.

For a delivery with `fault: "after-commit"`, the harness injects `effects.CrashAfterCommit` immediately after the first new receipt commits, before `fulfill` returns. This exception inherits `BaseException`. The receiver records the accepted receipt and injection independently. Reuse alone cannot fire this failpoint. An adapter must propagate the crash to the harness. Merely raising this exception does not count as a harness-injected fault.

The harness drives the complete bounded schedule. Candidate return values are diagnostic only. Assertions inspect the receiver-owned receipt snapshot per business order and the actual delivery outcomes. Effects outside an active delivery are rejected. Unsupported external effects are marked `unresolved` without importing the candidate. Withheld receipt observation is `incomplete`.

Only run trusted adapters. The reused local execution guard blocks ordinary network sockets, AWS SDK imports, child processes and ctypes before adapter import. It is defense in depth, **not a hostile-code sandbox**: trusted Python can access local files and internal objects. A blocked operation makes the result `unresolved`, even if candidate code catches the error.

The runner captures all `.py` files under the adapter's directory, rejects source symlinks, and executes a fresh temporary copy of those captured bytes for each case. `__file__` points into that copy, supporting adapters that load a sibling `worker.py` with `importlib`. Cached bytecode is not copied. The runner does not install a package or add this folder to sys.path; use __file__ and importlib for sibling source, as the DispatchDesk example does. Arbitrary dependencies, non-Python assets, standard library and files outside this source folder are not attested. Keep adapters in a dedicated small folder. Recorded hashes identify captured source bytes, not authorship or a signed artifact. Changes to the original source or the copied source during execution make the affected results `incomplete` unless stronger evidence determines a violation or unresolved result.

Bounds: 64 KiB plan, 16 cases, 8 candidates, 8 deliveries per case, 8 allowed effect calls per delivery and 32 per case, 64 Python source files totaling 256 KiB in at most 128 directories per adapter, 2 seconds per source capture/import/build/delivery, and 60 seconds for a suite. A delivery's diagnostic `effectCalls` saturates at 9 to record the first denied call. Captured console output is truncated at 16 KiB per case. POSIX signal timeouts handle accidental hangs in trusted Python; they are not a resource-isolation guarantee against hostile native code. Results report exceeded bounds explicitly.

Process exits are 0 `pass`, 1 `violation`, 2 `incomplete`, 3 `unresolved`. Aggregate precedence is unresolved, violation, incomplete, pass. The intentional missing-observer and unsupported-effect controls mean even the correct business-key candidate's full suite is not wholly passed. Select `--case crash-retry` for the compact passing repair example.
