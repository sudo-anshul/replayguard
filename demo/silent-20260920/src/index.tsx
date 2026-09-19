import {Composition,registerRoot} from 'remotion';
import {SilentFilm} from './Film';
import {Film} from './types';
const draft:Film={title:'ReplayGuard silent tutorial',fps:30,durationFrames:360,draft:true,silent:true,scenes:[{id:'scope-preview',kind:'scope',duration:12,durationFrames:360,startFrame:0,chapter:'02 / Challenge the key',title:'Same product ≠ same order.',support:'The fulfillment key must identify the business order.',scope:'Explanation'}]};
registerRoot(()=> <Composition id="ReplayGuardSilent" component={SilentFilm} width={1920} height={1080} fps={30} durationInFrames={draft.durationFrames} defaultProps={draft} calculateMetadata={({props})=>({durationInFrames:props.durationFrames,fps:props.fps})}/>);
