#!/usr/bin/env python3
"""Regressão: chamada dinâmica e ausência opcional não podem bloquear pré-jogo."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import montar_pacote_editorial as pack
from scripts import extrair_fatos_estruturados as facts


def main():
    config=json.loads((ROOT/"config/pre-jogo.json").read_text(encoding="utf-8"))
    article={
      "title":"Santos FC x Flamengo pelo Brasileirão: transmissão, horário e prováveis escalações",
      "excerpt":"Santos FC e Flamengo se enfrentam em 8 de outubro de 2026, às 19h30 (de Brasília), pelo Brasileirão; veja transmissão, prováveis escalações e informações do confronto.",
    }
    lineup_facts=[
      {"field":"home_lineup","text":"Santos FC: Ana; Beto; Caio; Davi; Enzo; Fabio; Guga; Hugo; Igor; Joao e Kaua."},
      {"field":"away_lineup","text":"Flamengo: Leo; Mateus; Natan; Otavio; Paulo; Raul; Saulo; Tiago; Ulisses; Vitor e Wesley."},
      {"field":"home_coach","text":"Técnico do Santos FC: Técnico A."},
      {"field":"away_coach","text":"Técnico do Flamengo: Técnico B."},
    ]
    reqs={
      "transmission":{"id":"transmission","status":"unavailable_after_check","facts":[]},
      "probable_lineups_and_coaches":{"id":"probable_lineups_and_coaches","status":"verified","facts":lineup_facts},
    }
    title, excerpt = pack.adjusted_service_headline(article, reqs, config=config)
    expected = "Santos FC x Flamengo: veja escalações, destaques e onde assistir"
    assert title == expected, title
    assert "transmissão" not in excerpt.casefold()
    # O formato NÃO deve ser silenciosamente substituído por "horário".
    assert "required_transmission_not_verified" in pack.approved_headline_errors(
        title, reqs, config=config,
    )
    reqs["probable_lineups_and_coaches"] = {
        "id": "probable_lineups_and_coaches",
        "status": "unavailable_after_check", "facts": [],
    }
    missing_title, _ = pack.adjusted_service_headline(article, reqs, config=config)
    assert missing_title == expected
    assert "required_probable_lineups_not_verified" in pack.approved_headline_errors(
        missing_title, reqs, config=config,
    )

    reqs["transmission"] = {"status": "verified", "facts": [
        {"field": "transmission", "text": "Transmissão: Canal confirmado."}
    ]}
    reqs["probable_lineups_and_coaches"] = {
        "status": "verified", "facts": lineup_facts,
    }
    complete, _ = pack.adjusted_service_headline(article, reqs, config=config)
    assert complete == expected
    assert not pack.approved_headline_errors(complete, reqs, config=config)
    assert "titulo_fora_do_modelo_fixo" in pack.approved_headline_errors(
        "Santos FC x Flamengo pelo Brasileirão: horário", reqs, config=config,
    )
    reqs["transmission"]["status"] = "unavailable_after_check"
    assert "required_transmission_not_verified" in pack.approved_headline_errors(
        complete, reqs, config=config,
    )
    reqs["transmission"]["status"] = "verified"
    reqs["probable_lineups_and_coaches"]["facts"] = []
    assert "required_probable_lineups_not_verified" in pack.approved_headline_errors(
        complete, reqs, config=config,
    )

    gap={
      "id":"transmission","status":"pending","facts":[],"sources":[],
      "candidate_status":"no_candidates","candidate_source_count":0,
      "allow_unavailable_after_check":True,"conflict_detected":False,
    }
    resolved=facts.resolve_allowed_gap(gap,competition_slug="brasileirao",config=config)
    assert resolved["status"]=="unavailable_after_check"
    assert resolved["validator_accepted"] is True
    print("OK: manchete fixa e promessas de escalação/transmissão condicionadas à verificação.")


if __name__=="__main__":
    main()
