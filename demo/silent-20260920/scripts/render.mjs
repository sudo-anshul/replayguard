import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2),arg=k=>args.includes(k)?args[args.indexOf(k)+1]:undefined;
const props=path.join(root,'prepared.json'),manifest=arg('--manifest');
if(manifest){const prepared=spawnSync(process.execPath,[path.join(root,'scripts/prepare.mjs'),'--manifest',path.resolve(manifest),...(args.includes('--draft')?['--draft']:[])],{stdio:'inherit'});if(prepared.status)process.exit(prepared.status);}
if(!fs.existsSync(props))throw new Error('Prepare the manifest first.');
const film=JSON.parse(fs.readFileSync(props,'utf8'));
const frame=arg('--frame');
if(frame===undefined&&film.draft&&!args.includes('--draft'))throw new Error('Draft film requires explicit --draft; never publish it.');
const output=path.resolve(arg('--output')??path.join(root,frame!==undefined?'previews/frame.png':'render/replayguard-demo-silent.mp4'));fs.mkdirSync(path.dirname(output),{recursive:true});
const command=frame!==undefined?['remotion','still','src/index.tsx','ReplayGuardSilent',output,`--props=${props}`,`--frame=${frame}`]:['remotion','render','src/index.tsx','ReplayGuardSilent',output,`--props=${props}`,'--codec=h264','--crf=18','--pixel-format=yuv420p','--muted','--concurrency=1','--image-format=jpeg','--jpeg-quality=88'];
if(arg('--scale'))command.push(`--scale=${arg('--scale')}`);
if(arg('--frames'))command.push(`--frames=${arg('--frames')}`);
const run=spawnSync('npx',command,{cwd:root,stdio:'inherit'});process.exit(run.status??1);
