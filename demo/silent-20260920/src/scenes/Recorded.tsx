import {Video} from '@remotion/media';
import {staticFile,interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
import {Shell} from '../Shell';
import {C,clamp,ease} from '../theme';
import {Scene} from '../types';
export const Recorded:React.FC<{scene:Scene}>=({scene})=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig();const time=frame/fps;
 const box={x:76,y:196,w:1768,h:760};
 const initial=scene.crop??{x:0,y:0,w:scene.sourceWidth??1440,h:scene.sourceHeight??900};
 const focus=scene.focus;const zoom=focus?interpolate(time,[focus.at,focus.at+.8,focus.until-.8,focus.until],[0,1,1,0],{...clamp,easing:ease}):0;
 const crop=focus?{x:initial.x+(focus.crop.x-initial.x)*zoom,y:initial.y+(focus.crop.y-initial.y)*zoom,w:initial.w+(focus.crop.w-initial.w)*zoom,h:initial.h+(focus.crop.h-initial.h)*zoom}:initial;
 const scale=Math.min(box.w/crop.w,box.h/crop.h);
 const padX=(box.w-crop.w*scale)/2,padY=(box.h-crop.h*scale)/2;
 return <Shell scene={scene}>
  <div style={{position:'absolute',left:box.x,top:box.y,width:box.w,height:box.h,overflow:'hidden',background:C.white,border:`1px solid ${C.line}`,borderRadius:16,boxShadow:'0 12px 30px rgba(21,45,42,.06)'}}>
   {scene.video?<div style={{position:'absolute',left:padX,top:padY,width:crop.w*scale,height:crop.h*scale,overflow:'hidden'}}><Video src={staticFile(scene.video)} muted trimBefore={Math.round((scene.videoStart??0)*fps)} playbackRate={scene.playbackRate??1} style={{position:'absolute',left:-crop.x*scale,top:-crop.y*scale,width:(scene.sourceWidth??1440)*scale,height:(scene.sourceHeight??900)*scale,maxWidth:'none'}}/></div>:<div style={{display:'grid',height:'100%',placeItems:'center',fontSize:37,color:C.muted}}>Awaiting the new recorded interaction</div>}
  </div>
  {(scene.highlights??[]).map((h,index)=>{
   if(time<h.at||time>h.until)return null;const color=h.tone==='red'?C.red:h.tone==='amber'?C.amber:C.green;
   return <div key={index} style={{position:'absolute',left:h.x,top:h.y,width:h.w,height:h.h,border:`4px solid ${color}`,borderRadius:8,boxShadow:'0 0 0 4px rgba(255,255,255,.8)',opacity:interpolate(time,[h.at,h.at+.2,h.until-.2,h.until],[0,1,1,0],clamp)}}>{h.label?<div style={{position:'absolute',left:0,top:-42,color:'white',background:color,fontSize:23,fontWeight:600,padding:'4px 11px',borderRadius:4,whiteSpace:'nowrap'}}>{h.label}</div>:null}</div>;
  })}
 </Shell>;
};
