import {CSSProperties, ReactNode} from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
export const C={paper:'#f4f6f2',white:'#fff',ink:'#152d2a',muted:'#58716b',line:'#cfdbd2',green:'#176d50',red:'#a43f21',amber:'#946419',mint:'#e8f3e9',warm:'#fff0e6',lime:'#d5f184'};
export const sans='Avenir Next, Segoe UI, Arial, sans-serif';
export const mono='SFMono-Regular, Menlo, Consolas, monospace';
export const clamp={extrapolateLeft:'clamp' as const,extrapolateRight:'clamp' as const};
export const ease=Easing.bezier(.16,1,.3,1);
export const stage:CSSProperties={position:'absolute',inset:0,background:C.paper,color:C.ink,fontFamily:sans,overflow:'hidden'};
export const Reveal:React.FC<{children?:ReactNode;at?:number;style?:CSSProperties}>=({children,at=0,style})=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig();
 return <div style={{opacity:interpolate(frame,[at*fps,(at+.4)*fps],[0,1],clamp),translate:`0 ${interpolate(frame,[at*fps,(at+.55)*fps],[20,0],{...clamp,easing:ease})}px`,...style}}>{children}</div>;
};
export const Brand:React.FC<{size?:number}>=({size=30})=><div style={{display:'flex',alignItems:'center',gap:13,fontWeight:650,fontSize:size,letterSpacing:-1}}><svg width={size*1.15} height={size*1.15} viewBox="0 0 40 40" fill="none"><rect width="40" height="40" rx="11" fill={C.lime}/><path d="M12 15.5h11a6 6 0 0 1 6 6v3M28 24.5H17a6 6 0 0 1-6-6v-3m5-4.5-4.5 4.5L16 20m8 0 4.5 4.5L24 29" stroke={C.ink} strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round"/></svg>ReplayGuard</div>;
