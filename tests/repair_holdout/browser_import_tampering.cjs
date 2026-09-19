#!/usr/bin/env node
/* Independent, loopback-only import checks using real transfer outputs.
   No Python/candidate execution and no remote requests occur in this test. */
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const args = process.argv.slice(2), root = path.resolve(__dirname, '../..');
const option = (key, fallback) => { const i = args.indexOf(key); return i < 0 ? fallback : args[i + 1]; };
const referencePath = option('--reference'), mutantPath = option('--mutant');
if (!referencePath || !mutantPath) throw Error('Use --reference reference.json --mutant no-business-key.json');
const base = option('--base', 'http://127.0.0.1:8088');
const pagePath = option('--page', '/repair.html');
if (!['/repair.html', '/index.html', '/'].includes(pagePath)) throw Error('Unsupported local page path.');
const local = ['127.0.0.1', 'localhost', '[::1]'];
if (!local.includes(new URL(base).hostname)) throw Error('Only loopback URLs are allowed.');
const out = path.resolve(option('--out', path.join(root, 'docs/repair-lab/import-tampering-results')));
fs.mkdirSync(out, { recursive: true });
const referenceBytes = fs.readFileSync(referencePath), reference = JSON.parse(referenceBytes);
const mutantBytes = fs.readFileSync(mutantPath), mutant = JSON.parse(mutantBytes);
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const clone = object => JSON.parse(JSON.stringify(object));
const contract = require(path.join(root, 'web/repair-contract.js'));
const r = report => report.results.find(result => result.status === 'pass');
const invalid = [];
function add(name, baseReport, mutate) { const report = clone(baseReport); mutate(report); invalid.push({ name, report }); }
add('false-pass-on-duplicate-effect', mutant, report => { report.results.find(x => x.status === 'violation').status = 'pass'; });
add('missing-snapshot-claimed-pass', reference, report => { r(report).receipts = null; });
add('changed-result-expectations', reference, report => { r(report).expectedOrders[0].order.quantity += 1; });
add('changed-observed-input', reference, report => { r(report).deliveries[0].order.quantity += 1; });
add('orphan-accepted-receipt', reference, report => { r(report).receipts[0].acceptedDeliveryId = 'not-a-declared-delivery'; });
add('receipt-for-unrequested-order', reference, report => { r(report).receipts[0].order.orderId += '-different-order'; });
add('acceptance-link-removed', reference, report => { const result = r(report), receipt = result.receipts[0]; result.deliveries.find(d => d.deliveryId === receipt.acceptedDeliveryId).acceptedReceiptIds = []; });
add('event-refers-to-unknown-receipt', reference, report => { r(report).events.find(e => e.type === 'receipt-accepted').receiptId = 'not-in-the-observer-snapshot'; });
add('event-order-disagrees-with-receipt', reference, report => { r(report).events.find(e => e.type === 'receipt-accepted').order.quantity += 1; });
add('completed-delivery-marked-unattempted', reference, report => { r(report).deliveries.find(d => d.outcome === 'completed').attempted = false; });
add('required-import-marked-failed', reference, report => { r(report).execution.imported = false; });
add('conflict-outcome-without-conflict-observation', reference, report => { report.results.find(x => x.deliveries.some(d => d.outcome === 'conflict')).deliveries.find(d => d.outcome === 'conflict').conflictObserved = false; });
add('unconfigured-fault-claimed-injected', reference, report => { r(report).deliveries.find(d => d.fault === 'none').faultInjected = true; });
add('malformed-source-fingerprint', reference, report => { const sources = report.candidates[0].sourceSha256; sources[Object.keys(sources)[0]] = 'not-a-sha256'; });
add('false-summary-pass', mutant, report => { report.summary.status = 'pass'; report.summary.exitCode = 0; });
add('missing-candidate-case-result', reference, report => { report.results.pop(); });

function installedPlaywright() {
  for (const candidate of [process.env.PLAYWRIGHT_MODULE_PATH, 'playwright', path.resolve(path.dirname(process.execPath), '../lib/node_modules/@playwright/cli/node_modules/playwright')].filter(Boolean)) {
    try { return require(candidate); } catch {}
  }
  throw Error('An installed Playwright runtime is required; no dependencies are installed by this test.');
}
const { chromium } = installedPlaywright();
const checks = [], blockedRequests = [], pageErrors = [];
const sourceFiles = ['web/repair-contract.js', 'web/repair-data.js', 'web/repair-imports.js', 'web/repair-app.js', 'web/repair-motion.js', 'web/repair.css', 'web/repair.html', 'web/index.html'];
const record = { startedAt: new Date().toISOString(), referenceSha256: digest(referenceBytes), mutantSha256: digest(mutantBytes), checks, blockedRequests, pageErrors,
  sourceAtStart: Object.fromEntries(sourceFiles.map(name => [name, digest(fs.readFileSync(path.join(root, name)))])) };
const assert = (condition, text) => { if (!condition) throw Error(text); };
let browser;
(async () => {
  browser = await chromium.launch({ headless: true }); record.browser = browser.version();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', acceptDownloads: true });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (local.includes(url.hostname) || url.protocol === 'blob:') return route.continue(); blockedRequests.push(url.href); return route.abort(); });
  const page = await context.newPage(); page.setDefaultTimeout(6000); page.on('pageerror', error => pageErrors.push(error.message));
  const text = async selector => (await page.locator(selector).textContent()).trim();
  async function test(name, fn) { try { checks.push({ name, status: 'pass', observed: await fn() }); } catch (error) { checks.push({ name, status: 'fail', error: error.message }); } }
  async function upload(name, bytes) {
    const prior = await text('#import-status');
    await page.locator('#report-file').setInputFiles({ name, mimeType: 'application/json', buffer: bytes });
    await page.waitForFunction(prior => document.querySelector('#import-status').textContent.trim() !== prior && document.querySelector('#report-file').value === '', prior);
    return text('#import-status');
  }
  async function choose(kind, id) {
    for (const button of await page.locator('[data-' + kind + ']').all()) {
      if (await button.getAttribute('data-' + kind) === id) { await button.click(); return; }
    }
    throw Error('Missing ' + kind + ': ' + id);
  }
  async function display() { return page.evaluate(() => ({ case: document.querySelector('#case-list [aria-current="true"]').dataset.case, candidate: document.querySelector('#candidate-buttons [aria-pressed="true"]').dataset.candidate, source: document.querySelector('#source-select').value,
    values: Object.fromEntries(['order-receipts','verdict','result-title','result-description','check-list','delivery-trail','fingerprints'].map(id => [id, document.getElementById(id).textContent])) })); }
  async function originalDownload() {
    await page.locator('#view-json').click();
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#download-json').click()]);
    const stream = await download.createReadStream(), chunks = []; for await (const chunk of stream) chunks.push(chunk);
    await page.locator('#close-json').click();
    return Buffer.concat(chunks);
  }
  await page.goto(base + pagePath, { waitUntil: 'networkidle' });
  await page.locator('#result-panel').waitFor({ state: 'visible' });
  await page.screenshot({ path: path.join(out, 'current-main-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(out, 'current-main-narrow.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const bundled = JSON.parse(fs.readFileSync(path.join(root, 'web/repair-example.json')));
  for (const state of ['pass', 'violation', 'incomplete', 'unresolved']) {
    const result = bundled.results.find(item => item.status === state);
    if (!result) continue;
    await choose('case', result.caseId);
    await choose('candidate', result.candidateId);
    await page.locator('#result-panel').screenshot({ path: path.join(out, 'current-main-state-' + state + '.png') });
  }
  await test('genuine-transfer-report-imports-and-round-trips', async () => {
    contract.validate(reference);
    const message = await upload('transfer-control.json', referenceBytes);
    assert(message.startsWith('Imported '), message);
    assert((await text('#source-context')).includes('origin unauthenticated'), 'Origin caveat absent.');
    assert(digest(await originalDownload()) === digest(referenceBytes), 'Original report bytes changed.');
    return { message, downloadedSha256: digest(referenceBytes) };
  });
  for (const fixture of invalid) {
    const bytes = Buffer.from(JSON.stringify(fixture.report, null, 2) + '\n');
    fs.writeFileSync(path.join(out, fixture.name + '.json'), bytes);
    await test(fixture.name, async () => {
      const baselineName = 'control-before-' + fixture.name + '.json';
      assert((await upload(baselineName, referenceBytes)).startsWith('Imported '), 'Positive control failed.');
      const before = await display();
      let directRejected = false, reason = '';
      try { contract.validate(fixture.report); } catch (error) { directRejected = true; reason = error.message; }
      const message = await upload(fixture.name + '.json', bytes);
      const unchanged = JSON.stringify(await display()) === JSON.stringify(before);
      const preservedBytes = digest(await originalDownload()) === digest(referenceBytes);
      assert(directRejected && message.startsWith('Could not import:'), 'Contradictory report accepted: ' + message);
      assert(unchanged && preservedBytes, 'Failed import replaced the last accepted comparison or bytes.');
      return { reason, message, previousComparisonPreserved: unchanged, originalBytesPreserved: preservedBytes };
    });
  }
  await test('valid-shaped-source-claim-remains-unauthenticated', async () => {
    const changed = clone(reference), sources = changed.candidates[0].sourceSha256;
    sources[Object.keys(sources)[0]] = 'a'.repeat(64);
    const bytes = Buffer.from(JSON.stringify(changed));
    const message = await upload('different-source-claim.json', bytes);
    assert(message.startsWith('Imported '), 'Viewer pretends to authenticate unknown source bytes: ' + message);
    assert((await text('#source-context')).includes('origin unauthenticated'), 'Origin caveat absent.');
    assert((await page.locator('.technical-details').textContent()).includes('do not authenticate'), 'Source identity caveat absent.');
    return { acceptedAsClaim: true, sourceOriginAuthenticated: false };
  });
  await upload('final-control.json', referenceBytes);
  await page.screenshot({ path: path.join(out, 'desktop-import.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(out, 'narrow-import.png'), fullPage: true });
  await test('narrow-import-has-no-document-overflow', async () => {
    const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    assert(sizes.document <= sizes.viewport, JSON.stringify(sizes)); return sizes;
  });
  await test('no-remote-requests-or-page-errors', async () => { assert(!blockedRequests.length && !pageErrors.length, JSON.stringify({ blockedRequests, pageErrors })); return { blockedRequests, pageErrors }; });
})().catch(error => checks.push({ name: 'suite', status: 'fail', error: error.stack })).finally(async () => {
  if (browser) await browser.close();
  record.sourceAtEnd = Object.fromEntries(sourceFiles.map(name => [name, digest(fs.readFileSync(path.join(root, name)))]));
  record.sourceStableDuringTest = JSON.stringify(record.sourceAtStart) === JSON.stringify(record.sourceAtEnd);
  record.completedAt = new Date().toISOString(); record.passed = checks.filter(c => c.status === 'pass').length; record.failed = checks.filter(c => c.status === 'fail').length;
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(record, null, 2) + '\n');
  console.log(JSON.stringify({ output: out, passed: record.passed, failed: record.failed, sourceStableDuringTest: record.sourceStableDuringTest }));
  process.exitCode = record.failed || !record.sourceStableDuringTest ? 1 : 0;
});
