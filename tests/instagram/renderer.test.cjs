const test=require('node:test');
const assert=require('node:assert/strict');
const {validate,parts,html}=require('../../scripts/instagram/render.cjs');
test('reject stale-format, invalid times, duplicates and unsorted rows',()=>{
 for(const rows of [[],[{time:'25:00',desc:'x'}],[{time:'12:00',desc:'x'},{time:'11:00',desc:'y'}],[{time:'12:00',desc:'x'},{time:'12:00',desc:'x'}]])assert.throws(()=>validate(rows));
});
test('preserve names and escape markup without interpreting agenda HTML',()=>{
 const row={time:'14:00',desc:'A & B <teste> - Copa - Final'};
 assert.deepEqual(parts(row),['A & B <teste> - Copa','Final']);
 const result=html([row],'2026-11-13',1,1,'');
 assert.ok(result.includes('A &amp; B &lt;teste&gt; - Copa'));
 assert.ok(!result.includes('<teste>'));
});
