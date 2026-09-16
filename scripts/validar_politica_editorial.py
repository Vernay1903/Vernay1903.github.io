#!/usr/bin/env python3
"""Valida a proibição de citar fontes/consultas internas no corpo da matéria.

Esta regra não impede citar uma emissora como informação de transmissão. Ela
bloqueia construções de atribuição de pesquisa como "segundo o site...",
"conforme o portal..." e menções ao processo interno de busca/consulta.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
TAG_RE = re.compile(r"<[^>]+>")

ATTRIBUTION_PATTERNS = [
    re.compile(r"\bsegundo\s+(?:o|a)\s+(?:site|portal|jornal|ve[ií]culo|fonte)\b", re.IGNORECASE),
    re.compile(r"\bconforme\s+(?:o|a)\s+(?:site|portal|jornal|ve[ií]culo|fonte)\b", re.IGNORECASE),
    re.compile(r"\bde\s+acordo\s+com\s+(?:o|a)\s+(?:site|portal|jornal|ve[ií]culo|fonte)\b", re.IGNORECASE),
    re.compile(r"\bsegundo\s+(?:o\s+)?(?:ge|espn|arsenal|manchester city|premier league)\b", re.IGNORECASE),
    re.compile(r"\bconforme\s+(?:o\s+)?(?:ge|espn|arsenal|manchester city|premier league)\b", re.IGNORECASE),
    re.compile(r"\bde\s+acordo\s+com\s+(?:o\s+)?(?:ge|espn|arsenal|manchester city|premier league)\b", re.IGNORECASE),
    re.compile(r"\b(?:fontes?|sites?|portais?)\s+consultad[oa]s?\b", re.IGNORECASE),
    re.compile(r"\b(?:em|ap[oó]s)\s+consulta\s+(?:ao|aos|à|às)\b", re.IGNORECASE),
    re.compile(r"\b(?:na|durante a)\s+pesquisa\s+(?:realizada|interna)\b", re.IGNORECASE),
    re.compile(r"\b(?:busca|consulta|pesquisa)\s+interna\b", re.IGNORECASE),
]


def fail(message: str) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_config() -> dict[str, Any]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        fail(f"Não foi possível ler config/pre-jogo.json: {exc}")
    if not isinstance(config, dict):
        fail("config/pre-jogo.json deve conter um objeto JSON.")
    policy = config.get("editorial", {}).get("source_attribution_policy")
    if not isinstance(policy, dict):
        fail("Política de atribuição de fontes ausente.")
    required = {
        "research_sources_are_internal_only": True,
        "forbid_source_names_in_article_body": True,
        "forbid_research_process_mentions": True,
        "forbid_query_mentions": True,
        "write_verified_facts_directly": True,
    }
    for key, expected in required.items():
        if policy.get(key) is not expected:
            fail(f"A política editorial obrigatória está inválida em {key}.")
    return config


def visible_text(body_html: str) -> str:
    return html.unescape(TAG_RE.sub(" ", body_html))


def find_forbidden_attributions(body_html: str) -> list[str]:
    text = visible_text(body_html)
    matches: list[str] = []
    for pattern in ATTRIBUTION_PATTERNS:
        match = pattern.search(text)
        if match:
            matches.append(match.group(0))
    return matches


def validate_body_policy(body_html: str, config: dict[str, Any] | None = None) -> list[str]:
    if config is None:
        config = load_config()
    policy = config["editorial"]["source_attribution_policy"]
    if policy.get("research_sources_are_internal_only") is not True:
        return ["research_sources_are_internal_only deve permanecer true"]

    matches = find_forbidden_attributions(body_html)
    return [f"atribuição de fonte/processo interno proibida: {item}" for item in matches]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rejeita corpo editorial que exponha fontes ou consultas internas."
    )
    parser.add_argument("--data", required=True, type=Path, help='JSON contendo o campo "body_html".')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    try:
        payload = json.loads(args.data.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        fail(f"Arquivo editorial inválido: {exc}")
    if not isinstance(payload, dict) or not isinstance(payload.get("body_html"), str):
        fail('O arquivo deve conter "body_html" em texto.')

    errors = validate_body_policy(payload["body_html"], config)
    if errors:
        fail("; ".join(errors))
    print("OK: corpo editorial sem atribuições de fontes/consultas internas.")


if __name__ == "__main__":
    main()
