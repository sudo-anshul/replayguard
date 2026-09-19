'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const referencePath = path.join(root, 'web/reference-repair.js');
const reference = require(referencePath);
const script = fs.readFileSync(referencePath, 'utf8');
const VERSION = '63bc428117f9df20427f2aa789c78ca61348845e';
const SOURCES = {
  worker: {path: 'src/worker.py', sha256: 'de7873c61f4d140e7229d7ae4eb1c03aaf0f2ec34b22d00291c25c7a3cea5b4f'},
  provider: {path: 'src/provider.py', sha256: '0c053a5cbf7f57da3aeb0fef2c2ddf6312682a70cdeccd9618bcbdccaeb91a8a'}
};
const RANGES = {
  workerRepair: ['worker', 105, 108],
  workerKey: ['worker', 65, 67],
  providerWrite: ['provider', 109, 129],
  providerSelection: ['provider', 86, 94],
  providerValidation: ['provider', 44, 46]
};

function assertDeepFrozen(value) {
  if (value && typeof value === 'object') {
    assert.equal(Object.isFrozen(value), true);
    Object.values(value).forEach(assertDeepFrozen);
  }
}

test('reference has a fixed source version and exact compact metadata schema', () => {
  assert.deepEqual(Object.keys(reference).sort(), ['excerpts', 'files', 'schemaVersion', 'version']);
  assert.equal(reference.schemaVersion, 1);
  assert.equal(reference.version, VERSION);
  assert.deepEqual(reference.files, SOURCES);
  assert.deepEqual(Object.keys(reference.excerpts).sort(), Object.keys(RANGES).sort());
});

for (const [name, file] of Object.entries(SOURCES)) {
  test(`${name} whole-file SHA-256 matches the reference source bytes`, () => {
    const bytes = fs.readFileSync(path.join(root, file.path));
    const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
    assert.equal(sha256, file.sha256, `${file.path} changed; the versioned repair reference must be reviewed`);
    assert.equal(reference.files[name].sha256, sha256);
  });
}

for (const [name, [file, start, end]] of Object.entries(RANGES)) {
  test(`${name} preserves exact source lines ${start}-${end}, including indentation and LF`, () => {
    const excerpt = reference.excerpts[name];
    assert.deepEqual(Object.keys(excerpt).sort(), ['end', 'file', 'start', 'text']);
    assert.equal(excerpt.file, file);
    assert.equal(excerpt.start, start);
    assert.equal(excerpt.end, end);
    const bytes = fs.readFileSync(path.join(root, SOURCES[file].path));
    const lines = bytes.toString('utf8').match(/[^\n]*\n|[^\n]+$/g);
    const expected = Buffer.from(lines.slice(start - 1, end).join(''), 'utf8');
    assert.deepEqual(Buffer.from(excerpt.text, 'utf8'), expected);
    assert.equal(excerpt.text.split('\n').length - 1, end - start + 1);
    assert.ok(excerpt.text.endsWith('\n'));
    assert.ok(excerpt.text.length < bytes.length / 2, 'an excerpt must stay focused, not duplicate a whole source file');
  });
}

test('CommonJS exports only recursively immutable reference data', () => {
  assertDeepFrozen(reference);
  assert.throws(() => { reference.version = 'changed'; }, TypeError);
  assert.throws(() => { reference.files.worker.sha256 = 'changed'; }, TypeError);
  assert.throws(() => { reference.excerpts.workerRepair.text = 'changed'; }, TypeError);
  assert.throws(() => { reference.excerpts.extra = {}; }, TypeError);
  assert.equal(Object.hasOwn(globalThis, 'ReplayGuardReferenceRepair'), false);
});

test('browser export matches Node data and prevents binding or nested mutation', () => {
  const context = vm.createContext({});
  vm.runInContext(script, context, {filename: 'reference-repair.js', timeout: 1000});
  const browser = context.ReplayGuardReferenceRepair;
  assert.deepEqual(JSON.parse(JSON.stringify(browser)), reference);
  assertDeepFrozen(browser);
  assert.deepEqual(Object.keys(context), ['ReplayGuardReferenceRepair']);
  const descriptor = Object.getOwnPropertyDescriptor(context, 'ReplayGuardReferenceRepair');
  assert.equal(descriptor.writable, false);
  assert.equal(descriptor.configurable, false);
  assert.throws(() => { context.ReplayGuardReferenceRepair = {}; }, TypeError);
  assert.throws(() => { browser.excerpts.providerWrite.text = 'changed'; }, TypeError);
  assert.equal(context.ReplayGuardReferenceRepair, browser);
});
