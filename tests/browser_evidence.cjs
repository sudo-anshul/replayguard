#!/usr/bin/env node
/* Local-only browser regression. Requires an already-installed Playwright/browser.
   node tests/browser_evidence.cjs
   Optional fixture override: --fixture /path/contradictory-passed.json
   Optional: --base http://127.0.0.1:8088 --out docs/iteration-02
   No install, remote requests, AWS calls, or source/evidence mutations. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const args = process.argv.slice(2);
const option = (key, fallback) => { const i = args.indexOf(key); return i >= 0 ? args[i + 1] : fallback; };
const root = path.resolve(__dirname, '..');
const base = option('--base', 'http://127.0.0.1:8088/recorded-lab.html');
const parsedBase = new URL(base);
if (!['127.0.0.1', 'localhost', '[::1]'].includes(parsedBase.hostname)) throw Error('Only loopback URLs are allowed.');
const fixture = option('--fixture', process.env.RG_CONTRADICTION_FILE || path.join(root, 'tests/fixtures/contradictory-passed.json'));
if (!fixture || !fs.existsSync(fixture)) throw Error('The exact supervisor contradiction fixture is required (tests/fixtures/contradictory-passed.json or --fixture).');
const out = path.resolve(root, option('--out', 'docs/iteration-02'));
fs.mkdirSync(out, { recursive: true });
function installedPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE_PATH, 'playwright', path.resolve(path.dirname(process.execPath), '../lib/node_modules/@playwright/cli/node_modules/playwright')].filter(Boolean);
  for (const candidate of candidates) { try { return require(candidate); } catch {} }
  throw Error('An installed Playwright module is required; this script never installs dependencies. Set PLAYWRIGHT_MODULE_PATH if needed.');
}
const { chromium } = installedPlaywright();
const samplePath = path.join(root, 'web/evidence.json');
const sampleBytes = fs.readFileSync(samplePath);
const sample = JSON.parse(sampleBytes);
const sha = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const protectedFiles = ['web/evidence.json', 'web/regression-case.zip', 'evidence/latest.json'].filter(f => fs.existsSync(path.join(root, f)));
const protectedBefore = Object.fromEntries(protectedFiles.map(f => [f, sha(path.join(root, f))]));
const checks = []; const blockedRequests = []; const pageErrors = []; const requests = [];
const report = { startedAt: new Date().toISOString(), base, fixtureSha256: sha(fixture), checks, blockedRequests, pageErrors, requests };
let browser;
(async () => {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) || url.protocol === 'blob:') return route.continue();
    blockedRequests.push(route.request().url()); await route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  const assert = (value, message) => { if (!value) throw Error(message); };
  const read = selector => page.locator(selector).textContent();
  const check = async (name, operation) => {
    try { const observed = await operation(); checks.push({ name, status: 'passed', observed }); }
    catch (error) { checks.push({ name, status: 'failed', error: error.message }); }
  };
  async function settled() { await page.waitForFunction(() => !/loading/i.test(document.querySelector('#evidence-title')?.textContent || '') && document.querySelector('#run-status')?.textContent.trim() !== 'LOADING'); }
  async function loadSample() { await page.goto(base, { waitUntil: 'networkidle' }); await settled(); }
  async function upload(value, name) {
    const previous = await read('#import-message');
    await page.locator('#evidence-upload').setInputFiles(typeof value === 'string' ? value : { name, mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(value)) });
    await page.waitForFunction(old => { const n = document.querySelector('#import-message'); return n && n.textContent !== old && n.textContent.length > 0; }, previous);
  }
  async function snapshot() { return page.evaluate(() => Object.fromEntries(['run-status','source-badge','claimed-verdict','verification-summary','verification-reasons','evidence-title','evidence-subtitle','region','recorded-at','vulnerable-count','repaired-count','vulnerable-attempts','repaired-attempts','vulnerable-receipts','repaired-receipts','timeline','assertions','assertion-counter','remaining-assertions','evidence-file-label'].map(id => [id, document.getElementById(id)?.textContent]))); }
  async function shot(name, selector = '#receipts') { await page.locator(selector).screenshot({ path: path.join(out, name) }); }
  async function downloadedBytes() {
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#download-evidence').click()]);
    const stream = await download.createReadStream(); const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    return Buffer.concat(chunks);
  }
  async function restored() { await page.locator('#restore-sample').click(); await page.waitForFunction(() => !/import/i.test(document.querySelector('#evidence-title')?.textContent || '') && document.querySelector('#repaired-count')?.textContent.trim() === '1'); }

  await loadSample();
  await check('sample headline is conservatively unverified', async () => {
    const status = (await read('#run-status')).trim(); assert(status === 'UNVERIFIED', 'Sample headline must be UNVERIFIED, never derived PASSED.');
    return {status, title: await read('#evidence-title'), receipts: [await read('#vulnerable-count'), await read('#repaired-count')]};
  });
  await check('exact supervisor contradiction is unresolved', async () => {
    await upload(fixture); assert((await read('#run-status')).trim() === 'UNRESOLVED', 'Contradiction must be UNRESOLVED.');
    assert((await read('#repaired-count')).trim() === '2', 'Contradictory raw receipts must remain visible.');
    assert((await read('#source-badge')).trim() === 'YOUR FILE', 'Imported source must be visible.');
    assert(/PASSED/.test(await read('#claimed-verdict')), 'Supplied PASSED value must remain visibly labeled as a file claim.');
    assert(/unauthenticated/i.test(await read('.evidence-trust')), 'Unauthenticated AWS origin must be visible.');
    assert(await page.locator('#assertions .assertion.unresolved').count() > 0, 'Contradiction must appear in recomputed browser checks.');
    await page.screenshot({path:path.join(out,'after-contradiction-desktop.png')});
    await shot('after-contradiction-receipts.png'); await shot('after-contradiction-header.png', '#experiment');
    return {status: await read('#run-status'), receipts: [await read('#vulnerable-count'), await read('#repaired-count')], assertionCounter: await read('#assertion-counter')};
  });
  await check('legitimate import is unverified and preserves exact dialog bytes', async () => {
    await upload(samplePath); assert((await read('#run-status')).trim() === 'UNVERIFIED', 'Legitimate import must remain UNVERIFIED.');
    assert((await read('#repaired-count')).trim() === '1', 'Legitimate imported receipt count is 1.');
    await page.locator('#view-evidence').click();
    const raw = await read('#json-content'); assert(raw === sampleBytes.toString(), 'JSON dialog must show the exact original text.');
    await page.keyboard.press('Escape'); assert((await downloadedBytes()).equals(sampleBytes), 'Downloaded JSON bytes differ from the original file.'); return {status: await read('#run-status'), exactDialogText: true, exactDownloadBytes: true};
  });
  await check('malformed import preserves all previous evidence state', async () => {
    const before = await snapshot(); await upload({schemaVersion:1, status:'passed'}, 'malformed-browser-test.json');
    const after = await snapshot(); assert(JSON.stringify(before) === JSON.stringify(after), 'Malformed import changed the prior data view.');
    assert(/reject|could not|invalid|failed/i.test(await read('#import-message')), 'Import rejection must be visible.');
    await shot('malformed-import-preserved.png', '.evidence-tools'); return {preserved:true, message: await read('#import-message')};
  });
  await check('off-DOM rendering failure rolls back model and view', async () => {
    const before = await snapshot();
    await page.evaluate(() => {
      const original = document.createElement;
      window.__rgTestRenderFailure = { original, fired: false };
      document.createElement = function(tag, ...rest) {
        const state = window.__rgTestRenderFailure;
        if (!state.fired && tag === 'li') { state.fired = true; document.createElement = original; throw Error('TEST_ONLY_RENDER_FAILURE'); }
        return original.call(this, tag, ...rest);
      };
    });
    try {
      await upload(fixture);
      const fired = await page.evaluate(() => window.__rgTestRenderFailure?.fired);
      assert(fired, 'Render injection did not reach an off-DOM list element.');
      assert(JSON.stringify(before) === JSON.stringify(await snapshot()), 'Render failure changed prior model/view.');
      assert((await downloadedBytes()).equals(sampleBytes), 'Render failure changed the downloadable data model.');
      return {injected:true, preserved:true, message:await read('#import-message')};
    } finally { await page.evaluate(() => { const state=window.__rgTestRenderFailure; if(state) document.createElement=state.original; delete window.__rgTestRenderFailure; }); }
  });
  await check('empty observations render incomplete and clear previous content', async () => {
    const empty = structuredClone(sample); empty.status='incomplete'; empty.events=[]; empty.assertions=[]; empty.receipts={vulnerable:[],repaired:[]}; empty.attempts={vulnerable:[],repaired:[]}; empty.messages=[]; empty.queueObservations=[];
    await upload(empty,'empty-observations.json');
    assert((await read('#run-status')).trim() === 'INCOMPLETE', 'Empty observations must be INCOMPLETE.');
    assert(await page.locator('.receipt-ticket').count() === 0, 'Old receipt cards survived an empty import.');
    assert(!/awaiting credentials|sign in to AWS|configure AWS/i.test(await read('.evidence-bar')), 'Empty state must not prompt for AWS credentials.');
    await shot('empty-incomplete-header.png', '#experiment'); return {status:await read('#run-status'), receiptCards:0, assertionCounter:await read('#assertion-counter')};
  });
  await check('restore sample recovers archived recording', async () => {
    await restored(); assert((await read('#run-status')).trim() === 'UNVERIFIED', 'Restored sample must remain UNVERIFIED.');
    assert((await read('#vulnerable-count')).trim()==='2' && (await read('#repaired-count')).trim()==='1','Restore sample counts incorrect.');
    return {status:await read('#run-status'),title:await read('#evidence-title')};
  });
  await check('keyboard expands derived checks with reasons and values', async () => {
    const row = page.locator('#assertions details.assertion').first();
    await row.locator('summary').focus(); await page.keyboard.press('Enter');
    assert(await row.evaluate(node=>node.open), 'Enter did not expand a derived check.');
    assert(await row.locator('.assertion-detail').isVisible(), 'Expanded check reason is not visible.');
    const values = await row.locator('dt').allTextContents(); assert(values.includes('Expected') && values.includes('Observed'), 'Derived check lacks Expected/Observed labels.');
    await shot('derived-check-expanded.png', '#assertions');
    await row.locator('summary').focus(); await page.keyboard.press('Enter');
    if (await page.locator('#more-assertions').isVisible()) {
      await page.locator('#more-assertions > summary').focus(); await page.keyboard.press('Enter');
      assert(await page.locator('#remaining-assertions').isVisible(), 'Keyboard did not reveal remaining browser checks.');
      await page.keyboard.press('Enter');
    }
    return {rowKeyboardExpanded:true,reasonVisible:true,values,allChecksKeyboardExpanded:true};
  });
  await check('keyboard dialog opens, prevents background focus, and restores trigger focus', async () => {
    await page.locator('#view-evidence').focus(); await page.keyboard.press('Enter');
    const focusStates = [];
    try {
      assert(await page.locator('#json-dialog').isVisible(),'Keyboard did not open JSON dialog.');
      assert(await page.evaluate(() => document.querySelector('#json-dialog').contains(document.activeElement)), 'Dialog did not receive focus.');
      for (let i=0;i<5;i++) {
        await page.keyboard.press('Tab');
        const state = await page.evaluate(() => ({tag:document.activeElement.tagName,id:document.activeElement.id,documentFocused:document.hasFocus(),inside:document.querySelector('#json-dialog').contains(document.activeElement)}));
        focusStates.push(state);
        assert(state.inside, 'Tab escaped the explicit dialog focus cycle.');
      }
    } finally { await page.keyboard.press('Escape'); }
    assert(!await page.locator('#json-dialog').isVisible(),'Escape did not dismiss dialog.');
    assert(await page.locator('#view-evidence').evaluate(node=>node===document.activeElement),'Focus did not return to JSON trigger.');
    return {openedByKeyboard:true, backgroundControlsNotFocused:true, focusStates, escapeClosed:true, focusReturned:true};
  });
  for (const width of [390,320]) await check(`reflow at ${width}px`,async()=>{
    await page.setViewportSize({width,height:844}); await page.locator('#receipts').scrollIntoViewIfNeeded(); await page.locator('#receipt-title').click();
    const dimensions=await page.evaluate(()=>({viewport:innerWidth,body:document.body.scrollWidth,document:document.documentElement.scrollWidth}));
    assert(dimensions.body<=width && dimensions.document<=width,'Horizontal page overflow.');
    await shot(`receipts-${width}.png`); await shot(`evidence-tools-${width}.png`,'.evidence-tools');
    await upload(fixture);
    const contradictionDimensions=await page.evaluate(()=>({viewport:innerWidth,body:document.body.scrollWidth,document:document.documentElement.scrollWidth}));
    assert(contradictionDimensions.body<=width && contradictionDimensions.document<=width,'Contradiction reasons overflow the narrow page.');
    await shot(`contradiction-trust-${width}.png`,'.evidence-trust');
    await restored(); return {recorded:dimensions,contradiction:contradictionDimensions};
  });
  await check('initial loading and sample failure do not request AWS credentials',async()=>{
    const loadingPage=await context.newPage(); let release; const gate=new Promise(resolve=>{release=resolve;});
    await loadingPage.route('**/evidence.json',async route=>{await gate;await route.fulfill({status:503,contentType:'application/json',body:'{"error":"test sample unavailable"}'});});
    try{
      await loadingPage.goto(base,{waitUntil:'domcontentloaded'});
      await loadingPage.waitForFunction(()=>document.querySelector('#run-status'));
      const initial=await loadingPage.locator('.evidence-bar').textContent();
      assert(!/awaiting credentials|sign in to AWS|configure AWS/i.test(initial),'Loading state requests AWS credentials.');
      await loadingPage.locator('.evidence-bar').screenshot({path:path.join(out,'initial-loading.png')});
      release();
      await loadingPage.waitForFunction(()=>/unavailable|could not|failed|not loaded|unable/i.test(document.querySelector('.evidence-bar')?.textContent||''));
      const failure=await loadingPage.locator('.evidence-bar').textContent();
      assert((await loadingPage.locator('#run-status').textContent()).trim()==='INCOMPLETE','Fetch failure must remain INCOMPLETE.');
      assert(!/awaiting credentials|sign in to AWS|configure AWS/i.test(failure),'Sample failure requests AWS credentials.');
      assert(await loadingPage.locator('#import-evidence').isEnabled(),'Import must remain usable after sample failure.');
      await loadingPage.locator('.evidence-bar').screenshot({path:path.join(out,'sample-unavailable.png')});
      return {initial,failure,importEnabled:true};
    }finally{release();await loadingPage.close();}
  });
  await check('protected AWS source artifacts remain byte-identical',async()=>{
    const after=Object.fromEntries(protectedFiles.map(f=>[f,sha(path.join(root,f))]));assert(JSON.stringify(protectedBefore)===JSON.stringify(after),'Protected AWS artifacts changed.');return after;
  });
  await check('no remote page request or uncaught browser exception',async()=>{assert(blockedRequests.length===0,'Page attempted a remote request.');assert(pageErrors.length===0,'Uncaught browser errors: '+pageErrors.join('; '));return {blockedRequests,pageErrors};});
  report.completedAt=new Date().toISOString(); report.status=checks.some(c=>c.status==='failed')?'failed':'passed';
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({status:report.status,checks:checks.map(({name,status,error})=>({name,status,error}))},null,2));
  process.exitCode=report.status==='passed'?0:1;
})().catch(error=>{report.status='incomplete';report.error=error.stack;fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(report,null,2)+'\n');console.error(error);process.exitCode=2;}).finally(async()=>{if(browser)await browser.close();});
