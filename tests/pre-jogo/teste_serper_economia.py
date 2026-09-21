#!/usr/bin/env python3
"""Garante parada antecipada na Serper sem relaxar filtros editoriais."""
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import buscar_fontes_serper as search  # noqa: E402


def result(title: str, url: str):
    return {"organic": [{"title": title, "link": url, "snippet": title, "position": 1}]}


def plan(requirement_id, queries):
    return {
        "title": "Teste editorial sem publicação",
        "slug": "teste.html",
        "date": "19/09/2026",
        "match_context": {"home": "Arsenal", "away": "Manchester City",
                          "competition": "Premier League", "competition_slug": "premier-league"},
        "tasks": [{
            "requirement_id": requirement_id,
            "queries": queries,
            "stages": [{"source_type": "official", "domains": []},
                       {"source_type": "major_sports_media", "domains": []}],
        }],
    }


def main():
    reason = search.classify_serper_error_body('{"message":"Not enough credits"}')
    assert "créditos insuficientes" in reason
    assert "CHAVE_SECRETA" not in search.classify_serper_error_body(
        '{"message":"Not enough credits CHAVE_SECRETA"}')
    cfg = {"monitored_clubs": [
        {"name": "Arsenal", "slug": "arsenal", "aliases": ["Arsenal FC"]},
        {"name": "Manchester City", "slug": "manchester-city", "aliases": ["Man City"]},
    ], "research": {"discovery": {"official_domains": {"competitions": {}}}}}
    calls = []

    def fake_request(**kw):
        calls.append(kw["query"])
        return kw["query"], result("Arsenal x Manchester City transmissão ao vivo 2026", "https://example.org/arsenal-manchester-city-transmissao-2026")

    with mock.patch.object(search, "request_serper", side_effect=fake_request):
        out = search.discover_candidates_for_plan(
            plan("transmission", ["primeira", "segunda", "terceira"]), config=cfg)
    assert len(calls) == 1, calls
    assert out["query_count"] == 1
    assert out["tasks"][0]["search_status"] == "candidates_found"

    calls.clear()
    def fake_form(**kw):
        calls.append(kw["query"])
        if kw["query"] == "arsenal":
            return "arsenal", result("Arsenal won last match 2026", "https://example.org/arsenal-form")
        return "city", result("Manchester City won last match 2026", "https://example.org/city-form")
    with mock.patch.object(search, "request_serper", side_effect=fake_form):
        out = search.discover_candidates_for_plan(
            plan("recent_form_both_teams", ["arsenal", "city", "extra"]), config=cfg)
    assert calls == ["arsenal", "city"], calls
    assert out["query_count"] == 2
    assert len(out["tasks"][0]["candidates"]) == 2

    print("OK: a Serper economiza consultas sem aceitar forma recente unilateral.")


if __name__ == "__main__":
    main()
