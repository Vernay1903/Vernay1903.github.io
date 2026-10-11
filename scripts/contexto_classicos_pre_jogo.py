#!/usr/bin/env python3
"""Conhecimento editorial estável de rivalidades, independente de API e de placares.

Somente enquadramento histórico atemporal, nunca fatos atuais do jogo.
Não generalizar: Liverpool x City não é o dérbi de Manchester ou Merseyside.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

CATALOG = Path(__file__).resolve().parent.parent / "config" / "classicos-pre-jogo.json"


def key(value: Any) -> str:
    value = "".join(c for c in unicodedata.normalize("NFKD", str(value or ""))
                    if not unicodedata.combining(c)).casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def find_rivalry(home: str, away: str) -> dict[str, str] | None:
    if not home or not away or key(home) == key(away):
        return None
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    wanted = frozenset((key(home), key(away)))
    for row in catalog["rivalries"]:
        if frozenset(map(key, row["teams"])) == wanted:
            return {k: str(row[k]) for k in ("name", "kind", "background", "angle")}
    return None
