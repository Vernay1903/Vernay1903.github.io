#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import aplicar_lote_pre_jogo_automatico as apply_batch
from scripts import buscar_fontes_serper as source_search
from scripts import extrair_fatos_openai as grounded_extractor
from scripts import ler_fontes_candidatas as page_reader
from scripts import preparar_lote_pre_jogo_automatico as prepare_batch


def main() -> None:
    config = {
        "research": {
            "discovery": {
                "official_domains": {
                    "competitions": {"libertadores": ["conmebol.com"]}
                }
            }
        }
    }
    article = {
        "match_context": {"competition_slug": "libertadores"},
        "requirements": [
            {
                "id": "stadium_and_location",
                "facts": [{"field": "stadium", "text": "Estádio: Maracanã."}],
                "sources": [
                    {
                        "source_type": "official",
                        "url": "https://www.conmebol.com/exemplo",
                    }
                ],
                "source_candidates": [
                    {
                        "source_type": "major_sports_media",
                        "url": "https://example.com/noticia",
                        "content_checked": True,
                    }
                ],
            }
        ],
    }
    package = {
        "date": "17/09/2026",
        "match_context": {
            "home": "Flamengo",
            "away": "Independiente del Valle",
            "competition": "Libertadores",
            "competition_slug": "libertadores",
            "kickoff_time_brasilia": "21:30",
        },
    }

    snapshot = prepare_batch.status_snapshot(article, package, config)
    assert snapshot is not None
    assert snapshot["match"]["stadium"] == "Maracanã"
    assert snapshot["article_source_policy"]["internal_only"] is True
    assert snapshot["article_source_policy"]["send_sources_to_model"] is False
    assert snapshot["evidence"] == [
        {
            "source_type": "official_competition",
            "url": "https://www.conmebol.com/exemplo",
        }
    ]

    article_no_official = {
        "match_context": {"competition_slug": "libertadores"},
        "requirements": [
            {
                "id": "transmission",
                "facts": [],
                "sources": [
                    {"source_type": "major_sports_media", "url": "https://example.com/x"}
                ],
            }
        ],
    }
    assert prepare_batch.status_snapshot(article_no_official, package, config) is None

    relevance_config = {
        "monitored_clubs": [
            {
                "name": "Bayern de Munique",
                "slug": "bayern-de-munique",
                "aliases": ["Bayern Munich", "FC Bayern München", "Bayern München"],
            }
        ],
        "research": {
            "discovery": {
                "official_domains": {
                    "competitions": {"bundesliga": ["bundesliga.com"]}
                }
            }
        },
    }
    context = {
        "home": "FC Bayern München",
        "away": "1. FC Union Berlin",
        "competition": "Bundesliga",
        "competition_slug": "bundesliga",
    }
    candidates = [
        {
            "title": "Bayern Munich vs Union Berlin - Bundesliga head-to-head",
            "snippet": "Previous Bundesliga meetings between Bayern and Union Berlin.",
            "url": "https://www.bundesliga.com/en/bundesliga/news/bayern-munich-union-berlin-head-to-head",
            "domain": "bundesliga.com",
        },
        {
            "title": "Union Berlin vs Bayer Leverkusen",
            "snippet": "Related search text also mentions Bayern Munich, but this is a different fixture.",
            "url": "https://www.bundesliga.com/en/bundesliga/news/union-berlin-bayer-leverkusen",
            "domain": "bundesliga.com",
        },
    ]
    filtered_h2h = source_search.filter_results_for_requirement(
        "competition_specific_head_to_head",
        candidates,
        context=context,
        config=relevance_config,
    )
    assert len(filtered_h2h) == 1
    assert "bayern-munich-union-berlin" in filtered_h2h[0]["url"]

    recent_candidates = [
        {
            "title": "Bayern Munich recent Bundesliga results",
            "snippet": "Bayern won twice and drew once in the first three league games.",
            "url": "https://www.bundesliga.com/en/bundesliga/bayern-munich-form",
            "domain": "bundesliga.com",
        },
        {
            "title": "Union Berlin recent Bundesliga results",
            "snippet": "Union Berlin won its latest Bundesliga match and has recent results here.",
            "url": "https://www.bundesliga.com/en/bundesliga/union-berlin-form",
            "domain": "bundesliga.com",
        },
        {
            "title": "Union Berlin - Bundesliga",
            "snippet": "Clube J Vitórias-Empate-Perdas V-E-P G +/- P",
            "url": "https://www.bundesliga.com/en/bundesliga/clubs/1-fc-union-berlin",
            "domain": "bundesliga.com",
        },
    ]
    filtered_form = source_search.filter_results_for_requirement(
        "recent_form_both_teams",
        recent_candidates,
        context=context,
        config=relevance_config,
    )
    assert len(filtered_form) >= 2
    assert "bayern" in filtered_form[0]["url"]
    assert any("union-berlin-form" in item["url"] for item in filtered_form[:2])
    assert not any("clubs/1-fc-union-berlin" in item["url"] for item in filtered_form)

    only_home = source_search.filter_results_for_requirement(
        "recent_form_both_teams",
        recent_candidates[:1],
        context=context,
        config=relevance_config,
    )
    assert only_home == []

    expanded = source_search.expanded_queries(
        "competition_specific_head_to_head",
        ['"FC Bayern München" "1. FC Union Berlin" "Bundesliga" histórico confrontos'],
        context,
        "2026-09-18",
    )
    assert any("head to head" in item for item in expanded)

    shared_segment = (
        "On Friday night, FC Bayern Munich welcome 1. FC Union Berlin to the Allianz Arena on "
        "Bundesliga Matchday 4. In 14 Bundesliga encounters the hosts are unbeaten (W9, D5), "
        "without ever losing. The champions are unbeaten in the first three league games with "
        "two wins and one draw."
    )
    shared_source = {
        "publisher": "FC Bayern",
        "url": "https://fcbayern.com/example/bayern-union-facts",
        "source_type": "official",
        "checked_at": "2026-09-17T17:00:00-03:00",
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "title": "Facts FC Bayern vs. Union Berlin | Bundesliga 26/27",
        "page_evidence": {
            "metadata": {},
            "evidence_segments": [shared_segment],
            "segment_count": 1,
        },
    }
    checked_requirements = [
        {
            "id": "stadium_and_location",
            "required_for_drafting": True,
            "source_candidates": [],
            "ready_for_fact_extraction": False,
        },
        {
            "id": "recent_form_both_teams",
            "required_for_drafting": True,
            "source_candidates": [shared_source],
            "ready_for_fact_extraction": True,
        },
        {
            "id": "competition_specific_head_to_head",
            "required_for_drafting": True,
            "source_candidates": [
                {
                    "publisher": "ESPN",
                    "url": "https://example.com/union-paderborn",
                    "source_type": "major_sports_media",
                    "checked_at": "2026-09-17T17:00:00-03:00",
                    "content_checked": True,
                    "eligible_for_factual_validation": True,
                    "title": "Union Berlin 0-1 Paderborn",
                    "page_evidence": {"metadata": {}, "evidence_segments": ["Union Berlin 0-1 Paderborn"]},
                }
            ],
            "ready_for_fact_extraction": True,
        },
    ]
    reused_requirements, reused_count = page_reader.reuse_checked_sources_across_requirements(
        checked_requirements,
        context=context,
    )
    by_id = {item["id"]: item for item in reused_requirements}
    assert reused_count >= 2
    assert by_id["stadium_and_location"]["source_candidates"][0]["url"] == shared_source["url"]
    assert by_id["competition_specific_head_to_head"]["source_candidates"][0]["url"] == shared_source["url"]
    assert by_id["competition_specific_head_to_head"]["source_candidates"][0]["passo34_6_cross_requirement_reuse"] is True

    assert grounded_extractor.controlled_zero_away_wins_grounding(
        field="h2h_away_wins",
        value="0",
        support=shared_segment,
        context=context,
        site_config=relevance_config,
    ) is True
    assert grounded_extractor.controlled_zero_away_wins_grounding(
        field="h2h_away_wins",
        value="1",
        support=shared_segment,
        context=context,
        site_config=relevance_config,
    ) is False

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "approved.txt"
        path.write_text("a.html\n\n b.html \na.html\n", encoding="utf-8")
        assert apply_batch.approved_slugs(path) == {"a.html", "b.html"}
        missing = Path(tmp) / "missing.txt"
        assert apply_batch.approved_slugs(missing) == set()

        json_path = Path(tmp) / "sample.json"
        json_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
        digest = prepare_batch.sha256_file(json_path)
        assert len(digest) == 64
        assert digest == apply_batch.sha256_file(json_path)

    print("OK: travas centrais do Passo 34 e ajustes 34.5/34.6 validados.")


if __name__ == "__main__":
    main()
