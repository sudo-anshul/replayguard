'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const context = vm.createContext({ TextDecoder, TextEncoder, Uint8Array });
for (const name of ['web/repair-contract.js', 'ui/repair-data.js', 'ui/repair-imports.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, name), 'utf8'), context);
}
const api = context.RepairImports;
const raw = fs.readFileSync(path.join(root, 'web/repair-example.json'));
const transfer = fs.readFileSync(path.join(root, 'web/repair-transfer.json'));
const clone = value => JSON.parse(JSON.stringify(value));
const file = (name, bytes, read) => ({ name, size: bytes.length, arrayBuffer: read || (() => Promise.resolve(Uint8Array.from(bytes).buffer)) });
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test('recorded and synthetic-transfer reports keep their separate original bytes and validated verdicts', () => {
  const local = api.decode(Uint8Array.from(raw), 'recording.json');
  const other = api.decode(Uint8Array.from(transfer), 'dispatchdesk.json');
  assert.equal(Buffer.compare(Buffer.from(local.bytes), raw), 0);
  assert.equal(Buffer.compare(Buffer.from(other.bytes), transfer), 0);
  assert.equal(local.model.get('interleaved-retries', 'overbroad-key').counts['ORDER-B'], 0);
  assert.equal(other.model.plans.size, 5);
  for (const result of other.model.results.values()) assert.equal(result.status, 'pass');
});

test('UTF-8 BOM, CRLF formatting and whitespace survive original-byte export', () => {
  const bytes = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('\r\n ' + raw.toString().replaceAll('\n', '\r\n') + '\r\n')]);
  const report = api.decode(Uint8Array.from(bytes), 'formatted.json');
  assert.equal(Buffer.compare(Buffer.from(report.bytes), bytes), 0);
  const snapshot = Buffer.from(report.bytes);
  bytes.fill(0);
  assert.equal(Buffer.compare(Buffer.from(report.bytes), snapshot), 0, 'stored bytes must not alias a caller buffer');
});

test('malformed UTF-8, invalid JSON and oversized data never reach report validation', () => {
  assert.throws(() => api.decode(new Uint8Array([0xc3, 0x28]), 'invalid.json'), /UTF-8/);
  assert.throws(() => api.decode(new TextEncoder().encode('{'), 'invalid.json'), /valid JSON/);
  assert.throws(() => api.decode(new Uint8Array(api.MAX_BYTES + 1), 'large.json'), /8 MiB/);
});

test('optimistic summaries and receipt contradictions cannot become an accepted import', async () => {
  let active = api.decode(Uint8Array.from(transfer), 'previous.json');
  const previous = active;
  const loader = api.createLoader(entry => { active = entry; });
  const optimistic = JSON.parse(raw);
  optimistic.summary.status = 'pass'; optimistic.summary.exitCode = 0;
  const first = await loader.load(file('false-pass.json', Buffer.from(JSON.stringify(optimistic))));
  assert.equal(first.status, 'rejected');
  assert.equal(active, previous);
  const contradictory = JSON.parse(raw);
  contradictory.results[0].receipts[0].order.quantity = 99;
  const second = await loader.load(file('contradiction.json', Buffer.from(JSON.stringify(contradictory))));
  assert.equal(second.status, 'rejected');
  assert.equal(active, previous);
  assert.equal(Buffer.compare(Buffer.from(active.bytes), transfer), 0);
});

test('a later import wins when an earlier file read completes last', async () => {
  const first = deferred(), commits = [];
  const loader = api.createLoader(entry => commits.push(entry.name));
  const slow = loader.load(file('slow.json', raw, () => first.promise));
  const fast = await loader.load(file('newer.json', transfer));
  first.resolve(Uint8Array.from(raw).buffer);
  assert.equal(fast.status, 'accepted');
  assert.equal((await slow).status, 'superseded');
  assert.deepEqual(commits, ['newer.json']);
});

test('a stale rejected read cannot replace newer import feedback', async () => {
  const first = deferred(), commits = [];
  const loader = api.createLoader(entry => commits.push(entry.name));
  const stale = loader.load(file('stale.json', raw, () => first.promise));
  assert.equal((await loader.load(file('latest.json', transfer))).status, 'accepted');
  first.reject(new Error('read failed'));
  assert.equal((await stale).status, 'superseded');
  assert.deepEqual(commits, ['latest.json']);
});

test('explicit source selection cancels an unfinished import without committing it', async () => {
  const first = deferred(), commits = [];
  const loader = api.createLoader(entry => commits.push(entry.name));
  const pending = loader.load(file('pending.json', raw, () => first.promise));
  loader.cancel();
  first.resolve(Uint8Array.from(raw).buffer);
  assert.equal((await pending).status, 'superseded');
  assert.deepEqual(commits, []);
});

test('a rendering rejection is returned to the UI as a failed transaction', async () => {
  const loader = api.createLoader(() => { throw new Error('render transaction rolled back'); });
  const outcome = await loader.load(file('valid.json', raw));
  assert.equal(outcome.status, 'rejected');
  assert.match(outcome.error.message, /rolled back/);
});

test('unusual optional metadata is retained as data without changing the evidence model', () => {
  const report = JSON.parse(transfer);
  report.recordedAt = { accidental: 'non-string' };
  report.startedAt = 123;
  report.candidates[0].sourceHashScope = { accidental: 'non-string' };
  report.candidates[0].title = '<img src=x onerror=alert(1)>';
  const imported = api.decode(new TextEncoder().encode(JSON.stringify(report)), 'metadata.json');
  assert.equal(imported.model.candidates.values().next().value.title, '<img src=x onerror=alert(1)>');
  for (const result of imported.model.results.values()) assert.equal(result.status, 'pass');
  assert.deepEqual(clone(imported.model.report.recordedAt), { accidental: 'non-string' });
});
