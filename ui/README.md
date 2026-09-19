# ReplayGuard public interface

This source integrates the accepted receipt-story proposal into the public repair
viewer. The established paper, forest-green and lime identity stays intact. The
opening explains a retry repair through recorded receipts; the inspector then
lets a developer inspect every declared case, import their own run and retain its
original evidence. The tutorial demonstrates a SKU key losing a different valid
order, then restores the order key.

Build from the repository root:

```sh
python3 -I -S scripts/build_web.py
python3 -I -S scripts/build_web.py --check
```

The build creates identical `web/index.html` and `web/repair.html` aliases,
content-versioned local CSS/JavaScript assets, the shared mark and a deterministic
`web/build-manifest.json`. The manifest identifies source and output bytes. It is
not an authentication claim. No framework, package install or remote rendering
dependency is required. The reference report and DispatchDesk recording are
embedded as escaped JSON strings so decoding preserves their original UTF-8
bytes. The evidence contracts remain in `web/repair-contract.js` unchanged.

## Source ownership

- `index.template.html`: page narrative, landmarks, controls and static copy.
- `repair.css`: main layout, semantic colors, type, hover/focus and breakpoints.
- `repair-data.js`: presentation derived through the existing report validator.
- `repair-imports.js`: bounded UTF-8 loading, byte retention and request ordering.
- `repair-app.js`: report selection, stable controls, local tutorial and replay.
- `repair-motion.js`: native scroll progression and responsive presentation.
- `shared-tokens.css`: supporting AWS, archive and adapter-guide page identity.

Edit these sources, then rebuild; do not hand-edit generated main-page assets.
The supporting `web/aws-run.html`, `web/adapter-guide.html` and
`web/recorded-lab.html` remain directly maintained historical/guide pages. Their
evidence semantics stay separate from the local comparison.

## Interaction contract

The opening always shows `repair-example.json`. Changing or importing a report
affects only the inspector and its downloadable bytes. DispatchDesk is a
separately authored **synthetic** example, not outside-user validation.

Candidate/case buttons remain in place while selections update their attributes
and results. Imports validate before committing. Rejected files retain the prior
model and bytes; a newer import or an explicit source choice supersedes an older
unfinished read. Successful imports move focus to the inspector. The original
JSON dialog returns focus to its trigger when closed.

Native scrolling advances and reverses the four recorded deliveries. Replay
controls claim manual ownership until Follow scroll is selected. Scroll updates
do not announce continuously in the live region. The story pins only when the
receipt board and chapter copy fit. Short windows retain normal-flow chapters and
their receipt summaries. Reduced motion removes pinning and displacement;
recorded deliveries remain accessible through manual controls. No wheel/touch
events are intercepted.

## Checks

```sh
node --test tests/test_repair_ui_data.cjs tests/test_repair_ui_imports.cjs
python3 -I -S -m unittest discover -s tests -p 'test_web_build.py' -v
```

These cover actual recorded counts, the evidence states, contradictory imports,
byte retention, stale asynchronous reads and deterministic output. They do not
establish rendered accessibility or visual quality. Browser review must also
exercise desktop, narrow and short layouts, keyboard ownership, import errors,
dialog focus return, reverse scrolling and reduced motion. The older Playwright
holdout scripts have been updated for the current selectors; executing them is
an optional separate browser check.

## Separate AWS key-scope viewer

`aws-key-scope.template.html`, `aws-key-scope.css`, `aws-key-scope-data.js` and
`aws-key-scope.js` power `web/aws-key-scope.html`. Its report kind and semantics
are separate from the local repair contract. Do not route AWS reports through
`repair-contract.js` or substitute the local four-delivery animation for AWS's
actual schedule.

After a real bounded AWS run has been retained, place its exact report bytes at
`web/aws-key-scope-report.json` and its exported archive at
`web/aws-key-scope-regression.zip`, then run the normal web build. Without a
report, the page explicitly remains incomplete with unknown counts and disabled
downloads. No mock fixture belongs in these public paths.

The build reruns `scripts/verify_key_case.py` against the raw observations. It
embeds that derived result and original-file SHA-256, rather than trusting the
report's saved summary. The browser fetches the local report, checks its exact
hash and independently recounts matching receipts from the latest complete
ledger queries. Full trace/phase-gate verification remains attributed to the
offline verifier. These checks do not authenticate AWS origin.

Experiment completeness, each handler's business result and captured cleanup
are displayed separately. A successful experiment intentionally includes two
violating handlers. The download link is enabled only when the available ZIP
contains those exact report bytes. A mismatched or missing ZIP stays disabled.

Offline display/build controls use synthetic observations only in memory or
temporary roots:

```sh
node --test tests/test_aws_key_scope_ui.cjs
python3 -I -S -m unittest discover -s tests -p 'test_web_aws_view.py' -v
```
