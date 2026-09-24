import test from 'node:test';
import assert from 'node:assert/strict';
import {segments} from '../src/evidence.mjs';
test('preserves Unicode source and only highlights exact spans',()=>{
  const text='😀 Review Atlas'; const parts=segments(text,[{start:10,end:15,value:'Atlas',kind:'system'}]);
  assert.equal(parts.map(p=>p.text).join(''),text); assert.equal(parts[1].kind,'system');
});
test('rejects mismatched, overlapping and invalid ranges without changing source',()=>{
  const spans=[{start:0,end:3,value:'abc',kind:'goal'},{start:1,end:3,value:'bc',kind:'entity'}, {start:3,end:99,value:'x',kind:'goal'}];
  const parts=segments('abcdef',spans); assert.equal(parts.filter(p=>p.kind).length,1);assert.equal(parts.map(p=>p.text).join(''),'abcdef');
});
