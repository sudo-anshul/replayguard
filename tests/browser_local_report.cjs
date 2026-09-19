#!/usr/bin/env node
/* Local-only browser workflow regression for reports from the unchanged local runner.
   Requires an already-installed Playwright package and Chromium; never installs them.
   node tests/browser_local_report.cjs
   Options: --base http://127.0.0.1:8088 --out docs/iteration-03
            --normal /path/local-results.json --mutated /path/broken-key-results.json
   Start the static site separately. No AWS APIs, remote requests, or source changes.
   Exit 0: all checked; 1: functional failure; 2: incomplete browser capability. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const args = process.argv.slice(2);
const option = (key, fallback) => { const i = args.indexOf(key); return i >= 0 ? args[i + 1] : fallback; };
const root = path.resolve(__dirname, '..');
const base = option('--base', 'http://127.0.0.1:8088/recorded-lab.html');
const loopback = ['127.0.0.1', 'localhost', '[::1]'];
if (!loopback.includes(new URL(base).hostname)) throw Error('Only loopback URLs are allowed.');
const out = path.resolve(root, option('--out', 'docs/iteration-03'));
const normalPath = path.resolve(root, option('--normal', 'docs/iteration-03/generated/local-results.json'));
const mutatedPath = path.resolve(root, option('--mutated', 'docs/iteration-03/generated/broken-key-results.json'));
for (const file of [normalPath, mutatedPath]) if (!fs.existsSync(file)) throw Error('Missing real runner report: ' + file);
const normalBytes = fs.readFileSync(normalPath), mutatedBytes = fs.readFileSync(mutatedPath);
const normal = JSON.parse(normalBytes), mutated = JSON.parse(mutatedBytes);
const digest = value => crypto.createHash('sha256').update(value).digest('hex');
const fileDigest = file => digest(fs.readFileSync(file));
function installedPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE_PATH, 'playwright', path.resolve(path.dirname(process.execPath), '../lib/node_modules/@playwright/cli/node_modules/playwright')].filter(Boolean);
  for (const candidate of candidates) { try { return require(candidate); } catch {} }
  throw Error('An installed Playwright package is required. Set PLAYWRIGHT_MODULE_PATH; this script never installs dependencies.');
}
const { chromium } = installedPlaywright();
fs.mkdirSync(out, { recursive: true });
const protectedFiles = ['src/worker.py', 'src/provider.py', 'scripts/run_local.py', 'web/evidence.json', 'web/regression-case.zip', 'evidence/latest.json'];
const fingerprints = () => Object.fromEntries(protectedFiles.map(file => [file, fileDigest(path.join(root, file))]));
const beforeFingerprints = fingerprints();
const checks = [], blockedRequests = [], pageErrors = [], requests = [];
const report = { startedAt: new Date().toISOString(), base, fixtures: { normal: { path: path.relative(root, normalPath), sha256: digest(normalBytes) }, mutated: { path: path.relative(root, mutatedPath), sha256: digest(mutatedBytes) } }, checks, blockedRequests, pageErrors, requests };
const caseIds = ['no-fault', 'crash-after-fulfillment', 'different-message-ids', 'missing-observation', 'ambiguous-side-effect'];
const expected = {
  'no-fault': { vulnerable: ['pass', '1'], repaired: ['pass', '1'] },
  'crash-after-fulfillment': { vulnerable: ['violation', '2'], repaired: ['pass', '1'] },
  'different-message-ids': { vulnerable: ['violation', '2'], repaired: ['pass', '1'] },
  'missing-observation': { vulnerable: ['incomplete', null], repaired: ['incomplete', null] },
  'ambiguous-side-effect': { vulnerable: ['unresolved', null], repaired: ['unresolved', null] },
};
let browser;
(async () => {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (loopback.includes(url.hostname) || url.protocol === 'blob:') return route.continue();
    blockedRequests.push(route.request().url()); await route.abort();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  const read = async selector => (await page.locator(selector).textContent()).trim();
  async function check(name, operation) {
    try { checks.push({ name, status: 'passed', observed: await operation() }); }
    catch (error) { checks.push({ name, status: 'failed', error: error.message }); }
  }
  async function settled() { await page.waitForFunction(() => document.querySelector('#run-status')?.textContent.trim() !== 'LOADING' && !/loading/i.test(document.querySelector('#evidence-title')?.textContent || '')); }
  async function upload(value, name = 'browser-fixture.json') {
    await page.locator('#evidence-upload').setInputFiles([]);
    const previous = await read('#import-message');
    await page.locator('#evidence-upload').setInputFiles(typeof value === 'string' ? value : { name, mimeType: 'application/json', buffer: Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value)) });
    await page.waitForFunction(old => { const node = document.querySelector('#import-message'); return node && node.textContent.trim() !== old && node.textContent.trim().length > 0; }, previous);
  }
  async function downloadBytes() {
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#download-evidence').click()]);
    const stream = await download.createReadStream(), chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    return Buffer.concat(chunks);
  }
  async function snapshot() {
    return page.evaluate(() => ({
      text: Object.fromEntries(['run-status', 'source-badge', 'claimed-verdict', 'verification-summary', 'verification-reasons', 'evidence-title', 'evidence-subtitle', 'vulnerable-business-state', 'repaired-business-state', 'vulnerable-run-id', 'repaired-run-id', 'vulnerable-count', 'repaired-count', 'vulnerable-attempts', 'repaired-attempts', 'vulnerable-receipts', 'repaired-receipts', 'timeline', 'assertions', 'assertion-counter', 'remaining-assertions', 'evidence-file-label', 'fingerprints'].map(id => [id, document.getElementById(id)?.textContent])),
      source: document.querySelector('#source-choice')?.value,
      case: document.querySelector('#case-selector')?.value,
      modes: [...document.querySelectorAll('button[data-mode]')].map(node => [node.dataset.mode, node.getAttribute('aria-pressed')]),
    }));
  }
  async function selectCase(id) { await page.locator('#case-selector').selectOption(id); }
  async function selectSource(value) { await page.locator('#source-choice').selectOption(value); await page.waitForFunction(expected => document.querySelector('#source-choice')?.value === expected, value); await settled(); }
  async function shot(name, selector) {
    // Capture at scroll origin so off-screen fixed elements are not painted into
    // a tall element screenshot by Chromium's beyond-viewport compositor.
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    const options = { path: path.join(out, name) };
    if (selector) { options.clip = await page.locator(selector).boundingBox(); options.fullPage = true; }
    await page.screenshot(options);
  }
  async function validateRow(id, mode, source = normal) {
    const row = source.results.find(row => row.caseId === id && row.mode === mode);
    assert(row, 'Missing fixture row');
    const state = await read('#' + mode + '-business-state');
    assert(new RegExp('\\b' + row.observedStatus + '(?:ed)?\\b', 'i').test(state), `${id}/${mode} should show ${row.observedStatus}, got ${state}`);
    assert((await read('#' + mode + '-run-id')).includes(row.runId), 'Visible run ID does not belong to selected case/mode.');
    const count = await read('#' + mode + '-count');
    if (row.ledgerSnapshot === null) assert(/unknown|—|\?/i.test(count) && count !== '0', 'A missing ledger must show an unknown count, never zero.');
    else assert(count === String(row.ledgerSnapshot.length), 'Receipt count does not match selected row ledger.');
    const cards = await page.locator('#' + mode + '-receipts .receipt-ticket').count();
    assert(cards === (row.ledgerSnapshot?.length || 0), 'Receipt cards from another case survived.');
    await page.locator('button[data-mode="' + mode + '"]').click();
    assert(await page.locator('button[data-mode="' + mode + '"]').getAttribute('aria-pressed') === 'true', 'Selected trace does not announce its pressed state.');
    const timeline = await read('#timeline');
    if (row.events.length) {
      assert(await page.locator('#timeline li:not(.empty-state)').count() === row.events.length, 'Trace event count differs from the selected case/mode.');
      assert(!/not executed/i.test(timeline), 'Executed trace is mislabeled as not executed.');
      for (const receiptId of new Set(row.events.map(event => event.receiptId).filter(Boolean))) assert(timeline.includes(receiptId.slice(0, 12)), 'Selected trace is missing its own receipt identity.');
      const otherRow = source.results.find(item => item.caseId === id && item.mode !== mode);
      for (const receiptId of new Set(otherRow.events.map(event => event.receiptId).filter(Boolean))) assert(!timeline.includes(receiptId.slice(0, 12)), 'Selected trace contains the other handler\'s receipt identity.');
    } else assert(/not executed|no execution|unsupported/i.test(timeline), 'Unsupported case must explicitly state that it did not execute.');
    return { state, count, runId: row.runId, receiptCards: cards, traceEvents: row.events.length, executionPerformed: row.execution.performed };
  }

  await page.goto(base, { waitUntil: 'networkidle' }); await settled();
  await check('initial historical AWS sample remains unverified', async () => {
    assert(await read('#run-status') === 'UNVERIFIED', 'Archived AWS source must remain UNVERIFIED.');
    return { status: await read('#run-status'), source: await read('#source-badge') };
  });
  await check('fresh normal local report imports with five selectable cases', async () => {
    await upload(normalPath);
    assert(!/rejected|failed to import/i.test(await read('#import-message')), 'Fresh local runner report was rejected.');
    assert(/local/i.test(await read('#source-badge')), 'Local execution source must be explicit.');
    const options = await page.locator('#case-selector option').evaluateAll(nodes => nodes.map(node => node.value));
    assert(JSON.stringify([...options].sort()) === JSON.stringify([...caseIds].sort()), 'Case selector does not contain the exact five cases.');
    assert(await page.locator('#case-selector').inputValue() === 'crash-after-fulfillment', 'Crash-after-fulfillment should be selected on first local import.');
    const experiment = await read('#suite-summary');
    assert(/10\s*\/\s*10/.test(experiment), 'Expected suite outcomes must report 10/10 matched.');
    assert(/suite/i.test(experiment) && /expected|expectation/i.test(experiment), 'Suite result must be labeled as expectations, distinct from handler safety.');
    await shot('after-normal-desktop.png'); await shot('after-normal-experiment.png', '#experiment');
    return { source: await read('#source-badge'), suiteStatus: await read('#run-status'), options, importMessage: await read('#import-message') };
  });
  for (const id of caseIds) await check('case ' + id + ' keeps both handlers and traces distinct', async () => {
    await selectCase(id);
    const rows = {};
    for (const mode of ['vulnerable', 'repaired']) {
      const row = normal.results.find(row => row.caseId === id && row.mode === mode);
      assert(row.observedStatus === expected[id][mode][0], 'The baseline fixture changed expected business outcomes.');
      rows[mode] = await validateRow(id, mode);
    }
    if (id === 'missing-observation') {
      assert(!/\bpass(?:ed)?\b/i.test(await read('#repaired-business-state')), 'Missing observation cannot be a business pass.');
      await shot('after-missing-observation.png', '#receipts');
    }
    if (id === 'ambiguous-side-effect') {
      const receipts = await read('#receipts');
      assert(/not executed|no execution|unsupported/i.test(receipts), 'Unsupported case must have an explicit no-execution explanation.');
      assert(await read('#vulnerable-attempts') === '0' && await read('#repaired-attempts') === '0', 'Unsupported case must not claim handler invocations.');
      await shot('after-unsupported-case.png', '#receipts');
    }
    if (id === 'different-message-ids') await shot('after-different-message-ids.png', '#receipts');
    return rows;
  });
  await check('source and case fingerprints remain inspectable by keyboard', async () => {
    const summary = page.locator('#fingerprints > summary'); await summary.focus(); await page.keyboard.press('Enter');
    assert(await page.locator('#fingerprints').evaluate(node => node.open), 'Fingerprint details did not open with keyboard.');
    const text = await read('#fingerprints');
    for (const value of Object.values(normal.sourceSha256)) assert(text.includes(value), 'Exact source fingerprint missing.');
    for (const id of caseIds) {
      await selectCase(id);
      assert((await read('#fingerprints')).includes(normal.caseSha256['cases/local/' + id + '.json']), 'Selected case fingerprint missing.');
    }
    await shot('after-fingerprints.png', '#fingerprints');
    await summary.focus(); await page.keyboard.press('Enter'); return { sourceFingerprints: Object.keys(normal.sourceSha256).length, caseFingerprints: Object.keys(normal.caseSha256).length };
  });
  await check('broken-key runner report shows repaired violation and suite mismatch', async () => {
    await upload(mutatedPath); await selectCase('crash-after-fulfillment');
    const row = await validateRow('crash-after-fulfillment', 'repaired', mutated);
    assert(/violation/i.test(row.state) && row.count === '2', 'Broken repair must display duplicate fulfillment.');
    const experiment = await read('#suite-summary');
    assert(/8\s*\/\s*10/.test(experiment), 'Mutated suite must display 8/10 expectations matched.');
    assert(/mismatch|failed|not matched/i.test(await read('#experiment')), 'Expected outcome mismatch must be explicit.');
    assert((await read('#fingerprints')).includes(mutated.sourceSha256['src/worker.py']), 'Mutated worker fingerprint must replace the normal one.');
    await shot('after-broken-key-desktop.png'); await shot('after-broken-key-experiment.png', '#experiment'); await shot('after-broken-key-receipts.png', '#receipts');
    await selectCase('different-message-ids'); await validateRow('different-message-ids', 'repaired', mutated);
    return { repaired: row, suiteStatus: await read('#run-status'), workerSha256: mutated.sourceSha256['src/worker.py'] };
  });
  await check('raw local JSON dialog and download preserve exact original bytes', async () => {
    await page.locator('#view-evidence').click();
    assert(await page.locator('#json-content').textContent() === mutatedBytes.toString(), 'Dialog rewrote the original JSON.');
    await page.keyboard.press('Escape');
    assert((await downloadBytes()).equals(mutatedBytes), 'Download differs from imported bytes.');
    return { dialogExact: true, downloadExact: true, sha256: digest(mutatedBytes) };
  });

  const invalid = [
    ['malformed JSON', Buffer.from('{"provenance":"local-execution", bad'), 'malformed.json'],
    ['mixed-case row', (() => { const value = structuredClone(normal); value.results[2].case.id = 'no-fault'; return value; })(), 'mixed-case.json'],
    ['mixed-run row', (() => { const value = structuredClone(normal); value.results[3].runId = value.results[0].runId; return value; })(), 'mixed-run.json'],
    ['duplicate case/mode row', (() => { const value = structuredClone(normal); value.results.push(structuredClone(value.results[2])); return value; })(), 'duplicate-row.json'],
    ['forged handler outcome flags', (() => { const value = structuredClone(mutated); for (const row of value.results) if (row.mode === 'repaired' && row.observedStatus === 'violation') { row.observedStatus = 'pass'; row.exitCode = 0; row.expectationMatched = true; } Object.assign(value.suite, { status: 'passed', exitCode: 0, expectationsMatched: true, matchedCount: 10, allHandlersSafe: true }); return value; })(), 'forged-handler-flags.json'],
    ['forged suite safety flag', (() => { const value = structuredClone(normal); value.suite.allHandlersSafe = true; return value; })(), 'forged-suite-flag.json'],
  ];
  for (const [name, value, filename] of invalid) await check(name + ' rejects without changing prior view or download bytes', async () => {
    const before = await snapshot();
    await upload(value, filename);
    assert(/reject|invalid|could not|failed/i.test(await read('#import-message')), 'Invalid report was not rejected visibly.');
    assert(JSON.stringify(before) === JSON.stringify(await snapshot()), 'Rejected import changed the prior displayed state.');
    assert((await downloadBytes()).equals(mutatedBytes), 'Rejected import changed raw downloadable bytes.');
    return { displayedStatePreserved: true, downloadBytesPreserved: true, message: await read('#import-message') };
  });
  await shot('after-rejected-local-import.png', '.evidence-tools');
  await check('source selector returns to historical AWS and back to imported local data', async () => {
    await selectSource('aws-sample');
    assert(await read('#run-status') === 'UNVERIFIED', 'Recorded AWS source must remain UNVERIFIED.');
    assert(await read('#vulnerable-count') === '2' && await read('#repaired-count') === '1', 'Recorded AWS receipts did not restore.');
    assert((await downloadBytes()).equals(fs.readFileSync(path.join(root, 'web/evidence.json'))), 'AWS selection downloadable bytes are incorrect.');
    await selectSource('import'); await selectCase('crash-after-fulfillment');
    await validateRow('crash-after-fulfillment', 'repaired', mutated);
    assert((await downloadBytes()).equals(mutatedBytes), 'Returning to imported source lost original bytes.');
    await page.locator('#restore-sample').click(); await settled();
    await page.waitForFunction(() => document.querySelector('#source-choice')?.value === 'aws-sample');
    assert(await read('#run-status') === 'UNVERIFIED', 'Restore recorded sample did not return to AWS.');
    await selectSource('local-sample');
    assert(/local/i.test(await read('#source-badge')), 'Bundled local source must be explicit.');
    assert((await downloadBytes()).equals(fs.readFileSync(path.join(root, 'web/local-example.json'))), 'Bundled local download bytes are incorrect.');
    return { awsRestored: true, importedRetained: true, bundledLocalSource: await read('#source-badge') };
  });
  const probePage = await context.newPage();
  const keyboardProbe = { browser: browser.version(), platform: process.platform, headless: true, recordedAt: new Date().toISOString(), explanation: 'Plain HTML controls with no application handlers isolate browser native popup support from application behavior.', expected: ['one', 'two', 'one', 'one'], observed: {} };
  try {
    await probePage.setContent('<label for="native">Native popup</label><select id="native"><option value="one">One</option><option value="two" selected>Two</option><option value="three">Three</option></select><label for="list">Rendered listbox</label><select id="list" size="3"><option value="one">One</option><option value="two" selected>Two</option><option value="three">Three</option></select>');
    for (const id of ['native', 'list']) {
      await probePage.locator('#' + id).focus(); keyboardProbe.observed[id] = [];
      for (const key of ['Home', 'ArrowDown', 'ArrowUp', 'Enter']) { await probePage.keyboard.press(key); keyboardProbe.observed[id].push({ key, value: await probePage.locator('#' + id).inputValue() }); }
    }
  } finally { await probePage.close(); }
  keyboardProbe.nativePopupSupported = JSON.stringify(keyboardProbe.observed.native.map(item => item.value)) === JSON.stringify(keyboardProbe.expected);
  report.keyboardSelectProbe = keyboardProbe;
  fs.writeFileSync(path.join(out, 'keyboard-select-probe.json'), JSON.stringify(keyboardProbe, null, 2) + '\n');
  if (!keyboardProbe.nativePopupSupported) checks.push({ name: 'native popup keyboard selection for source and case', status: 'incomplete', reason: 'The installed headless browser does not change even a plain native select using Home/Arrow/Enter. Source/case changes are verified with selectOption; popup keyboard selection needs a browser environment with native menu support.', observed: keyboardProbe });
  else await check('native popup keyboard selection for source and case', async () => {
    await page.locator('#source-choice').focus(); await page.keyboard.press('Home'); await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#source-choice')?.value === 'aws-sample');
    await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#source-choice')?.value === 'local-sample');
    await page.locator('#case-selector').focus(); await page.keyboard.press('Home'); await page.keyboard.press('Enter');
    assert(await page.locator('#case-selector').inputValue() === 'no-fault', 'Home/Enter did not choose first case.');
    await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
    assert(await page.locator('#case-selector').inputValue() === 'crash-after-fulfillment', 'ArrowDown/Enter did not choose crash case.');
    return { sourceAndCaseKeyboardSelection: true };
  });
  await check('keyboard focus reaches labeled source/case controls, trace buttons, and JSON dialog', async () => {
    await page.keyboard.press('Escape'); await selectSource('local-sample'); await selectCase('crash-after-fulfillment');
    assert(await page.getByLabel('Evidence source', { exact: true }).getAttribute('id') === 'source-choice', 'Source control is missing its programmatic label.');
    assert(await page.getByLabel('Regression case', { exact: true }).getAttribute('id') === 'case-selector', 'Case control is missing its programmatic label.');
    await page.locator('#source-choice').focus(); await page.keyboard.press('Tab');
    assert(await page.locator('#import-report-trigger').evaluate(node => node === document.activeElement), 'Tab does not reach the import button after the source control.');
    await page.keyboard.press('Tab');
    assert(await page.locator('#case-selector').evaluate(node => node === document.activeElement), 'Tab does not reach the case selector.');
    await page.keyboard.press('Shift+Tab');
    assert(await page.locator('#import-report-trigger').evaluate(node => node === document.activeElement), 'Reverse Tab does not return from the case selector.');
    await page.locator('button[data-mode="repaired"]').focus(); await page.keyboard.press('Enter');
    assert(await page.locator('button[data-mode="repaired"]').getAttribute('aria-pressed') === 'true', 'Keyboard did not activate repaired trace.');
    await page.locator('#view-evidence').focus(); await page.keyboard.press('Enter');
    assert(await page.locator('#json-dialog').isVisible(), 'Keyboard did not open JSON dialog.');
    const focus = [];
    try {
      for (let i = 0; i < 5; i++) {
        await page.keyboard.press('Tab');
        const state = await page.evaluate(() => ({ id: document.activeElement.id, inside: document.querySelector('#json-dialog').contains(document.activeElement) }));
        assert(state.inside, 'Tab escaped JSON dialog.'); focus.push(state);
      }
    } finally { await page.keyboard.press('Escape'); }
    assert(!await page.locator('#json-dialog').isVisible(), 'Escape did not close JSON dialog.');
    assert(await page.locator('#view-evidence').evaluate(node => node === document.activeElement), 'Closing dialog did not restore trigger focus.');
    return { sourceAndCaseLabelsAndTabOrder: true, traceKeyboardNavigation: true, dialogFocus: focus, focusReturned: true };
  });
  for (const width of [390, 320]) await check('local report reflows at ' + width + 'px', async () => {
    await page.setViewportSize({ width, height: 844 });
    await selectSource('local-sample'); await selectCase('crash-after-fulfillment');
    await page.keyboard.press('Escape');
    await page.locator('#receipt-title').click();
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth, body: document.body.scrollWidth, document: document.documentElement.scrollWidth }));
    assert(dimensions.body <= width && dimensions.document <= width, 'Normal local report overflows horizontally.');
    await shot('local-controls-' + width + '.png', '#experiment'); await shot('local-receipts-' + width + '.png', '#receipts');
    await selectSource('import'); await selectCase('crash-after-fulfillment');
    await page.locator('#receipt-title').click();
    const mutatedDimensions = await page.evaluate(() => ({ viewport: innerWidth, body: document.body.scrollWidth, document: document.documentElement.scrollWidth }));
    assert(mutatedDimensions.body <= width && mutatedDimensions.document <= width, 'Broken-key local report overflows horizontally.');
    await shot('broken-key-receipts-' + width + '.png', '#receipts');
    await shot('local-evidence-tools-' + width + '.png', '.evidence-tools');
    return { normal: dimensions, mutated: mutatedDimensions };
  });
  await check('handler source, runner, and archived AWS artifacts remain byte-identical', async () => {
    const after = fingerprints(); assert(JSON.stringify(beforeFingerprints) === JSON.stringify(after), 'Protected source or archived AWS file changed.'); return after;
  });
  await check('browser made no remote request and raised no uncaught exception', async () => {
    assert(blockedRequests.length === 0, 'Page attempted remote requests.'); assert(pageErrors.length === 0, 'Uncaught browser errors: ' + pageErrors.join('; '));
    return { blockedRequests, pageErrors };
  });
  report.completedAt = new Date().toISOString(); report.status = checks.some(check => check.status === 'failed') ? 'failed' : checks.some(check => check.status === 'incomplete') ? 'incomplete' : 'passed';
  report.counts = Object.fromEntries(['passed', 'failed', 'incomplete'].map(status => [status, checks.filter(check => check.status === status).length]));
  fs.writeFileSync(path.join(out, 'browser-local-results.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: report.status, checks: checks.map(({ name, status, error }) => ({ name, status, error })) }, null, 2));
  process.exitCode = report.status === 'passed' ? 0 : report.status === 'incomplete' ? 2 : 1;
})().catch(error => {
  report.status = 'incomplete'; report.error = error.stack; report.completedAt = new Date().toISOString();
  fs.writeFileSync(path.join(out, 'browser-local-results.json'), JSON.stringify(report, null, 2) + '\n');
  console.error(error); process.exitCode = 2;
}).finally(async () => { if (browser) await browser.close(); });
