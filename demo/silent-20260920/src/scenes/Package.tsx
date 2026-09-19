import {Shell} from '../Shell';
import {C,mono,Reveal} from '../theme';
import {Scene} from '../types';
export const Package:React.FC<{scene:Scene}>=({scene})=><Shell scene={scene}>
 <div style={{position:'absolute',left:140,top:304,right:140,display:'grid',gridTemplateColumns:'1fr 1fr',gap:34}}>{[
  ['01','INPUTS','The orders and delivery sequence'],['02','FAULT','The exact interruption boundary'],['03','ASSERTIONS','What each valid order must receive'],['04','EVIDENCE','Original receipts and result reports'],
 ].map(([n,title,description],i)=><Reveal key={n} at={i*.65} style={{background:C.white,border:`1px solid ${C.line}`,borderRadius:16,padding:'36px 38px',height:223,boxSizing:'border-box'}}><div style={{display:'flex',alignItems:'center',gap:26}}><span style={{fontFamily:mono,fontSize:28,color:C.green}}>{n}</span><strong style={{fontSize:37,letterSpacing:-.8}}>{title}</strong></div><p style={{fontSize:29,lineHeight:1.4,color:C.muted,margin:'27px 0 0'}}>{description}</p></Reveal>)}</div>
</Shell>;
