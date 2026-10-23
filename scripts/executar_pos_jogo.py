"""Coleta dos quatro clubes, preparação factual e redação revisada; sem publicação."""
import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from selecionar_pos_jogos import select, TZ
from preparar_fatos_pos_jogo import build, when, pair
from coletar_competicoes_pre_jogo import BASE, fetch
from editorial_pos_jogo import prepare
from redigir_pos_jogo_openai import generate


def read(path): return json.loads(Path(path).read_text())
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def reviewed_packet(candidate, summary, schedules, entry, now):
    review=read(ROOT/entry['review']); narrative=read(ROOT/entry['narrative']); reference=read(ROOT/entry['reference_facts'])
    if reference['fixture_id']!=candidate['fixture_id'] or narrative['fixture_id']!=candidate['fixture_id']:
        raise ValueError('Apuração pertence a outro jogo')
    if reference['match']['match_date']!=candidate['match_date']:
        raise ValueError('Data diverge da apuração')
    # Não reaproveitar campanha e agendas perecíveis indefinidamente.
    stamp=when(reference['generated_at'])
    if stamp>now or now-stamp>timedelta(hours=24):raise ValueError('Apuração precisa ser renovada (24h)')
    facts=build(candidate,summary,schedules,review,now)
    if facts['upcoming']!=reference['upcoming']:
        raise ValueError('Calendário mudou desde a apuração narrativa; requer nova conferência')
    if not facts['ready_for_drafting']:raise ValueError('Fatos insuficientes para redação')
    return facts,narrative


def run(target, news, out, *, execute=False, max_articles=1, query=fetch, writer=generate, now=None, registry=None, auto_research=False, researcher=None):
    now=now or datetime.now(TZ)
    if max_articles!=1:raise ValueError('Teste integrado limitado a uma matéria por execução')
    out=Path(out).resolve()
    if not out.is_relative_to((ROOT/'build/pos-jogo').resolve()):raise ValueError('Saída fora do piloto')
    if not isinstance(news,list) or not all(isinstance(x,dict) for x in news):raise ValueError('Notícias inválidas')
    registry=read(ROOT/'config/apuracoes-pos-jogo.json') if registry is None else registry
    if auto_research and researcher is None:
        from apurar_pos_jogo import apurar
        researcher=apurar
    seen={}
    def capture(url):
        if url not in seen:
            seen[url]=query(url)
            save(out/'coleta'/f'{hashlib.sha256(url.encode()).hexdigest()[:20]}.json',{'url':url,'checked_at':now.isoformat(),'data':seen[url]})
        return seen[url]
    selection=select(target,news,capture,now)
    report={'step':7,'target_date':target.isoformat(),'mode':'generate' if execute else 'collect_only',
        'selection':selection,'results':[],'publication_enabled':False,'api_articles_attempted':0,'research_attempted':0}
    save(out/'selecao.json',selection)
    if not selection['collection_complete']:
        report['status']='collection_failed';save(out/'relatorio.json',report);return report
    for candidate in selection['selected']:
        fid=candidate['fixture_id']; row={'fixture_id':fid};report['results'].append(row)
        try:
            if not re.fullmatch(r'espn-\d+',fid):raise ValueError('ID inválido')
            summary=capture(candidate['source_url'])
            ids=[str(t['team']['id']) for t in pair(summary['header']['competitions'][0]).values()]
            if not all(t.isdigit() for t in ids):raise ValueError('ID de equipe inválido')
            schedules={t:capture(f'{BASE}/all/teams/{t}/schedule?fixture=true&season={target.year}') for t in ids}
            directory=out/fid
            if auto_research:
                if report['research_attempted']>=1:
                    row['status']='research_test_limit';continue
                report['research_attempted']+=1
                facts,narrative=researcher(candidate,summary,schedules,directory/'apuracao',now)
            elif fid in registry:
                facts,narrative=reviewed_packet(candidate,summary,schedules,registry[fid],now)
            else:
                row.update(status='needs_source_review',reason='Coleta recebida; faltam conferência externa e apuração narrativa deste jogo')
                continue
            save(directory/'fatos.json',facts);save(directory/'narrativa.json',narrative)
            links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
            package=prepare(facts,narrative,links)
            save(directory/'pacote.json',package)
            if not execute:row['status']='ready_for_drafting';continue
            if (directory/'redacao/tentativa.json').exists():row['status']='already_attempted';continue
            if report['api_articles_attempted']>=max_articles:row['status']='test_limit';continue
            report['api_articles_attempted']+=1
            meta=writer(package,directory/'redacao',execute=True)
            if not meta or meta.get('semantic_review_passed') is not True or meta.get('fixture_id')!=fid:
                raise ValueError('Redação não confirmou revisão do jogo selecionado')
            row['status']='draft_reviewed'
        except (ValueError,KeyError,TypeError,OSError) as exc:
            row.update(status='blocked',reason=str(exc))
        finally:
            save(out/'relatorio.json',report)
    if not selection['selected']:report['status']='no_eligible_matches'
    elif any(r['status'] in {'blocked','needs_source_review'} for r in report['results']):report['status']='pending'
    else:report['status']='completed'
    save(out/'relatorio.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--date',type=date.fromisoformat,required=True)
    p.add_argument('--noticias',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--auto-research',action='store_true',help='Apurar uma partida com páginas abertas; usa API mesmo sem --execute')
    a=p.parse_args()
    result=run(a.date,read(a.noticias),a.output_dir,execute=a.execute,auto_research=a.auto_research)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']=='collection_failed' or ((a.execute or a.auto_research) and result['status']=='pending'):raise SystemExit(1)
if __name__=='__main__':main()
