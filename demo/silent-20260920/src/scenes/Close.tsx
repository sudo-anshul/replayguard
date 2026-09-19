import {AbsoluteFill} from 'remotion';
import {Brand,C,Reveal,stage} from '../theme';
import {Scene} from '../types';
export const Close:React.FC<{scene:Scene}>=({scene})=><AbsoluteFill style={stage}>
 <div style={{position:'absolute',left:120,top:102}}><Brand size={39}/></div>
 <Reveal at={.15} style={{position:'absolute',left:120,right:120,top:311}}><h1 style={{fontSize:110,fontWeight:650,letterSpacing:-5.5,lineHeight:1.1,margin:0}}>Keep the failure.<br/><span style={{color:C.green}}>Test the repair.</span></h1></Reveal>
 <Reveal at={.65} style={{position:'absolute',left:126,top:676,width:940,height:4,background:C.green}}/>
 <Reveal at={1.05} style={{position:'absolute',left:126,right:126,bottom:120}}><div style={{fontSize:31,color:C.muted,marginBottom:30}}>{scene.title}</div><div style={{fontSize:30,fontWeight:600,marginBottom:13}}>{scene.localUrl??'Live demo URL pending'}</div><div style={{fontSize:27,color:C.muted}}>{scene.repositoryUrl??'github.com/sudo-anshul/replayguard'}</div></Reveal>
</AbsoluteFill>;
