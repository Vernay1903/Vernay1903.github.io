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
    assert result["facts"][0]["text"] == "Transmissão: TV Globo, ge tv e Paramount+.", result

    # Outra partida com os mesmos clubes, mas mandos invertidos,
    # nunca fornece canal para o jogo-alvo.
    first_leg = source("Fluminense x Palmeiras: semifinal no Maracanã")
    blocked = facts.extract_transmission_requirement(
        requirement(first_leg), match_context=context, config=config,
    )
    assert blocked["status"] != "verified", blocked

    # JustWatch Brasil publica "streaming ao vivo na HBO Max" em prosa.
    stream = facts.broadcast_names_from_prose(
        "Você pode assistir a FC Inter de Milão vs. FC Shakhtar Donetsk "
        "em streaming ao vivo na HBO Max."
    )
    assert stream == "HBO Max", stream
    assert facts.broadcast_names_from_prose(
        "HBO Max é um serviço de streaming com filmes e séries."
    ) is None
    # JustWatch Brasil tem temporada 26-27 e dia do jogo, mas não ano
    # explícito no artigo. O calendário da fonte deve coincidir com a pauta.
    guide_title = "FC Inter de Milão vs. FC Shakhtar Donetsk: Streaming ao vivo e TV hoje"
    guide = source(guide_title)
    guide["url"] = (
        "https://sports.justwatch.com/br/futebol/liga-dos-campeoes-da-uefa/"
        "fc-inter-de-milao-fc-shakhtar-donetsk-26-27"
    )
    guide["page_evidence"]["metadata"]["title"] = guide_title
    guide["page_evidence"]["metadata"]["description"] = (
        "Onde assistir a FC Inter de Milão x FC Shakhtar Donetsk "
        "em streaming ou na TV: No Prime Video? Descubra agora no JustWatch!"
    )
    guide["page_evidence"]["evidence_segments"] = [
        guide_title,
        "FC Inter de Milão vs. FC Shakhtar Donetsk é um evento de Futebol "
        "que vai ocorrer em 21 de out. às 04:00 PM. Você pode assistir "
        "em streaming ao vivo na HBO Max.",
    ]
    current_context = {
        "home": "Inter de Milão", "away": "FK Shakhtar Donetsk",
        "competition": "Champions League",
        "kickoff_brasilia": "2026-10-21T16:00:00-03:00",
    }
    live = facts.extract_transmission_requirement(
        requirement(guide), match_context=current_context, config=config,
    )
    assert live["status"] == "verified", live
    assert live["facts"][0]["text"] == "Transmissão: HBO Max."
    wrong_date = dict(current_context, kickoff_brasilia="2026-11-21T16:00:00-03:00")
    obsolete = facts.extract_transmission_requirement(
        requirement(guide), match_context=wrong_date, config=config,
    )
    assert obsolete["status"] != "verified", obsolete

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
