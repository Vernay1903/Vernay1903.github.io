#!/usr/bin/env python3
"""O apelido 'Flu' só vale em reportagem atual cujo título identifique Fluminense."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.extrair_fatos_estruturados import extract_individual_team_context
CONFIG=json.loads((ROOT/"config"/"pre-jogo.json").read_text(encoding="utf-8"))
CTX={"home":"Fluminense","away":"Palmeiras","competition_slug":"libertadores",
     "kickoff_brasilia":"2026-10-14T21:30:00-03:00"}

def item(title, sentence, url):
    return {"url":url, "title":title, "source_type":"major_sports_media",
            "published_hint":"Sun, 11 Oct 2026 15:00:00 GMT",
            "content_checked":True,"eligible_for_factual_validation":True,
            "editorial_target_side":"home","editorial_target_team":"Fluminense",
            "page_evidence":{"metadata":{"description":title},
                             "evidence_segments":[sentence],
                             "content_sha256":"a"*64}}

def extract(source):
    return extract_individual_team_context(
        [{"id":"editorial_context_both_teams","source_candidates":[source]}],
        match_context=CTX,config=CONFIG)

def check():
    match=item(
        "Fluminense terá time misto antes da Libertadores",
        "Já o Flu, com foco na semifinal da Copa Libertadores, terá um time misto para poupar titulares importantes.",
        "https://ge.globo.com/futebol/fluminense/noticia/2026/10/11/fluminense.html",
    )
    accepted=extract(match)
    assert accepted is not None and accepted["status"]=="verified",accepted
    assert any(f["field"]=="home_stakes_individual_1" for f in accepted["facts"])
    unrelated=item(
        "Flamengo discute seu elenco para o próximo clássico",
        "Já o Flu, com foco na semifinal da Copa Libertadores, terá um time misto para poupar titulares importantes.",
        "https://ge.globo.com/futebol/flamengo/noticia/2026/10/11/flamengo.html",
    )
    assert extract(unrelated) is None, "Apelido sozinho sem clube no título deve ser rejeitado"
    english=item(
        "Fluminense se prepara para a Libertadores",
        "An analyst studied seasonal flu cases while Palmeiras and Fluminense prepared for their next matches.",
        "https://ge.globo.com/futebol/fluminense/noticia/2026/10/11/saude.html",
    )
    assert extract(english) is None, "Palavra inglesa flu não é apelido"
    print("OK: Flu vinculado ao clube por manchete; fontes ambíguas rejeitadas.")

if __name__=="__main__":
    check()
