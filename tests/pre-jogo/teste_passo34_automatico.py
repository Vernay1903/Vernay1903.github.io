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

    print("OK: travas centrais do Passo 34 validadas.")


if __name__ == "__main__":
    main()
