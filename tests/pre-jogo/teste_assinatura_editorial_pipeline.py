#!/usr/bin/env python3
"""Impede reutilização de redação quando mudam o prompt ou os validadores."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import preparar_redacao_pre_jogo as prepare
from scripts import redigir_pre_jogo_openai as writer

TZ = ZoneInfo("America/Sao_Paulo")


def main():
    fingerprint = prepare.editorial_build_fingerprint()
    assert len(fingerprint) == 64
    assert fingerprint == prepare.editorial_build_fingerprint()
    assert len(prepare.EDITORIAL_BUILD_FILES) == len(set(prepare.EDITORIAL_BUILD_FILES))
    for path in prepare.EDITORIAL_BUILD_FILES:
        assert (ROOT / path).is_file()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "contracts").mkdir()
        contract = {"step": 25, "editorial_build_fingerprint": fingerprint}
        (root / "contracts" / "example.json").write_text(
            json.dumps(contract), encoding="utf-8",
        )
        now = datetime.now(TZ)
        sha = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
        ).strip()
        manifest = {
            "step": 34,
            "target_date": now.date().isoformat(),
            "source_main_sha": sha,
            "generated_at": now.isoformat(),
            "articles": [{"contract": "contracts/example.json"}],
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        base = [
            sys.executable, str(ROOT / "scripts/validar_artifact_pre_jogo.py"),
            "--manifest", str(path), "--date", now.date().isoformat(),
            "--base-main-sha", sha,
        ]
        accepted = subprocess.run(base, cwd=ROOT, capture_output=True, text=True)
        assert accepted.returncode == 0, accepted.stderr

        contract["editorial_build_fingerprint"] = "0" * 64
        (root / "contracts" / "example.json").write_text(
            json.dumps(contract), encoding="utf-8",
        )
        rejected = subprocess.run(base, cwd=ROOT, capture_output=True, text=True)
        assert rejected.returncode != 0 and "editorial antigo" in (
            rejected.stderr + rejected.stdout
        ).lower(), rejected

        try:
            writer.validate_contract_for_model(contract, {})
        except SystemExit:
            pass
        else:
            raise AssertionError("Redator aceitou contrato do prompt antigo")

    print("OK: contratos atuais aceitos; prompt/contrato antigos barrados no preparo, redator e publicação.")


if __name__ == "__main__":
    main()
