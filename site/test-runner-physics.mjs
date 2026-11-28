import {test} from 'node:test';
import assert from 'node:assert/strict';
import {makeObstacle,makeCoinTrail,obstacleTouchesBody,advanceBody} from './runner-physics.js';

test('varied obstacles and independent coin patterns stay reachable',()=>{
 let seed=17;const random=()=>((seed=(seed*1664525+1013904223)>>>0)/4294967296);
 const kinds=new Set(),counts=new Set();let last='';
 for(let i=0;i<200;i++){
  const o=makeObstacle(430,last,random);assert.notEqual(o.kind,last);last=o.kind;kinds.add(last);
  assert.ok(o.h>=20&&o.h<=32&&o.w<=38);
  const coins=makeCoinTrail(432,106,random);counts.add(coins.length);
  for(const c of coins)assert.ok(c.y>=30&&c.y<=82);
 }
 assert.equal(kinds.size,5);assert.deepEqual([...counts].sort(),[0,1,2,3,4,5]);
});
test('shape collision ignores empty triangle corners and allows a complete jump',()=>{
 const spike={x:60,w:30,h:30,kind:'spike'};
 assert.equal(obstacleTouchesBody(spike,{y:52},40,30,106),false);
 assert.equal(obstacleTouchesBody(spike,{y:76},52,30,106),true);
 for(const kind of ['block','spike','orb','steps','crystal']){
  const body={y:76,velocity:-390,squash:0,squashVelocity:0};
  for(let i=0;i<20;i++)advanceBody(body,1/60,76);
  assert.equal(obstacleTouchesBody({x:52,w:38,h:32,kind},body,52,30,106),false);
  let impact=0;for(let i=0;i<45;i++)impact=Math.max(impact,advanceBody(body,1/60,76));
  assert.ok(impact>300);assert.equal(body.y,76);
 }
});
