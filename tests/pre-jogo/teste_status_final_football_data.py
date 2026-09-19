#!/usr/bin/env python3
"""Status final da Football-Data: só libera o jogo correto e ainda não iniciado."""
import json
import os
import sys
import tempfile
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import validar_status_final_pre_jogo as status
from scripts import preparar_lote_pre_jogo_automatico as prepare

def main():
    local=(datetime.now(ZoneInfo("America/Sao_Paulo"))+timedelta(days=2)).replace(hour=19,minute=30,second=0,microsecond=0)
    utc=local.astimezone(timezone.utc).isoformat()
    data={
      "id":9876543,"utcDate":utc,"status":"TIMED",
      "homeTeam":{"id":65,"name":"Manchester City"},"awayTeam":{"id":71,"name":"Sunderland"},
      "competition":{"code":"PL"}
    }
    fixture={
      "id":9876543,"provider":"football-data.org","home":"Manchester City","away":"Sunderland",
      "provider_data":{"home_team_id":65,"away_team_id":71,"utc_date":utc,"competition_code":"PL"}
    }
    package={"fixture_id":9876543,"date":local.strftime("%d/%m/%Y"),
             "match_context":{"home":"Manchester City","away":"Sunderland",
                              "competition":"Premier League","kickoff_time_brasilia":"19:30"}}
    with tempfile.TemporaryDirectory() as temp:
        bd=Path(temp)
        (bd/"fixtures-normalizados.json").write_text(json.dumps({
           "provider":"football-data.org","target_date":local.date().isoformat(),"fixtures":[fixture]
        }))
        with patch.object(prepare,"DEFAULT_BUILD",bd):
            row=prepare.football_data_status_row({},package)
            assert row and row["source_type"]=="official_fixture_data" and row["match_id"]==9876543,row
            snapshot=prepare.status_snapshot({"requirements":[]},package,{"research":{"discovery":{"official_domains":{}}}})
            assert snapshot is not None and snapshot["evidence"]==[row]
        with patch.dict(os.environ,{"FOOTBALL_DATA_TOKEN":"token-teste"}), \
             patch.object(status.fixtures_api,"request_json",return_value=(data,{})) as call:
            good=status.validate_status(snapshot,execute=True)
            assert good["publication_status_gate_passed"] is True
            assert call.call_count==1
            for field,invalid in (
                ("status","POSTPONED"),
                ("utcDate",(local+timedelta(hours=1)).astimezone(timezone.utc).isoformat()),
                ("id",44),
            ):
                bad=deepcopy(data);bad[field]=invalid
                with patch.object(status.fixtures_api,"request_json",return_value=(bad,{})):
                    try: status.validate_status(snapshot,execute=True)
                    except SystemExit: pass
                    else: raise AssertionError(f"Falha do status {field} deveria bloquear.")
        with patch.dict(os.environ,{"FOOTBALL_DATA_TOKEN":""}):
            try:status.validate_status(snapshot,execute=True)
            except SystemExit:pass
            else:raise AssertionError("Sem token deve bloquear.")
    print("OK: check oficial bloqueia jogos adiados/reagendados, IDs trocados e token ausente.")

if __name__=="__main__":
    main()
