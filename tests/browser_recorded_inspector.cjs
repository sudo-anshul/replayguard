/* Local-only secondary recorded inspector regression; requires installed Playwright. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname,'..');
const moduleNames = [process.env.PLAYWRIGHT_MODULE_PATH,'playwright',path.resolve(path.dirname(process.execPath),'../lib/node_modules/@playwright/cli/node_modules/playwright')].filter(Boolean);
let playwright;
for (const moduleName of moduleNames) { try { playwright=require(moduleName);break; } catch {} }
if (!playwright) throw Error('Use an already-installed Playwright/browser. This test never downloads dependencies.');
(async()=>{
 const browser=await playwright.chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 const checks=[]; const remote=[];
 await context.route('**/*',route=>{
  if (new URL(route.request().url()).hostname!=='127.0.0.1') {remote.push(route.request().url());return route.abort();}
  return route.continue();
 });
 const page=await context.newPage();
 try {
  await page.goto('http://127.0.0.1:8088/aws-run.html');
  await page.waitForFunction(()=>document.querySelector('#verdict').textContent==='BROWSER: UNVERIFIED');
  assert.match(await page.locator('#notice').textContent(),/file claims: PASSED.*AWS origin is unauthenticated/);
  checks.push({case:'shipped-sample',status:await page.locator('#verdict').textContent(),claim:'PASSED',browserChecks:'18/18',origin:'unauthenticated'});
  await page.route('**/evidence.json',route=>route.fulfill({status:200,contentType:'application/json',body:fs.readFileSync(path.join(root,'tests/fixtures/contradictory-passed.json'))}));
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#verdict').textContent==='BROWSER: UNRESOLVED');
  assert.equal((await page.locator('#repaired-count').textContent()).trim(),'2');
  assert.match(await page.locator('#notice').textContent(),/file claims: PASSED/);
  checks.push({case:'contradictory-sample-response',status:await page.locator('#verdict').textContent(),repairedReceipts:2,claim:'PASSED'});
  assert.deepEqual(remote,[]);
  fs.writeFileSync(path.join(root,'docs/iteration-02/recorded-inspector-results.json'),JSON.stringify({status:'passed',recordedAt:new Date().toISOString(),checks,remote},null,2)+'\n');
  console.log('Secondary inspector: 2 checks passed; only loopback requests.');
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
