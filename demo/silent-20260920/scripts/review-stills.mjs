if (!process.env.CHROME_EXECUTABLE) throw new Error('Set CHROME_EXECUTABLE to an installed Chrome/Chromium executable.');
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {openBrowser,selectComposition,renderStill} from '@remotion/renderer';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const props=JSON.parse(fs.readFileSync(path.join(root,'prepared.json'),'utf8'));
const outputDir=path.join(root,'previews');fs.mkdirSync(outputDir,{recursive:true});
const serveUrl=await bundle({enableCaching:false,entryPoint:path.join(root,'src/index.tsx'),publicDir:path.join(root,'public'),outDir:path.join(root,'.review-bundle'),webpackOverride:config=>({...config,cache:false})});
const browserExecutable=process.env.CHROME_EXECUTABLE;
const browser=await openBrowser('chrome',{browserExecutable});
try {
 const composition=await selectComposition({serveUrl,id:'ReplayGuardSilent',inputProps:props,browserExecutable,browserInstance:browser});
 const selections=[['01-aws-hook',6],['03-aws-comparison',4],['03-aws-commit',2],['03-aws-worker',2],['19-close',4],['02-first-failure',4],['02-fault-explanation',6.5],['05-key-scope',3],['05-key-scope',8],['16-package',4.5],['04-two-orders',3],['04-final-snapshot',4],['07-baseline',5],['08-edit-sku',3],['08-edit-sku-saved',2],['09-run-sku',4],['10-import-broken',5],['11-failure-trace',2.8],['11-failure-trace-trail',2],['11-failure-trace-retry',2],['12-restore',3],['12-restore-saved',2],['13-run-restored',4],['14-import-restored',5],['15-recorded-summary',6],['17-export',2.7],['18-states',3],['18-unresolved',2]];
 const onlyAt=process.argv.indexOf('--only');const only=onlyAt<0?null:new Set((process.argv[onlyAt+1]??'').split(','));
 const checkpoints=selections.filter(([id])=>!only||only.has(id)).map(([id,offset])=>{const s=props.scenes.find(s=>s.id===id);if(!s)throw new Error(`Missing proof scene ${id}`);return [id,s.startFrame/30+Math.min(offset,s.duration-.1)];});
 const results=[];
 for(const [label,seconds] of checkpoints){const frame=Math.round(seconds*30),output=path.join(outputDir,`${String(frame).padStart(4,'0')}-${label}.png`);await renderStill({serveUrl,composition,inputProps:props,frame,output,imageFormat:'png',browserExecutable,browserInstance:browser,logLevel:'error'});results.push({label,seconds,frame,output});console.log(`Reviewed frame: ${label}`);}
 fs.writeFileSync(path.join(outputDir,'manifest.json'),JSON.stringify(results,null,2)+'\n');
}finally{await browser.close({silent:true});}
