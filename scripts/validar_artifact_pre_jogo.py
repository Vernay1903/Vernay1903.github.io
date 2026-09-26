#!/usr/bin/env python3
"""Valida se um artifact de preparo pode ser reutilizado na publicação.

Rejeita data divergente, timestamp inválido/antigo/futuro e, principalmente,
artifact produzido sobre outro SHA da main. Não consulta rede nem altera arquivos.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def validate_manifest(
    data: dict,
    *,
    target_date: str,
    base_main_sha: str,
    now: datetime,
) -> None:
    if data.get("step") != 34 or data.get("target_date") != target_date:
        raise ValueError("etapa/data do artifact divergente")
    if not re.fullmatch(r"[0-9a-f]{40}", base_main_sha or "", flags=re.IGNORECASE):
        raise ValueError("SHA atual da main inválido")
    source_sha = data.get("source_main_sha")
    if source_sha != base_main_sha:
        raise ValueError("artifact foi preparado sobre outro SHA da main")

    raw = data.get("generated_at")
    if not isinstance(raw, str):
        raise ValueError("artifact sem generated_at")
    try:
        generated = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("generated_at inválido") from exc
    if generated.tzinfo is None:
        raise ValueError("generated_at sem timezone")

    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=TZ)
    except ValueError as exc:
        raise ValueError("target_date inválida") from exc

    local_generated = generated.astimezone(TZ)
    local_now = now.astimezone(TZ)
    if local_now.date() != target.date():
        raise ValueError("publicação fora da data-alvo")
    if local_generated > local_now:
        raise ValueError("artifact com timestamp futuro")
    if local_generated < target - timedelta(hours=2):
        raise ValueError("artifact antigo demais para a data-alvo")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--base-main-sha", required=True)
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("ERRO: manifesto do artifact não é objeto JSON")
    try:
        validate_manifest(
            data,
            target_date=args.date,
            base_main_sha=args.base_main_sha,
            now=datetime.now(TZ),
        )
    except ValueError as exc:
        raise SystemExit(f"ERRO: artifact de preparo rejeitado: {exc}") from exc
    print("OK: artifact fresco e produzido sobre a mesma main da publicação.")


if __name__ == "__main__":
    main()
