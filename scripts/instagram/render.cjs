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
  *{box-sizing:border-box}body{margin:0;width:1080px;height:1920px;background:#fff;color:#0b203b;font-family:Arial,Helvetica,sans-serif}
  header{height:330px;background:#0b203b;padding:150px 60px 40px}header img{display:block;width:960px;height:137px;object-fit:contain;background:white}
  h1{font-size:76px;margin:38px 0 22px;text-align:center;letter-spacing:-2px}
  .date{width:max-content;max-width:960px;margin:auto;border:2px solid #244eaa;border-radius:60px;padding:16px 40px;color:#244eaa;font-size:33px;font-weight:700;text-transform:uppercase;background:#f7f9ff}
  .count{text-align:right;font-size:23px;color:#244eaa;margin:22px 62px 14px}
  main{height:925px;margin:0 48px;border:2px solid #c6d4ee;border-radius:30px;padding:0 28px;display:flex;flex-direction:column}
  .row{flex:1;min-height:0;display:grid;grid-template-columns:158px 1fr;gap:20px;align-items:center;padding:22px 0;border-bottom:1px solid #dce4f1}
  .row:last-child{border:0}.time{font-size:45px;font-weight:700;color:#244eaa}.fixture{font-size:38px;line-height:1.16;font-weight:700;overflow-wrap:anywhere}.league{font-size:28px;line-height:1.2;margin-top:8px}
  footer{position:absolute;top:1590px;left:0;width:1080px;height:330px;background:#0b203b;text-align:center;padding:42px 40px;color:white}
  footer strong{font-size:39px}footer p{font-size:31px;margin:16px 0}
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
      if(current.length && (current.length===5 || !await fits([...current,row]))) { groups.push(current);current=[]; }
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
