# Portable repair-kit validation

The final `web/replayguard-repair-lab.zip` is **32,330 bytes / 22 files**.
SHA-256:

```text
e01bdcaef59a813f56c96a4ba9e10c25175d41dd33c56d7e9b29b5b29d9d2555
```

[Final validation](numeric-parity-final/package-validation.json) passed at
**2026-09-19 04:08:15 UTC** after the core's numeric-normalization correction.
The extraction used the archive's own runtime and sources, a sanitized
environment, Python `-I -S`, the local guard, and macOS OS-level network denial.

| Actual execution | Result |
| --- | --- |
| Copied business-key candidate, crash/retry | Pass, exit 0 |
| Same copied file with `key=None` | Violation, exit 1 |
| Original bytes restored to the copied file | Pass, exit 0 |
| DispatchDesk's independent five-case plan | Five passes, exit 0 |

Each report identified the actual candidate source hashes. Guard self-tests
passed, and no candidate-blocked operation was recorded. The validator also
checked every archive checksum and manifest entry, byte-identical re-export,
and preservation of all **50** previously fingerprinted historical evidence and
archive files. These are five validation categories and four CLI executions;
they are not fifty new application scenarios.

The exporter's **seven unit checks** cover scope/hash completeness, missing
runtime rejection, source-symlink rejection, deterministic re-export, and
refusal to replace package sources, historical ZIPs, or preserved evidence.

The earlier [attempt-01](attempt-01/package-validation.json) and
[pre-normalization validation](final/package-validation.json) remain intact.
They passed their bounded package checks before the later cross-runtime number
correction. The current ZIP and numeric-parity report supersede those snapshots.

A separate fresh extraction then produced the [actual demo CLI transcript](../media/execution/final/transcript.txt)
and [recording manifest](../media/execution/final/manifest.json). They retain all
four real command outputs, source hashes, exit codes, and per-order counts:
one receipt, two after the deliberate mutation, and one after restoration;
then all five DispatchDesk cases passed. This is recorded command output, not
simulated terminal typing or a screen recording of an AWS execution.

To rerun against a new, unused work directory:

```sh
python3 -I -S docs/repair-lab/validate_archive.py \
  --archive web/replayguard-repair-lab.zip \
  --work-dir /tmp/replayguard-kit-new \
  --output /tmp/replayguard-kit-evidence-new
```

The validator's optional `--protected-manifest` additionally verifies the
workspace's pre-recorded historical hashes. That private workspace manifest is
not needed to execute the portable kit and is not included in it.

No fresh AWS run, deployment, public upload, or human-customer validation is
claimed. The receipts are the local simulated effect. The guard remains a
trusted-code defense, not a hostile-code sandbox.
