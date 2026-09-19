import {ReactNode} from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {Scene} from './types';
import {Brand,C,clamp,Reveal,stage} from './theme';
export const Shell:React.FC<{scene:Scene;children:ReactNode;dark?:boolean}>=({scene,children})=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig();
 return <AbsoluteFill style={stage}>
  <div style={{position:'absolute',left:76,right:76,top:40,display:'flex',justifyContent:'space-between',alignItems:'center'}}><Brand/><div style={{display:'flex',gap:22,alignItems:'center',fontSize:22,color:C.muted}}><span>{scene.chapter}</span><span style={{display:'inline-block',width:6,height:6,borderRadius:3,background:C.green}}/><strong style={{fontWeight:650,color:C.green}}>{scene.helper?'Actual local Python · separate recording helper':scene.scope}</strong></div></div>
  <Reveal at={.05} style={{position:'absolute',left:76,right:76,top:104}}><h1 style={{fontSize:57,fontWeight:650,lineHeight:1.09,letterSpacing:-2.25,margin:0}}>{scene.title}</h1></Reveal>
  {children}
  <div style={{position:'absolute',left:76,right:76,bottom:45,minHeight:52,display:'flex',alignItems:'center',justifyContent:'space-between',gap:40}}><div style={{fontSize:29,lineHeight:1.25,fontWeight:500,color:C.ink,maxWidth:1450}}>{scene.support}</div>{scene.proofNote?<div style={{fontSize:18,lineHeight:1.35,color:C.muted,maxWidth:340,textAlign:'right',whiteSpace:'pre-line'}}>{scene.proofNote}</div>:null}</div>
  <div style={{position:'absolute',left:76,right:76,bottom:24,height:2,background:C.line}}><div style={{height:2,background:C.green,width:`${100*interpolate(frame,[0,scene.duration*fps],[0,1],clamp)}%`}}/></div>
 </AbsoluteFill>;
};
