import {interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
import {Shell} from '../Shell';
import {C,clamp,Reveal} from '../theme';
import {Scene} from '../types';
export const Fault:React.FC<{scene:Scene}>=({scene})=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig();const beat=Math.min(1.7,scene.duration/5);const before=scene.faultBoundary==='before-response';
 const labels=['Order received','Receipt committed',before?'Response fails':'Worker crashes','Message returns'];
 const descriptions=['A valid business order','The effect already exists',before?'Before success is returned':'After fulfillment succeeds','SQS delivers the retry'];
 return <Shell scene={scene}>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0}}><path d="M278 518H1642" stroke={C.line} strokeWidth="4"/><path d="M278 518H1642" stroke={C.green} strokeWidth="5" strokeDasharray="1364" strokeDashoffset={1364*(1-interpolate(frame,[.5*fps,(3*beat+.5)*fps],[0,1],clamp))}/></svg>
  <div style={{position:'absolute',left:90,right:90,top:402,display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:36}}>{labels.map((label,i)=><Reveal key={label} at={i*beat+.2} style={{textAlign:'center'}}><div style={{margin:'0 auto 34px',width:232,height:232,background:i===2?C.warm:C.white,border:`2px solid ${i===2?C.red:C.green}`,borderRadius:24,display:'grid',placeItems:'center',fontSize:i===0?40:92,fontWeight:550,color:i===2?C.red:C.green}}>{i===0?'ORDER':i===1?'✓':i===2?'×':'↻'}</div><div style={{fontSize:34,fontWeight:650,letterSpacing:-.6}}>{label}</div><div style={{fontSize:25,color:C.muted,marginTop:16,lineHeight:1.4}}>{descriptions[i]}</div></Reveal>)}</div>
 </Shell>;
};
