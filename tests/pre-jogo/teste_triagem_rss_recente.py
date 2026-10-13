#!/usr/bin/env python3
"""A busca gratuita não deve reservar as três leituras para notícias de outras datas."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.buscar_fontes_serper import candidate_recent_for_article


def row(hint):
    return {"url": "https://goal.com/exemplo", "published_hint": hint}


def main() -> None:
    target = "2026-10-14"
    assert candidate_recent_for_article(row("Mon, 12 Oct 2026 23:54:00 GMT"), target)
    assert candidate_recent_for_article(row("Mon, 12 Oct 2026 23:54:00 GMT"), "14/10/2026")
    assert not candidate_recent_for_article(row("Mon, 03 May 2021 12:01:00 GMT"), target)
    assert not candidate_recent_for_article(row("Mon, 23 Feb 2026 16:33:00 GMT"), target)
    assert not candidate_recent_for_article(row("Fri, 14 Aug 2026 15:19:00 GMT"), target)
    assert not candidate_recent_for_article(row("Mon, 21 Sep 2026 16:25:00 GMT"), target)
    assert not candidate_recent_for_article(row("Wed, 14 Nov 2026 15:19:00 GMT"), target)
    assert not candidate_recent_for_article(row("ontem"), target)
    assert candidate_recent_for_article(row(None), target)
    print("OK: fontes históricas são rejeitadas na busca antes de consumir leituras gratuitas.")


if __name__ == "__main__":
    main()
