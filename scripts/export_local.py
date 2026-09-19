#!/usr/bin/env python3
"""Package current executable local regression and a byte-identical AWS archive."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
README = '''# ReplayGuard: execute a regression locally

Requirements: Python 3.11+ on macOS or Linux (POSIX delivery timers).
Windows is not supported by this runner. No pip install, third-party dependencies, AWS
credentials, network connection or paid service is needed. From this extracted
folder, run:

```sh
python3 -I -S scripts/run_local.py --output local-results.json
```

This command imports and executes **the worker and fulfillment receiver source
in this archive**. A local Lambda transport calls the real receiver; a memory
ledger implements its conditional-write API. The observer reads a separate
ledger snapshot rather than trusting the handler's return value. Python audit
hooks block network/process attempts; clean extraction validation also used a
macOS OS-level network-denial profile. See the recorded validation outside this
archive for the exact platform and command.

The fixed suite includes both no-fault controls, a crash/retry comparison,
different message IDs for the same business order, withheld observations, and
an explicitly unsupported external-side-effect model. Suite success means the
observed business verdicts match the declared case expectations. It DOES NOT
mean the intentionally vulnerable handler is safe.

Check one handler's business verdict (the process exit code is its result):

```sh
python3 -I -S scripts/run_local.py --case crash-after-fulfillment --mode vulnerable
# expected violation: exit 1
python3 -I -S scripts/run_local.py --case crash-after-fulfillment --mode repaired
# expected pass: exit 0
```

Exit codes: 0 pass, 1 business violation, 2 incomplete/missing observation,
3 unresolved/unsupported. An immediately throwing handler cannot satisfy a
successful-fulfillment control. Declared schedules are bounded local calls;
they do not simulate AWS visibility timing, deployment, delivery guarantees,
concurrency, throttling or network failure. The receipt is the simulated effect.
An arbitrary external side effect without an atomic receiver contract remains
unsupported. The Python guard is not a sandbox for hostile native code.

## Different action: verify archived AWS observations

```sh
python3 -I -S scripts/verify_case.py evidence/latest.json --case cases/crash-after-fulfillment.json
```

This checks the consistency of saved AWS JSON. It does not execute the handlers
or prove that a changed implementation passed on AWS. The genuine historical
AWS run and its matching source are preserved byte-for-byte inside
`historical/aws-regression-case.zip`. Do not rewrite its hashes or label new
local results as AWS evidence. Cloud work is currently stopped: cumulative
spending headroom is unresolved, and this iteration allows $0 chargeable work.
Both original project stacks have saved DELETE_COMPLETE records; this local
command neither checks nor recreates them.

`SHA256SUMS` records every other package file. On macOS use
`shasum -a 256 -c SHA256SUMS`; on Linux use `sha256sum -c SHA256SUMS`.
Hashes establish byte consistency, not AWS-signed authenticity. The fixed plan
is at `docs/iteration-01/plan.json`; local results fingerprint executed code and
case inputs. No stored result is used as a current pass/fail oracle.
'''


def assemble():
    required = [
        'scripts/run_local.py', 'scripts/export_local.py', 'scripts/verify_case.py',
        'src/worker.py', 'src/provider.py', 'cases/crash-after-fulfillment.json',
        'docs/iteration-01/plan.json', 'docs/iteration-01/historical-sha256.json',
        'evidence/latest.json', 'LICENSE',
        'tests/test_core.py', 'tests/test_local.py',
    ]
    for pattern in ('local_lab/*.py', 'cases/local/*.json'):
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            raise ValueError(f'Missing required package files: {pattern}')
        required += [p.relative_to(ROOT).as_posix() for p in matches]
    files = {}
    for name in required:
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing or symlinked required file: {name}')
        files[name] = path.read_bytes()
    historical = ROOT / 'web/regression-case.zip'
    if not historical.is_file():
        historical = ROOT / 'historical/aws-regression-case.zip'
    if historical.is_symlink():
        raise ValueError('Historical AWS archive must not be a symlink')
    files['historical/aws-regression-case.zip'] = historical.read_bytes()
    expected = json.loads((ROOT / 'docs/iteration-01/historical-sha256.json').read_text())['web/regression-case.zip']
    if hashlib.sha256(files['historical/aws-regression-case.zip']).hexdigest() != expected:
        raise ValueError('Historical AWS source archive changed; refusing to re-label it')
    files['README.md'] = README.encode()
    files['PACKAGE.json'] = (json.dumps({
        'schemaVersion': 1,
        'kind': 'executable-local-regression',
        'iteration': 'RG-SUP-001-9c7acfba',
        'command': 'python3 -I -S scripts/run_local.py --output local-results.json',
        'historicalAwsArchiveSha256': expected,
        'requiresNetwork': False,
        'requiresThirdPartyPackages': False,
        'containsStoredPassOracle': False,
    }, indent=2) + '\n').encode()
    files['SHA256SUMS'] = ''.join(
        f'{hashlib.sha256(data).hexdigest()}  {name}\n'
        for name, data in sorted(files.items())
    ).encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'web/replayguard-local-regression.zip')
    args = parser.parse_args()
    try:
        files = assemble()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_name(args.output.name + '.tmp')
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 9, 19, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
        temp.replace(args.output)
        print(f'Exported {len(files)} files: {args.output}')
        print('Local execution package; archived AWS evidence retained unchanged.')
        return 0
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
