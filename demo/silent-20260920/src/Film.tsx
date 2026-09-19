import {AbsoluteFill,Sequence} from 'remotion';
import {Film as FilmProps,Scene} from './types';
import {C,sans} from './theme';
import {Recorded} from './scenes/Recorded';
import {Scope} from './scenes/Scope';
import {Fault} from './scenes/Fault';
import {Report} from './scenes/Report';
import {Package} from './scenes/Package';
import {Close} from './scenes/Close';
const Visual:React.FC<{scene:Scene}>=({scene})=>{
 switch(scene.kind){case 'recorded':return <Recorded scene={scene}/>;case 'scope':return <Scope scene={scene}/>;case 'fault':return <Fault scene={scene}/>;case 'report':return <Report scene={scene}/>;case 'package':return <Package scene={scene}/>;case 'close':return <Close scene={scene}/>;}
};
export const SilentFilm:React.FC<FilmProps>=film=><AbsoluteFill style={{background:C.paper,fontFamily:sans}}>
 {film.scenes.map(scene=><Sequence key={scene.id} name={scene.id} from={scene.startFrame} durationInFrames={scene.durationFrames}><Visual scene={scene}/></Sequence>)}
 {film.draft?<div style={{position:'absolute',right:24,bottom:2,fontSize:17,color:C.red,background:'white',padding:'4px 8px'}}>DRAFT · ASSETS PENDING · SILENT</div>:null}
</AbsoluteFill>;
