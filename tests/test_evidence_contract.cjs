'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const contractPath = path.join(root, 'web/evidence-contract.js');
const {analyzeEvidence, requiredAssertionIds} = require(contractPath);
const sampleBytes = fs.readFileSync(path.join(root, 'web/evidence.json'), 'utf8');
const fixture = () => JSON.parse(sampleBytes);
const byId = (result, id) => result.checks.find(check => check.id === id);
const receiptCheck = (result, mode, order = 'ORDER-1042') => byId(result, mode + '-' + order + '-receipt-count');
function rejects(change, expression = /./) {
  const data = fixture(); change(data);
  const before = JSON.stringify(data);
  assert.throws(() => analyzeEvidence(data), expression);
  assert.equal(JSON.stringify(data), before, 'rejection must not mutate the input');
}
function contradictoryFixture() {
  // Same mutation as supervisor review-02: a distinct second repaired receipt,
  // retaining the original row's key and every supplied passed claim.
  const data = fixture();
  data.receipts.repaired.push({...data.receipts.repaired[0], receiptId: 'review-only-contradictory-receipt'});
  return data;
}

test('legitimate shipped AWS evidence remains UNVERIFIED despite all supported checks', () => {
  const result = analyzeEvidence(fixture());
  assert.equal(result.status, 'unverified');
  assert.equal(result.claimedStatus, 'passed');
  assert.equal(result.provenanceAuthenticated, false);
  assert.equal(result.supportedChecksPassed, result.totalChecks);
  assert.equal(result.totalChecks, 18);
  assert.match(result.reasons.join(' '), /not authenticated/);
  assert.match(result.reasons.join(' '), /do not replace/);
});

test('exact supervisor contradiction shape becomes unresolved with count 2, never passed', () => {
  const data = contradictoryFixture();
  assert.equal(data.status, 'passed');
  assert.ok(data.assertions.every(claim => claim.status === 'passed'));
  const result = analyzeEvidence(data);
  assert.equal(result.status, 'unresolved');
  assert.equal(result.claimedStatus, 'passed');
  assert.equal(receiptCheck(result, 'repaired').status, 'unresolved');
  assert.equal(receiptCheck(result, 'repaired').expected, 1);
  assert.equal(receiptCheck(result, 'repaired').observed, 2);
  assert.equal(byId(result, 'repaired-ORDER-1042-same-receipt').status, 'unresolved');
  assert.ok(result.supportedChecksPassed < result.totalChecks);
});

test('supplied overall and assertion statuses are not a derived-result oracle', () => {
  for (const claim of ['passed', 'incomplete', 'unresolved']) {
    const data = fixture(); data.status = claim;
    data.assertions.forEach(assertion => { assertion.status = claim; assertion.expected = 'fabricated expectation'; assertion.observed = 'fabricated observation'; });
    const result = analyzeEvidence(data);
    assert.equal(result.status, 'unverified');
    assert.equal(result.claimedStatus, claim);
    assert.equal(receiptCheck(result, 'repaired').observed, 1);
    assert.ok(result.checks.every(check => check.status === 'passed'));
  }
});

test('analysis does not mutate frozen raw input and returns a separate rendering clone', () => {
  const data = fixture();
  function freeze(value) { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } }
  freeze(data);
  const before = JSON.stringify(data);
  const result = analyzeEvidence(data);
  assert.equal(JSON.stringify(data), before);
  assert.notEqual(result.data, data);
  assert.notEqual(result.data.receipts.repaired, data.receipts.repaired);
  result.data.receipts.repaired[0].receiptId = 'render-only-change';
  assert.equal(JSON.stringify(data), before);
});

for (const key of ['events', 'messages', 'assertions', 'queueObservations', 'apiErrors']) {
  test('missing ' + key + ' normalizes to [] and remains incomplete', () => {
    const data = fixture(); delete data[key];
    const before = JSON.stringify(data);
    const result = analyzeEvidence(data);
    assert.equal(result.status, 'incomplete');
    assert.deepEqual(result.data[key], []);
    assert.equal(JSON.stringify(data), before);
  });
  test('null or wrong-type ' + key + ' is rejected rather than treated as absent', () => {
    for (const value of [null, {}, '[]', 0, false]) rejects(data => { data[key] = value; }, new RegExp(key));
  });
}

for (const key of ['receipts', 'collection', 'inputs', 'artifacts', 'attempts', 'deployment']) {
  test('wrong-type object ' + key + ' is rejected transactionally', () => {
    for (const value of [null, [], 'object', 0, false]) rejects(data => { data[key] = value; }, new RegExp(key));
  });
}

test('empty assertion list and missing required assertion ID are incomplete', () => {
  const empty = fixture(); empty.assertions = [];
  const emptyResult = analyzeEvidence(empty);
  assert.equal(emptyResult.status, 'incomplete');
  assert.equal(byId(emptyResult, 'required-assertion-ids').status, 'incomplete');
  const missing = fixture(); missing.assertions = missing.assertions.filter(claim => claim.id !== 'queues-drained');
  const result = analyzeEvidence(missing);
  assert.equal(result.status, 'incomplete');
  assert.deepEqual(byId(result, 'required-assertion-ids').observed, ['queues-drained']);
});

test('empty receipts or missing handler receipt array cannot produce an apparent pass', () => {
  for (const mode of ['vulnerable', 'repaired']) {
    for (const absent of [false, true]) {
      const data = fixture();
      if (absent) delete data.receipts[mode]; else data.receipts[mode] = [];
      const result = analyzeEvidence(data);
      assert.equal(result.status, 'incomplete');
      assert.equal(receiptCheck(result, mode).status, 'incomplete');
      assert.equal(receiptCheck(result, mode).observed, 0);
    }
  }
});

test('receipt IDs are unique per handler and duplicate rows are rejected', () => {
  rejects(data => data.receipts.repaired.push({...data.receipts.repaired[0]}), /duplicates a receipt identity/);
  rejects(data => { data.receipts.vulnerable[1].receiptId = data.receipts.vulnerable[0].receiptId; }, /duplicates a receipt identity/);
});

test('receipt run, order, mode and submitted message mismatches reject', () => {
  for (const [key, value] of [['runId', 'different-run'], ['orderId', 'OTHER-ORDER'], ['mode', 'vulnerable'], ['messageId', 'different-message']]) {
    rejects(data => { data.receipts.repaired[0][key] = value; }, /match|order|group/);
  }
  rejects(data => { data.receipts.unknown = []; }, /mode/);
});

test('receipt payload and ledger-key contradictions derive unresolved', () => {
  for (const [key, value] of [['sku', 'OTHER-SKU'], ['quantity', 2], ['PK', 'OTHER-PARTITION'], ['SK', 'OTHER-KEY'], ['idempotencyKey', 'different-key']]) {
    const data = fixture(); data.receipts.repaired[0][key] = value;
    const result = analyzeEvidence(data);
    assert.equal(result.status, 'unresolved');
    assert.equal(byId(result, 'repaired-ledger-inputs').status, 'unresolved');
  }
});

test('receipt scalar types are strict, including nulls and booleans', () => {
  for (const [key, value] of [['receiptId', null], ['quantity', true], ['quantity', '1'], ['receiveCount', '1'], ['createdAt', 123], ['createdAt', 'not-a-date'], ['PK', {}], ['invocationId', null]]) {
    rejects(data => { data.receipts.repaired[0][key] = value; }, /receipts/);
  }
});

test('counts are per actual case order, not a total-row shortcut', () => {
  const data = fixture();
  const second = {orderId: 'ORDER-SECOND', sku: 'SECOND-SKU', quantity: 1};
  data.case.orders.push(second); data.inputs.orders.push({...second}); data.case.bounds.maxMessages = 4;
  for (const mode of ['vulnerable', 'repaired']) data.messages.push({mode, orderId: second.orderId, messageId: mode + '-second-message'});
  // Keep two total repaired rows, one for each order. This is not a duplicate.
  const original = data.receipts.repaired[0];
  data.receipts.repaired.push({...original, ...second, messageId: 'repaired-second-message', receiptId: 'second-key', idempotencyKey: 'second-key', SK: 'RECEIPT#second-key'});
  for (const id of requiredAssertionIds(data.case.orders)) if (!data.assertions.some(claim => claim.id === id)) data.assertions.push({id, label: id, status: 'passed'});
  const result = analyzeEvidence(data);
  assert.equal(receiptCheck(result, 'repaired').observed, 1);
  assert.equal(receiptCheck(result, 'repaired', 'ORDER-SECOND').observed, 1);
  assert.equal(receiptCheck(result, 'repaired', 'ORDER-SECOND').status, 'passed');
  assert.equal(receiptCheck(result, 'vulnerable', 'ORDER-SECOND').observed, 0);
  assert.equal(result.status, 'incomplete');
});

test('unsupported schema, local provenance, or invented claimed status rejects', () => {
  rejects(data => { data.schemaVersion = 2; }, /schemaVersion 1/);
  rejects(data => { data.schemaVersion = true; }, /schemaVersion 1/);
  rejects(data => { data.provenance = 'local-execution'; }, /python3 -I -S scripts\/run_local\.py/);
  rejects(data => { data.provenance = 'test-fixture'; }, /provenance/);
  rejects(data => { data.status = 'verified'; }, /supplied/);
  for (const value of [null, [], 'json']) assert.throws(() => analyzeEvidence(value), /object/);
});

test('event mode, run, order, source, and message identities are validated', () => {
  for (const [key, value] of [['runId', 'other-run'], ['orderId', 'UNKNOWN'], ['mode', 'other-mode'], ['source', 'provider'], ['messageId', 'other-message']]) {
    rejects(data => { data.events[0][key] = value; }, /match|order|mode|component/);
  }
  rejects(data => { data.events[0] = null; }, /object/);
  rejects(data => { data.events[0].receiveCount = '2'; }, /integer/);
  rejects(data => { data.events[0].eventTimestamp = '1000'; }, /integer/);
  rejects(data => { data.events[0].eventTimestamp = null; }, /integer/);
  rejects(data => { data.events[0].timestamp = 'invalid'; }, /timestamp/);
});

test('incompatible worker and provider request correlations reject', () => {
  rejects(data => { const receives = data.events.filter(event => event.stage === 'received' && event.mode === 'repaired'); receives[1].requestId = receives[0].requestId; }, /incompatible deliveries/);
  rejects(data => { const provider = data.events.find(event => event.source === 'provider' && event.mode === 'repaired'); const wrongWorker = data.events.find(event => event.source === 'worker' && event.mode === 'vulnerable'); provider.workerRequestId = wrongWorker.requestId; }, /different worker delivery/);
  rejects(data => { const providers = data.events.filter(event => event.source === 'provider'); providers[1].requestId = providers[0].requestId; }, /incompatible provider/);
});

test('missing provider observations or an unknown worker reference stays incomplete', () => {
  const absent = fixture(); absent.events = absent.events.filter(event => event.source !== 'provider');
  assert.equal(analyzeEvidence(absent).status, 'incomplete');
  assert.equal(byId(analyzeEvidence(absent), 'event-correlations').status, 'incomplete');
  const partialMode = fixture(); partialMode.events = partialMode.events.filter(event => event.mode !== 'repaired');
  assert.equal(byId(analyzeEvidence(partialMode), 'event-correlations').status, 'incomplete');
  const missing = fixture(); missing.events.find(event => event.source === 'provider').workerRequestId = 'unobserved-worker-request';
  assert.equal(analyzeEvidence(missing).status, 'incomplete');
});

test('receipt invocationId must link to its accepting provider request', () => {
  const data = fixture(); data.receipts.repaired[0].invocationId = 'unrelated-provider-request';
  const result = analyzeEvidence(data);
  assert.equal(result.status, 'incomplete');
  assert.equal(byId(result, 'event-correlations').status, 'incomplete');
  assert.equal(byId(result, 'event-correlations').observed.missingLedgerProviderReferences, 1);
});

test('orphan provider acceptance is incomplete despite supplied passes and a one-row repaired ledger', () => {
  const bytes = fs.readFileSync(path.join(__dirname, 'fixtures/orphan-provider-acceptance.json'));
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), '9291a53d007257e1c696bf464bcfe442d8b4922bdc7c163d0bc56efacec9b70b');
  const data = JSON.parse(bytes);
  const before = JSON.stringify(data);
  const result = analyzeEvidence(data);
  assert.equal(data.status, 'passed');
  assert.ok(data.assertions.every(claim => claim.status === 'passed'));
  assert.equal(result.status, 'incomplete');
  assert.equal(result.claimedStatus, 'passed');
  assert.equal(receiptCheck(result, 'repaired').observed, 1);
  assert.equal(byId(result, 'event-correlations').status, 'incomplete');
  assert.equal(byId(result, 'event-correlations').observed.missingAcceptedProviderReceipts, 1);
  assert.equal(JSON.stringify(data), before);
});

test('fresh acceptance cannot borrow a ledger row from another provider invocation', () => {
  const data = fixture();
  const accepted = data.events.find(event => event.source === 'provider' && event.mode === 'repaired' && event.stage === 'accepted');
  data.events.push({...accepted, requestId: 'other-accepting-provider-request', eventId: 'other-provider-event'});
  const result = analyzeEvidence(data);
  assert.equal(result.status, 'incomplete');
  assert.equal(byId(result, 'event-correlations').observed.missingAcceptedProviderReceipts, 1);
});

test('legitimate provider reuse needs only its original receipt, not a new retry receipt', () => {
  const data = fixture();
  const reused = data.events.find(event => event.source === 'provider' && event.mode === 'repaired' && event.stage === 'reused');
  const original = data.receipts.repaired[0];
  assert.equal(reused.receiptId, original.receiptId);
  assert.notEqual(reused.requestId, original.invocationId);
  assert.notEqual(reused.receiveCount, original.receiveCount);
  const result = analyzeEvidence(data);
  assert.equal(result.status, 'unverified');
  assert.equal(byId(result, 'event-correlations').status, 'passed');
  assert.equal(byId(result, 'event-correlations').observed.missingAcceptedProviderReceipts, 0);
});

test('opposite provider and worker acceptance claims are unresolved', () => {
  const data = fixture();
  const provider = data.events.find(event => event.source === 'provider' && event.mode === 'repaired' && event.stage === 'reused');
  provider.stage = 'accepted'; provider.accepted = true; provider.reused = false;
  const result = analyzeEvidence(data);
  assert.equal(result.status, 'unresolved');
  assert.equal(byId(result, 'event-correlations').status, 'unresolved');
  assert.equal(byId(result, 'event-correlations').observed.contraryProviderResponses, 1);
});

test('missing provider flags are incomplete and internally conflicting stage flags are unresolved', () => {
  const missing = fixture(); delete missing.events.find(event => event.source === 'provider').accepted;
  assert.equal(byId(analyzeEvidence(missing), 'event-correlations').status, 'incomplete');
  const contrary = fixture(); contrary.events.find(event => event.source === 'provider').reused = true;
  const result = analyzeEvidence(contrary);
  assert.equal(result.status, 'unresolved');
  assert.equal(byId(result, 'event-correlations').observed.contraryProviderStages, 1);
});

test('tampered attempts cannot replace missing raw delivery events', () => {
  const data = fixture(); data.events = [];
  assert.ok(data.attempts.repaired.length);
  const result = analyzeEvidence(data);
  assert.equal(result.status, 'incomplete');
  assert.equal(byId(result, 'repaired-ORDER-1042-redelivery').status, 'incomplete');
  rejects(value => { value.attempts.repaired[0].runId = 'another-run'; }, /runId/);
  rejects(value => { value.attempts.repaired = null; }, /array/);
});

test('missing completion and inverted retry timing are not supported passes', () => {
  const missing = fixture(); missing.events = missing.events.filter(event => event.stage !== 'completed');
  assert.equal(analyzeEvidence(missing).status, 'incomplete');
  const reversed = fixture();
  const retry = reversed.events.find(event => event.mode === 'repaired' && event.stage === 'received' && event.receiveCount === 2);
  retry.eventTimestamp += 200000;
  const result = analyzeEvidence(reversed);
  assert.equal(result.status, 'incomplete');
  assert.equal(byId(result, 'repaired-ORDER-1042-completed').status, 'incomplete');
});

test('a different fault condition or new acceptance on repaired retry is unresolved', () => {
  const fault = fixture(); fault.events.find(event => event.stage === 'fault_injected').fault = 'another-fault';
  assert.equal(analyzeEvidence(fault).status, 'unresolved');
  const acceptance = fixture(); const success = acceptance.events.find(event => event.mode === 'repaired' && event.stage === 'fulfillment_succeeded' && event.receiveCount === 2);
  success.accepted = true; success.reused = false;
  assert.equal(analyzeEvidence(acceptance).status, 'unresolved');
  rejects(data => { data.events.find(event => event.stage === 'fulfillment_succeeded').accepted = 'true'; }, /boolean/);
});

test('queue containers, counts, timestamps and optional run identity are validated', () => {
  for (const field of ['queue', 'dlq']) for (const value of [null, [], 'empty']) rejects(data => { data.queueObservations[0][field] = value; }, /object/);
  for (const value of ['0', false, -1, 0.5]) rejects(data => { data.queueObservations[0].queue.visible = value; }, /integer/);
  rejects(data => { data.queueObservations[0].observedAt = null; }, /timestamp/);
  rejects(data => { data.queueObservations[0].runId = 'other-run'; }, /runId/);
});

test('dead letters contradict the run and missing grace or final reads are incomplete', () => {
  const dead = fixture(); dead.queueObservations.at(-1).dlq.visible = 1;
  assert.equal(analyzeEvidence(dead).status, 'unresolved');
  const short = fixture(); short.queueObservations = short.queueObservations.slice(-1);
  assert.equal(analyzeEvidence(short).status, 'incomplete');
  const missing = fixture(); delete missing.collection.lastLedgerReadAt.repaired;
  assert.equal(analyzeEvidence(missing).status, 'incomplete');
  rejects(data => { data.collection.lastLedgerReadAt = null; }, /object/);
  rejects(data => { data.collection.lastLedgerReadAt.repaired = null; }, /timestamp/);
});

test('actual collection errors override supplied passed claims', () => {
  const data = fixture(); data.apiErrors.push({operation: 'logs.FilterLogEvents', code: 'AccessDenied', message: 'Observation missing'});
  assert.equal(analyzeEvidence(data).status, 'incomplete');
  const unparsed = fixture(); unparsed.collection.unparsedLogEvents = 1;
  assert.equal(analyzeEvidence(unparsed).status, 'incomplete');
  rejects(value => { value.collection.unparsedLogEvents = '0'; }, /integer/);
  rejects(value => { value.apiErrors = [null]; }, /object/);
});

test('timeouts, budget exhaustion and missing completion metadata remain incomplete', () => {
  for (const reason of ['Observation deadline reached', 'Read budget reached (300 AWS API calls)', 'Interrupted', '']) {
    const data = fixture(); data.collection.stopReason = reason;
    if (reason === '') assert.throws(() => analyzeEvidence(data), /nonempty string/);
    else { const result = analyzeEvidence(data); assert.equal(result.status, 'incomplete'); assert.equal(byId(result, 'collection-complete').status, 'incomplete'); }
  }
  const missing = fixture(); delete missing.collection.stopReason;
  assert.equal(byId(analyzeEvidence(missing), 'collection-complete').status, 'incomplete');
  const budget = fixture(); budget.collection.apiCalls = budget.collection.maxApiCalls + 1;
  assert.equal(byId(analyzeEvidence(budget), 'collection-complete').status, 'incomplete');
});

test('malformed, duplicate, or wrong-type assertion entries reject', () => {
  rejects(data => { data.assertions[0] = null; }, /object/);
  rejects(data => { data.assertions[0].status = true; }, /status/);
  rejects(data => { data.assertions[0].label = {}; }, /string/);
  rejects(data => { data.assertions.push({...data.assertions[0]}); }, /duplicated/);
});

test('case input identities and bounded quantities cannot be silently changed', () => {
  rejects(data => { data.inputs.orders[0].orderId = 'UNKNOWN'; }, /unknown/);
  rejects(data => { data.case.orders.push({...data.case.orders[0]}); }, /duplicate/);
  rejects(data => { data.case.orders[0].quantity = true; }, /integer/);
  rejects(data => { data.case.bounds.maxWaitSeconds = 10000; }, /integer/);
  rejects(data => { data.case.fault.type = 'none'; }, /supports only/);
  const mismatch = fixture(); mismatch.inputs.orders[0].quantity = 2;
  assert.equal(analyzeEvidence(mismatch).status, 'unresolved');
});

test('cyclic, nonfinite, accessor and prototype-polluting data cannot alter contract state', () => {
  const cycle = fixture(); cycle.extra = cycle;
  assert.throws(() => analyzeEvidence(cycle), /cyclic/);
  const nonfinite = fixture(); nonfinite.extra = Infinity;
  assert.throws(() => analyzeEvidence(nonfinite), /JSON values/);
  const accessor = fixture(); Object.defineProperty(accessor, 'bad', {enumerable: true, get() { throw new Error('getter must not run'); }});
  assert.throws(() => analyzeEvidence(accessor), /accessor/);
  const special = fixture(); Object.defineProperty(special, '__proto__', {value: {polluted: true}, enumerable: true});
  const result = analyzeEvidence(special);
  assert.equal({}.polluted, undefined);
  assert.equal(Object.getPrototypeOf(result.data), Object.prototype);
  assert.equal(Object.getOwnPropertyDescriptor(result.data, '__proto__').value.polluted, true);
});

test('same pure contract works as browser global without Node APIs or DOM', () => {
  const context = vm.createContext({inputJSON: sampleBytes});
  vm.runInContext(fs.readFileSync(contractPath, 'utf8'), context);
  const result = vm.runInContext('ReplayGuardEvidence.analyzeEvidence(JSON.parse(inputJSON))', context);
  assert.equal(result.status, 'unverified');
  assert.equal(result.provenanceAuthenticated, false);
  assert.equal(result.supportedChecksPassed, result.totalChecks);
});
