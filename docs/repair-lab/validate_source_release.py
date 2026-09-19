#!/usr/bin/env python3
"""Validate a local allowlisted source ZIP without modifying its included files."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    dest = args.output_dir.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    extracted = dest / 'extracted'
    checks, commands = [], []

    def check(name, value, observed):
        checks.append({'name': name, 'status': 'pass' if value else 'fail', 'observed': observed})
        if not value:
            raise AssertionError(name)

    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        check('unique-safe-paths', len(set(names)) == len(names) and all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names), len(names))
        check('no-private-directories-or-config', not any(any(p in {'.git', '.aws', '.venv', 'node_modules', 'competitive-review', 'accounts', 'account'} for p in PurePosixPath(n).parts) or PurePosixPath(n).name in {'deployment.local.json', 'credentials', 'credentials.json', '.env', 'config.local.json'} for n in names), 'Checked archive path allowlist boundary')
        zipped.extractall(extracted)
    sums = dict(line.split('  ', 1)[::-1] for line in (extracted / 'SOURCE-SHA256SUMS').read_text().splitlines())
    check('checksum-scope-complete', set(sums) == set(names) - {'SOURCE-SHA256SUMS'}, len(sums))
    check('every-checksum-matches', all(sha(extracted / name) == digest for name, digest in sums.items()), len(sums))
    metadata = json.loads((extracted / 'SOURCE-PACKAGE.json').read_text())
    check('source-hash-scope-complete', set(metadata['sourceSha256']) == set(names) - {'SOURCE-PACKAGE.json', 'SOURCE-SHA256SUMS'}, len(metadata['sourceSha256']))
    check('every-source-hash-matches', all(sha(extracted / name) == digest for name, digest in metadata['sourceSha256'].items()), len(metadata['sourceSha256']))
    check('separate-video-not-in-source-zip', not any(n.endswith(('.mp4', '.aiff', '.wav', '.mp3')) for n in names), 'Video is a separate companion artifact')
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin', 'LANG': 'en_US.UTF-8', 'TMPDIR': str(dest)}
    wrapper = ['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'] if Path('/usr/bin/sandbox-exec').is_file() else []

    def command(label, argv, expected=0):
        result = subprocess.run(wrapper + list(map(str, argv)), cwd=extracted, env=env, capture_output=True, text=True, timeout=120)
        (dest / (label + '.stdout.txt')).write_text(result.stdout)
        (dest / (label + '.stderr.txt')).write_text(result.stderr)
        item = {'label': label, 'argv': list(map(str, argv)), 'networkWrapper': wrapper, 'exitCode': result.returncode, 'expectedExitCode': expected}
        commands.append(item)
        check(label, result.returncode == expected, item)

    py = [sys.executable, '-I', '-S', '-B']
    command('selected-case', py + ['scripts/test_repair.py', '--candidate', 'business-key', '--case', 'crash-retry', '--output', dest / 'selected-case.json'])
    report = json.loads((dest / 'selected-case.json').read_text())
    check('selected-case-passes', report['summary']['status'] == 'pass', report['summary'])
    command('complete-comparison-expected-nonzero', py + ['scripts/test_repair.py', '--output', dest / 'complete-comparison.json'], expected=3)
    # The documented transfer driver imports a sibling helper. Its child repair
    # CLI processes still run with -I -S; the driver uses normal script lookup.
    command('independent-transfer', [sys.executable, '-B', 'tests/repair_holdout/run_transfer.py', '--output-dir', dest / 'transfer'])
    transfer = json.loads((dest / 'transfer/summary.json').read_text())
    check('transfer-outcomes-and-integrity', transfer['passed'] == 45 and transfer['failed'] == 0, {'passed': transfer['passed'], 'failed': transfer['failed']})
    command('repair-engine-and-export-tests', py + ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_repair*.py', '-v'])
    command('source-export-tests', py + ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_source_export.py', '-v'])
    node = shutil.which('node')
    if node:
        testfiles = sorted(str(p.relative_to(extracted)) for p in (extracted / 'tests').glob('test_*.cjs'))
        command('javascript-contract-tests', [node, '--test'] + testfiles)
    recreated = dest / 'source-recreated.zip'
    command('source-reexport', py + ['scripts/export_source_release.py', '--output', recreated])
    check('deterministic-reexport-identical', archive.read_bytes() == recreated.read_bytes(), {'originalSha256': sha(archive), 'recreatedSha256': sha(recreated)})
    check('included-source-bytes-unchanged', all(sha(extracted / name) == digest for name, digest in sums.items()), len(sums))
    result = {'schemaVersion': 1, 'kind': 'allowlisted-source-release-validation', 'completedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'archive': str(archive), 'archiveSha256': sha(archive), 'archiveBytes': archive.stat().st_size, 'files': len(names), 'newCloudEvidence': False, 'published': False, 'checks': checks, 'commands': commands, 'passed': len(checks), 'failed': 0}
    (dest / 'source-release-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('archive', 'archiveSha256', 'archiveBytes', 'files', 'passed', 'failed')}))


if __name__ == '__main__':
    main()
