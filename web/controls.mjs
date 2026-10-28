// Left hand moves (WASD), right hand acts: face buttons in a diamond on IJKL, shoulders above it.
export const keyButtons={KeyW:4,KeyS:5,KeyA:6,KeyD:7,ArrowUp:4,ArrowDown:5,ArrowLeft:6,ArrowRight:7,
  KeyT:4,KeyG:5,KeyF:6,KeyH:7,KeyK:0,Space:0,KeyJ:1,KeyL:8,KeyI:9,KeyU:10,KeyO:11,KeyY:12,KeyP:13,
  Enter:3,ShiftLeft:2,ShiftRight:2,KeyC:14,KeyM:15};
const padButtons=[0,8,1,9,10,11,12,13,2,3,14,15,4,5,6,7];
// On a pad with sticks, WASD and the arrows move the left and right stick, and TFGH is the D-pad.
const stickKeys={KeyA:[0,-1],KeyD:[0,1],KeyW:[1,-1],KeyS:[1,1],ArrowLeft:[2,-1],ArrowRight:[2,1],ArrowUp:[3,-1],ArrowDown:[3,1]};
const DEAD_ZONE=.15;
export function isControlKey(code,analog){return code in keyButtons||(analog&&code in stickKeys);}
export function inputMask(keys,touch,pad,analog=false){
  let mask=0;
  for(const key of keys)if(key in keyButtons&&!(analog&&key in stickKeys))mask|=1<<keyButtons[key];
  for(const button of touch)mask|=1<<button;
  if(pad){
    pad.buttons?.forEach((b,n)=>{if(n<padButtons.length&&(b.pressed||b.value>.5))mask|=1<<padButtons[n];});
    if(!analog){
      if(pad.axes?.[0]<-.35)mask|=1<<6;if(pad.axes?.[0]>.35)mask|=1<<7;
      if(pad.axes?.[1]<-.35)mask|=1<<4;if(pad.axes?.[1]>.35)mask|=1<<5;
    }
  }
  return mask;
}
// [lx, ly, rx, ry] in libretro's -32767..32767 range; keys, touch sticks and the gamepad add up.
export function inputAxes(keys,sticks,pad){
  const axes=[sticks[0][0],sticks[0][1],sticks[1][0],sticks[1][1]];
  for(const key of keys)if(key in stickKeys)axes[stickKeys[key][0]]+=stickKeys[key][1];
  pad?.axes?.slice(0,4).forEach((v,n)=>{if(Math.abs(v)>DEAD_ZONE)axes[n]+=v;});
  return axes.map(v=>Math.round(Math.max(-1,Math.min(1,v))*32767)||0);
}
