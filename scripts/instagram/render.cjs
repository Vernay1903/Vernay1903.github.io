// Deterministic Story renderer: exact agenda text, no generative AI or paid APIs.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function validate(rows) {
  if (!Array.isArray(rows) || !rows.length) throw Error('Agenda vazia ou inválida.');
  const seen = new Set(); let previous = '';
  for (const row of rows) {
    if (!row || Object.keys(row).sort().join(',') !== 'desc,time' ||
        typeof row.time !== 'string' || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(row.time) ||
        typeof row.desc !== 'string' || !row.desc.trim() || row.desc.length > 500 || row.time < previous)
      throw Error('Item inválido ou agenda fora de ordem.');
    const key = JSON.stringify(row);
    if (seen.has(key)) throw Error('Evento duplicado.');
    seen.add(key); previous = row.time;
  }
}
function parts(row) {
  const at = row.desc.lastIndexOf(' - ');
  return at < 0 ? [row.desc, ''] : [row.desc.slice(0, at), row.desc.slice(at + 3)];
}
function html(rows, date, page, pages, logo) {
  const label = new Intl.DateTimeFormat('pt-BR', {day:'2-digit',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(date+'T12:00:00Z'));
  return `<!doctype html><html lang="pt-BR"><meta charset="utf-8"><style>
  *{box-sizing:border-box}body{margin:0;width:1080px;height:1920px;background:#f4f7fc;color:#102540;font-family:Arial,Helvetica,sans-serif}
  header{height:288px;padding:120px 72px 32px;background:#fff}header img{display:block;width:936px;height:136px;object-fit:contain}
  h1{font-size:88px;line-height:1.05;margin:40px 64px 20px;letter-spacing:-3px;font-weight:900}
  .date{margin:0 64px;color:#2459a6;font-size:34px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
  .count{text-align:right;font-size:28px;font-weight:700;color:#5a6d86;margin:24px 64px 20px}
  main{height:1032px;margin:0 56px;display:flex;flex-direction:column;gap:20px}
  .row{flex:1;min-height:0;display:grid;grid-template-columns:174px 1fr;gap:28px;align-items:center;padding:22px 30px;background:#fff;border:1px solid #dfe7f2;border-left:8px solid #145be3;border-radius:20px}
  .time{font-size:48px;line-height:1;font-weight:800;color:#145be3;font-variant-numeric:tabular-nums}
  .fixture{font-size:46px;line-height:1.18;font-weight:700;overflow-wrap:anywhere;letter-spacing:-.7px}
  .league{font-size:31px;line-height:1.25;margin-top:14px;color:#52637a}
  footer{position:absolute;top:1634px;left:64px;width:952px;height:156px;border-top:2px solid #d6e1ef;text-align:left;padding:28px 0;color:#102540}
  footer strong{font-size:40px;letter-spacing:-.5px}footer p{font-size:32px;margin:14px 0;color:#52637a}
  </style><header><img alt="Corte dos Esportes" src="data:image/webp;base64,${logo}"></header>
  <h1>AGENDA DO DIA</h1><div class="date">${esc(label)}</div><div class="count">${page} / ${pages}</div><main>
  ${rows.map(row => {const [fixture, league] = parts(row);return `<div class="row"><div class="time">${esc(row.time)}</div><div class="details"><div class="fixture">${esc(fixture)}</div><div class="league">${esc(league)}</div></div></div>`;}).join('')}
  </main><footer><strong>cortedosesportes.com.br</strong><p>Acesse o site pelo link na bio</p></footer></html>`;
}
async function render() {
  const date = process.env.AGENDA_DATE;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '') || new Date(date+'T12:00:00Z').toISOString().slice(0,10)!==date) throw Error('Defina AGENDA_DATE como YYYY-MM-DD.');
  const source = fs.readFileSync(path.join(root,'agenda.json'));
  const rows = JSON.parse(source); validate(rows);
  const out = path.resolve(process.env.STORY_OUTPUT || path.join(root,'out/instagram'));
  fs.mkdirSync(out,{recursive:true});
  // Remove only previous renderer outputs, so upload-artifact never includes stale pages.
  for(const file of fs.readdirSync(out)) if (/^story-\d+\.jpg$/.test(file) || file==='manifest.json') fs.unlinkSync(path.join(out,file));
  const logo = fs.readFileSync(path.join(root,'logo-mobile.webp')).toString('base64');
  const browser = await chromium.launch({headless:true, ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
    const groups=[]; let current=[];
    async function fits(group) {
      await page.setContent(html(group,date,1,1,logo));
      await page.locator('header img').evaluate(img => img.decode());
      return page.locator('.row').evaluateAll(items=>items.every(row=>{
        const details=row.querySelector('.details');
        return details.getBoundingClientRect().height <= row.getBoundingClientRect().height - 44;
      }));
    }
    for(const row of rows) {
      if(current.length && (current.length===4 || !await fits([...current,row]))) { groups.push(current);current=[]; }
      current.push(row);
      if(!await fits(current)) throw Error('Evento não cabe no Story; revisão necessária.');
    }
    if(current.length)groups.push(current);
    const files=[];
    for(let i=0;i<groups.length;i++){
      await page.setContent(html(groups[i],date,i+1,groups.length,logo));
      await page.locator('header img').evaluate(img=>img.decode());
      const file=`story-${String(i+1).padStart(2,'0')}.jpg`;
      await page.screenshot({path:path.join(out,file),type:'jpeg',quality:95});files.push(file);
    }
    fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({date,agenda_sha256:crypto.createHash('sha256').update(source).digest('hex'),events:rows.length,pages:groups.map((events,i)=>({file:files[i],events})),mode:'preview'},null,2)+'\n');
    console.log(`${rows.length} eventos em ${files.length} Stories. Prévia: nenhuma publicação.`);
  } finally {await browser.close();}
}
module.exports={validate,parts,html};
if(require.main===module)render().catch(e=>{console.error(e.message);process.exitCode=1;});
