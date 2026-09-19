#!/usr/bin/env python3
"""Regressões da recuperação do Passo 34; não consulta APIs nem publica."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import recuperar_preparo_pre_jogo_automatico as recovery  # noqa: E402


def main() -> None:
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    plan = recovery.command_plan(today)
    assert len(plan) == 11
    assert plan[0][0] == "scripts/buscar_fixtures_football_data.py"
    assert plan[-1][0] == "scripts/montar_pacote_editorial.py"
    assert plan[6][0] == "scripts/buscar_fontes_serper.py"
    assert plan[8][0] == "scripts/ler_fontes_candidatas.py"
    assert all("--force" in cmd for cmd in plan)

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        config = root / "config" / "pre-jogo.json"
        config.parent.mkdir()
        original = json.dumps(
            {"timezone": "America/Sao_Paulo",
             "monitored_clubs": [{"name": str(i)} for i in range(10)],
             "research": {"discovery": {"external_search_enabled": False}}},
            ensure_ascii=False,
        ).encode()
        config.write_bytes(original)
        build = root / "build" / "pre-jogo"
        output = build / "automatico"
        source = build / "automatico-source"
        calls = []

        def fake_call(*args):
            calls.append(args)
            external = json.loads(config.read_text())["research"]["discovery"]["external_search_enabled"]
            if args[0] in ("scripts/buscar_fontes_serper.py",
                           "scripts/estruturar_evidencias_candidatas.py",
                           "scripts/ler_fontes_candidatas.py",
                           "scripts/extrair_fatos_estruturados.py"):
                assert external is True
            else:
                assert external is False
            if args[0] == "scripts/preparar_lote_pre_jogo_automatico.py":
                output.mkdir(parents=True, exist_ok=True)
                (output / "manifest.json").write_text(
                    json.dumps({"step": 34, "target_date": today,
                                "prepared_count": 0, "skipped_count": 0}),
                    encoding="utf-8",
                )

        secret_env = {"FOOTBALL_DATA_TOKEN": "teste", "CDE_FREE_RESEARCH": "1",
                      "OPENAI_API_KEY": "teste", "SERPER_API_KEY": ""}
        with mock.patch.object(recovery, "ROOT", root), \
             mock.patch.object(recovery, "CONFIG", config), \
             mock.patch.object(recovery, "BUILD", build), \
             mock.patch.object(recovery, "OUTPUT", output), \
             mock.patch.object(recovery, "SOURCE", source), \
             mock.patch.object(recovery, "call", side_effect=fake_call), \
             mock.patch.object(recovery, "verify_checkout_unchanged"), \
             mock.patch.object(recovery.subprocess, "check_output", return_value="abc123"), \
             mock.patch.dict(os.environ, secret_env):
            recovery.run(today)
            assert config.read_bytes() == original
            assert (source / "manifest.json").exists()
            assert len(calls) == 12
            calls.clear()

            def raise_scrape(*args):
                if args[0] == "scripts/ler_fontes_candidatas.py":
                    raise RuntimeError("falha externa simulada")
                fake_call(*args)

            with mock.patch.object(recovery, "call", side_effect=raise_scrape):
                try:
                    recovery.run(today)
                except RuntimeError as exc:
                    assert "falha externa simulada" in str(exc)
                else:
                    raise AssertionError("Falha de API não deve ser escondida.")
            assert config.read_bytes() == original

            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                try:
                    recovery.run(today)
                except SystemExit as exc:
                    assert "OPENAI_API_KEY" in str(exc)
                else:
                    raise AssertionError("Secret ausente deve bloquear recuperação.")

    print("OK: recuperação controla todos os passos, restaura configuração e propaga falhas sem publicar.")


if __name__ == "__main__":
    main()
