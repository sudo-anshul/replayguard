#!/usr/bin/env node
/* Import untouched runtime edge reports in a real loopback browser. */
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const args = process.argv.slice(2), root = path.resolve(__dirname, '../..');
const option = (key, fallback) => { const index = args.indexOf(key); return index < 0 ? fallback : args[index + 1]; };
const reportPaths = args.flatMap((arg, index) => arg === '--report' ? [path.resolve(args[index + 1])] : []);
if (!reportPaths.length) throw Error('Supply one or more --report FILE arguments.');
const base = option('--base', 'http://127.0.0.1:8088'), allowed = ['127.0.0.1', 'localhost', '[::1]'];
if (!allowed.includes(new URL(base).hostname)) throw Error('Only loopback URLs are allowed.');
const out = path.resolve(option('--out', path.join(root, 'docs/repair-lab/native-browser-results')));
fs.mkdirSync(out, { recursive: true });
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const sources = ['web/repair-contract.js', 'web/repair-app.js', 'web/repair.css', 'web/repair.html'];
const fingerprints = () => Object.fromEntries(sources.map(name => [name, digest(fs.readFileSync(path.join(root, name)))]));
const contract = require(path.join(root, 'web/repair-contract.js'));
const labels = { pass: 'Passed', violation: 'Violation', incomplete: 'Incomplete', unresolved: 'Unresolved' };
let playwright;
for (const candidate of [process.env.PLAYWRIGHT_MODULE_PATH, 'playwright', path.resolve(path.dirname(process.execPath), '../lib/node_modules/@playwright/cli/node_modules/playwright')].filter(Boolean)) { try { playwright = require(candidate); break; } catch {} }
if (!playwright) throw Error('An already installed Playwright runtime is required.');
const checks = [], blockedRequests = [], pageErrors = [];
const record = { startedAt: new Date().toISOString(), sourceAtStart: fingerprints(), checks, blockedRequests, pageErrors };
let browser;
const assert = (condition, message) => { if (!condition) throw Error(message); };
(async () => {
  browser = await playwright.chromium.launch({ headless: true }); record.browser = browser.version();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', acceptDownloads: true });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (allowed.includes(url.hostname) || url.protocol === 'blob:') return route.continue(); blockedRequests.push(url.href); return route.abort(); });
  const page = await context.newPage(); page.setDefaultTimeout(6000); page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto(base + '/repair.html', { waitUntil: 'networkidle' });
  for (const [index, file] of reportPaths.entries()) {
    const bytes = fs.readFileSync(file), report = JSON.parse(bytes), name = 'native-' + index + '-' + path.basename(path.dirname(file)) + '-' + path.basename(file);
    try {
      contract.validate(report);
      await page.locator('#report-file').setInputFiles({ name, mimeType: 'application/json', buffer: bytes });
      await page.waitForFunction(name => document.querySelector('#import-status').textContent.includes(name) || document.querySelector('#import-status').textContent.startsWith('Could not import:'), name);
      const message = await page.locator('#import-status').textContent();
      assert(message.startsWith('Imported '), message);
      const observed = [];
      for (const result of report.results) {
        await page.locator('#case-select').selectOption(result.caseId);
        await page.locator('#candidate-select').selectOption(result.candidateId);
        const status = (await page.locator('#finding-status').textContent()).trim();
        assert(status === labels[result.status], 'Rendered status differs: ' + result.caseId + ', ' + status + ' vs ' + result.status);
        observed.push({ caseId: result.caseId, candidateId: result.candidateId, supplied: result.status, rendered: status });
      }
      await page.locator('#json-button').click();
      const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#download-json').click()]);
      const stream = await download.createReadStream(), chunks = []; for await (const chunk of stream) chunks.push(chunk);
      await page.locator('#close-json').click();
      assert(digest(Buffer.concat(chunks)) === digest(bytes), 'The original native report bytes changed.');
      await page.setViewportSize({ width: 390, height: 844 });
      const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
      assert(sizes.document <= sizes.viewport, 'Native report causes narrow overflow: ' + JSON.stringify(sizes));
      await page.setViewportSize({ width: 1440, height: 1000 });
      checks.push({ name, status: 'pass', source: file, sha256: digest(bytes), observed, originalBytesPreserved: true, narrow: sizes });
    } catch (error) { checks.push({ name, status: 'fail', source: file, sha256: digest(bytes), error: error.message }); }
  }
})().catch(error => checks.push({ name: 'suite', status: 'fail', error: error.stack })).finally(async () => {
  if (browser) await browser.close();
  record.sourceAtEnd = fingerprints(); record.sourceStableDuringTest = JSON.stringify(record.sourceAtStart) === JSON.stringify(record.sourceAtEnd);
  record.completedAt = new Date().toISOString(); record.passed = checks.filter(check => check.status === 'pass').length; record.failed = checks.filter(check => check.status === 'fail').length;
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(record, null, 2) + '\n');
  console.log(JSON.stringify({ output: out, passed: record.passed, failed: record.failed, sourceStableDuringTest: record.sourceStableDuringTest, blockedRequests, pageErrors }));
  process.exitCode = record.failed || !record.sourceStableDuringTest || blockedRequests.length || pageErrors.length ? 1 : 0;
});
