# Adversarial import fixture

`contradictory-passed.json` is the exact supervisor-provided test input from review 2. It is a disposable edited copy of the recorded export: a second repaired receipt was added while saved passed/assertion flags were retained. It is **not genuine AWS evidence of a second repaired fulfillment**, and must never be used to claim a cloud experiment result.

The import UI must expose its contradiction as UNRESOLVED while retaining the supplied claims only as claims. The original AWS evidence in `web/evidence.json` and `evidence/latest.json` is untouched. Run the local browser test with `node tests/browser_evidence.cjs` using an already-installed Playwright/browser and a loopback server on port 8088.

Fixture SHA-256: `008c76c9ff0c017ab00441a791515df4c8349539a310f04ca1a744955d307073`.
