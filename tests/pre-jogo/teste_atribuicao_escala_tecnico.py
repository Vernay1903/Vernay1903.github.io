#!/usr/bin/env python3
"""Nomes de ambos na manchete não permitem inverter escalações por seção."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import extrair_fatos_estruturados as facts


def main():
    config = facts.load_config()
    ctx = {"home": "Palmeiras", "away": "Fluminense",
           "competition": "Libertadores", "competition_slug": "libertadores",
           "kickoff_brasilia": "2026-10-21T21:30:00-03:00"}
    title = "Palmeiras x Fluminense: escalações da volta 21/10/2026"
    source = {
        "url": "https://trivela.com.br/onde-assistir/palmeiras-fluminense-2026.html",
        "title": title, "source_type": "major_sports_media",
        "publisher": "Trivela", "content_checked": True,
        "eligible_for_factual_validation": True,
        "checked_at": "2026-10-20T12:00:00-03:00",
        "page_evidence": {"metadata": {"title": title}, "evidence_segments": [
            f"{title}. Palmeiras | Provável escalação: Jogador A; Jogador B; Jogador C.",
            f"{title}. Palmeiras | Técnico: Treinador Azul.",
            f"{title}. Fluminense | Provável escalação: Atleta D; Atleta E; Atleta F.",
            f"{title}. Fluminense | Técnico: Treinador Verde.",
        ]}
    }
    req = {"id": "probable_lineups_and_coaches", "source_candidates": [source]}
    for suffix, labels in (("lineup", (r"prov[aá]vel escala[cç][aã]o",)),
                           ("coach", (r"t[eé]cnico",))):
        claims = facts.extract_team_labeled_claims(
            req, match_context=ctx, config=config, labels=labels,
            field_suffix=suffix, max_chars=300,
        )
        by_field = {claim["field"]: claim["value"] for claim in claims}
        assert len(by_field) == 2, by_field
        assert "Jogador A" in by_field["home_lineup"] if suffix == "lineup" else "Treinador Azul" in by_field["home_coach"]
        assert "Atleta D" in by_field["away_lineup"] if suffix == "lineup" else "Treinador Verde" in by_field["away_coach"]
    print("OK: escalação e técnico de cada clube não são trocados.")


if __name__ == "__main__":
    main()
