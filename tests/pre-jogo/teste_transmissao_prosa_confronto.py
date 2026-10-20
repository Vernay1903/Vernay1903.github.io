#!/usr/bin/env python3
"""Transmissão em prosa: regredir caso real Palmeiras x Fluminense 21/10/2026."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import extrair_fatos_estruturados as facts


def source(title):
    return {
        "publisher": "Veículo esportivo de teste",
        "url": "https://example.org/reportagem",
        "source_type": "major_sports_media",
        "title": title,
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "checked_at": "2026-10-20T10:00:00-03:00",
        "page_evidence": {
            "metadata": {"title": title},
            "evidence_segments": [
                title,
                "Transmissão: ge TV e Paramount+.",
                "A partida tem transmissão ao vivo e com imagem na TV Globo, "
                "ge TV e Paramount+.",
            ],
        },
    }


def requirement(src):
    return {
        "id": "transmission", "status": "pending",
        "required_for_drafting": True,
        "allow_unavailable_after_check": True,
        "source_candidates": [src],
    }


def main():
    config = facts.load_config()
    context = {"home": "Palmeiras", "away": "Fluminense",
               "competition": "Libertadores"}
    good = source("Palmeiras x Fluminense Palpite - Onde assistir e escalações (21/10)")
    result = facts.extract_transmission_requirement(
        requirement(good), match_context=context, config=config,
    )
    assert result["status"] == "verified", result
    assert "TV Globo" in result["facts"][0]["text"], result
    assert "ge tv" in result["facts"][0]["text"], result
    assert "Paramount+" in result["facts"][0]["text"], result

    # Outra partida com os mesmos clubes, mas mandos invertidos,
    # nunca fornece canal para o jogo-alvo.
    first_leg = source("Fluminense x Palmeiras: semifinal no Maracanã")
    blocked = facts.extract_transmission_requirement(
        requirement(first_leg), match_context=context, config=config,
    )
    assert blocked["status"] != "verified", blocked

    # Nenhuma emissora é deduzida de um texto que apenas promete informar.
    assert facts.broadcast_names_from_prose(
        "A transmissão será informada em breve."
    ) is None
    # A mesma fonte pode ter chamada parcial e lista completa.
    # Emissoras completamente diferentes continuam sendo conflito.
    competing = [
        {"field": "transmission", "value": "TV Globo",
         "source": {"url": "https://example.org/uma"}},
        {"field": "transmission", "value": "ESPN",
         "source": {"url": "https://example.org/uma"}},
    ]
    assert len(facts.eliminate_incomplete_broadcast_claims(competing)) == 2
    print("OK: transmissão em prosa verificada, ida/volta segregadas.")


if __name__ == "__main__":
    main()
