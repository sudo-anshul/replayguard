import {interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
import {Shell} from '../Shell';
import {C,clamp,mono,Reveal} from '../theme';
import {Scene} from '../types';
export const Scope:React.FC<{scene:Scene}>=({scene})=>{
 const f=useCurrentFrame(),{fps}=useVideoConfig();const time=f/fps;const splitAt=scene.duration*.52;const correct=time>=splitAt;
 const title=correct?'orderId':'sku';const color=correct?C.green:C.red;
 return <Shell scene={scene}>
  <div style={{position:'absolute',left:100,right:100,top:243,display:'flex',justifyContent:'space-between',alignItems:'center'}}><div style={{fontSize:32,color:C.muted}}>Two distinct business orders</div><div style={{fontSize:32,color:C.muted}}>Fulfillment key</div></div>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0}}>
   {[0,1].map(i=><path key={i} d={correct?`M700 ${440+i*240}C1010 ${440+i*240} 1020 ${440+i*240} 1290 ${440+i*240}`:`M700 ${440+i*240}C1010 ${440+i*240} 1020 560 1290 560`} fill="none" stroke={color} strokeWidth="5" strokeDasharray="850" strokeDashoffset={850*(1-interpolate(time,[correct?splitAt:0,correct?splitAt+.85:.85],[0,1],clamp))}/>) }
  </svg>
  {[0,1].map(i=><Reveal key={i} at={i*.28} style={{position:'absolute',left:100,top:351+i*240,width:600,height:180,background:C.white,border:`2px solid ${C.line}`,borderRadius:16,padding:'30px 36px',boxSizing:'border-box'}}><div style={{fontFamily:mono,fontSize:38,fontWeight:600}}>ORDER {i===0?'A':'B'}</div><div style={{fontSize:27,color:C.muted,marginTop:18}}>Same product · different order ID</div></Reveal>)}
  <div style={{position:'absolute',left:1250,top:333,fontSize:27,color:C.muted}}>key = <strong style={{fontFamily:mono,color}}>{title}</strong></div>
  {correct?[0,1].map(i=><Reveal key={i} at={splitAt+i*.2} style={{position:'absolute',left:1270,top:384+i*240,width:475,height:130,background:C.mint,border:`2px solid ${C.green}`,borderRadius:16,display:'grid',placeItems:'center',fontSize:36,fontFamily:mono}}>ORDER {i===0?'A':'B'}</Reveal>):<Reveal at={.4} style={{position:'absolute',left:1270,top:484,width:475,height:150,background:C.warm,border:`2px solid ${C.red}`,borderRadius:16,display:'grid',placeItems:'center',fontSize:36,fontFamily:mono}}>SHARED PRODUCT</Reveal>}
  <Reveal at={.7} style={{position:'absolute',left:100,right:100,top:830,color,fontSize:42,fontWeight:600,letterSpacing:-1}}>{correct?'One key for each business order.':'A product key merges two valid orders.'}</Reveal>
 </Shell>;
};
