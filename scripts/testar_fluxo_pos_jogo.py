"""Teste controlado: snapshots históricos + redação real pela API + pacote sem publicar."""
import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path
import executar_pos_jogo as pipeline
from selecionar_pos_jogos import TEAMS, PILOT


def main():
    root=pipeline.ROOT
    fixtures=root/'tests/pos-jogo/fixtures/real-leipzig-20261021'
    summary=pipeline.read(fixtures/'summary.json')
    candidate=pipeline.read(fixtures/'selection.json')['selected'][0]
    schedules={i:pipeline.read(fixtures/f'schedule-{i}.json') for i in ('86','11420')}
    # Envelope dos calendários reconstruído da ficha arquivada; nenhum HTTP de coleta.
    event={'id':candidate['fixture_id'].split('-')[1],
           'league':{'slug':candidate['competition_code'],'name':candidate['competition']},
           'competitions':copy.deepcopy(summary['header']['competitions'])}
    calendars={str(TEAMS[n][0]):{'team':{'id':str(TEAMS[n][0]),'displayName':TEAMS[n][1]},
                               'events':[event] if n=='Real Madrid' else []} for n in PILOT}
    def query(url):
        if '/summary?' in url:return summary
        team=url.split('/teams/')[1].split('/')[0]
        return schedules[team] if 'fixture=true' in url else calendars[team]
    now=datetime.fromisoformat('2026-10-22T12:00:00-03:00')
    out=root/'build/pos-jogo/fluxo-passo11'
    state=out/'tempo.json'
    site=root/'current-main'
    news=pipeline.read(site/'noticias.json')
    # Primeira observação exige espera; nenhuma chamada API deve ocorrer.
    waiting=pipeline.run(date(2026,10,21),news,out/'primeira-observacao',execute=True,
                         query=query,now=now-timedelta(minutes=50),timing_state=state,site_root=site)
    if waiting['status']!='waiting' or waiting['api_articles_attempted']:
        raise ValueError('Primeira observação não respeitou a espera')
    result=pipeline.run(date(2026,10,21),news,out/'liberado',execute=True,
                        query=query,now=now,timing_state=state,site_root=site)
    rows=[r for r in result['results'] if r['status']=='package_ready']
    if len(rows)!=1 or result['status']!='completed':
        raise ValueError('Fluxo não gerou exatamente um pacote: '+json.dumps(result,ensure_ascii=False))
    pipeline.save(out/'resultado-teste.json',{'mode':'historical_snapshot_replay_with_live_writer',
        'collection_clock_simulated':True,'automatic_source_discovery_exercised':False,
        'source_packet':'previously_reviewed_archived_packet',
        'real_writer_api':True,'result':result,'publication_enabled':False})
    print(json.dumps(rows[0]['package'],ensure_ascii=False))

if __name__=='__main__':main()
