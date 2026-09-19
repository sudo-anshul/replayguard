# ReplayGuard local source snapshot

This archive contains the current static UI, bounded local repair runtime,
reference/application adapters, tests, public run instructions, and selected
historical evidence required by the retained regressions. It is an explicitly
allowlisted source snapshot, not a Git history export or a public deployment.
Private strategy/prior-project research, account configuration, credentials,
and unrelated workspace files are excluded. Old downloadable archives and AWS
evidence retain their original bytes; they do not attest to a new cloud run.
This local revision used no new AWS resources or calls. Remaining gross
spend headroom is unresolved; credits are not treated as measured headroom.

## Run locally

Requires Python 3.11+ on macOS or Linux/POSIX. No package installation or AWS
credentials are needed for the repair lab:

```sh
python3 -I -S scripts/test_repair.py --candidate business-key --case crash-retry --output repaired.json
python3 -m http.server 8088 --bind 127.0.0.1 --directory web
```

Open http://127.0.0.1:8088/ . The static UI reads JSON; it does not run Python.
Read docs/repair-lab/runbook.md for pass/fail/restoration, the independent
DispatchDesk example, trusted-code and simulation limits. The complete
comparison intentionally includes incomplete/unresolved controls and does not
have an all-green exit status. No new cloud execution is claimed.

## Reproduce checks

```sh
python3 -I -S -m unittest discover -s tests -p 'test_repair*.py'
python3 tests/repair_holdout/run_transfer.py --output-dir /tmp/replayguard-transfer-new
```

JavaScript contract checks additionally require an already-installed Node.js:

```sh
node --test tests/test_*.cjs
```

Browser checks require an already-installed Playwright/browser and the loopback
server; they must not install dependencies or query AWS. The historical AWS
deployment scripts and requirements are retained as source, not authorization
to run them. Publication and chargeable work remain stopped.
Some retained historical browser and media scripts refer to artifacts outside
this allowlist and require the original workspace. Self-contained validation
is claimed for the documented commands above; it does not imply that every
retained historical script can run from this archive alone.

## Verify and re-export

SOURCE-SHA256SUMS covers every other archive file. SOURCE-PACKAGE.json records
the exact source-file hashes and exclusions. Verify with `shasum -a 256 -c
SOURCE-SHA256SUMS` on macOS or `sha256sum -c SOURCE-SHA256SUMS` on Linux.

```sh
python3 -I -S scripts/export_source_release.py --output source-recreated.zip
```

The same included bytes produce the same ZIP in the same Python/zlib runtime.
Hashes establish byte consistency, not authorship, Git history or authentic
AWS execution. Public report imports remain unauthenticated. This snapshot
does not include a YouTube upload, live URL, or submitted hackathon entry.
The companion narrated MP4 is distributed separately from this source ZIP;
its script, subtitles, captures and render manifest are included under
docs/repair-lab/media/.
