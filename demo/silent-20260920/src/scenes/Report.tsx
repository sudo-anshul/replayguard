import {Shell} from '../Shell';
import {C,mono,Reveal} from '../theme';
import {Scene} from '../types';
export const Report:React.FC<{scene:Scene}>=({scene})=><Shell scene={scene}>
 <div style={{position:'absolute',left:76,right:76,top:251,display:'grid',gridTemplateColumns:`repeat(${Math.max(scene.rows?.length??0,1)},1fr)`,gap:30}}>
 {(scene.rows??[]).map((row,index)=>{const pass=row.status==='pass';return <Reveal key={row.label} at={index*.7} style={{background:C.white,border:`1px solid ${C.line}`,borderTop:`5px solid ${pass?C.green:C.red}`,borderRadius:12,padding:'34px 30px',height:610,boxSizing:'border-box'}}><div style={{fontSize:28,color:C.muted}}>{row.label}</div><div style={{fontSize:46,fontWeight:650,color:pass?C.green:C.red,margin:'21px 0 25px',textTransform:'capitalize'}}>{row.status}</div>{row.expected.map(order=><div key={order.id} style={{borderTop:`1px solid ${C.line}`,paddingTop:22,marginTop:22}}><div style={{fontFamily:mono,fontSize:29}}>{order.id}</div><div style={{display:'flex',alignItems:'baseline',gap:15,marginTop:13}}><strong style={{fontSize:68,fontWeight:600,letterSpacing:-3}}>{row.observed.find(o=>o.id===order.id)?.count??'—'}</strong><span style={{fontSize:25,color:C.muted}}>observed / {order.count} expected</span></div></div>)}<div style={{marginTop:30,fontSize:20,color:C.muted}}>Report SHA {row.sourceHash.slice(0,12)}</div></Reveal>})}
 {!scene.rows?.length?<div style={{fontSize:38,color:C.muted,marginTop:180,textAlign:'center'}}>Awaiting verified output reports</div>:null}
 </div>
</Shell>;
