#!/usr/bin/env python3
"""Prepara, em lote, contratos/rascunhos para publicação automática de pré-jogos.

Este script NÃO publica nada. Ele recebe os pacotes editoriais limpos do Passo 24,
chama os Passos 25 e 26 apenas para os artigos integralmente resolvidos, cria um
snapshot interno mínimo para a checagem oficial final e grava um artifact compacto
que poderá ser usado pela execução das 00:01.

Passo 34.3: quando a extração determinística não resolve todos os requisitos,
este orquestrador pode executar o fallback factual OpenAI estritamente aterrado
em páginas já checadas e depois reconstruir o pacote editorial limpo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_BUILD = ROOT / "build" / "pre-jogo"
DEFAULT_OUTPUT = DEFAULT_BUILD / "automatico"


def fail(message: str) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"Arquivo não encontrado: {path}")
    except json.JSONDecodeError as exc:
        fail(f"JSON inválido em {path}: {exc}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_output_dir(path: Path) -> Path:
    resolved = path.resolve()
    allowed = DEFAULT_BUILD.resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError:
        fail("A preparação automática só pode gravar dentro de build/pre-jogo/.")
    return resolved


def normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def domain_matches(host: str, domain: str) -> bool:
    allowed = domain.strip().lower().rstrip(".")
    if allowed.startswith("www."):
        allowed = allowed[4:]
    return host == allowed or host.endswith("." + allowed)


def official_source_rows(article: dict[str, Any], config: dict[str, Any]) -> list[dict[str, str]]:
    context = article.get("match_context") if isinstance(article.get("match_context"), dict) else {}
    competition_slug = context.get("competition_slug")
    official = config.get("research", {}).get("discovery", {}).get("official_domains", {})
    competition_domains = official.get("competitions", {}) if isinstance(official, dict) else {}
    comp_domains = []
    if isinstance(competition_slug, str) and isinstance(competition_domains, dict):
        raw = competition_domains.get(competition_slug, [])
        if isinstance(raw, list):
            comp_domains = [str(item) for item in raw]

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    requirements = article.get("requirements", [])
    if not isinstance(requirements, list):
        requirements = []

    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        containers = []
        for key in ("sources", "source_candidates"):
            value = requirement.get(key, [])
            if isinstance(value, list):
                containers.extend(value)
        for source in containers:
            if not isinstance(source, dict):
                continue
            source_type = source.get("source_type")
            url = source.get("url")
            if source_type != "official" or not isinstance(url, str) or not url.startswith("https://"):
                continue
            if source.get("content_checked") is False:
                continue
            if url in seen:
                continue
            seen.add(url)
            host = normalize_host(url)
            kind = "official_competition" if any(domain_matches(host, d) for d in comp_domains) else "official_club"
            rows.append({"source_type": kind, "url": url})
    return rows


def stadium_from_article(article: dict[str, Any]) -> str | None:
    requirements = article.get("requirements", [])
    if not isinstance(requirements, list):
        return None
    for requirement in requirements:
        if not isinstance(requirement, dict) or requirement.get("id") != "stadium_and_location":
            continue
        for fact in requirement.get("facts", []):
            if not isinstance(fact, dict):
                continue
            text = fact.get("text")
            field = fact.get("field")
            if not isinstance(text, str) or not text.strip():
                continue
            if field == "stadium":
                value = text.strip().rstrip(".")
                for prefix in ("Estádio:", "Estadio:", "Stadium:", "Local:"):
                    if value.casefold().startswith(prefix.casefold()):
                        value = value[len(prefix):].strip()
                return value or None
    return None


def status_snapshot(article: dict[str, Any], package: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    rows = official_source_rows(article, config)
    if not rows:
        return None
    context = package.get("match_context") if isinstance(package.get("match_context"), dict) else {}
    home = context.get("home")
    away = context.get("away")
    date_br = package.get("date")
    kickoff = context.get("kickoff_time_brasilia")
    if not all(isinstance(value, str) and value.strip() for value in (home, away, date_br)):
        return None
    return {
        "article_source_policy": {
            "internal_only": True,
            "send_sources_to_model": False,
            "show_sources_in_article": False,
            "show_research_process_in_article": False,
        },
        "match": {
            "home": home,
            "away": away,
            "competition": context.get("competition"),
            "date": date_br,
            "kickoff_brasilia": kickoff,
            "stadium": stadium_from_article(article),
        },
        "evidence": rows,
    }


def run_command(args: list[str]) -> tuple[bool, str]:
    process = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
        check=False,
    )
    output = process.stdout or ""
    if output:
        print(output.rstrip())
    return process.returncode == 0, output


def package_manifest_needs_fallback(path: Path) -> bool:
    data = load_json(path)
    if not isinstance(data, dict):
        return False
    for article in data.get("articles", []):
        if isinstance(article, dict) and article.get("ready_for_drafting") is not True:
            return True
    return False


def run_grounded_fact_fallback(args: argparse.Namespace) -> tuple[bool, bool]:
    """Tenta o Passo 34.3 sem transformar falha do provedor em publicação insegura."""
    if not package_manifest_needs_fallback(args.packages):
        return False, True

    checked = DEFAULT_BUILD / f"paginas-checadas-{args.date}.json"
    if not checked.exists():
        print("AVISO: Passo 34.3 não executado porque o manifesto de páginas checadas não existe.")
        return True, False

    print("PASSO 34.3 — tentando resolver somente lacunas factuais com grounding extrativo.")
    ok, _ = run_command([
        sys.executable,
        "scripts/extrair_fatos_openai.py",
        "--date", args.date,
        "--checked", str(checked),
        "--facts", str(args.facts),
        "--output-dir", str(DEFAULT_BUILD),
        "--execute",
        "--force",
    ])
    if not ok:
        print("AVISO: fallback factual OpenAI falhou; matéria continuará bloqueada em vez de forçar dados.")
        return True, False

    ok, _ = run_command([
        sys.executable,
        "scripts/montar_pacote_editorial.py",
        "--date", args.date,
        "--facts", str(args.facts),
        "--output-dir", str(DEFAULT_BUILD),
        "--force",
    ])
    if not ok:
        print("AVISO: fatos aterrrados foram gerados, mas o pacote editorial não pôde ser reconstruído; publicação continua bloqueada.")
        return True, False

    print("OK: Passo 34.3 concluiu fallback factual e reconstruiu o pacote editorial limpo.")
    return True, True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepara lote automático de pré-jogos sem publicar.")
    parser.add_argument("--date", required=True, help="Data-alvo YYYY-MM-DD.")
    parser.add_argument("--packages", required=True, type=Path, help="Manifesto pacotes-editoriais-AAAA-MM-DD.json.")
    parser.add_argument("--facts", required=True, type=Path, help="Manifesto fatos-estruturados-AAAA-MM-DD.json.")
    parser.add_argument("--source-main-sha", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--execute", action="store_true", help="Autoriza chamadas reais à OpenAI no Passo 26.")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.execute:
        fail("Preparação automática externa bloqueada. Use --execute explicitamente.")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        fail("OPENAI_API_KEY não configurada.")

    config = load_json(CONFIG_PATH)
    if not isinstance(config, dict) or config.get("timezone") != "America/Sao_Paulo":
        fail("config/pre-jogo.json inválido.")

    fallback_attempted, fallback_succeeded = run_grounded_fact_fallback(args)

    packages_manifest = load_json(args.packages)
    facts_manifest = load_json(args.facts)
    if not isinstance(packages_manifest, dict) or packages_manifest.get("target_date") != args.date:
        fail("Manifesto de pacotes editoriais não corresponde à data-alvo.")
    if not isinstance(facts_manifest, dict) or facts_manifest.get("target_date") != args.date:
        fail("Manifesto de fatos não corresponde à data-alvo.")

    output_dir = safe_output_dir(args.output_dir)
    if output_dir.exists() and args.force:
        shutil.rmtree(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        fail(f"Diretório automático já contém arquivos: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "contracts").mkdir()
    (output_dir / "drafts").mkdir()
    (output_dir / "status").mkdir()

    fact_by_slug = {
        item.get("slug"): item
        for item in facts_manifest.get("articles", [])
        if isinstance(item, dict) and isinstance(item.get("slug"), str)
    }
    packages = [item for item in packages_manifest.get("articles", []) if isinstance(item, dict)]
    packages.sort(key=lambda item: str(item.get("match_context", {}).get("kickoff_brasilia", "")))

    prepared: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for package in packages:
        slug = package.get("slug")
        if not isinstance(slug, str) or not slug.endswith(".html"):
            skipped.append({"slug": slug, "reason": "invalid_slug"})
            continue
        if package.get("ready_for_drafting") is not True:
            skipped.append({
                "slug": slug,
                "reason": "research_incomplete",
                "unresolved": package.get("unresolved_required_requirement_ids", []),
            })
            continue

        fact_article = fact_by_slug.get(slug)
        if not isinstance(fact_article, dict):
            skipped.append({"slug": slug, "reason": "facts_missing"})
            continue

        snapshot = status_snapshot(fact_article, package, config)
        if snapshot is None:
            skipped.append({"slug": slug, "reason": "no_official_source_for_final_status"})
            continue

        package_file = DEFAULT_BUILD / f"pacotes-editoriais-{args.date}" / Path(slug).with_suffix(".json").name
        if not package_file.exists():
            skipped.append({"slug": slug, "reason": "clean_package_file_missing"})
            continue

        ok, _ = run_command([
            sys.executable,
            "scripts/preparar_redacao_pre_jogo.py",
            "--package", str(package_file),
            "--output-dir", str(DEFAULT_BUILD),
            "--force",
        ])
        if not ok:
            skipped.append({"slug": slug, "reason": "contract_generation_failed"})
            continue

        basename = Path(slug).with_suffix(".json").name
        contract_src = DEFAULT_BUILD / "contratos-redacao" / basename
        if not contract_src.exists():
            skipped.append({"slug": slug, "reason": "contract_missing_after_generation"})
            continue

        ok, _ = run_command([
            sys.executable,
            "scripts/redigir_pre_jogo_openai.py",
            "--contract", str(contract_src),
            "--execute",
            "--output-dir", str(DEFAULT_BUILD),
            "--force",
        ])
        if not ok:
            skipped.append({"slug": slug, "reason": "draft_generation_or_validation_failed"})
            continue

        draft_src = DEFAULT_BUILD / "rascunhos-modelo" / basename
        if not draft_src.exists():
            skipped.append({"slug": slug, "reason": "draft_missing_after_generation"})
            continue

        contract_dest = output_dir / "contracts" / basename
        draft_dest = output_dir / "drafts" / basename
        status_dest = output_dir / "status" / basename
        shutil.copy2(contract_src, contract_dest)
        shutil.copy2(draft_src, draft_dest)
        status_dest.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        contract = load_json(contract_dest)
        draft = load_json(draft_dest)
        if not isinstance(contract, dict) or not isinstance(draft, dict):
            skipped.append({"slug": slug, "reason": "prepared_json_invalid"})
            for path in (contract_dest, draft_dest, status_dest):
                path.unlink(missing_ok=True)
            continue
        if draft.get("draft_validated") is not True or int(draft.get("word_count", 0)) < int(config["article"]["min_words"]):
            skipped.append({"slug": slug, "reason": "draft_not_validated"})
            for path in (contract_dest, draft_dest, status_dest):
                path.unlink(missing_ok=True)
            continue

        context = contract.get("match_context") if isinstance(contract.get("match_context"), dict) else {}
        prepared.append({
            "slug": slug,
            "title": contract.get("title"),
            "excerpt": contract.get("excerpt"),
            "date": contract.get("date"),
            "kickoff_time_brasilia": context.get("kickoff_time_brasilia"),
            "home": context.get("home"),
            "away": context.get("away"),
            "competition": context.get("competition"),
            "competition_slug": context.get("competition_slug"),
            "contract": f"contracts/{basename}",
            "draft": f"drafts/{basename}",
            "status_snapshot": f"status/{basename}",
            "sha256": {
                "contract": sha256_file(contract_dest),
                "draft": sha256_file(draft_dest),
                "status_snapshot": sha256_file(status_dest),
            },
        })

    manifest = {
        "step": 34,
        "mode": "automatic_preparation",
        "generated_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
        "target_date": args.date,
        "timezone": "America/Sao_Paulo",
        "source_main_sha": args.source_main_sha,
        "monitored_club_count": len(config.get("monitored_clubs", [])),
        "prepared_count": len(prepared),
        "skipped_count": len(skipped),
        "articles": prepared,
        "skipped": skipped,
        "grounded_fact_fallback_attempted": fallback_attempted,
        "grounded_fact_fallback_succeeded": fallback_succeeded,
        "publication_unlocked": False,
        "requires_final_official_status_check": True,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("PASSO 34 — PREPARAÇÃO AUTOMÁTICA CONCLUÍDA")
    print(f"Data-alvo: {args.date}")
    print(f"Fallback factual aterrado: {'executado' if fallback_attempted else 'não necessário'} | sucesso={fallback_succeeded}")
    print(f"Matérias prontas para a janela das 00:01: {len(prepared)}")
    print(f"Matérias bloqueadas/puladas por segurança: {len(skipped)}")
    for item in prepared:
        print(f"- PRONTA | {item['kickoff_time_brasilia']} | {item['home']} x {item['away']} | {item['slug']}")
    for item in skipped:
        print(f"- BLOQUEADA | {item.get('slug')} | {item.get('reason')}")
    print("Nenhum HTML da raiz, noticias.json ou sitemap.xml foi alterado.")


if __name__ == "__main__":
    main()
