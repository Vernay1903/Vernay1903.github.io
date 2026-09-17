#!/usr/bin/env python3
"""Aplica em lote matérias automáticas aprovadas na main local, sem executar push.

O script só aceita artigos preparados no Passo 34 e listados como aprovados pela
checagem oficial final. Ele recompõe noticias.json e sitemap.xml contra o estado
ATUAL do repositório, permitindo publicar mais de uma matéria no mesmo commit sem
usar cópias antigas desses arquivos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "pre-jogo"
NOTICIAS = ROOT / "noticias.json"
SITEMAP = ROOT / "sitemap.xml"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import preparar_pacote_publicacao_pre_jogo as package_builder  # noqa: E402
from scripts import planejar_pre_jogos as planner  # noqa: E402


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


def approved_slugs(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def validate_artifact_files(root: Path, article: dict[str, Any]) -> tuple[Path, Path, Path]:
    required = {
        "contract": article.get("contract"),
        "draft": article.get("draft"),
        "status_snapshot": article.get("status_snapshot"),
    }
    hashes = article.get("sha256")
    if not isinstance(hashes, dict):
        fail(f"Manifesto sem hashes para {article.get('slug')}")

    paths: dict[str, Path] = {}
    for key, relative in required.items():
        if not isinstance(relative, str) or not relative:
            fail(f"Caminho {key} inválido para {article.get('slug')}")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            fail(f"Caminho fora do artifact: {relative}")
        if not path.is_file():
            fail(f"Arquivo ausente no artifact: {relative}")
        expected = hashes.get(key)
        if not isinstance(expected, str) or sha256_file(path) != expected:
            fail(f"SHA-256 inválido no artifact para {article.get('slug')} ({key})")
        paths[key] = path
    return paths["contract"], paths["draft"], paths["status_snapshot"]


def parse_br_date(raw: str) -> date:
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        fail(f"Data editorial inválida: {raw}")


def parse_kickoff(raw: Any) -> time:
    if not isinstance(raw, str):
        fail("Horário de início ausente no manifesto automático.")
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        fail(f"Horário inválido: {raw}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aplica lote automático aprovado sem executar git push.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--approved", required=True, type=Path, help="Arquivo com um slug aprovado por linha.")
    parser.add_argument("--previews-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_json(args.manifest)
    if not isinstance(manifest, dict) or manifest.get("step") != 34:
        fail("Manifesto automático inválido.")
    if manifest.get("timezone") != "America/Sao_Paulo":
        fail("Timezone do manifesto automático inválido.")

    target_raw = manifest.get("target_date")
    if not isinstance(target_raw, str):
        fail("Manifesto sem target_date.")
    try:
        target_date = datetime.strptime(target_raw, "%Y-%m-%d").date()
    except ValueError:
        fail("target_date inválida no manifesto.")

    artifact_root = args.artifact_root.resolve()
    previews_root = args.previews_root.resolve()
    allowed = approved_slugs(args.approved)
    config = load_json(ROOT / "config" / "pre-jogo.json")
    if not isinstance(config, dict):
        fail("config/pre-jogo.json inválido.")

    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    if not args.dry_run and now.date() != target_date:
        fail(f"Publicação automática só pode ocorrer na data-alvo {target_date.isoformat()}.")
    if not args.dry_run and now.time() < time(0, 1):
        fail("Publicação automática bloqueada antes de 00:01 de Brasília.")

    noticias_original = NOTICIAS.read_text(encoding="utf-8")
    sitemap_original = SITEMAP.read_text(encoding="utf-8")
    try:
        noticias_items = json.loads(noticias_original)
    except json.JSONDecodeError as exc:
        fail(f"noticias.json inválido antes da publicação: {exc}")
    if not isinstance(noticias_items, list):
        fail("noticias.json precisa ser um array.")

    prepared_articles = [item for item in manifest.get("articles", []) if isinstance(item, dict)]
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for article in prepared_articles:
        slug = article.get("slug")
        if not isinstance(slug, str) or not slug.endswith(".html"):
            skipped.append({"slug": slug, "reason": "invalid_slug"})
            continue
        if slug not in allowed:
            skipped.append({"slug": slug, "reason": "final_status_not_approved"})
            continue

        contract_path, _draft_path, _status_path = validate_artifact_files(artifact_root, article)
        contract = load_json(contract_path)
        if not isinstance(contract, dict) or contract.get("slug") != slug:
            skipped.append({"slug": slug, "reason": "contract_mismatch"})
            continue

        date_br = contract.get("date")
        if not isinstance(date_br, str) or parse_br_date(date_br) != target_date:
            skipped.append({"slug": slug, "reason": "article_date_mismatch"})
            continue

        kickoff = parse_kickoff(article.get("kickoff_time_brasilia"))
        if not args.dry_run and now.time() >= kickoff:
            skipped.append({"slug": slug, "reason": "kickoff_already_reached"})
            continue

        target_html = ROOT / slug
        if target_html.exists():
            skipped.append({"slug": slug, "reason": "html_already_exists"})
            continue
        if any(isinstance(item, dict) and item.get("url") == slug for item in noticias_items):
            skipped.append({"slug": slug, "reason": "url_already_in_noticias"})
            continue

        match = {
            "home": article.get("home"),
            "away": article.get("away"),
        }
        if planner.news_same_match(
            {"date": date_br, "category": "Futebol", "title": str(article.get("title", "")), "url": slug},
            match=match,
            target_date=target_date,
            config=config,
        ):
            # A chamada acima valida o formato do próprio registro; a checagem real é abaixo.
            existing_same_match = any(
                planner.news_same_match(
                    item,
                    match=match,
                    target_date=target_date,
                    config=config,
                )
                for item in noticias_items
                if isinstance(item, dict)
            )
            if existing_same_match:
                skipped.append({"slug": slug, "reason": "same_match_already_in_noticias"})
                continue

        preview = previews_root / "previews" / slug
        if not preview.is_file():
            skipped.append({"slug": slug, "reason": "preview_missing"})
            continue
        preview_text = preview.read_text(encoding="utf-8")
        if "{{" in preview_text or "}}" in preview_text:
            skipped.append({"slug": slug, "reason": "preview_has_unresolved_placeholder"})
            continue
        if preview_text.count('data-ad-slot="8702501261"') != 3:
            skipped.append({"slug": slug, "reason": "preview_ad_count_invalid"})
            continue

        selected.append({**article, "contract_data": contract, "preview_path": preview})

    selected.sort(key=lambda item: (str(item.get("kickoff_time_brasilia", "")), str(item.get("slug", ""))))

    noticias_new = noticias_original
    sitemap_new = sitemap_original
    # Cada função insere no topo; iteramos ao contrário para preservar a ordem cronológica no resultado final.
    for article in reversed(selected):
        contract = article["contract_data"]
        noticias_new = package_builder.build_noticias_copy(
            noticias_new,
            title=str(contract["title"]),
            excerpt=str(contract["excerpt"]),
            slug=str(contract["slug"]),
            date_br=str(contract["date"]),
        )
        sitemap_new = package_builder.build_sitemap_copy(
            sitemap_new,
            slug=str(contract["slug"]),
            lastmod=package_builder.date_to_iso(str(contract["date"])),
        )

    changed_files: list[str] = []
    if selected:
        changed_files = [str(item["slug"]) for item in selected] + ["noticias.json", "sitemap.xml"]
        if not args.dry_run:
            for article in selected:
                (ROOT / str(article["slug"])).write_text(
                    Path(article["preview_path"]).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            NOTICIAS.write_text(noticias_new, encoding="utf-8")
            SITEMAP.write_text(sitemap_new, encoding="utf-8")

    report = {
        "step": 34,
        "mode": "dry_run" if args.dry_run else "apply_local_before_git_push",
        "generated_at": now.isoformat(),
        "target_date": target_raw,
        "approved_slug_count": len(allowed),
        "selected_count": len(selected),
        "skipped_count": len(skipped),
        "selected_slugs": [item["slug"] for item in selected],
        "skipped": skipped,
        "changed_file_count": len(changed_files),
        "changed_files": changed_files,
        "noticias_and_sitemap_built_from_current_main": True,
        "commit_created": False,
        "push_executed": False,
        "dry_run": bool(args.dry_run),
    }
    report_path = args.report.resolve()
    try:
        report_path.relative_to(BUILD.resolve())
    except ValueError:
        fail("Relatório do lote deve ficar dentro de build/pre-jogo/.")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("PASSO 34 — LOTE DE PUBLICAÇÃO AVALIADO")
    print(f"Data-alvo: {target_raw}")
    print(f"Matérias selecionadas: {len(selected)}")
    print(f"Matérias puladas: {len(skipped)}")
    print(f"Arquivos {'que seriam alterados' if args.dry_run else 'alterados localmente'}: {len(changed_files)}")
    for article in selected:
        print(f"- PUBLICÁVEL | {article.get('kickoff_time_brasilia')} | {article.get('home')} x {article.get('away')} | {article.get('slug')}")
    for item in skipped:
        print(f"- PULADA | {item.get('slug')} | {item.get('reason')}")
    print("Commit criado: não")
    print("Push executado: não")


if __name__ == "__main__":
    main()
