"""Espera desde o encerramento registrado; detecção é alternativa explícita."""
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


def recorded_finish(summary,status,kickoff,now):
    """Aceita somente evento explícito de fim com relógio absoluto, nunca duração estimada."""
    events=list(summary.get('keyEvents',[]))
    events += [r.get('play',{}) for r in summary.get('commentary',[]) if isinstance(r,dict)]
    candidates=[];all_times=[]
    for e in events:
        if not isinstance(e,dict) or not e.get('wallclock'):continue
        try:t=when(e['wallclock'])
        except (ValueError,TypeError):continue
        if not kickoff<t<=now:continue
        all_times.append(t)
        kind=e.get('type',{}).get('type')
        text=e.get('text','').strip().lower()
        terminal=text.startswith('match ends,')
        if status in {'STATUS_FULL_TIME','STATUS_FINAL'}:
            terminal=terminal or (kind=='end-regular-time' and e.get('period',{}).get('number')==2)
        # Fim dos 90 minutos NÃO encerra prorrogação ou disputa de pênaltis.
        if terminal:candidates.append(t)
    if not candidates:return None
    end=max(candidates)
    if any(t>end for t in all_times):return None
    return end


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
    changed=previous is not None and previous.get('signature')!=signature
    if previous is None or changed:
        previous={'signature':signature,'match_date':kickoff.date().isoformat(),'first_final_seen_at':now.isoformat()}
        state['fixtures'][fid]=previous
    first=when(previous['first_final_seen_at'])
    if first>now or first<kickoff:raise ValueError('Estado de espera com data inconsistente')
    end=recorded_finish(summary,status['name'],kickoff,now)
    if changed:previous['result_changed_at']=now.isoformat()
    baseline=end or first
    basis='source_recorded_final' if end else 'first_observed_final_fallback'
    # Uma correção de resultado mantém sua própria espera; não retroceder o relógio.
    if previous.get('result_changed_at'):
        baseline=max(baseline,when(previous['result_changed_at']))
        basis='result_change_confirmation'
    eligible_at=baseline+timedelta(minutes=minutes)
    previous.update(finished_at=end.isoformat() if end else None,timing_basis=basis,eligible_at=eligible_at.isoformat())
    return {'eligible':now>=eligible_at,'status':'eligible' if now>=eligible_at else 'waiting_after_final',
        'first_final_seen_at':first.isoformat(),'finished_at':end.isoformat() if end else None,
        'eligible_at':eligible_at.isoformat(),'basis':basis,'wait_minutes':minutes}
