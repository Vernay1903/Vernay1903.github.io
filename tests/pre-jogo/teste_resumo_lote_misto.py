#!/usr/bin/env python3
"""Regressão de lotes mistos: somente bloqueados não impedem artigos válidos."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.resumir_preparo_pre_jogo import avaliar_lote


def manifesto(ready, blocked):
    return {
        "prepared_count": ready,
        "skipped_count": blocked,
        "articles": [{"slug": f"aprovada-{i}.html"} for i in range(ready)],
        "skipped": [{"slug": f"bloqueada-{i}.html", "reason": "research_incomplete"}
                    for i in range(blocked)],
    }


def main():
    assert avaliar_lote(manifesto(1, 3))[0] is True
    assert avaliar_lote(manifesto(4, 0))[0] is True
    assert avaliar_lote(manifesto(0, 3))[0] is False
    assert avaliar_lote(manifesto(0, 0))[0] is True
    invalid = manifesto(1, 1)
    invalid["prepared_count"] = 2
    assert avaliar_lote(invalid)[0] is False
    print("OK: lotes mistos publicados parcialmente sem mascarar falhas reais.")


if __name__ == "__main__":
    main()
