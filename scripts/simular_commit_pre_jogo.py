#!/usr/bin/env python3
"""Simula localmente o futuro commit de publicação do pré-jogo.

O script aplica SOMENTE os três arquivos preparados no Passo 28:
- <slug>.html (create)
- noticias.json (modify)
- sitemap.xml (modify)

Depois cria um commit APENAS LOCAL em uma branch temporária, valida que o commit
contém exatamente três alterações e remove a branch local. Nenhum push é feito.
O relatório final é salvo apenas em build/pre-jogo/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = ROOT / "build" / "pre-jogo" / "source-step28"
DEFAULT_REPORT = ROOT / "build" / "pre-jogo" / "commit-simulation" / "report.json"
SIM_BRANCH = "pre-jogo-simulacao-passo-29"


def fail(message: str) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_output(*args: str) -> str:
    proc = run_git(*args)
    return proc.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(package_dir: Path) -> dict[str, Any]:
    path = package_dir / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"manifest.json não encontrado em {package_dir}")
    except json.JSONDecodeError as exc:
        fail(f"manifest.json inválido: {exc}")
    if not isinstance(data, dict):
        fail("manifest.json precisa ser um objeto JSON.")
    return data


def validate_package(package_dir: Path) -> tuple[dict[str, Any], str, list[str]]:
    manifest = load_manifest(package_dir)
    if manifest.get("step") != 28:
        fail("O pacote não pertence ao Passo 28.")
    if manifest.get("prepared_change_count") != 3:
        fail("O pacote precisa conter exatamente três alterações preparadas.")
    if manifest.get("published_files_touched") is not False:
        fail("O Passo 28 indica alteração publicada indevida.")
    if manifest.get("commit_executed") is not False:
        fail("O Passo 28 já indica commit executado; pacote recusado.")
    if manifest.get("publication_unlocked") is not False:
        fail("O Passo 28 liberou publicação indevidamente.")

    slug = manifest.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html") or "/" in slug or "\\" in slug:
        fail("Slug inválido no manifest do Passo 28.")

    expected_targets = [slug, "noticias.json", "sitemap.xml"]
    prepared = manifest.get("prepared_changes")
    if not isinstance(prepared, list) or len(prepared) != 3:
        fail("prepared_changes precisa ter exatamente três itens.")

    prepared_targets = [item.get("target") for item in prepared if isinstance(item, dict)]
    if prepared_targets != expected_targets:
        fail(
            "A ordem/escopo de prepared_changes diverge do contrato do Passo 29: "
            f"{prepared_targets}"
        )

    actual_files = sorted(path.name for path in package_dir.iterdir() if path.is_file())
    expected_files = sorted([*expected_targets, "manifest.json"])
    if actual_files != expected_files:
        fail(f"Pacote contém arquivos inesperados: {actual_files}")

    for item in prepared:
        target = item["target"]
        path = package_dir / target
        if not path.is_file():
            fail(f"Arquivo preparado ausente: {target}")
        expected_sha = item.get("sha256")
        if not isinstance(expected_sha, str) or sha256_file(path) != expected_sha:
            fail(f"SHA-256 divergente no pacote: {target}")

    operations = {item["target"]: item.get("operation") for item in prepared}
    if operations.get(slug) != "create":
        fail("O HTML precisa estar marcado como create.")
    if operations.get("noticias.json") != "modify" or operations.get("sitemap.xml") != "modify":
        fail("noticias.json e sitemap.xml precisam estar marcados como modify.")

    return manifest, slug, expected_targets


def ensure_clean_checkout() -> None:
    status = git_output("status", "--porcelain=v1", "--untracked-files=all")
    if status:
        fail("Checkout não está limpo antes da simulação:\n" + status)


def remote_ref(ref: str) -> str:
    proc = run_git("ls-remote", "origin", ref, check=False)
    if proc.returncode != 0:
        fail("Não foi possível consultar o repositório remoto: " + proc.stderr.strip())
    line = proc.stdout.strip()
    if not line:
        return ""
    return line.split()[0]


def apply_package(package_dir: Path, targets: list[str]) -> None:
    for target in targets:
        src = package_dir / target
        dst = ROOT / target
        if target.endswith(".html") and dst.exists():
            fail(f"HTML já existe na raiz antes da simulação: {target}")
        shutil.copyfile(src, dst)
        if sha256_file(src) != sha256_file(dst):
            fail(f"Cópia divergente após aplicar pacote: {target}")


def changed_paths_worktree() -> set[str]:
    modified = set(filter(None, git_output("diff", "--name-only").splitlines()))
    untracked = set(
        filter(
            None,
            git_output("ls-files", "--others", "--exclude-standard").splitlines(),
        )
    )
    return modified | untracked


def staged_paths() -> list[str]:
    return list(filter(None, git_output("diff", "--cached", "--name-only").splitlines()))


def simulate_commit(package_dir: Path, report_path: Path) -> dict[str, Any]:
    manifest, slug, targets = validate_package(package_dir)
    expected = set(targets)

    ensure_clean_checkout()
    base_sha = git_output("rev-parse", "HEAD")
    original_branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    remote_main_before = remote_ref("refs/heads/main")
    if not remote_main_before:
        fail("Não foi possível determinar o SHA remoto de main.")
    if base_sha != remote_main_before:
        fail(
            "Checkout não corresponde exatamente à main remota antes da simulação: "
            f"local={base_sha}, remoto={remote_main_before}"
        )
    if remote_ref(f"refs/heads/{SIM_BRANCH}"):
        fail(f"Branch remota inesperada já existe: {SIM_BRANCH}")

    if run_git("show-ref", "--verify", f"refs/heads/{SIM_BRANCH}", check=False).returncode == 0:
        fail(f"Branch local temporária já existe: {SIM_BRANCH}")

    local_commit = ""
    commit_name_status: list[str] = []
    try:
        run_git("switch", "-c", SIM_BRANCH)
        apply_package(package_dir, targets)

        observed = changed_paths_worktree()
        if observed != expected:
            fail(
                "A aplicação do pacote alterou arquivos fora do escopo: "
                f"esperado={sorted(expected)} observado={sorted(observed)}"
            )

        run_git("add", "--", *targets)
        staged = staged_paths()
        if set(staged) != expected or len(staged) != 3:
            fail(f"Stage precisa conter exatamente três arquivos: {staged}")

        # Depois do git add, não pode sobrar nenhuma quarta alteração fora do índice.
        leftover = changed_paths_worktree()
        if leftover:
            fail(f"Há alterações fora do stage: {sorted(leftover)}")

        check = run_git("diff", "--cached", "--check", check=False)
        if check.returncode != 0:
            fail("git diff --cached --check falhou:\n" + check.stdout + check.stderr)

        run_git("config", "user.name", "Corte dos Esportes - Simulação")
        run_git("config", "user.email", "simulacao@cortedosesportes.local")
        run_git(
            "commit",
            "--no-gpg-sign",
            "-m",
            f"SIMULAÇÃO: publicar pré-jogo {slug}",
        )
        local_commit = git_output("rev-parse", "HEAD")
        parent = git_output("rev-parse", "HEAD^")
        if parent != base_sha:
            fail("Commit local de simulação não tem a main de origem como pai direto.")

        commit_name_status = list(
            filter(None, git_output("diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD").splitlines())
        )
        commit_paths = [line.split("\t", 1)[1] for line in commit_name_status if "\t" in line]
        if set(commit_paths) != expected or len(commit_paths) != 3:
            fail(f"Commit local contém escopo incorreto: {commit_name_status}")

        expected_status = {
            slug: "A",
            "noticias.json": "M",
            "sitemap.xml": "M",
        }
        actual_status = {
            line.split("\t", 1)[1]: line.split("\t", 1)[0]
            for line in commit_name_status
            if "\t" in line
        }
        if actual_status != expected_status:
            fail(f"Tipos de alteração inesperados no commit local: {actual_status}")

        for target in targets:
            committed_blob = run_git("show", f"HEAD:{target}").stdout.encode("utf-8")
            package_bytes = (package_dir / target).read_bytes()
            if committed_blob != package_bytes:
                fail(f"Conteúdo do commit local diverge do pacote: {target}")

        remote_main_after = remote_ref("refs/heads/main")
        remote_sim_after = remote_ref(f"refs/heads/{SIM_BRANCH}")
        if remote_main_after != remote_main_before:
            fail("A main remota mudou durante a simulação.")
        if remote_sim_after:
            fail("A branch temporária apareceu no remoto, o que não deveria ocorrer.")

        report = {
            "step": 29,
            "mode": "local_commit_simulation_only",
            "source_step": manifest.get("step"),
            "slug": slug,
            "base_main_sha": base_sha,
            "remote_main_sha_before": remote_main_before,
            "remote_main_sha_after": remote_main_after,
            "local_commit_sha": local_commit,
            "local_branch": SIM_BRANCH,
            "changed_files": targets,
            "changed_file_count": 3,
            "commit_name_status": commit_name_status,
            "remote_push_executed": False,
            "remote_branch_created": False,
            "remote_main_unchanged": True,
            "main_published": False,
            "publication_unlocked": False,
        }
    finally:
        # Volta ao estado original mesmo após falha. Nada desta limpeza é enviado ao remoto.
        run_git("reset", "--hard", base_sha, check=False)
        run_git("clean", "-fd", "--", slug, check=False)
        if original_branch and original_branch != "HEAD":
            run_git("switch", original_branch, check=False)
        else:
            run_git("switch", "--detach", base_sha, check=False)
        run_git("branch", "-D", SIM_BRANCH, check=False)

    final_status = git_output("status", "--porcelain=v1", "--untracked-files=all")
    if final_status:
        fail("Checkout não voltou limpo após a simulação:\n" + final_status)
    if git_output("rev-parse", "HEAD") != base_sha:
        fail("Checkout não voltou ao mesmo commit-base após a simulação.")

    report["temporary_local_branch_removed"] = True
    report["checkout_restored_clean"] = True
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simula o commit de publicação sem push.")
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    package_dir = args.package_dir.resolve()
    report_path = args.report.resolve()
    allowed_build = (ROOT / "build" / "pre-jogo").resolve()
    try:
        package_dir.relative_to(allowed_build)
        report_path.relative_to(allowed_build)
    except ValueError:
        fail("Passo 29 só aceita pacote e relatório dentro de build/pre-jogo/.")

    report = simulate_commit(package_dir, report_path)
    print("OK: commit local do Passo 29 simulado e descartado sem push.")
    print(f"Commit local temporário: {report['local_commit_sha']}")
    print("Arquivos no commit: 3")
    for item in report["commit_name_status"]:
        print(f"  {item}")
    print("main remota alterada: não")
    print("branch remota criada: não")
    print("checkout restaurado: sim")
    print("publicação liberada: não")


if __name__ == "__main__":
    main()
