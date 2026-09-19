#!/usr/bin/env node
/* Capture actual local product states for the demo; no injected UI or remote calls. */
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..'), out = path.join(root, 'docs/repair-lab/media');
fs.mkdirSync(out, { recursive: true });
const previousManifest = path.join(out, 'capture-manifest-before-final-copy.json');
if (fs.existsSync(path.join(out, 'capture-manifest.json')) && !fs.existsSync(previousManifest)) fs.copyFileSync(path.join(out, 'capture-manifest.json'), previousManifest);
const base = 'http://127.0.0.1:8088', local = ['127.0.0.1', 'localhost', '[::1]'];
const digest = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const files = ['web/index.html','web/repair.html','web/adapter-guide.html','web/repair-app.js','web/repair-contract.js','web/repair.css','web/repair-example.json','web/repair-transfer.json','web/aws-run.html','web/aws-run.js','web/aws-run.css','web/evidence.json'];
const fingerprints = () => Object.fromEntries(files.map(file => [file,digest(path.join(root,file))]));
const manifest = { startedAt: new Date().toISOString(), viewport: { width:1440,height:1000 }, sourceBefore:fingerprints(), captures:[], layoutChecks:[], blockedRequests:[], pageErrors:[], scope:'Actual loopback-rendered product states. No DOM content changed, no AWS calls, no simulated typing.' };
let playwright;
for (const p of [process.env.PLAYWRIGHT_MODULE_PATH,'playwright',path.resolve(path.dirname(process.execPath),'../lib/node_modules/@playwright/cli/node_modules/playwright')].filter(Boolean)) { try { playwright=require(p);break; } catch {} }
if (!playwright) throw Error('Installed Playwright required.');
let browser;
(async()=>{
  browser=await playwright.chromium.launch({headless:true});manifest.browser=browser.version();
  const context=await browser.newContext({viewport:manifest.viewport,reducedMotion:'reduce'});
  await context.route('**/*',route=>{const u=new URL(route.request().url());if(local.includes(u.hostname)||u.protocol==='blob:')return route.continue();manifest.blockedRequests.push(u.href);return route.abort();});
  const page=await context.newPage();page.on('pageerror',e=>manifest.pageErrors.push(e.message));page.setDefaultTimeout(6000);
  async function capture(name,detail,clip){
    await page.screenshot({path:path.join(out,name),fullPage:true,...clip?{clip}: {}});
    manifest.captures.push({file:name,url:page.url(),viewport:page.viewportSize(),clip:clip||'full page',sha256:digest(path.join(out,name)),...detail});
  }
  async function reportRegion(){
    const box=await page.locator('.bench').boundingBox(),bar=await page.locator('.report-bar').boundingBox(),finding=await page.locator('#finding').boundingBox();
    return{x:Math.max(0,Math.floor(box.x-8)),y:Math.max(0,Math.floor(bar.y-8)),width:Math.min(1440-Math.max(0,Math.floor(box.x-8)),Math.ceil(box.width+16)),height:Math.ceil(finding.y+finding.height-bar.y+24)};
  }
  await page.goto(base+'/index.html',{waitUntil:'networkidle'});await page.locator('#bench-content').waitFor({state:'visible'});
  const main=JSON.parse(fs.readFileSync(path.join(root,'web/repair-example.json')));
  const interleaved=main.cases.find(c=>c.id.includes('interleav'));
  if(!interleaved)throw Error('No interleaved two-order case in current main report.');
  await page.locator('#case-select').selectOption(interleaved.id);
  const overbroad=main.candidates.find(c=>c.id.includes('overbroad'));
  if(overbroad)await page.locator('#candidate-select').selectOption(overbroad.id);
  for (const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:width===1440?1000:844});
    const metrics=await page.evaluate(()=>({
      viewport:innerWidth,document:document.documentElement.scrollWidth,
      title:document.querySelector('#page-title').innerText.replace(/\s+/g,' ').trim(),
      runTitle:document.querySelector('#run-title').innerText.replace(/\s+/g,' ').trim(),
      runCommandTabIndex:document.querySelector('#run-command').tabIndex,
      jsonVisible:!!document.querySelector('#json-button').getClientRects().length,
      comparisonScrollWidth:document.querySelector('.comparison-scroll').scrollWidth,
      comparisonClientWidth:document.querySelector('.comparison-scroll').clientWidth
    }));
    metrics.passed=metrics.document<=metrics.viewport&&metrics.title==='Your fix should protect every order.'&&metrics.runTitle==='A test you can take back to your code.'&&metrics.runCommandTabIndex===0&&metrics.jsonVisible;
    manifest.layoutChecks.push(metrics);
    if(!metrics.passed)throw Error('Final layout check failed: '+JSON.stringify(metrics));
    await capture('layout-'+width+'.png',{source:'Actual final viewport layout check',caseId:interleaved.id},{x:0,y:0,width,height:width===1440?1000:844});
  }
  await page.setViewportSize(manifest.viewport);
  const key=await page.locator('.comparison-key').boundingBox();
  await capture('comparison.png',{source:'Recorded local comparison',caseId:interleaved.id,candidateId:overbroad?.id,content:'Real main header, delivery plan and both expected-order rows.'},{x:0,y:0,width:1440,height:Math.ceil(key.y+key.height+20)});
  const schedule=await page.locator('.schedule').boundingBox();
  await capture('comparison-detail.png',{source:'Actual delivery plan, table headers and both order rows; tighter video crop of current main.',caseId:interleaved.id},{x:Math.floor(schedule.x),y:Math.floor(schedule.y),width:Math.ceil(schedule.width),height:Math.ceil(key.y+key.height-schedule.y+7)});
  await capture('main-full.png',{source:'Recorded local comparison',caseId:interleaved.id});
  await page.setViewportSize({width:390,height:844});await capture('narrow.png',{source:'Current main at narrow viewport',caseId:interleaved.id});await page.setViewportSize(manifest.viewport);
  await page.locator('#report-select').selectOption('transfer');await page.waitForFunction(()=>document.querySelector('#report-origin').textContent.includes('independent-worker'));
  const transfer=JSON.parse(fs.readFileSync(path.join(root,'web/repair-transfer.json'))),tc=transfer.cases.find(c=>c.id.includes('interleav'));
  await page.locator('#case-select').selectOption(tc.id);
  await capture('independent.png',{source:'Recorded independent DispatchDesk worker',caseId:tc.id,reportSha256:digest(path.join(root,'web/repair-transfer.json')),content:'Report provenance, independent orders, receipts and inspected result.'},await reportRegion());
  await page.locator('#report-select').selectOption('reference');await page.waitForFunction(()=>document.querySelector('#report-origin').textContent==='Recorded local comparison');
  const incomplete=main.results.find(r=>r.status==='incomplete'&&r.candidateId==='business-key')||main.results.find(r=>r.status==='incomplete');
  await page.locator('#case-select').selectOption(incomplete.caseId);await page.locator('#candidate-select').selectOption(incomplete.candidateId);
  await capture('incomplete.png',{source:'Actual missing-observation control',caseId:incomplete.caseId,candidateId:incomplete.candidateId,status:incomplete.status},await reportRegion());
  await page.locator('#run').screenshot({path:path.join(out,'run-kit.png')});
  manifest.captures.push({file:'run-kit.png',url:page.url(),viewport:page.viewportSize(),region:'#run',source:'Actual extraction command, adapter and import workflow',sha256:digest(path.join(out,'run-kit.png'))});
  await page.goto(base+'/aws-run.html',{waitUntil:'networkidle'});await page.waitForFunction(()=>!document.querySelector('#verdict').textContent.includes('AWAITING'));
  await capture('aws.png',{source:'Actual retained AWS observations displayed at the AWS route',mode:'vulnerable',liveAWSExecution:false,evidenceSha256:digest(path.join(root,'web/evidence.json'))});
  await page.goto(base+'/adapter-guide.html',{waitUntil:'networkidle'});
  const adapterHeading=page.getByRole('heading',{name:'2. Implement one adapter function',exact:true});
  const headingBox=await adapterHeading.boundingBox(),codeBox=await adapterHeading.locator('..').locator('pre').boundingBox();
  await capture('adapter.png',{source:'Actual local public adapter guide code and explanation.'},{x:Math.floor(codeBox.x),y:Math.floor(headingBox.y),width:Math.ceil(codeBox.width),height:Math.ceil(codeBox.y+codeBox.height-headingBox.y+12)});
})().catch(error=>{manifest.error=error.stack;process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();manifest.completedAt=new Date().toISOString();manifest.sourceAfter=fingerprints();manifest.sourceStable=JSON.stringify(manifest.sourceBefore)===JSON.stringify(manifest.sourceAfter);
  for(const capture of manifest.captures){const png=fs.readFileSync(path.join(out,capture.file));capture.imageDimensions={width:png.readUInt32BE(16),height:png.readUInt32BE(20)};}
  fs.writeFileSync(path.join(out,'capture-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  console.log(JSON.stringify({output:out,captures:manifest.captures.map(c=>c.file),sourceStable:manifest.sourceStable,blockedRequests:manifest.blockedRequests,pageErrors:manifest.pageErrors,error:manifest.error}));
  if(!manifest.sourceStable||manifest.blockedRequests.length||manifest.pageErrors.length)process.exitCode=1;
});
