"""Espera persistente desde a primeira observação do encerramento, em Brasília."""
import json
from datetime import datetime,timedelta
from pathlib import Path
from preparar_fatos_pos_jogo import when,pair,match_outcome
from selecionar_pos_jogos import TZ,FINAL,integer
ROOT=Path(__file__).resolve().parents[1]


def dates_to_check(now):
    local=when(now.isoformat()).date()
    return [local-timedelta(days=1),local]


def load_state(path):
    path=Path(path)
    if not path.exists():return {'version':1,'fixtures':{}}
    data=json.loads(path.read_text())
    if data.get('version')!=1 or not isinstance(data.get('fixtures'),dict):raise ValueError('Estado de espera inválido')
    return data


def save_state(path,state):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


def observe(candidate,summary,state,now):
    now=when(now.isoformat())
    config=json.loads((ROOT/'config/tempo-pos-jogo.json').read_text())
    minutes=config['wait_minutes']
    if type(minutes) is not int or minutes<=0:raise ValueError('Intervalo inválido')
    h=summary['header'];comps=h['competitions']
    if 'espn-'+str(h['id'])!=candidate['fixture_id'] or len(comps)!=1:
        raise ValueError('Encerramento pertence a outro jogo')
    c=comps[0];fid=candidate['fixture_id'];status=c['status']['type']
    if status.get('completed') is not True or status.get('name') not in FINAL:
        state['fixtures'].pop(fid,None)
        return {'status':'waiting_for_final','eligible':False}
    kickoff=when(c['date'])
    if kickoff!=when(candidate['kickoff']) or kickoff>=now:raise ValueError('Horário da partida divergente')
    teams=pair(c);score={side:integer(t['score']) for side,t in teams.items()}
    if score!=candidate['score']:raise ValueError('Placar mudou entre coleta e confirmação')
    signature={'kickoff':kickoff.isoformat(),'competition':h['league']['slug'],
        'teams':{s:str(t['team']['id']) for s,t in teams.items()},'score':score,'status':status['name']}
    if status['name'] in {'STATUS_FINAL_PEN','STATUS_FINAL_AET'}:
        signature['outcome']=match_outcome(c)
    previous=state['fixtures'].get(fid)
    if previous is None or previous.get('signature')!=signature:
        previous={'signature':signature,'match_date':kickoff.date().isoformat(),'first_final_seen_at':now.isoformat()}
        state['fixtures'][fid]=previous
    first=when(previous['first_final_seen_at'])
    if first>now or first<kickoff:raise ValueError('Estado de espera com data inconsistente')
    eligible_at=first+timedelta(minutes=minutes)
    return {'eligible':now>=eligible_at,'status':'eligible' if now>=eligible_at else 'waiting_after_final',
        'first_final_seen_at':first.isoformat(),'eligible_at':eligible_at.isoformat(),
        'basis':'first_observed_final','wait_minutes':minutes}
