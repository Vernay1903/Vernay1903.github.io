#!/usr/bin/env python3
"""Recupera o preparo ausente na própria execução de publicação do Passo 34.

A recuperação NÃO publica nada: cria somente um lote dentro de build/pre-jogo/.
Usa as mesmas etapas e travas do preparo agendado, mas não depende de um
segundo agendamento do GitHub Actions. Falhas externas interrompem o job.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "pre-jogo.json"
BUILD = ROOT / "build" / "pre-jogo"
OUTPUT = BUILD / "automatico"
SOURCE = BUILD / "automatico-source"
TZ = ZoneInfo("America/Sao_Paulo")


def fail(message: str) -> None:
    raise SystemExit(f"ERRO: {message}")


def call(*args: str) -> None:
    print("RECUPERAÇÃO: " + " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def verify_checkout_unchanged() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    outside_build = [
        line for line in result.stdout.splitlines()
        if not line.startswith("?? build/") and not line.startswith("!! build/")
    ]
    if outside_build:
        fail("Recuperação alterou arquivos fora de build/: " + "; ".join(outside_build[:8]))


def command_plan(target: str) -> list[list[str]]:
    """Lista explícita para auditoria/testes; todas as saídas ficam em build/."""
    return [
        ["scripts/buscar_fixtures_football_data.py", "--date", target, "--force"],
        ["scripts/identificar_jogos.py", "--date", target, "--force"],
        ["scripts/planejar_pre_jogos.py", "--date", target, "--force"],
        ["scripts/preparar_dados_editoriais.py", "--date", target, "--force"],
        ["scripts/preparar_pesquisa_factual.py", "--date", target, "--force"],
        ["scripts/planejar_coleta_fontes.py", "--date", target, "--force"],
        ["scripts/buscar_fontes_serper.py", "--date", target, "--execute", "--force"],
        ["scripts/estruturar_evidencias_candidatas.py", "--date", target, "--force"],
        ["scripts/ler_fontes_candidatas.py", "--date", target, "--execute", "--force"],
        ["scripts/extrair_fatos_estruturados.py", "--date", target, "--force"],
        ["scripts/enriquecer_fatos_football_data.py", "--date", target, "--execute", "--force"],
        ["scripts/montar_pacote_editorial.py", "--date", target, "--force"],
    ]


def run(target: str) -> None:
    now = datetime.now(TZ)
    try:
        desired = datetime.strptime(target, "%Y-%m-%d").date()
    except ValueError:
        fail("--date deve usar YYYY-MM-DD.")
    if desired != now.date():
        fail(f"Recuperação só pode preparar a data corrente de Brasília: {now.date()}.")

    if os.environ.get("CDE_FREE_RESEARCH") != "1":
        fail("Recuperação paga desativada: é obrigatório CDE_FREE_RESEARCH=1.")
    if not os.environ.get("FOOTBALL_DATA_TOKEN", "").strip():
        fail("FOOTBALL_DATA_TOKEN ausente: não é possível confirmar um dia sem partidas.")

    raw_config = CONFIG.read_bytes()
    config = json.loads(raw_config)
    if config.get("timezone") != "America/Sao_Paulo" or len(config.get("monitored_clubs", [])) != 10:
        fail("Configuração dos 10 clubes/timezone inválida.")

    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    SOURCE.mkdir(parents=True)

    plan = command_plan(target)
    # Recuperação sem partidas encerra antes de RSS, Serper ou OpenAI.
    for command in plan[:3]:
        call(*command)
    games = json.loads((BUILD / f"jogos-{target}.json").read_text(encoding="utf-8"))
    planned = json.loads((BUILD / f"planos-{target}.json").read_text(encoding="utf-8"))
    if games.get("target_date") != target or planned.get("target_date") != target:
        fail("Data da identificação/planejamento divergente na recuperação.")
    if games.get("selected_count") == 0:
        if games.get("matches") != [] or planned.get("planned_count") != 0 or planned.get("skipped_count") != 0:
            fail("Relatórios não comprovam ausência de jogos elegíveis.")
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        call(
            "scripts/registrar_preparo_vazio_pre_jogo.py",
            "--date", target, "--source-main-sha", sha, "--force",
        )
        manifest = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("no_eligible_matches") is not True or manifest.get("target_date") != target:
            fail("Registro de dia sem jogos inválido na recuperação.")
        shutil.copytree(OUTPUT, SOURCE, dirs_exist_ok=True)
        verify_checkout_unchanged()
        print("RECUPERAÇÃO: sem jogos dos clubes; sem RSS, OpenAI ou publicação.", flush=True)
        return

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        fail("OPENAI_API_KEY ausente para jogos elegíveis; nenhuma publicação foi feita.")
    for command in plan[3:6]:
        call(*command)

    try:
        config["research"]["discovery"]["external_search_enabled"] = True
        CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for command in command_plan(target)[6:11]:
            call(*command)
    finally:
        CONFIG.write_bytes(raw_config)

    call(*command_plan(target)[11])
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    call(
        "scripts/preparar_lote_pre_jogo_automatico.py",
        "--date", target,
        "--packages", f"build/pre-jogo/pacotes-editoriais-{target}.json",
        "--facts", f"build/pre-jogo/fatos-estruturados-{target}.json",
        "--source-main-sha", sha,
        "--output-dir", "build/pre-jogo/automatico",
        "--execute", "--force",
    )
    manifest = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("step") != 34 or manifest.get("target_date") != target:
        fail("Manifesto da recuperação inválido: data/etapa divergente.")
    shutil.copytree(OUTPUT, SOURCE, dirs_exist_ok=True)
    verify_checkout_unchanged()
    print(
        f"RECUPERAÇÃO CONCLUÍDA: prontas={manifest['prepared_count']}, "
        f"bloqueadas={manifest['skipped_count']}; nenhuma matéria publicada.",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        datetime.strptime(args.date, "%Y-%m-%d")
        for command in command_plan(args.date):
            print(" ".join(command))
        print("scripts/preparar_lote_pre_jogo_automatico.py --execute --force")
        print("SIMULAÇÃO: nenhuma API, arquivo versionado ou publicação foi alterada.")
    else:
        run(args.date)


if __name__ == "__main__":
    main()
