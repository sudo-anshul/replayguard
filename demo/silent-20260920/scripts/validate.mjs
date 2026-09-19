import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const video=path.resolve(process.argv[2]??path.join(root,'render/replayguard-demo-silent.mp4'));
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const input=JSON.parse(fs.readFileSync(path.join(root,'prepared.json'),'utf8'));
const assets=JSON.parse(fs.readFileSync(path.join(root,'asset-manifest.json'),'utf8'));
const probed=spawnSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',video],{encoding:'utf8'});
if(probed.status)throw new Error(probed.stderr);
const probe=JSON.parse(probed.stdout);fs.writeFileSync(path.join(root,'final-ffprobe.json'),JSON.stringify(probe,null,2)+'\n');
const decode=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-i',video,'-f','null','-'],{encoding:'utf8'});
fs.writeFileSync(path.join(root,'final-decode.log'),decode.stderr);
const v=probe.streams.filter(x=>x.codec_type==='video'),audio=probe.streams.filter(x=>x.codec_type==='audio');
const duration=Number(probe.format.duration),sourceChecks=assets.assets.map(a=>({id:a.id,role:a.role,unchanged:fs.existsSync(a.source)&&sha(a.source)===a.sha256}));
const checks={
  fullDecodePassed:decode.status===0,
  zeroAudioStreams:audio.length===0,
  singleVideoStream:v.length===1,
  fullHD:v[0]?.width===1920&&v[0]?.height===1080,
  h264:v[0]?.codec_name==='h264',
  containerFrameRate30:v[0]?.avg_frame_rate==='30/1',
  frameCountMatchesComposition:Number(v[0]?.nb_frames)===input.durationFrames,
  underThreeMinutes:duration<180,
  withinEditorialBudget:duration<=175,
  durationMatchesComposition:Math.abs(duration-input.durationFrames/input.fps)<1/30,
  notDraft:input.draft===false&&assets.draft===false,
  explicitlySilent:input.silent===true&&assets.silent===true,
  capturedActionContentAtLeast66Percent:assets.capturedActionContentRatio>=.66,
  sourceAssetsUnchanged:sourceChecks.every(c=>c.unchanged),
};
const result={validatedAt:new Date().toISOString(),status:Object.values(checks).every(Boolean)?'passed':'incomplete',video:{file:video,sha256:sha(video),bytes:fs.statSync(video).size,durationSeconds:duration,width:v[0]?.width,height:v[0]?.height,codec:v[0]?.codec_name,frames:Number(v[0]?.nb_frames),containerFrameRate:v[0]?.avg_frame_rate,audioStreams:audio.length},checks,sourceChecks,capturedActionContentSeconds:assets.capturedActionContentSeconds,capturedActionContentRatio:assets.capturedActionContentRatio,editorialReadingHoldSeconds:assets.editorialReadingHoldSeconds,metricScope:assets.metricScope,preparedSha256:sha(path.join(root,'prepared.json')),assetManifestSha256:sha(path.join(root,'asset-manifest.json')),scope:'Technical validation. Captured source rate is documented per asset; 30 fps describes the final composition, not necessarily capture rate. Visual pacing/readability review is recorded separately.'};
fs.writeFileSync(path.join(root,'final-validation.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));if(result.status!=='passed')process.exit(1);
