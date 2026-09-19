import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {bundle} from '@remotion/bundler';
import {openBrowser,selectComposition,renderMedia} from '@remotion/renderer';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const arg=k=>{const i=process.argv.indexOf(k);return i<0?undefined:process.argv[i+1];};
const props=JSON.parse(fs.readFileSync(path.join(root,'prepared.json'),'utf8'));
if(props.draft||props.silent!==true)throw new Error('Bounded release render requires final silent props.');
const output=path.resolve(arg('--output')??path.join(root,'render/replayguard-demo-silent.mp4'));
const chunkSize=Number(arg('--chunk-frames')??400);
if(!Number.isInteger(chunkSize)||chunkSize<30||chunkSize>600)throw new Error('Chunk size must be30–600frames.');
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sourceFiles=dir=>fs.readdirSync(dir,{withFileTypes:true}).flatMap(x=>x.isDirectory()?sourceFiles(path.join(dir,x.name)):[path.join(dir,x.name)]).sort();
const fingerprint=crypto.createHash('sha256').update([path.join(root,'prepared.json'),...sourceFiles(path.join(root,'src'))].map(sha).join('\n')).digest('hex');
const partsRoot=path.join(root,'.render-parts',fingerprint.slice(0,16));fs.mkdirSync(partsRoot,{recursive:true});fs.mkdirSync(path.dirname(output),{recursive:true});
const browserExecutable=process.env.CHROME_EXECUTABLE;
if(!browserExecutable||!fs.existsSync(browserExecutable))throw new Error('Set CHROME_EXECUTABLE to installed Chrome/Chromium.');
const serveUrl=await bundle({entryPoint:path.join(root,'src/index.tsx'),publicDir:path.join(root,'public'),outDir:path.join(root,'.bounded-bundle'),enableCaching:false,symlinkPublicDir:true});
const browser=await openBrowser('chrome',{browserExecutable});
const manifest={fingerprint,preparedSha256:sha(path.join(root,'prepared.json')),method:'Sequential inclusive frame ranges from one frozen composition, then FFmpeg stream-copy concatenation. No audio and no omitted/repeated composition frames.',chunkSize,totalFrames:props.durationFrames,parts:[]};
try{
 const composition=await selectComposition({serveUrl,id:'ReplayGuardSilent',inputProps:props,browserExecutable,browserInstance:browser});
 for(let start=0,index=0;start<props.durationFrames;start+=chunkSize,index++){
  const end=Math.min(props.durationFrames-1,start+chunkSize-1),file=path.join(partsRoot,`${String(index).padStart(3,'0')}.mp4`),expectedFrames=end-start+1;
  let valid=false;
  if(fs.existsSync(file)){
   const checked=spawnSync('ffprobe',['-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','json',file],{encoding:'utf8'});
   try{valid=checked.status===0&&Number(JSON.parse(checked.stdout).streams[0].nb_frames)===expectedFrames;}catch{}
  }
  if(!valid){
   console.log(`Rendering chunk${index+1}: frames${start}–${end}`);
   await renderMedia({serveUrl,composition,inputProps:props,outputLocation:file,frameRange:[start,end],codec:'h264',crf:18,pixelFormat:'yuv420p',muted:true,concurrency:1,imageFormat:'jpeg',jpegQuality:88,browserExecutable,puppeteerInstance:browser,logLevel:'error',overwrite:true});
  }
  const probe=spawnSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',file],{encoding:'utf8'});
  if(probe.status)throw new Error(probe.stderr);const p=JSON.parse(probe.stdout),v=p.streams.find(s=>s.codec_type==='video');
  if(Number(v?.nb_frames)!==expectedFrames||p.streams.some(s=>s.codec_type==='audio'))throw new Error(`Chunk frame/audio mismatch${index}`);
  manifest.parts.push({index,start,end,frames:expectedFrames,path:path.relative(root,file),sha256:sha(file),bytes:fs.statSync(file).size});
  fs.writeFileSync(path.join(root,'bounded-render-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  console.log(`Finished chunk${index+1}; ${end+1}/${props.durationFrames}frames`);
 }
}finally{await browser.close({silent:true});}
const concat=path.join(partsRoot,'parts.ffconcat');fs.writeFileSync(concat,manifest.parts.map(p=>`file '${path.join(root,p.path).replaceAll("'","'\\''")}'`).join('\n')+'\n');
const joined=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',concat,'-map','0:v:0','-c','copy','-an','-movflags','+faststart',output],{encoding:'utf8'});
if(joined.status)throw new Error(joined.stderr);
manifest.output={file:output,sha256:sha(output),bytes:fs.statSync(output).size};fs.writeFileSync(path.join(root,'bounded-render-manifest.json'),JSON.stringify(manifest,null,2)+'\n');console.log(`Encoded ${props.durationFrames}frames with zero audio: ${output}`);
