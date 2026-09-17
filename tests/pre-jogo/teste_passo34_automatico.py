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
            "snippet": "Bundesliga preview and recent results.",
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
            "snippet": "Bayern form and latest Bundesliga matches.",
            "url": "https://www.bundesliga.com/en/bundesliga/bayern-munich-form",
            "domain": "bundesliga.com",
        },
        {
            "title": "Union Berlin recent Bundesliga results",
            "snippet": "Union Berlin form and latest Bundesliga matches.",
            "url": "https://www.bundesliga.com/en/bundesliga/union-berlin-form",
            "domain": "bundesliga.com",
        },
        candidates[1],
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
    )
    assert any("head to head" in item for item in expanded)

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

    print("OK: travas centrais do Passo 34 e filtro 34.5 validados.")


if __name__ == "__main__":
    main()
