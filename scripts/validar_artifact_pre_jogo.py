#!/usr/bin/env python3
"""Valida se um artifact de preparo pode ser reutilizado na publicação.

Rejeita data divergente, timestamp inválido/antigo/futuro e, principalmente,
artifact produzido sobre outro SHA da main. Não consulta rede nem altera arquivos.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TZ = ZoneInfo("America/Sao_Paulo")


def agenda_only_change(source_sha: str, current_sha: str, *, worktree: Path | None = None) -> bool:
    """Aceita SHA distinto APENAS quando o histórico até a main alterou agenda.json.

    Não usa diff da área de trabalho: compara commits imutáveis. A preparação
    precisa ser ancestral da publicação; alterações editoriais nunca são ignoradas.
    Em caso de clone superficial ou erro de Git, a validação falha fechada.
    """
    if not all(re.fullmatch(r"[0-9a-f]{40}", value or "", flags=re.IGNORECASE)
               for value in (source_sha, current_sha)):
        return False
    root = worktree or Path(__file__).resolve().parent.parent
    try:
        ancestor = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", source_sha, current_sha],
            capture_output=True, check=False,
        )
        if ancestor.returncode != 0:
            return False
        changed = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", source_sha, current_sha, "--"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(changed) and all(path == "agenda.json" for path in changed)


def validate_manifest(
    data: dict,
    *,
    target_date: str,
    base_main_sha: str,
    now: datetime,
    allow_agenda_only_update: bool = False,
    worktree: Path | None = None,
) -> None:
    if data.get("step") != 34 or data.get("target_date") != target_date:
        raise ValueError("etapa/data do artifact divergente")
    if not re.fullmatch(r"[0-9a-f]{40}", base_main_sha or "", flags=re.IGNORECASE):
        raise ValueError("SHA atual da main inválido")
    source_sha = data.get("source_main_sha")
    if source_sha != base_main_sha:
        if not (allow_agenda_only_update and agenda_only_change(
            source_sha, base_main_sha, worktree=worktree
        )):
            raise ValueError("artifact foi preparado sobre outro SHA da main ou houve mudanças além de agenda.json")

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
    parser.add_argument("--allow-agenda-only-update", action="store_true",
                        help="Aceita SHA diferente só se agenda.json for a única mudança entre os commits.")
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("ERRO: manifesto do artifact não é objeto JSON")
    # Rejeitar o artifact ANTES de carregá-lo no job de publicação; isso
    # ativa a recuperação segura na data correta em vez de publicar texto
    # criado com regras editoriais antigas.
    if data.get("articles"):
        from scripts import preparar_redacao_pre_jogo as editorial
        expected = editorial.editorial_build_fingerprint()
        for article in data["articles"]:
            rel = article.get("contract")
            if not isinstance(rel, str) or not rel.startswith("contracts/"):
                raise SystemExit("ERRO: arquivo de contrato editorial inválido no artifact")
            path = (args.manifest.parent / rel).resolve()
            if not path.is_relative_to(args.manifest.parent.resolve()) or not path.is_file():
                raise SystemExit("ERRO: contrato editorial fora do artifact")
            contract = json.loads(path.read_text(encoding="utf-8"))
            if contract.get("editorial_build_fingerprint") != expected:
                raise SystemExit("ERRO: preparo editorial antigo. Recuperar com o prompt atual.")
    try:
        validate_manifest(
            data,
            target_date=args.date,
            base_main_sha=args.base_main_sha,
            now=datetime.now(TZ),
            allow_agenda_only_update=args.allow_agenda_only_update,
        )
    except ValueError as exc:
        raise SystemExit(f"ERRO: artifact de preparo rejeitado: {exc}") from exc
    print("OK: artifact fresco; mesmo SHA ou atualização comprovadamente restrita a agenda.json.")


if __name__ == "__main__":
    main()
