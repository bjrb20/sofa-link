import assert from 'node:assert/strict';
import {inputMask,inputAxes,isControlKey} from '../web/controls.mjs';
const keys=new Set(['ArrowUp','KeyW','Space']);
assert.equal(inputMask(keys,[],null),(1<<4)|1);
keys.delete('KeyW');assert.equal(inputMask(keys,[],null),(1<<4)|1);
assert.equal(inputMask([], [0,6],null),65);
const pad={buttons:[{pressed:true},{pressed:true}],axes:[-.6,.7]};
assert.equal(inputMask([],[],pad),1|(1<<8)|(1<<6)|(1<<5));
assert.equal(inputMask([],[],null),0);
// The browser's standard layout is the same for an Xbox pad and a DualSense: A/Cross, B/Circle, X/Square, Y/Triangle, ...
const press=n=>({buttons:Array.from({length:17},(_,i)=>({pressed:i===n,value:+(i===n)})),axes:[0,0,0,0]});
assert.deepEqual([...Array(17).keys()].map(n=>inputMask([],[],press(n),true)),
  [1,1<<8,1<<1,1<<9,1<<10,1<<11,1<<12,1<<13,1<<2,1<<3,1<<14,1<<15,1<<4,1<<5,1<<6,1<<7,0],'the Xbox and PS buttons do nothing');
assert.equal(inputMask([],[],{buttons:[,,,,,,{pressed:false,value:.6}],axes:[]}),1<<12,'a half-pulled trigger is L2');
// Consoles with sticks: WASD and the gamepad stick leave the D-pad.
assert.equal(inputMask(new Set(['KeyW','ArrowUp','KeyT']),[],null,true),1<<4,'on PS2 only TFGH is the D-pad');
assert.equal(inputMask([],[],{buttons:[],axes:[-.6,.7]},true),0);
const centre=[[0,0],[0,0]];
assert.deepEqual(inputAxes(new Set(['KeyA','ArrowDown']),centre,null),[-32767,0,0,32767]);
assert.deepEqual(inputAxes(new Set(['KeyA','KeyD']),centre,null),[0,0,0,0]);
assert.deepEqual(inputAxes([],centre,{axes:[1,-1,.1,0]}),[32767,-32767,0,0],'a small offset is inside the dead zone');
assert.deepEqual(inputAxes([],[[1,0],[0,-1]],null),[32767,0,0,-32767]);
assert.deepEqual(inputAxes(new Set(['KeyD']),[[1,0],[0,0]],{axes:[1,0,0,0]}),[32767,0,0,0],'sources add, then clamp');
assert.ok(isControlKey('KeyI',false)&&isControlKey('ArrowUp',true)&&!isControlKey('KeyB',true));
// Left hand moves; right hand has the face buttons in a diamond, the shoulders above them, and Start.
const one=code=>inputMask(new Set([code]),[],null);
assert.deepEqual(['KeyK','Space','KeyJ','KeyL','KeyI'].map(one),[1,1,1<<1,1<<8,1<<9],'Cross, Square, Circle, Triangle');
assert.deepEqual(['KeyU','KeyO','KeyY','KeyP'].map(one),[1<<10,1<<11,1<<12,1<<13],'L1, R1, L2, R2');
assert.deepEqual(['Enter','ShiftRight','ShiftLeft','KeyC','KeyM'].map(one),[1<<3,1<<2,1<<2,1<<14,1<<15],'Start, Select, L3, R3');
assert.deepEqual(['KeyX','KeyZ','KeyV','KeyQ','KeyE','Digit1','Digit3'].map(one),[0,0,0,0,0,0,0],'the old left-hand keys are free');
assert.equal(inputMask(new Set(['KeyI','ArrowUp']),[],null,true),1<<9,'on PS2 the arrows are the right stick, I is still Triangle');
console.log('Keyboard aliases, simultaneous touch buttons, standard gamepad mapping and sticks pass.');
