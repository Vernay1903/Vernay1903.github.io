#!/usr/bin/env python3
"""Não aceitar os onze titulares projetados na ida como escalação da volta."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import extrair_fatos_estruturados as facts


def candidate(title):
    content = (
        "Palmeiras e Fluminense se enfrentam pela Libertadores. "
        "Provável Palmeiras: Carlos Miguel; Murilo; Gustavo Gómez; Barboza; "
        "Giay; Marlon Freitas; Andreas Pereira; Piquerez; Arias; Flaco López; Sosa."
    )
    return {
        "title": title,
        "url": "https://ge.globo.com/futebol/libertadores/noticia/2026/10/14/duelo.html",
        "publisher": "ge.globo.com",
        "source_type": "major_sports_media",
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "checked_at": "2026-10-20T11:00:00-03:00",
        "page_evidence": {
            "metadata": {"title": title},
            "evidence_segments": [content],
        }
    }


def main():
    config = facts.load_config()
    context = {
        "home": "Palmeiras", "away": "Fluminense",
        "competition": "Libertadores",
        "competition_slug": "libertadores",
        "kickoff_brasilia": "2026-10-21T21:30:00-03:00",
    }
    item = {
        "id": "probable_lineups_and_coaches",
        "source_candidates": [candidate("Fluminense x Palmeiras: escalações da ida")],
    }
    forbidden = facts.extract_team_labeled_claims(
        item, match_context=context, config=config,
        labels=(r"prov[aá]vel",), field_suffix="lineup", max_chars=350,
    )
    assert forbidden == [], forbidden

    item["source_candidates"] = [candidate("Palmeiras x Fluminense: escalações da volta")]
    allowed = facts.extract_team_labeled_claims(
        item, match_context=context, config=config,
        labels=(r"prov[aá]vel",), field_suffix="lineup", max_chars=350,
    )
    assert allowed, "Não descartar fonte de confronto com mando correto."
    print("OK: prováveis da ida bloqueadas na volta; título orientado mantido.")


if __name__ == "__main__":
    main()
