import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2),arg=k=>args.includes(k)?args[args.indexOf(k)+1]:undefined;
const manifest=path.resolve(arg('--manifest')??path.join(root,'storyboard.json'));
const draft=args.includes('--draft'),base=path.dirname(manifest);
const source=JSON.parse(fs.readFileSync(manifest,'utf8'));
const catalogPath=path.resolve(base,source.assetsFile??'assets.json');
const catalog=JSON.parse(fs.readFileSync(catalogPath,'utf8'));
const catalogBase=path.dirname(catalogPath),resolve=p=>path.resolve(catalogBase,p);
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const media=path.join(root,'public','media');fs.mkdirSync(media,{recursive:true});
const assets=[],warnings=[],missing=[];let startFrame=0,captureBasedSeconds=0,editorialHoldSeconds=0;
const fps=30;
for(const [id,entry] of Object.entries(catalog.supportingEvidence??{})){const file=resolve(entry.path);if(entry.expectedSha256&&sha(file)!==entry.expectedSha256)throw new Error(`Frozen supporting evidence changed: ${id}.`);assets.push({role:'supporting-evidence',id,source:file,sha256:sha(file),bytes:fs.statSync(file).size});}

function probe(file){const p=spawnSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',file],{encoding:'utf8'});if(p.status)throw new Error(p.stderr);return JSON.parse(p.stdout);}
function reportRow(id){
 const entry=catalog.reports[id];if(!entry?.path)throw new Error(`Report ${id} has no source path.`);
 const file=resolve(entry.path),report=JSON.parse(fs.readFileSync(file,'utf8'));
 const result=report.results.find(r=>r.caseId===(entry.caseId??'interleaved-retries')&&(!entry.candidateId||r.candidateId===entry.candidateId));
 if(!result)throw new Error(`No matching recorded result for ${id}.`);
 const expected=result.expectedOrders.map(x=>({id:x.order.orderId,count:x.count}));
 const observed=expected.map(x=>({id:x.id,count:result.receipts.filter(r=>r.order.orderId===x.id).length}));
 const sourceHash=sha(file);let execution;
 if(entry.execution){execution=JSON.parse(fs.readFileSync(resolve(entry.execution),'utf8'));if(execution.reportSha256!==sourceHash)throw new Error(`Report hash differs from actual execution ${id}.`);if((execution.status??execution.reportedStatus)!==result.status)throw new Error(`Status mismatch ${id}.`);for(const row of observed)if((execution.receiptCounts??execution.observedReceiptsByOrder)[row.id]!==row.count)throw new Error(`Receipt mismatch ${id}/${row.id}.`);}
 assets.push({role:'recorded-report',id,source:file,sha256:sourceHash,bytes:fs.statSync(file).size,...(entry.execution?{executionSource:resolve(entry.execution),executionSha256:sha(resolve(entry.execution))}:{})});
 return {label:entry.label,status:result.status,expected,observed,sourceHash,...(execution?{exitCode:execution.processExitCode}:{})};
}
if(source.silent!==true||source.audio)throw new Error('This release must be explicitly silent with no audio source.');
const scenes=source.scenes.map(raw=>{
 const s={...raw};
 if(!['recorded','scope','fault','report','package','close'].includes(s.kind))throw new Error(`Invalid scene ${s.id}.`);
  if(s.audio)throw new Error(`Audio source is forbidden in ${s.id}.`);
  if(s.kind==='close'&&!draft&&(!s.localUrl||!s.repositoryUrl))throw new Error('Final close requires the verified live and repository URLs.');
 if(!(s.duration>0))throw new Error(`Invalid duration ${s.id}.`);
 if((s.title??'').length>92||(s.support??'').length>130)throw new Error(`Tighten the on-screen copy for ${s.id}.`);
 s.durationFrames=Math.round(s.duration*fps);s.duration=s.durationFrames/fps;s.startFrame=startFrame;startFrame+=s.durationFrames;
 if(s.kind==='recorded'){
  const entry=catalog.captures[s.capture];
  if(!entry?.path||!fs.existsSync(resolve(entry.path))){missing.push(s.capture);if(!draft)throw new Error(`Missing genuine capture ${s.capture}.`);}
  else {
   const file=resolve(entry.path),p=probe(file),v=p.streams.find(x=>x.codec_type==='video');if(!v)throw new Error(`No video in ${s.capture}.`);
   const duration=Number(v.duration??p.format.duration),speed=s.playbackRate??1,start=s.videoStart??0;
   if(speed<.75||speed>1.5)throw new Error(`Capture speed must be 0.75–1.5× for ${s.id}.`);
   if(start+s.duration*speed>duration+.04)throw new Error(`${s.id} needs ${(start+s.duration*speed-duration).toFixed(3)}s more recorded footage. Trim deliberately; never silently hold/loop.`);
   const crop=s.crop??{x:0,y:0,w:v.width,h:v.height};
   if(crop.x<0||crop.y<0||crop.w<=0||crop.h<=0||crop.x+crop.w>v.width||crop.y+crop.h>v.height)throw new Error(`Invalid crop ${s.id}.`);
   const digest=sha(file),name=`${digest.slice(0,18)}${path.extname(file)}`,destination=path.join(media,name);
   if(!fs.existsSync(destination)){try{fs.linkSync(file,destination);}catch{fs.copyFileSync(file,destination);}}
   s.video=`media/${name}`;s.sourceWidth=v.width;s.sourceHeight=v.height;s.crop=crop;s.captureMethod=entry.method;
   let editorial;
   if(entry.encodedManifest){editorial=JSON.parse(fs.readFileSync(resolve(entry.encodedManifest),'utf8'));if(editorial.videoSha256!==digest)throw new Error(`Edited capture hash mismatch ${s.id}.`);const clipEnd=start+s.duration*speed;const holds=editorial.frames.reduce((sum,f)=>{const holdStart=f.outputStartSeconds+f.retainedIntervalSeconds,holdEnd=holdStart+f.editorialReadingHoldSeconds;return sum+Math.max(0,Math.min(clipEnd,holdEnd)-Math.max(start,holdStart));},0)/speed;s.editorialReadingHoldSeconds=holds;s.sourceElapsedSeconds=editorial.sourceElapsedSeconds;editorialHoldSeconds+=holds;}
   assets.push({role:'captured-actions',id:s.capture,scene:s.id,source:file,sha256:digest,bytes:fs.statSync(file).size,sourceWidth:v.width,sourceHeight:v.height,sourceDuration:duration,start,speed,duration:s.duration,crop,method:entry.method,recordedAt:entry.recordedAt??null,...(editorial?{originalCaptureElapsedSeconds:editorial.sourceElapsedSeconds,omittedElapsedGapSeconds:editorial.omittedElapsedGapSeconds,editorialReadingHoldSeconds:s.editorialReadingHoldSeconds,encodedManifest:resolve(entry.encodedManifest),encodedManifestSha256:sha(resolve(entry.encodedManifest))}:{}),...(entry.manifest?{captureManifest:resolve(entry.manifest),captureManifestSha256:sha(resolve(entry.manifest))}:{})});
   captureBasedSeconds+=s.duration;
  }
  delete s.capture;
 }
 if(s.kind==='report'){
  if(!s.reportSources?.length)throw new Error(`${s.id} must reference actual reports.`);
  s.rows=s.reportSources.map(reportRow);delete s.reportSources;
 }
 for(const h of s.highlights??[]){if(h.at<0||h.until>s.duration||h.until-h.at<.5||h.x<76||h.y<196||h.x+h.w>1844||h.y+h.h>956)throw new Error(`Invalid/evidence-covering highlight ${s.id}.`);}
 return s;
});
const seconds=startFrame/fps;
if(seconds>175)throw new Error(`Silent film is ${seconds}s; maximum175s.`);
if(!draft&&captureBasedSeconds/seconds<.66)throw new Error('Final silent film requires at least66% captured-action content, with reading holds separately disclosed.');
if(missing.length)warnings.push(`Missing captures: ${[...new Set(missing)].join(', ')}`);
const film={title:source.title,fps,durationFrames:startFrame,scenes,silent:true,draft};
fs.writeFileSync(path.join(root,'prepared.json'),JSON.stringify(film,null,2)+'\n');
fs.writeFileSync(path.join(root,'asset-manifest.json'),JSON.stringify({preparedAt:new Date().toISOString(),manifest,manifestSha256:sha(manifest),catalog:catalogPath,catalogSha256:sha(catalogPath),durationSeconds:seconds,capturedActionContentSeconds:captureBasedSeconds,capturedActionContentRatio:captureBasedSeconds/seconds,editorialReadingHoldSeconds:editorialHoldSeconds,metricScope:'Captured-action content includes explicitly documented reading holds. It is not continuous native-video footage or a claim about execution duration.',silent:true,draft,assets,warnings},null,2)+'\n');
console.log(JSON.stringify({durationSeconds:seconds,sceneCount:scenes.length,silent:true,draft,missing:[...new Set(missing)],capturedActionContentRatio:captureBasedSeconds/seconds,editorialReadingHoldSeconds:editorialHoldSeconds},null,2));
