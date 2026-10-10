#!/usr/bin/env python3
"""Regressao offline: a cota RSS e por confronto nas duas fases de pesquisa."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import buscar_fontes_serper as discovery
from scripts import ler_fontes_candidatas_passo34_10 as reader
from scripts import pesquisa_publica_gratuita as rss


def sample_plan(slug: str) -> dict:
    return {
        "slug": slug,
        "date": "2026-10-10",
        "match_context": {
            "home": "Arsenal",
            "away": "Leeds",
            "competition": "Premier League",
        },
        "tasks": [{
            "requirement_id": "stadium_and_location",
            "queries": ["Arsenal Leeds stadium 2026"],
            "stages": [{"source_type": "official", "domains": ["arsenal.com"]}],
        }],
    }


def main() -> None:
    feed = (
        "<rss><channel><item><title>Arsenal Leeds estadio 2026</title>"
        "<link>https://www.arsenal.com/news/arsenal-leeds-2026</link>"
        "<description>Somente URL candidata; nao serve como prova factual.</description>"
        "</item></channel></rss>"
    ).encode("utf-8")
    old_count = rss._RSS_REQUESTS
    old_cache = rss._SEARCH_CACHE.copy()
    try:
        with patch.dict(os.environ, {"CDE_FREE_RESEARCH": "1", "CDE_RSS_MAX_REQUESTS": "1"}):
            with patch.object(rss, "fetch", return_value=(feed, "utf-8")) as mocked:
                for slug in ("arsenal-leeds.html", "augsburg-bayern.html", "inter-parma.html"):
                    result = discovery.discover_candidates_for_plan(sample_plan(slug), config={})
                    assert result["tasks"][0]["candidates"], slug
                    assert rss._RSS_REQUESTS == 1, slug
                assert mocked.call_count == 3, mocked.call_count

            # A leitura das paginas tambem deve reiniciar a cota entre partidas.
            def previous(article, *, config, checked_at):
                assert rss._RSS_REQUESTS == 0, "O leitor herdou a cota do jogo anterior"
                return article

            article = {
                "slug": "arsenal-leeds.html",
                "date": "2026-10-10",
                "requirements": [],
                "match_context": {},
            }
            rss._RSS_REQUESTS = 30
            with patch.object(reader, "_PREVIOUS_CHECK_ARTICLE", side_effect=previous):
                result = reader.check_article(article, config={}, checked_at="2026-10-10T06:00:00-03:00")
            assert result["slug"] == article["slug"]
            assert rss._RSS_REQUESTS == 0
    finally:
        rss._RSS_REQUESTS = old_count
        rss._SEARCH_CACHE.clear()
        rss._SEARCH_CACHE.update(old_cache)

    print("OK: tres confrontos e o leitor tiveram cotas RSS independentes, sem rede ou custo.")


if __name__ == "__main__":
    main()
