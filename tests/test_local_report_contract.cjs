'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const contractPath = path.join(root, 'web/local-report-contract.js');
const {analyzeLocalReport} = require(contractPath);
const generated = path.join(root, 'docs/iteration-03/generated');
const normalBytes = fs.readFileSync(path.join(generated, 'local-results.json'), 'utf8');
const brokenBytes = fs.readFileSync(path.join(generated, 'broken-key-results.json'), 'utf8');
const fixture = () => JSON.parse(normalBytes);
const result = (data, id = 'no-fault', mode = 'repaired') => data.results.find(value => value.caseId === id && value.mode === mode);
const analyzed = (report, id = 'no-fault', mode = 'repaired') => report.cases.find(value => value.id === id).modes[mode];
const EXIT = {pass: 0, violation: 1, incomplete: 2, unresolved: 3};
function truthfullyClaim(data, target, status) {
  target.observedStatus = status; target.exitCode = EXIT[status]; target.expectationMatched = status === target.expectedStatus;
  const count = data.results.filter(value => value.observedStatus === value.expectedStatus).length;
  Object.assign(data.suite, {status: count === 10 ? 'passed' : 'failed', exitCode: count === 10 ? 0 : 1, matchedCount: count, totalCount: 10, expectationsMatched: count === 10, allHandlersSafe: data.results.every(value => value.observedStatus === 'pass')});
  data.command.exitCode = data.suite.exitCode;
}
function reject(change, pattern = /./) {
  const data = fixture(); change(data); const before = JSON.stringify(data);
  assert.throws(() => analyzeLocalReport(data), pattern);
  assert.equal(JSON.stringify(data), before, 'rejected import must not mutate its raw object');
}

test('fresh real normal full suite is UNVERIFIED and exposes all five paired cases', () => {
  const report = analyzeLocalReport(fixture());
  assert.equal(report.status, 'unverified'); assert.equal(report.sourceType, 'local');
  assert.equal(report.provenanceAuthenticated, false); assert.equal(report.claimedStatus, 'passed');
  assert.equal(report.cases.length, 5); assert.equal(report.derivedSuite.matchedCount, 10);
  assert.equal(report.derivedSuite.expectationsMatched, true); assert.equal(report.derivedSuite.allHandlersSafe, false);
  const expected = [['no-fault', 'pass', 'pass'], ['crash-after-fulfillment', 'violation', 'pass'], ['different-message-ids', 'violation', 'pass'], ['missing-observation', 'incomplete', 'incomplete'], ['ambiguous-side-effect', 'unresolved', 'unresolved']];
  for (const [id, vulnerable, repaired] of expected) {
    assert.equal(analyzed(report, id, 'vulnerable').derivedStatus, vulnerable);
    assert.equal(analyzed(report, id).derivedStatus, repaired);
  }
});

test('fresh broken-key suite exposes both repaired violations without overriding truthful failed flags', () => {
  const report = analyzeLocalReport(JSON.parse(brokenBytes));
  assert.equal(report.status, 'unresolved'); assert.equal(report.claimedStatus, 'failed');
  assert.equal(report.derivedSuite.matchedCount, 8); assert.equal(report.derivedSuite.allHandlersSafe, false);
  for (const id of ['crash-after-fulfillment', 'different-message-ids']) {
    const mode = analyzed(report, id); assert.equal(mode.derivedStatus, 'violation'); assert.equal(mode.receiptCount, 2); assert.equal(mode.expectationMatched, false);
  }
});

test('missing snapshot remains null/unknown and unsupported model invents no execution', () => {
  const report = analyzeLocalReport(fixture());
  for (const mode of ['vulnerable', 'repaired']) {
    const missing = analyzed(report, 'missing-observation', mode);
    assert.equal(missing.receiptCount, null); assert.equal(missing.derivedStatus, 'incomplete');
    assert.equal(missing.result.deliveries.length, 1);
    assert.equal(missing.checks.find(value => value.id === 'provider-ledger-correlation').status, 'incomplete');
    const unsupported = analyzed(report, 'ambiguous-side-effect', mode);
    assert.equal(unsupported.receiptCount, null); assert.equal(unsupported.derivedStatus, 'unresolved');
    assert.equal(unsupported.result.execution.performed, false); assert.deepEqual(unsupported.result.deliveries, []);
  }
});

test('both modes retain their own run IDs; IDs need not be globally identical', () => {
  const original = fixture(); const report = analyzeLocalReport(original);
  assert.equal(new Set(report.cases.flatMap(item => Object.values(item.modes).map(mode => mode.result.runId))).size, 5);
  const target = result(original), old = target.runId, changed = 'local-0123456789abcdef0123456789abcdef';
  const index = original.results.indexOf(target);
  original.results[index] = JSON.parse(JSON.stringify(target).split(old).join(changed));
  const rebased = analyzeLocalReport(original);
  assert.equal(rebased.status, 'unverified');
  assert.equal(analyzed(rebased).result.runId, changed);
  assert.notEqual(analyzed(rebased).result.runId, analyzed(rebased, 'no-fault', 'vulnerable').result.runId);
});

test('analysis clones frozen input without mutation and keeps supplied fingerprints inspectable', () => {
  const data = fixture();
  function freeze(value) { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } }
  freeze(data); const before = JSON.stringify(data); const report = analyzeLocalReport(data);
  assert.equal(JSON.stringify(data), before); assert.notEqual(report.data, data);
  assert.deepEqual(report.fingerprints.sources, data.sourceSha256); assert.deepEqual(report.fingerprints.cases, data.caseSha256);
  assert.equal(report.fingerprints.plan.sha256, data.plan.sha256);
  report.data.results[0].runId = 'render-only'; assert.equal(JSON.stringify(data), before);
});

test('saved assertion flags are ignored rather than used as an outcome oracle', () => {
  const data = fixture(); data.results.forEach(value => { value.assertions.forEach(item => { item.status = 'pass'; item.expected = 'forged'; item.observed = 'forged'; }); });
  const report = analyzeLocalReport(data);
  assert.equal(analyzed(report, 'crash-after-fulfillment', 'vulnerable').derivedStatus, 'violation');
  assert.equal(analyzed(report, 'missing-observation').derivedStatus, 'incomplete');
});

test('forged per-handler observedStatus, exit code and match flag are rejected', () => {
  reject(data => { result(data, 'crash-after-fulfillment', 'vulnerable').observedStatus = 'pass'; }, /raw-derived violation/);
  reject(data => { result(data).exitCode = 1; }, /exitCode/);
  reject(data => { result(data).expectationMatched = false; }, /expectationMatched/);
  reject(data => { result(data, 'missing-observation').observedStatus = 'pass'; }, /raw-derived incomplete/);
});

test('forged all-safe and suite success claims cannot hide business violations', () => {
  reject(data => { data.suite.allHandlersSafe = true; }, /allHandlersSafe/);
  reject(data => { data.suite.matchedCount = 9; }, /suite/);
  reject(data => { data.suite.exitCode = 1; }, /suite/);
  reject(data => { data.command.exitCode = 1; }, /command/);
  const broken = JSON.parse(brokenBytes); Object.assign(broken.suite, {status: 'passed', expectationsMatched: true, matchedCount: 10, exitCode: 0}); broken.command.exitCode = 0;
  assert.throws(() => analyzeLocalReport(broken), /suite/);
});

test('missing raw events do not inherit a supplied pass', () => {
  reject(data => { result(data).events = []; }, /raw-derived incomplete/);
  const data = fixture(); const target = result(data); target.events = []; truthfullyClaim(data, target, 'incomplete');
  const report = analyzeLocalReport(data); assert.equal(report.status, 'incomplete'); assert.equal(analyzed(report).derivedStatus, 'incomplete');
});

test('null ledger from another case stays unknown with truthful incomplete metadata', () => {
  reject(data => { result(data).ledgerSnapshot = null; }, /raw-derived incomplete/);
  const data = fixture(); const target = result(data); target.ledgerSnapshot = null; truthfullyClaim(data, target, 'incomplete');
  const report = analyzeLocalReport(data); assert.equal(report.status, 'incomplete'); assert.equal(analyzed(report).receiptCount, null);
});

test('a synthetic immediate exception remains a non-pass even if it is labeled expected', () => {
  const data = fixture(); const target = result(data);
  const delivery = target.deliveries[0]; delivery.returnedNormally = false; delivery.returned = null; delivery.error = {type: 'RuntimeError', message: 'immediate failure'};
  target.events = []; target.providerInvocations = []; target.ledgerSnapshot = []; target.ledgerOperations = []; target.execution.providerInvocations = 0;
  target.errors = [{...delivery.error, deliveryIndex: 1, expectedInjectedFault: true}];
  truthfullyClaim(data, target, 'incomplete');
  const report = analyzeLocalReport(data); assert.equal(analyzed(report).derivedStatus, 'incomplete'); assert.equal(analyzed(report).receiptCount, 0);
});

test('unsupported model rejects fabricated handler calls or even an invented empty snapshot', () => {
  reject(data => { const target = result(data, 'ambiguous-side-effect'); target.deliveries = [structuredClone(result(data).deliveries[0])]; target.execution.handlerInvocations = 1; target.execution.performed = true; }, /schedule|identity/);
  reject(data => { result(data, 'ambiguous-side-effect').ledgerSnapshot = []; }, /unsupported external effects/);
});

test('single-handler and incomplete suites provide a full-suite recovery command', () => {
  for (const count of [0, 1, 9]) reject(data => { data.results = data.results.slice(0, count); }, /complete ten-result.*python3 -I -S/);
  reject(data => { data.results = null; }, /array/);
  reject(data => { data.results.push(structuredClone(data.results[0])); }, /array/);
});

test('unsupported schema and mixed provenance reject', () => {
  reject(data => { data.schemaVersion = 2; }, /schemaVersion 1/);
  reject(data => { data.provenance = 'aws'; }, /local-execution/);
  reject(data => { result(data).provenance = 'aws'; }, /mixes local/);
  for (const value of [null, [], 'report']) assert.throws(() => analyzeLocalReport(value), /object/);
});

test('duplicate case/mode results and repeated ledger rows reject', () => {
  reject(data => { data.results[1] = structuredClone(data.results[0]); }, /duplicates the same case/);
  reject(data => { result(data).ledgerSnapshot.push(structuredClone(result(data).ledgerSnapshot[0])); }, /duplicates a ledger row/);
});

test('run-only and nested event/receipt/body identity changes reject', () => {
  reject(data => { result(data).runId = 'local-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'; }, /schedule|identity|result/);
  for (const key of ['runId', 'mode', 'orderId']) {
    reject(data => { result(data).events[0][key] = 'other'; }, /identity/);
    reject(data => { result(data).ledgerSnapshot[0][key] = 'other'; }, /identity/);
  }
  reject(data => { const body = JSON.parse(result(data).deliveries[0].input.Records[0].body); body.runId = 'other'; result(data).deliveries[0].input.Records[0].body = JSON.stringify(body); }, /run\/mode\/order\/fault/);
});

test('modes with different business inputs cannot be paired even if internally rebased', () => {
  reject(data => { const target = result(data); data.results[data.results.indexOf(target)] = JSON.parse(JSON.stringify(target).split('LOCAL-ORDER-1042').join('LOCAL-OTHER-ORDER')); }, /different declared business inputs/);
});

test('frozen schedules, expected outcomes and order quantities are not tunable', () => {
  reject(data => { result(data).case.expectedStatus.repaired = 'violation'; }, /frozen/);
  reject(data => { result(data).expectedStatus = 'violation'; }, /frozen/);
  reject(data => { result(data, 'different-message-ids').case.deliveries[1].messageKey = 'message-a'; }, /frozen/);
  reject(data => { result(data).case.order.quantity = true; }, /integer/);
});

for (const key of ['events', 'deliveries', 'providerInvocations', 'ledgerOperations', 'errors', 'assertions']) {
  test('null or wrong-type ' + key + ' is malformed rather than silently empty', () => {
    for (const value of [null, {}, '[]']) reject(data => { result(data)[key] = value; }, /array/);
  });
}

test('ledgerSnapshot allows null but not other scalar/object types', () => {
  for (const value of [{}, false, 'unknown', 0]) reject(data => { result(data).ledgerSnapshot = value; }, /array/);
});

test('delivery record types and schedule identities are strict', () => {
  reject(data => { result(data).deliveries[0].receiveCount = '1'; }, /schedule/);
  reject(data => { result(data).deliveries[0].returnedNormally = 'true'; }, /boolean/);
  reject(data => { result(data).deliveries[0].input.Records[0].attributes.ApproximateReceiveCount = '2'; }, /recorded delivery/);
  reject(data => { result(data).deliveries[0].input.Records[0].body = '{'; }, /valid JSON/);
  reject(data => { result(data).execution.handlerInvocations = 0; }, /execution counts/);
});

test('provider payload and request references must belong to this exact local delivery', () => {
  reject(data => { result(data).providerInvocations[0].payload.runId = 'other'; }, /result.*run|run\/mode/);
  reject(data => { result(data).providerInvocations[0].payload.workerRequestId = 'unrelated'; }, /worker delivery/);
  reject(data => { result(data).events.find(event => event.component === 'provider').requestId = 'unrelated'; }, /provider invocation/);
});

test('orphan successful provider invocation cannot keep a stale saved pass', () => {
  reject(data => {
    const target = result(data); const extra = structuredClone(target.providerInvocations[0]);
    extra.requestId = 'extra-provider-request'; extra.returned.receiptId = extra.returned.idempotencyKey = 'extra-accepted-receipt';
    target.providerInvocations.push(extra); target.execution.providerInvocations++;
  }, /raw-derived incomplete/);
});

test('orphan provider acceptance event absent from ledger cannot keep a saved pass', () => {
  reject(data => {
    const target = result(data); const extra = structuredClone(target.events.find(event => event.component === 'provider'));
    extra.receiptId = 'missing-ledger-receipt'; extra.localObservationIndex = target.events.length; target.events.push(extra);
  }, /raw-derived incomplete/);
});

test('exact supervisor ledger wrong-delivery fixture rejects without changing its supplied claims', () => {
  const bytes = fs.readFileSync(path.join(__dirname, 'fixtures/local-ledger-wrong-delivery.json'));
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), 'f62c67662317f48287652b439320415272ac64caa2202f4b2ace7313ce3a1b12');
  const data = JSON.parse(bytes), target = result(data, 'different-message-ids');
  assert.equal(target.observedStatus, 'pass'); assert.equal(data.suite.status, 'passed');
  const before = JSON.stringify(data);
  assert.throws(() => analyzeLocalReport(data), error => error.code === 'IDENTITY_MISMATCH' && /ledgerSnapshot\[0\]/.test(error.path) && /original accepting provider invocation/.test(error.message));
  assert.equal(JSON.stringify(data), before);
});

test('ledger creation receiveCount cannot be replaced by a later same-message retry count', () => {
  reject(data => { result(data, 'crash-after-fulfillment').ledgerSnapshot[0].receiveCount = 2; }, /ledgerSnapshot\[0\].*original accepting provider invocation/);
});

test('legitimate repeated provider reuse links to the original row and stays a supported pass', () => {
  const report = analyzeLocalReport(fixture());
  for (const id of ['crash-after-fulfillment', 'different-message-ids']) {
    const mode = analyzed(report, id); assert.equal(mode.receiptCount, 1);
    assert.equal(mode.result.providerInvocations.length, 2);
    assert.equal(mode.result.providerInvocations[1].returned.reused, true);
    const row = mode.result.ledgerSnapshot[0], original = mode.result.providerInvocations[0], reuse = mode.result.providerInvocations[1];
    assert.equal(row.invocationId, original.requestId); assert.notEqual(row.invocationId, reuse.requestId);
    assert.equal(row.messageId, original.payload.messageId); assert.equal(row.receiveCount, original.payload.receiveCount);
    if (id === 'different-message-ids') assert.notEqual(row.messageId, reuse.payload.messageId);
    else assert.notEqual(row.receiveCount, reuse.payload.receiveCount);
    assert.equal(mode.checks.find(value => value.id === 'provider-ledger-correlation').status, 'passed');
  }
});

test('opposite worker/provider/return claims become contradictions rather than passes', () => {
  reject(data => { const event = result(data).events.find(event => event.component === 'provider'); event.accepted = false; event.reused = true; }, /raw-derived unresolved/);
  reject(data => { result(data, 'different-message-ids').deliveries[1].returned.reused = false; }, /raw-derived unresolved/);
});

test('malformed fingerprint fields reject while valid changed fingerprints remain explicitly unauthenticated', () => {
  reject(data => { data.sourceSha256 = null; }, /object/);
  reject(data => { data.sourceSha256['src/worker.py'] = 'not-a-hash'; }, /fingerprint/);
  reject(data => { data.caseSha256['cases/local/no-fault.json'] = true; }, /fingerprint/);
  const data = fixture(); data.sourceSha256['src/worker.py'] = 'f'.repeat(64);
  const report = analyzeLocalReport(data); assert.equal(report.status, 'unverified'); assert.equal(report.fingerprints.sources['src/worker.py'], 'f'.repeat(64));
});

test('guard counters and forged guard passed flags are checked against raw entries', () => {
  reject(data => { data.noNetworkGuard.blockedOperationCount = 0; }, /counters/);
  reject(data => { data.noNetworkGuard.selfTests[0].blocked = false; }, /self-test outcomes/);
  reject(data => { data.runtime.isolated = 'true'; }, /boolean/);
});

test('input result order is irrelevant; output cases preserve the declared order', () => {
  const data = fixture(); data.results.reverse();
  assert.deepEqual(analyzeLocalReport(data).cases.map(value => value.id), ['no-fault', 'crash-after-fulfillment', 'different-message-ids', 'missing-observation', 'ambiguous-side-effect']);
});

test('browser global contract needs no Node APIs or DOM', () => {
  const context = vm.createContext({inputJSON: normalBytes}); vm.runInContext(fs.readFileSync(contractPath, 'utf8'), context);
  const report = vm.runInContext('ReplayGuardLocalReport.analyzeLocalReport(JSON.parse(inputJSON))', context);
  assert.equal(report.status, 'unverified'); assert.equal(report.cases.length, 5);
});
