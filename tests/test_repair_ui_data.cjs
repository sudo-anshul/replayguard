'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const publicWeb = path.resolve(__dirname, '../web');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(publicWeb, 'repair-contract.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../ui/repair-data.js'), 'utf8'), context);
const api = context.ProposalData;
const fixture = JSON.parse(fs.readFileSync(path.join(publicWeb, 'repair-example.json'), 'utf8'));
const clone = value => JSON.parse(JSON.stringify(value));
const model = api.create(clone(fixture));
let checked = 0;
function check(name, run) { run(); checked += 1; console.log('PASS ' + name); }
function reaggregate(report) {
  const plans = new Map(report.cases.map(plan => [plan.id, plan]));
  const rank = { pass: 0, incomplete: 1, violation: 2, unresolved: 3 };
  const counts = { pass: 0, violation: 0, incomplete: 0, unresolved: 0 };
  let status = 'pass';
  for (const result of report.results) {
    result.status = context.RepairContract.assess(result, plans.get(result.caseId)).status;
    counts[result.status] += 1;
    if (rank[result.status] > rank[status]) status = result.status;
  }
  report.summary = { status, counts, exitCode: { pass: 0, violation: 1, incomplete: 2, unresolved: 3 }[status] };
  return report;
}

check('loads the actual schema-v2 report and presents the policies in explanatory order', () => {
  assert.equal(model.plans.size, 8);
  assert.deepEqual(clone(api.candidates(model).map(candidate => candidate.id)), ['no-key', 'overbroad-key', 'business-key']);
});
check('coverage includes failures and unavailable evidence across all eight cases', () => {
  assert.deepEqual(clone(api.coverage(model, 'no-key')), { pass: 2, violation: 4, incomplete: 1, unresolved: 1, total: 8 });
  assert.deepEqual(clone(api.coverage(model, 'overbroad-key')), { pass: 4, violation: 2, incomplete: 1, unresolved: 1, total: 8 });
  assert.deepEqual(clone(api.coverage(model, 'business-key')), { pass: 6, violation: 0, incomplete: 1, unresolved: 1, total: 8 });
  model.report.summary.counts.pass = 999;
  assert.equal(api.coverage(model, 'business-key').pass, 6);
  assert.throws(() => api.coverage(model, 'missing'), /candidate/);
});
check('each recorded delivery advances the actual receipt sequence without inventing a future receipt', () => {
  const expected = [
    [[0, 0], [0, 0], [0, 0]],
    [[1, 0], [1, 0], [1, 0]],
    [[1, 1], [1, 0], [1, 1]],
    [[2, 1], [1, 0], [1, 1]],
    [[2, 2], [1, 0], [1, 1]]
  ];
  for (let step = 0; step <= 4; step += 1) {
    const replay = api.replay(model, 'interleaved-retries', step);
    assert.equal(replay.total, 4);
    assert.equal(replay.basis, 'recorded-events');
    assert.equal(replay.complete, step === 4);
    assert.equal(replay.delivery && replay.delivery.deliveryId, step ? 'd' + step : null);
    assert.deepEqual(clone(replay.byCandidate.map(candidate => Object.values(candidate.counts))), expected[step]);
    for (const candidate of replay.byCandidate) {
      assert.equal(candidate.basis, 'recorded-events');
      assert(candidate.events.every(event => Number(event.deliveryId.slice(1)) <= step));
    }
  }
});
check('crash replay exposes a committed receipt followed by a fault; repair reuse never adds a receipt', () => {
  const first = api.replay(model, 'crash-retry', 1).byCandidate.find(candidate => candidate.id === 'business-key');
  assert.deepEqual(clone(first.events.map(event => event.type)), ['receipt-accepted', 'fault-injected']);
  assert.equal(first.receipts.length, 1);
  const last = api.replay(model, 'crash-retry', 2).byCandidate.find(candidate => candidate.id === 'business-key');
  assert.equal(last.receipts.length, 1);
  assert.equal(last.events.at(-1).type, 'receipt-reused');
});
check('the SKU collision is a real recorded conflict and leaves the second order without a receipt', () => {
  const collision = api.replay(model, 'interleaved-retries', 2).byCandidate.find(candidate => candidate.id === 'overbroad-key');
  assert.equal(collision.events.at(-1).type, 'payload-conflict');
  assert.equal(collision.counts['ORDER-B'], 0);
});
check('final recorded counts agree with independent snapshots in every fully observed supported example', () => {
  for (const plan of model.plans.values()) {
    if (plan.effectModel !== 'receiver-owned-receipt' || plan.observation === 'missing') continue;
    for (const candidate of api.replay(model, plan.id, plan.deliveries.length).byCandidate) {
      assert.deepEqual(clone(candidate.counts), clone(model.get(plan.id, candidate.id).counts));
    }
  }
});
check('missing snapshots retain an explicit unknown final verdict despite available event projections', () => {
  const view = model.get('missing-snapshot', 'business-key');
  const replay = api.replay(model, 'missing-snapshot', 1).byCandidate.find(candidate => candidate.id === 'business-key');
  assert.equal(view.counts['ORDER-A'], null);
  assert.equal(replay.snapshotAvailable, false);
  assert.match(replay.reason, /snapshot is missing/);
  assert.equal(replay.receipts[0].fromEventOnly, true);
  assert.match(api.describe(view).title, /snapshot is missing/);
});
check('unsupported external effects are unavailable, not clean empty successes', () => {
  const replay = api.replay(model, 'unsupported-effect', 0);
  assert.equal(replay.total, 0);
  replay.byCandidate.forEach(candidate => {
    assert.equal(candidate.available, false);
    assert.equal(candidate.supported, false);
    assert.equal(candidate.events.length, 0);
  });
  assert.match(api.describe(model.get('unsupported-effect', 'business-key')).detail, /No passing result/);
});
check('unattempted delivery records never appear as a successful zero-receipt replay', () => {
  const report = clone(fixture);
  const result = report.results.find(result => result.caseId === 'clean-orders' && result.candidateId === 'business-key');
  result.deliveries = [];
  result.events = [];
  result.receipts = null;
  result.execution.completedSchedule = false;
  result.execution.snapshotComplete = false;
  const incomplete = api.create(reaggregate(report));
  const replay = api.replay(incomplete, 'clean-orders', 1).byCandidate.find(candidate => candidate.id === 'business-key');
  assert.equal(replay.available, false);
  assert.equal(replay.counts['ORDER-A'], null);
  assert.match(replay.reason, /incomplete execution/);
});
check('verdict copy names the business result and distinguishes missing, duplicate, pass and unknown states', () => {
  assert.match(api.describe(model.get('interleaved-retries', 'overbroad-key')).title, /valid order disappeared/);
  assert.match(api.describe(model.get('crash-retry', 'no-key')).title, /more than once/);
  assert.match(api.describe(model.get('interleaved-retries', 'business-key')).title, /Every order/);
  assert.match(api.describe(model.get('crash-retry', 'business-key')).title, /One order/);
  assert.match(api.describe(null).title, /No result/);
  assert.equal(api.checkLabel({ id: 'order:ORDER-A' }), 'One correct receipt for ORDER-A');
  assert.equal(api.checkLabel({ id: 'delivery:d2' }), 'Delivery d2 met its expected outcome');
});
check('import validation rejects optimistic claimed status and contradictory evidence', () => {
  const optimistic = clone(fixture);
  optimistic.results.find(result => result.status === 'violation').status = 'pass';
  assert.throws(() => api.create(optimistic), /contradicts the observations/);
  const contradiction = clone(fixture);
  contradiction.results[0].receipts[0].order.quantity = 99;
  assert.throws(() => api.create(contradiction), /contradicts the independent receipt snapshot/);
});
check('unknown candidate names remain plain strings and custom candidates retain stable source order', () => {
  const report = clone(fixture);
  for (const id of ['custom-z', 'custom-a']) {
    const candidate = clone(report.candidates.find(candidate => candidate.id === 'business-key'));
    candidate.id = id;
    candidate.title = '<img src=x onerror=alert(1)>';
    report.candidates.push(candidate);
    const extra = report.results.filter(result => result.candidateId === 'business-key').map(result => ({ ...clone(result), candidateId: id }));
    report.results.push(...extra);
  }
  const custom = api.create(reaggregate(report));
  assert.deepEqual(clone(api.candidates(custom).map(candidate => candidate.id)), ['no-key', 'overbroad-key', 'business-key', 'custom-z', 'custom-a']);
  assert.equal(api.candidates(custom)[3].title, '<img src=x onerror=alert(1)>');
});
check('replay rejects fractional or missing case inputs and bounds integer steps safely', () => {
  assert.throws(() => api.replay(model, 'unknown', 1), /case/);
  assert.throws(() => api.replay(model, 'crash-retry', 0.5), /integer/);
  assert.equal(api.replay(model, 'crash-retry', -1).step, 0);
  assert.equal(api.replay(model, 'crash-retry', 99).step, 2);
});

console.log('\n' + checked + ' UI data checks passed against repair-example.json.');
