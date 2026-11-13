const test=require('node:test');
const assert=require('node:assert/strict');
const {upcoming}=require('../../scripts/instagram/render.cjs');
test('filtra horário de São Paulo, exclui evento já iniciado e mantém ordem',()=>{
 const rows=[{time:'18:30',desc:'A'},{time:'20:20',desc:'B'},{time:'21:00',desc:'C'},{time:'22:00',desc:'D'}];
 assert.deepEqual(upcoming(rows,'2026-11-13',new Date('2026-11-13T23:20:00Z')), {rows:rows.slice(2),cutoff:'20:20'});
 assert.equal(rows.length,4);
});
test('recusa agenda de outro dia e seleção vazia',()=>{
 assert.throws(()=>upcoming([{time:'23:30',desc:'A'}],'2026-11-12',new Date('2026-11-13T23:20:00Z')));
 assert.throws(()=>upcoming([{time:'20:20',desc:'A'}],'2026-11-13',new Date('2026-11-13T23:20:00Z')));
});
