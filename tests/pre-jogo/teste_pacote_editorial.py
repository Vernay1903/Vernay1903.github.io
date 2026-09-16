#!/usr/bin/env python3
"""Teste determinístico do pacote editorial limpo do Passo 24."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import montar_pacote_editorial as package  # noqa: E402
from scripts import preparar_pesquisa_factual as research  # noqa: E402

OUTPUT = ROOT / "build" / "pre-jogo" / "teste-pacote-editorial.json"


def source(url: str, publisher: str = "Fonte oficial") -> dict:
    return {
        "publisher": publisher,
        "url": url,
        "source_type": "official",
        "checked_at": "2026-09-16T13:00:00-03:00",
    }


def verified_requirement(req_id: str, facts: list[dict[str, str]], config: dict) -> dict:
    item = research.build_requirement(req_id, config=config)
    item.update(
        {
            "status": "verified",
            "facts": facts,
            "sources": [source(f"https://example.com/{req_id}")],
            "source_candidates": [
                {
                    **source(f"https://example.com/candidate-{req_id}"),
                    "content_checked": True,
                    "verification_status": "page_checked_pending_fact_extraction",
                    "eligible_for_factual_validation": True,
                }
            ],
            "validator_accepted": True,
            "fact_extraction_status": "validated_structured_fact",
            "conflict_detected": False,
            "conflicts": [],
        }
    )
    return item


def complete_article(config: dict) -> dict:
    requirements = [
        verified_requirement(
            "stadium_and_location",
            [{"field": "stadium", "text": "A partida será disputada no Emirates Stadium."}],
            config,
        ),
        verified_requirement(
            "transmission",
            [{"field": "transmission", "text": "A transmissão será de ESPN e Disney+."}],
            config,
        ),
        verified_requirement(
            "probable_lineups_and_coaches",
            [
                {"field": "home_lineup", "text": "Arsenal: Raya; Timber; Saliba; Gabriel; Calafiori; Rice; Odegaard; Saka; Eze; Martinelli; Gyokeres."},
                {"field": "home_coach", "text": "Técnico do Arsenal: Mikel Arteta."},
                {"field": "away_lineup", "text": "Manchester City: Donnarumma; Lewis; Dias; Gvardiol; Ait-Nouri; Rodri; Reijnders; Foden; Cherki; Doku; Haaland."},
                {"field": "away_coach", "text": "Técnico do Manchester City: Pep Guardiola."},
            ],
            config,
        ),
        verified_requirement(
            "officiating",
            [{"field": "referee", "text": "Michael Oliver será o árbitro da partida."}],
            config,
        ),
        verified_requirement(
            "recent_form_both_teams",
            [
                {"field": "home_recent_form", "text": "O Arsenal soma três vitórias nos últimos cinco jogos."},
                {"field": "away_recent_form", "text": "O Manchester City venceu quatro dos últimos cinco jogos."},
            ],
            config,
        ),
        verified_requirement(
            "competition_specific_head_to_head",
            [
                {"field": "games", "text": "Foram 20 confrontos pela Premier League no recorte considerado."},
                {"field": "home_wins", "text": "O Arsenal venceu sete."},
                {"field": "away_wins", "text": "O Manchester City venceu dez."},
                {"field": "draws", "text": "Houve três empates."},
            ],
            config,
        ),
        research.build_requirement("competition_internal_link", config=config),
        verified_requirement(
            "stakes_and_qualification_scenarios_when_applicable",
            [{"field": "stakes", "text": "Os três pontos têm impacto direto na disputa pelas primeiras posições."}],
            config,
        ),
        research.build_requirement("upcoming_fixtures_when_useful", config=config),
    ]
    return {
        "title": "Arsenal x Manchester City pela Premier League: transmissão, horário e prováveis escalações",
        "excerpt": "Arsenal e Manchester City se enfrentam pela Premier League.",
        "date": "17/09/2026",
        "slug": "arsenal-manchester-city-premier-league-2026-transmissao-horario-escalacoes.html",
        "fixture_id": "teste-24",
        "match_context": {
            "home": "Arsenal",
            "away": "Manchester City",
            "competition": "Premier League",
            "competition_slug": "premier-league",
            "kickoff_time_brasilia": "16:00",
        },
        "requirements": requirements,
        "research_status": "structured_fact_extraction_completed",
        "conflict_requirement_ids": [],
        "validator_accepted_requirement_ids": [
            item["id"] for item in requirements if item.get("validator_accepted") is True
        ],
    }


def main() -> None:
    config = package.load_config()
    links = package.load_links()

    configured_competitions = set(config["editorial"]["competition_labels"])
    assert configured_competitions.issubset(set(links["links"]))
    assert "libertadores" in links["links"]
    assert "copa-do-brasil" in links["links"]

    article = complete_article(config)
    clean, provenance = package.build_article_packages(article, config=config, links=links)

    assert clean["ready_for_drafting"] is True
    assert clean["ready_for_html"] is False
    assert clean["publication_unlocked"] is False
    assert clean["provenance_available_to_drafter"] is False
    assert clean["unresolved_required_requirement_ids"] == []
    assert clean["competition_internal_link"]["url"] == (
        "https://cortedosesportes.com.br/premier-league-historia-campeoes.html"
    )
    assert clean["competition_internal_link"]["anchor_hint"] == "história da Premier League"

    assert package.scan_forbidden_keys(clean) == []
    assert package.scan_external_urls(clean, links["domain"]) == []
    serialized_clean = json.dumps(clean, ensure_ascii=False)
    assert "example.com" not in serialized_clean
    assert '"publisher"' not in serialized_clean
    assert '"sources"' not in serialized_clean
    assert "checked_at" not in serialized_clean
    assert "segundo o site" not in serialized_clean.casefold()

    assert provenance["internal_only"] is True
    assert provenance["available_to_drafter"] is False
    assert provenance["must_never_be_rendered_in_article"] is True
    serialized_provenance = json.dumps(provenance, ensure_ascii=False)
    assert "example.com" in serialized_provenance
    assert '"publisher"' in serialized_provenance

    missing = deepcopy(article)
    missing["requirements"] = [
        item for item in missing["requirements"] if item.get("id") != "officiating"
    ]
    missing_clean, _ = package.build_article_packages(missing, config=config, links=links)
    assert missing_clean["ready_for_drafting"] is False
    assert "officiating" in missing_clean["unresolved_required_requirement_ids"]

    unsupported = deepcopy(article)
    unsupported["match_context"]["competition_slug"] = "competicao-sem-link"
    unsupported_clean, _ = package.build_article_packages(unsupported, config=config, links=links)
    assert unsupported_clean["ready_for_drafting"] is False
    assert unsupported_clean["competition_internal_link"] is None
    assert "competition_internal_link" in unsupported_clean["unresolved_required_requirement_ids"]

    forbidden = deepcopy(article)
    for req in forbidden["requirements"]:
        if req.get("id") == "stadium_and_location":
            req["facts"] = [
                {
                    "field": "stadium",
                    "text": "Segundo o site X, a partida será disputada no Emirates Stadium.",
                }
            ]
            break
    blocked_forbidden = False
    try:
        package.build_article_packages(forbidden, config=config, links=links)
    except SystemExit:
        blocked_forbidden = True
    assert blocked_forbidden is True

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "step": 24,
        "clean_package_ready_for_drafting": clean["ready_for_drafting"],
        "clean_package_has_provenance": False,
        "external_source_urls_in_clean_package": 0,
        "internal_link": clean["competition_internal_link"],
        "provenance_separated": provenance["internal_only"],
        "missing_required_requirement_blocks_drafting": not missing_clean["ready_for_drafting"],
        "missing_internal_link_blocks_drafting": not unsupported_clean["ready_for_drafting"],
        "source_attribution_language_blocked": blocked_forbidden,
        "ready_for_html": False,
        "publication_unlocked": False,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: pacote editorial limpo do Passo 24 validado.")
    print("Fatos aceitos chegam ao redator sem fontes, consultas ou URLs externas.")
    print("Link interno da competição entra por mapa aprovado.")
    print("Proveniência permanece em pacote separado e indisponível à redação.")
    print("Requisito obrigatório ausente ou link não mapeado bloqueia a redação.")
    print("HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
