#!/usr/bin/env python3
"""Regression: updating ONLY agenda.json must not invalidate an editorial artifact."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.validar_artifact_pre_jogo import agenda_only_change, validate_manifest

TZ = ZoneInfo("America/Sao_Paulo")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def expect_rejected(manifest: dict, sha: str, now: datetime, root: Path, *, allow: bool) -> None:
    try:
        validate_manifest(manifest, target_date=now.date().isoformat(),
                          base_main_sha=sha, now=now,
                          allow_agenda_only_update=allow, worktree=root)
    except ValueError:
        return
    raise AssertionError("Validador autorizou um lote sobre commit incompatível.")


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        git(root, "init", "-q")
        git(root, "config", "user.email", "test@example.invalid")
        git(root, "config", "user.name", "Teste Automático")
        (root / "agenda.json").write_text("[]\n", encoding="utf-8")
        (root / "editorial.py").write_text("STYLE = 1\n", encoding="utf-8")
        initial = commit(root, "baseline")
        now = datetime.now(TZ)
        manifest = {"step": 34, "target_date": now.date().isoformat(),
                    "generated_at": now.isoformat(), "source_main_sha": initial}
        validate_manifest(manifest, target_date=now.date().isoformat(),
                          base_main_sha=initial, now=now, worktree=root)

        (root / "agenda.json").write_text('[{"time":"16h","desc":"Exemplo"}]\n', encoding="utf-8")
        agenda_sha = commit(root, "agenda only")
        expect_rejected(manifest, agenda_sha, now, root, allow=False)
        assert agenda_only_change(initial, agenda_sha, worktree=root)
        validate_manifest(manifest, target_date=now.date().isoformat(),
                          base_main_sha=agenda_sha, now=now,
                          allow_agenda_only_update=True, worktree=root)

        (root / "editorial.py").write_text("STYLE = 2\n", encoding="utf-8")
        editorial_sha = commit(root, "editorial changed")
        assert not agenda_only_change(initial, editorial_sha, worktree=root)
        expect_rejected(manifest, editorial_sha, now, root, allow=True)
        assert not agenda_only_change(editorial_sha, agenda_sha, worktree=root)
        assert not agenda_only_change("not-a-sha", agenda_sha, worktree=root)

    print("OK: agenda.json isolada é aceita; alterações editoriais ou histórico inválido são bloqueados.")


if __name__ == "__main__":
    main()
