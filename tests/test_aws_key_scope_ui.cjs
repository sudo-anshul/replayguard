'use strict';
/* Display-adapter controls only. These synthetic rows are not AWS evidence. */
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../ui/aws-key-scope-data.js'), 'utf8'), context);
const api = context.AwsKeyScopeData;
const copy = value => JSON.parse(JSON.stringify(value));
function fixture() {
  const orders = [{ orderId: 'A', sku: 'ONE', quantity: 1 }, { orderId: 'B', sku: 'ONE', quantity: 1 }];
  const ids = ['no-key', 'sku-key', 'order-key'], counts = [[2, 2], [1, 0], [1, 1]];
  const at = '2026-09-20T00:00:00Z';
  const evidence = { schemaVersion: 2, kind: 'replayguard-aws-key-scope-report', provenance: 'aws', runId: 'ui-mock', case: { orders, candidates: ids }, receipts: {}, events: [], ledgerObservations: [], collection: { lastLedgerReadAt: {} }, deployment: { stackArn: 'mock-stack' }, cleanup: { status: 'deleted', verified: true, stackArn: 'mock-stack', lastStackStatus: 'DELETE_COMPLETE' } };
  const verification = { experimentStatus: 'passed', operationalStatus: 'passed', runId: 'ui-mock', assertions: [], candidateResults: [] };
  ids.forEach((candidate, index) => {
    evidence.receipts[candidate] = orders.flatMap((order, oi) => Array.from({ length: counts[index][oi] }, (_, number) => ({ receiptId: candidate + oi + number, order: copy(order) })));
    evidence.ledgerObservations.push({ candidate, consistent: true, observedAt: at, items: copy(evidence.receipts[candidate]) });
    evidence.collection.lastLedgerReadAt[candidate] = at;
    verification.candidateResults.push({ candidate, status: index < 2 ? 'violation' : 'passed', receiptCounts: Object.fromEntries(orders.map((order, oi) => [order.orderId, counts[index][oi]])), assertions: [] });
  });
  return { evidence, view: { kind: 'replayguard-aws-key-scope-web-view', schemaVersion: 1, verification } };
}
test('browser counts derive from matching complete ledger queries while business violations stay violations', () => {
  const { evidence, view } = fixture(), model = api.inspect(evidence, view);
  assert.deepEqual(copy(model.rows.map(row => row.counts)), [{ A: 2, B: 2 }, { A: 1, B: 0 }, { A: 1, B: 1 }]);
  assert.deepEqual(copy(model.rows.map(row => row.status)), ['violation', 'violation', 'passed']);
  assert.equal(model.experimentStatus, 'passed');
});
test('altered generated counts become unresolved even when saved verification claims a pass', () => {
  const { evidence, view } = fixture();
  view.verification.candidateResults[0].receiptCounts.A = 1;
  const model = api.inspect(evidence, view);
  assert.equal(model.experimentStatus, 'unresolved');
  assert.equal(model.rows[0].status, 'unresolved');
  assert.equal(model.rows[0].counts.A, 2);
});
test('missing snapshot, mismatched query or stale final read never turns absent observations into zero', () => {
  for (const mutate of [e => { e.receipts['order-key'] = null; }, e => { e.ledgerObservations.at(-1).items = []; }, e => { e.collection.lastLedgerReadAt['order-key'] = '2026-09-20T00:01:00Z'; }]) {
    const { evidence, view } = fixture(); mutate(evidence);
    const model = api.inspect(evidence, view);
    assert.deepEqual(copy(model.rows[2].counts), { A: null, B: null });
    assert.equal(model.experimentStatus, 'unresolved');
  }
});
test('truthful incomplete query remains incomplete without manufacturing rejection', () => {
  const { evidence, view } = fixture(); evidence.receipts['sku-key'] = null;
  view.verification.experimentStatus = 'incomplete';
  Object.assign(view.verification.candidateResults[1], { status: 'incomplete', receiptCounts: { A: null, B: null } });
  const model = api.inspect(evidence, view);
  assert.equal(model.rows[1].status, 'incomplete');
  assert.equal(model.experimentStatus, 'incomplete');
});
test('extra real rows are counted instead of forcing the attractive two-receipt outcome', () => {
  const { evidence, view } = fixture();
  evidence.receipts['no-key'].push({ receiptId: 'extra', order: evidence.case.orders[0] });
  evidence.ledgerObservations[0].items = copy(evidence.receipts['no-key']);
  view.verification.candidateResults[0].receiptCounts.A = 3;
  assert.equal(api.inspect(evidence, view).rows[0].counts.A, 3);
});
test('bare cleanup boolean and a different stack do not establish deletion', () => {
  for (const mutate of [e => { delete e.cleanup.lastStackStatus; }, e => { e.cleanup.stackArn = 'another-stack'; }]) {
    const { evidence, view } = fixture(); mutate(evidence);
    const model = api.inspect(evidence, view);
    assert.equal(model.operationalStatus, 'unresolved');
    assert.equal(model.mismatch, true);
  }
});
test('local reports and another run cannot be displayed as the AWS comparison', () => {
  const { evidence, view } = fixture();
  assert.throws(() => api.inspect({ ...evidence, kind: 'replayguard-repair-report' }, view), /schema v2/);
  view.verification.runId = 'different-run';
  assert.throws(() => api.inspect(evidence, view), /different run/);
});
