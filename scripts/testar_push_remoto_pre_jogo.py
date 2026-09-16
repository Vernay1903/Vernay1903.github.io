#!/usr/bin/env python3
"""Testa o futuro push de publicação em uma branch remota temporária.

Este passo NÃO publica na main. Ele:
- valida o pacote aprovado do Passo 28;
- cria uma branch local temporária a partir da main atual;
- aplica exatamente HTML + noticias.json + sitemap.xml;
- cria um único commit local com exatamente esses três arquivos;
- faz push EXPLÍCITO somente para a branch remota de teste informada;
- confirma que a main remota não mudou;
- restaura o checkout local.

A exclusão da branch remota é responsabilidade do workflow do Passo 30, em
uma etapa `if: always()`, para que a limpeza também seja tentada após falhas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = ROOT / "build" / "pre-jogo" / "source-step28"
DEFAULT_REPORT = ROOT / "build" / "pre-jogo" / "remote-push-test" / "report.json"
BRANCH_RE = re.compile(r"^pre-jogo-teste-remoto-[0-9]+-[0-9]+$")


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
    return run_git(*args).stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_test_branch_name(branch: str) -> None:
    if not BRANCH_RE.fullmatch(branch):
        fail(
            "Branch remota de teste inválida. Esperado "
            "pre-jogo-teste-remoto-<run_id>-<attempt>."
        )
    if branch == "main" or branch.startswith("refs/"):
        fail("Branch de teste não pode apontar para main nem receber ref completa.")


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
        fail("O pacote do Passo 28 já indica arquivo publicado; recusado.")
    if manifest.get("commit_executed") is not False:
        fail("O pacote do Passo 28 já indica commit executado; recusado.")
    if manifest.get("publication_unlocked") is not False:
        fail("O pacote do Passo 28 liberou publicação indevidamente.")

    slug = manifest.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html") or "/" in slug or "\\" in slug:
        fail("Slug inválido no manifest do Passo 28.")

    targets = [slug, "noticias.json", "sitemap.xml"]
    prepared = manifest.get("prepared_changes")
    if not isinstance(prepared, list) or len(prepared) != 3:
        fail("prepared_changes precisa ter exatamente três itens.")
    prepared_targets = [item.get("target") for item in prepared if isinstance(item, dict)]
    if prepared_targets != targets:
        fail(f"Escopo/ordem do pacote inválidos: {prepared_targets}")

    actual_files = sorted(path.name for path in package_dir.iterdir() if path.is_file())
    expected_files = sorted([*targets, "manifest.json"])
    if actual_files != expected_files:
        fail(f"Pacote contém arquivos inesperados: {actual_files}")

    expected_operations = {
        slug: "create",
        "noticias.json": "modify",
        "sitemap.xml": "modify",
    }
    for item in prepared:
        target = item["target"]
        source = package_dir / target
        if not source.is_file():
            fail(f"Arquivo preparado ausente: {target}")
        if item.get("operation") != expected_operations[target]:
            fail(f"Operação inesperada para {target}: {item.get('operation')}")
        expected_sha = item.get("sha256")
        if not isinstance(expected_sha, str) or sha256_file(source) != expected_sha:
            fail(f"SHA-256 divergente no pacote: {target}")

    return manifest, slug, targets


def ensure_clean_checkout() -> None:
    status = git_output("status", "--porcelain=v1", "--untracked-files=all")
    if status:
        fail("Checkout não está limpo antes do teste remoto:\n" + status)


def remote_ref(ref: str) -> str:
    proc = run_git("ls-remote", "origin", ref, check=False)
    if proc.returncode != 0:
        fail("Não foi possível consultar o repositório remoto: " + proc.stderr.strip())
    line = proc.stdout.strip()
    return line.split()[0] if line else ""


def apply_package(package_dir: Path, targets: list[str]) -> None:
    for target in targets:
        src = package_dir / target
        dst = ROOT / target
        if target.endswith(".html") and dst.exists():
            fail(f"HTML já existe na raiz antes do teste: {target}")
        shutil.copyfile(src, dst)
        if sha256_file(src) != sha256_file(dst):
            fail(f"Cópia divergente após aplicar pacote: {target}")


def changed_paths_worktree() -> set[str]:
    modified = set(filter(None, git_output("diff", "--name-only").splitlines()))
    untracked = set(
        filter(None, git_output("ls-files", "--others", "--exclude-standard").splitlines())
    )
    return modified | untracked


def staged_paths() -> list[str]:
    return list(filter(None, git_output("diff", "--cached", "--name-only").splitlines()))


def prepare_and_push(package_dir: Path, branch: str, report_path: Path) -> dict[str, Any]:
    validate_test_branch_name(branch)
    manifest, slug, targets = validate_package(package_dir)
    expected = set(targets)

    ensure_clean_checkout()
    base_sha = git_output("rev-parse", "HEAD")
    original_branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
    if original_branch != "main":
        fail(f"Passo 30 precisa iniciar na branch main; atual={original_branch}")

    remote_main_before = remote_ref("refs/heads/main")
    if not remote_main_before:
        fail("Não foi possível determinar a main remota.")
    if base_sha != remote_main_before:
        fail(
            "Checkout não corresponde exatamente à main remota antes do push: "
            f"local={base_sha}, remoto={remote_main_before}"
        )
    if remote_ref(f"refs/heads/{branch}"):
        fail(f"Branch remota de teste já existe: {branch}")
    if run_git("show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0:
        fail(f"Branch local de teste já existe: {branch}")

    local_commit = ""
    commit_name_status: list[str] = []
    push_stdout = ""
    try:
        run_git("switch", "-c", branch)
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
        if changed_paths_worktree():
            fail("Há alterações fora do stage após preparar os três arquivos.")

        check = run_git("diff", "--cached", "--check", check=False)
        if check.returncode != 0:
            fail("git diff --cached --check falhou:\n" + check.stdout + check.stderr)

        run_git("config", "user.name", "Corte dos Esportes - Teste Remoto")
        run_git("config", "user.email", "teste-remoto@cortedosesportes.local")
        run_git(
            "commit",
            "--no-gpg-sign",
            "-m",
            f"TESTE REMOTO: pré-jogo {slug}",
        )
        local_commit = git_output("rev-parse", "HEAD")
        if git_output("rev-parse", "HEAD^") != base_sha:
            fail("Commit de teste não tem a main como pai direto.")

        commit_name_status = list(
            filter(None, git_output("diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD").splitlines())
        )
        actual_status = {
            line.split("\t", 1)[1]: line.split("\t", 1)[0]
            for line in commit_name_status
            if "\t" in line
        }
        expected_status = {slug: "A", "noticias.json": "M", "sitemap.xml": "M"}
        if actual_status != expected_status:
            fail(f"Tipos de alteração inesperados: {actual_status}")

        for target in targets:
            committed = run_git("show", f"HEAD:{target}").stdout.encode("utf-8")
            if committed != (package_dir / target).read_bytes():
                fail(f"Conteúdo do commit diverge do pacote: {target}")

        # ÚNICO push permitido neste script: HEAD -> branch remota temporária explícita.
        push = run_git("push", "--porcelain", "origin", f"HEAD:refs/heads/{branch}", check=False)
        push_stdout = (push.stdout + push.stderr).strip()
        if push.returncode != 0:
            fail("Push da branch temporária falhou:\n" + push_stdout)

        remote_branch_sha = remote_ref(f"refs/heads/{branch}")
        if remote_branch_sha != local_commit:
            fail(
                "SHA da branch remota temporária diverge do commit local: "
                f"local={local_commit}, remoto={remote_branch_sha}"
            )
        remote_main_after_push = remote_ref("refs/heads/main")
        if remote_main_after_push != remote_main_before:
            fail("A main remota mudou durante o push da branch temporária.")

        report = {
            "step": 30,
            "mode": "remote_temporary_branch_test",
            "source_step": manifest.get("step"),
            "slug": slug,
            "base_main_sha": base_sha,
            "remote_main_sha_before": remote_main_before,
            "remote_main_sha_after_push": remote_main_after_push,
            "temporary_remote_branch": branch,
            "remote_test_commit_sha": remote_branch_sha,
            "local_commit_sha": local_commit,
            "changed_files": targets,
            "changed_file_count": 3,
            "commit_name_status": commit_name_status,
            "push_destination": f"refs/heads/{branch}",
            "push_executed": True,
            "main_push_executed": False,
            "remote_main_unchanged_after_push": True,
            "remote_branch_created": True,
            "remote_branch_deletion_pending": True,
            "main_published": False,
            "publication_unlocked": False,
            "push_result_recorded": bool(push_stdout),
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        # O remoto NÃO é apagado aqui: o workflow faz isso em `if: always()`.
        run_git("reset", "--hard", base_sha, check=False)
        run_git("clean", "-fd", "--", slug, check=False)
        run_git("switch", "main", check=False)
        run_git("branch", "-D", branch, check=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Testa push para branch remota temporária.")
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--branch", required=True)
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
        fail("Passo 30 só aceita pacote e relatório dentro de build/pre-jogo/.")

    report = prepare_and_push(package_dir, args.branch, report_path)
    print("OK: commit enviado somente para branch remota temporária.")
    print(f"Branch remota temporária: {report['temporary_remote_branch']}")
    print(f"Commit remoto de teste: {report['remote_test_commit_sha']}")
    print("Arquivos enviados: 3")
    print("Push para main: não")
    print("Main remota alterada: não")
    print("Publicação na main: não")
    print("Exclusão da branch temporária: pendente para etapa de limpeza do workflow")


if __name__ == "__main__":
    main()
