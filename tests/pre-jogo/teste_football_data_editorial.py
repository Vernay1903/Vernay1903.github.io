#!/usr/bin/env python3
"""Regressão usando o enriquecedor atual; exclui jogos futuros e outra competição."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import enriquecer_fatos_football_data as fd


def main():
    now = datetime.now(timezone.utc)
    def game(h, a, hg, ag, code='PL', days=1, status='FINISHED'):
        return {'utcDate': (now - timedelta(days=days)).isoformat(), 'status': status,
                'homeTeam': {'id': h}, 'awayTeam': {'id': a},
                'score': {'fullTime': {'home': hg, 'away': ag}}, 'competition': {'code': code}}
    rows = [game(1,9,2,0), game(8,1,1,1,days=2), game(1,7,0,1,days=3),
            game(6,1,0,3,days=4), game(1,5,4,2,days=5)]
    result = fd.latest_form({'matches': rows}, 1, now)
    assert all(x in result for x in ['3 vitórias', '1 empate', '1 derrota']), result
    h2h = [game(1,2,2,0), game(2,1,1,1), game(1,2,0,3), game(1,2,1,1),
           game(1,2,5,0,'CL'), game(1,2,9,0,days=-1), game(1,2,9,0,status='SCHEDULED')]
    assert fd.head_to_head({'matches': h2h}, 1, 2, 'PL', now) == (4,1,1,2)
    assert fd.head_to_head({'matches': [game(1,2,2,0,'CL')]},1,2,'PL',now) is None
    print('OK: forma e confronto direto usam somente resultados passados e competição correta.')


if __name__ == '__main__': main()
