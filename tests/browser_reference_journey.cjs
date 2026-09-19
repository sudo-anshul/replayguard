#!/usr/bin/env node
/* Read-only local browser acceptance for compare -> reference -> run -> import.
   Requires already-installed Playwright + Chromium, never installs dependencies.
   node tests/browser_reference_journey.cjs [--base http://127.0.0.1:8088]
   Optional --out docs/iteration-04, --normal FILE, --mutated FILE, --fixture FILE.
   Serve web/ separately. This test never calls AWS or runs cloud scripts. */
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const args = process.argv.slice(2), root = path.resolve(__dirname, '..');
const option = (key, fallback) => { const i = args.indexOf(key); return i < 0 ? fallback : args[i + 1]; };
const base = option('--base', 'http://127.0.0.1:8088/recorded-lab.html');
const loopback = ['127.0.0.1', 'localhost', '[::1]'];
if (!loopback.includes(new URL(base).hostname)) throw Error('Only loopback URLs are allowed.');
const out = path.resolve(root, option('--out', 'docs/iteration-04'));
const shots = path.join(out, 'screenshots'); fs.mkdirSync(shots, { recursive: true });
const normalPath = path.resolve(root, option('--normal', 'docs/iteration-03/generated/local-results.json'));
const mutatedPath = path.resolve(root, option('--mutated', 'docs/iteration-03/generated/broken-key-results.json'));
const fixturePath = path.resolve(root, option('--fixture', 'tests/fixtures/local-ledger-wrong-delivery.json'));
const normalBytes = fs.readFileSync(normalPath), mutatedBytes = fs.readFileSync(mutatedPath), fixtureBytes = fs.readFileSync(fixturePath);
const normal = JSON.parse(normalBytes), mutated = JSON.parse(mutatedBytes);
const reference = require(path.join(root, 'web/reference-repair.js'));
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const protectedFiles = ['src/worker.py', 'src/provider.py', 'scripts/run_local.py', 'web/evidence.json', 'web/regression-case.zip', 'evidence/latest.json', '../replayguard-demo.mp4'];
const fingerprints = () => Object.fromEntries(protectedFiles.map(file => [file, digest(fs.readFileSync(path.resolve(root, file)))]));
const protectedBefore = fingerprints();
function installedPlaywright() {
  for (const candidate of [process.env.PLAYWRIGHT_MODULE_PATH, 'playwright', path.resolve(path.dirname(process.execPath), '../lib/node_modules/@playwright/cli/node_modules/playwright')].filter(Boolean)) {
    try { return require(candidate); } catch {}
  }
  throw Error('Installed Playwright is required. Set PLAYWRIGHT_MODULE_PATH; this script never installs dependencies.');
}
const { chromium } = installedPlaywright();
const checks = [], blockedRequests = [], pageErrors = [], requests = [];
const report = { startedAt: new Date().toISOString(), base, checks, blockedRequests, pageErrors, requests, fixtureSha256: digest(fixtureBytes), normalSha256: digest(normalBytes), mutatedSha256: digest(mutatedBytes), scope: 'New reference journey. Native source/case popup keyboard behavior has separate attributed supervisor evidence.' };
let browser;
(async () => {
  browser = await chromium.launch({ headless: true }); report.browser = browser.version();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (loopback.includes(url.hostname) || url.protocol === 'blob:') return route.continue();
    blockedRequests.push(route.request().url()); return route.abort();
  });
  const page = await context.newPage(); page.setDefaultTimeout(6000);
  page.on('pageerror', error => pageErrors.push(error.message)); page.on('request', request => requests.push(request.url()));
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  const text = async selector => (await page.locator(selector).textContent()).trim();
  async function check(name, work) { try { checks.push({ name, status: 'passed', observed: await work() }); } catch (error) { checks.push({ name, status: 'failed', error: error.message }); } }
  async function settled() { await page.waitForFunction(() => document.querySelector('#run-status')?.textContent.trim() !== 'LOADING'); }
  async function source(value) { await page.locator('#source-choice').selectOption(value); await page.waitForFunction(value => document.querySelector('#source-choice').value === value, value); }
  async function upload(file) {
    const previous = await text('#import-message');
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.locator('#import-local-report').click()]);
    await chooser.setFiles(file);
    await page.waitForFunction(before => document.querySelector('#import-message').textContent.trim() !== before && document.querySelector('#import-message').textContent.trim().length, previous);
  }
  async function download(selector) {
    const [item] = await Promise.all([page.waitForEvent('download'), page.locator(selector).click()]);
    const stream = await item.createReadStream(), chunks = []; for await (const chunk of stream) chunks.push(chunk);
    return { name: item.suggestedFilename(), bytes: Buffer.concat(chunks) };
  }
  async function shot(name, selector) {
    await page.locator('#toast').waitFor({ state: 'hidden' });
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
    const options = { path: path.join(shots, name) }; if (selector) { options.clip = await page.locator(selector).boundingBox(); options.fullPage = true; }
    await page.screenshot(options);
  }
  async function referenceSnapshot() { return page.locator('#reference-content').innerHTML(); }
  async function displaySnapshot() {
    return page.evaluate(() => ({ source: document.querySelector('#source-choice').value, case: document.querySelector('#case-selector').value, reference: document.querySelector('#reference-content').innerHTML,
      values: Object.fromEntries(['run-status', 'source-badge', 'suite-summary', 'case-summary', 'vulnerable-business-state', 'repaired-business-state', 'vulnerable-count', 'repaired-count', 'vulnerable-receipts', 'repaired-receipts', 'timeline', 'assertions', 'remaining-assertions', 'fingerprints'].map(id => [id, document.getElementById(id).textContent])) }));
  }
  await page.goto(base, { waitUntil: 'networkidle' }); await settled();
  await check('journey connects comparison, repair, local execution and import with local targets', async () => {
    const links = await page.locator('.journey a').evaluateAll(nodes => nodes.map(node => ({ text: node.textContent.trim(), href: node.getAttribute('href') })));
    assert(JSON.stringify(links.map(link => link.href)) === JSON.stringify(['#receipts', '#reference-repair', '#regression', '#import-result']), 'Journey targets/order are incorrect.');
    for (const link of links) assert(await page.locator(link.href).count() === 1, 'Journey target is missing.');
    assert(await page.locator('.top-source').getAttribute('href') === '#regression' && await text('.top-source') === 'Run locally', 'Top bar still points Local build at the empty remote repository.');
    await page.locator('.journey a[href="#receipts"]').click(); assert(new URL(page.url()).hash === '#receipts', 'Compare action did not navigate to receipts.');
    return links;
  });
  await check('keyboard repair link opens disclosure and keeps focus on its summary', async () => {
    await page.locator('.journey a[href="#reference-repair"]').focus(); await page.keyboard.press('Enter');
    assert(await page.locator('#reference-repair').evaluate(node => node.open), 'Repair link did not open the disclosure.');
    assert(await page.locator('#reference-repair-summary').evaluate(node => node === document.activeElement), 'Repair anchor default navigation stole focus from the summary.');
    assert(new URL(page.url()).hash === '#reference-repair', 'Repair link lost its local fragment.');
    await shot('after-reference-desktop.png', '#reference-repair'); return { open: true, summaryFocused: true };
  });
  await check('all displayed reference snippets preserve exact source lines and whole-file hashes', async () => {
    for (const [key, excerpt] of Object.entries(reference.excerpts)) {
      const file = reference.files[excerpt.file], bytes = fs.readFileSync(path.join(root, file.path));
      assert(digest(bytes) === file.sha256, 'Reference file fingerprint differs from included source.');
      const lines = bytes.toString('utf8').match(/[^\n]*\n|[^\n]+$/g);
      const exact = lines.slice(excerpt.start - 1, excerpt.end).join('');
      assert(await page.locator('#reference-' + key + ' code').textContent() === exact, key + ' DOM code differs from exact source lines.');
    }
    const identities = await text('.reference-identities');
    for (const file of Object.values(reference.files)) assert(identities.includes(file.sha256) && identities.includes(file.path), 'Reference source identity is not inspectable.');
    assert(identities.includes(reference.version), 'Reference commit is missing.');
    assert(/not evidence|do not authenticate/i.test(await text('.reference-trust')), 'Reference is not separated from imported execution origin.');
    assert(/does not guarantee exactly-once/i.test(await text('.reference-boundary')), 'Receiver contract boundary is missing.');
    return { version: reference.version, excerpts: Object.keys(reference.excerpts), hashes: reference.files };
  });
  await check('reference details and scrollable code are keyboard accessible', async () => {
    const contextSummary = page.locator('.reference-context-disclosure > summary'); await contextSummary.focus(); await page.keyboard.press('Enter');
    assert(await page.locator('.reference-context-disclosure').evaluate(node => node.open), 'Receiver context did not expand.');
    const identitySummary = page.locator('.reference-identities > summary'); await identitySummary.focus(); await page.keyboard.press('Enter');
    assert(await page.locator('.reference-identities').evaluate(node => node.open), 'Source identity did not expand.');
    const code = page.locator('#reference-providerWrite'); await code.focus();
    assert(await code.getAttribute('tabindex') === '0' && /exact src\/provider.py excerpt/i.test(await code.getAttribute('aria-label')), 'Scrollable receiver code lacks keyboard access or label.');
    const before = await code.evaluate(node => ({ top: node.scrollTop, scroll: node.scrollHeight, client: node.clientHeight }));
    await page.keyboard.press('PageDown');
    if (before.scroll > before.client) await page.waitForFunction(top => document.querySelector('#reference-providerWrite').scrollTop > top, before.top);
    const after = await code.evaluate(node => node.scrollTop);
    assert(before.scroll <= before.client || after > before.top, 'Scrollable code did not respond to PageDown.');
    await shot('after-reference-expanded.png', '#reference-repair');
    await code.evaluate(node => { node.scrollTop = 0; });
    return { receiverContext: true, sourceIdentity: true, labeledCode: true, codeScrollBefore: before, codeScrollAfter: after };
  });
  await check('local regression download preserves the runnable package and copy action provides exact CLI', async () => {
    await page.locator('#reference-content a[href="#regression"]').click(); assert(new URL(page.url()).hash === '#regression', 'Reference next step does not lead to local regression.');
    const expected = 'python3 -I -S scripts/run_local.py --output local-results.json';
    assert(await text('#local-run-command') === expected, 'Displayed local command is incorrect.');
    await page.evaluate(() => { window.__rgCopyOriginal = navigator.clipboard.writeText; navigator.clipboard.writeText = async value => { window.__rgCopied = value; }; });
    try { await page.locator('[data-copy="local-run-command"]').click(); assert(await page.evaluate(() => window.__rgCopied) === expected, 'Copy handler did not receive the exact command.'); }
    finally { await page.evaluate(() => { navigator.clipboard.writeText = window.__rgCopyOriginal; delete window.__rgCopyOriginal; delete window.__rgCopied; }); }
    const item = await download('a[download][href="./replayguard-local-regression.zip"]');
    assert(item.bytes.equals(fs.readFileSync(path.join(root, 'web/replayguard-local-regression.zip'))), 'Downloaded regression bytes differ from runnable package.');
    assert(/Import local-results.json/.test(await text('#import-result')), 'Explicit run-to-import step is missing.');
    await shot('after-run-import.png', '#regression'); return { command: expected, copyHandlerExact: true, operatingSystemClipboardTouched: false, filename: item.name, sha256: digest(item.bytes) };
  });
  let staticReference;
  await check('dedicated import action loads the normal five-case report while preserving reference code', async () => {
    staticReference = await referenceSnapshot(); await upload(normalPath);
    assert(/local/i.test(await text('#source-badge')) && /10\s*\/\s*10/.test(await text('#suite-summary')), 'Normal full suite did not import.');
    assert(await page.locator('#case-selector option').count() === 5, 'Imported full suite lacks five cases.');
    assert(await text('#vulnerable-count') === '2' && await text('#repaired-count') === '1', 'Normal crash comparison counts are incorrect.');
    assert(await referenceSnapshot() === staticReference, 'Import changed included reference content.');
    await shot('after-local-comparison.png', '#receipts'); await shot('after-local-journey.png', '#experiment');
    return { source: await text('#source-badge'), suite: await text('#suite-summary'), referencePreserved: true };
  });
  await check('broken-key report stays a violation and never replaces included reference source', async () => {
    await upload(mutatedPath); await page.locator('#case-selector').selectOption('different-message-ids');
    assert(await text('#repaired-business-state') === 'VIOLATION' && await text('#repaired-count') === '2', 'Broken repair is not visibly violated.');
    assert(/8\s*\/\s*10/.test(await text('#suite-summary')), 'Broken report suite mismatch is missing.');
    assert((await text('#fingerprints')).includes(mutated.sourceSha256['src/worker.py']), 'Imported worker fingerprint is not shown separately.');
    assert((await text('.reference-identities')).includes(reference.files.worker.sha256), 'Reference worker identity was replaced with imported identity.');
    assert(await referenceSnapshot() === staticReference, 'Broken import changed included reference code.');
    assert((await download('#download-evidence')).bytes.equals(mutatedBytes), 'Broken import download no longer has original raw bytes.');
    await shot('after-broken-key.png', '#receipts'); return { repaired: await text('#repaired-business-state'), referencePreserved: true, rawBytesPreserved: true };
  });
  await check('exact supervisor wrong-delivery report rejects with view, source and raw-byte rollback', async () => {
    assert(digest(fixtureBytes) === 'f62c67662317f48287652b439320415272ac64caa2202f4b2ace7313ce3a1b12', 'Supervisor fixture was modified.');
    const before = await displaySnapshot(); await upload(fixturePath);
    assert(/reject/i.test(await text('#import-message')), 'Wrong accepting-delivery identity was not rejected.');
    assert(await text('#journey-import-message') === await text('#import-message'), 'Rejection is not mirrored beside the new import action.');
    assert(JSON.stringify(before) === JSON.stringify(await displaySnapshot()), 'Rejected fixture changed prior data/reference view.');
    assert((await download('#download-evidence')).bytes.equals(mutatedBytes), 'Rejected fixture changed downloadable raw bytes.');
    await shot('after-wrong-delivery-rejected.png', '#evidence-tools'); return { fixtureSha256: digest(fixtureBytes), message: await text('#import-message'), viewAndReferencePreserved: true, rawBytesPreserved: true };
  });
  await check('source switches retain included reference and preserve incomplete/unresolved controls', async () => {
    await source('local-sample'); await page.locator('#case-selector').selectOption('missing-observation');
    assert(await text('#repaired-business-state') === 'INCOMPLETE' && await text('#repaired-count') === '—', 'Missing observation became a pass or zero count.');
    await shot('after-missing-observation.png', '#receipts');
    await page.locator('#case-selector').selectOption('ambiguous-side-effect');
    assert(await text('#repaired-business-state') === 'UNRESOLVED' && /No execution/i.test(await text('#repaired-execution')), 'Unsupported effect implies execution or a pass.');
    await shot('after-unsupported.png', '#receipts');
    await source('aws-sample'); assert(await text('#run-status') === 'UNVERIFIED', 'Recorded AWS sample became authenticated.');
    assert(await referenceSnapshot() === staticReference, 'Source selection changed included reference code.');
    await source('import'); assert((await download('#download-evidence')).bytes.equals(mutatedBytes), 'Source round trip lost previous accepted import.');
    return { missing: 'INCOMPLETE / unknown', unsupported: 'UNRESOLVED / no execution', aws: 'UNVERIFIED', referencePreserved: true, importedBytesPreserved: true };
  });
  for (const width of [390, 320]) await check('reference journey reflows without page overflow at ' + width + 'px', async () => {
    await page.setViewportSize({ width, height: 844 }); await source('aws-sample');
    await page.locator('.journey a[href="#reference-repair"]').click();
    const dimensions = await page.evaluate(() => ({ width: innerWidth, body: document.body.scrollWidth, document: document.documentElement.scrollWidth }));
    assert(dimensions.body <= width && dimensions.document <= width, 'Reference journey causes horizontal page overflow.');
    for (const key of Object.keys(reference.excerpts)) assert(await page.locator('#reference-' + key + ' code').textContent() === reference.excerpts[key].text, 'Narrow layout rewrote code text.');
    await shot('after-reference-' + width + '.png', '#reference-repair'); await shot('after-journey-' + width + '.png', '#experiment'); await shot('after-run-import-' + width + '.png', '#regression');
    return { dimensions, exactCodePreserved: true };
  });
  await check('refresh main comparison screenshot with current journey and actual recorded receipts', async () => {
    await page.setViewportSize({ width: 1440, height: 1000 }); await source('aws-sample');
    await page.locator('#toast').waitFor({ state: 'hidden' });
    assert(await text('#vulnerable-count') === '2' && await text('#repaired-count') === '1', 'AWS comparison changed unexpectedly.');
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
    const journey = await page.locator('.journey').boundingBox(), comparison = await page.locator('.comparison').boundingBox();
    const top = Math.min(journey.y, comparison.y), bottom = Math.max(journey.y + journey.height, comparison.y + comparison.height);
    const clip = { x: Math.min(journey.x, comparison.x), y: top, width: Math.max(journey.width, comparison.width), height: bottom - top };
    const image = await page.screenshot({ path: path.join(root, 'docs/screenshots/comparison.png'), clip, fullPage: true });
    fs.writeFileSync(path.join(shots, 'after-main-comparison.png'), image);
    return { source: 'Recorded AWS sample', receipts: [2, 1], includesJourney: true, sha256: digest(image) };
  });
  await check('protected source, historical AWS files and old video remain byte-identical', async () => { const after = fingerprints(); assert(JSON.stringify(after) === JSON.stringify(protectedBefore), 'Protected artifact changed.'); return after; });
  await check('all page requests stayed local and no uncaught error occurred', async () => { assert(!blockedRequests.length, 'Page attempted a remote request.'); assert(!pageErrors.length, 'Browser error: ' + pageErrors.join('; ')); return { blockedRequests, pageErrors }; });
  report.completedAt = new Date().toISOString(); report.status = checks.some(check => check.status === 'failed') ? 'failed' : 'passed';
  fs.writeFileSync(path.join(out, 'browser-reference-results.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: report.status, checks: checks.map(({ name, status, error }) => ({ name, status, error })) }, null, 2)); process.exitCode = report.status === 'passed' ? 0 : 1;
})().catch(error => { report.status = 'incomplete'; report.error = error.stack; fs.writeFileSync(path.join(out, 'browser-reference-results.json'), JSON.stringify(report, null, 2) + '\n'); console.error(error); process.exitCode = 2; }).finally(async () => { if (browser) await browser.close(); });
