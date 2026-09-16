#!/usr/bin/env python3
"""Cria um plano de matérias de pré-jogo sem publicar nenhum arquivo do site."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
NOTICIAS_PATH = ROOT / "noticias.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

COMMON_TEAM_TOKENS = {
    "afc",
    "cf",
    "cr",
    "ec",
    "fc",
    "sc",
    "se",
    "club",
    "clube",
}


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


def load_config() -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    if not isinstance(config, dict):
        fail("config/pre-jogo.json deve conter um objeto JSON.")
    if config.get("timezone") != "America/Sao_Paulo":
        fail('O timezone deve permanecer "America/Sao_Paulo".')

    publication = config.get("publication")
    if not isinstance(publication, dict):
        fail('Configuração "publication" ausente ou inválida.')
    if publication.get("prepare_time") != "23:30":
        fail('publication.prepare_time deve permanecer "23:30".')
    if publication.get("target_publish_time") != "00:01":
        fail('publication.target_publish_time deve permanecer "00:01".')

    slug_config = config.get("slug")
    if not isinstance(slug_config, dict):
        fail('Configuração "slug" ausente ou inválida.')
    suffix = slug_config.get("suffix")
    if not isinstance(suffix, str) or not suffix:
        fail('Configuração "slug.suffix" ausente ou inválida.')

    monitored = config.get("monitored_clubs")
    if not isinstance(monitored, list) or len(monitored) != 10:
        fail("A configuração deve conter exatamente os 10 clubes monitorados.")
    return config


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def slugify(value: str) -> str:
    return normalize_text(value).replace(" ", "-")


def club_alias_index(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for club in config["monitored_clubs"]:
        if not isinstance(club, dict):
            fail("Há um clube inválido em monitored_clubs.")
        name = club.get("name")
        slug = club.get("slug")
        aliases = club.get("aliases", [])
        if not isinstance(name, str) or not name.strip():
            fail("Todo clube monitorado precisa de name.")
        if not isinstance(slug, str) or not slug.strip():
            fail(f"Clube sem slug válido: {name}")
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            fail(f"Aliases inválidos para {name}.")

        entry = {
            "name": name.strip(),
            "slug": slug.strip(),
            "aliases": [name.strip(), *aliases],
        }
        for candidate in [name, slug.replace("-", " "), *aliases]:
            key = normalize_text(candidate)
            if key:
                index[key] = entry
    return index


def canonical_team(name: str, config: dict[str, Any]) -> dict[str, Any]:
    index = club_alias_index(config)
    matched = index.get(normalize_text(name))
    if matched:
        return matched
    return {
        "name": name.strip(),
        "slug": slugify(name),
        "aliases": [name.strip()],
    }


def team_search_variants(name: str, config: dict[str, Any]) -> set[str]:
    team = canonical_team(name, config)
    variants: set[str] = set()
    for raw in team["aliases"]:
        normalized = normalize_text(raw)
        if normalized:
            variants.add(normalized)
            tokens = normalized.split()
            trimmed = [token for token in tokens if token not in COMMON_TEAM_TOKENS]
            if trimmed:
                variants.add(" ".join(trimmed))
    source = normalize_text(name)
    if source:
        variants.add(source)
        tokens = source.split()
        trimmed = [token for token in tokens if token not in COMMON_TEAM_TOKENS]
        if trimmed:
            variants.add(" ".join(trimmed))
    return {value for value in variants if len(value) >= 3}


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_selected_matches(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O relatório de jogos deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do relatório de jogos não coincide com a data-alvo.")
    matches = data.get("matches")
    if not isinstance(matches, list):
        fail('O relatório de jogos deve conter um array "matches".')
    for idx, match in enumerate(matches):
        if not isinstance(match, dict):
            fail(f"Jogo selecionado na posição {idx} não é um objeto JSON.")
    return matches


def load_noticias(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list):
        fail("noticias.json deve ser um array.")
    return [item for item in data if isinstance(item, dict)]


def build_slug(match: dict[str, Any], target_date: date, config: dict[str, Any]) -> str:
    home = match.get("home")
    away = match.get("away")
    competition_slug = match.get("competition_slug")
    if not isinstance(home, str) or not home.strip():
        fail("Jogo selecionado sem mandante válido.")
    if not isinstance(away, str) or not away.strip():
        fail("Jogo selecionado sem visitante válido.")
    if not isinstance(competition_slug, str) or not competition_slug.strip():
        fail("Jogo selecionado sem competition_slug válido.")

    home_slug = canonical_team(home, config)["slug"]
    away_slug = canonical_team(away, config)["slug"]
    competition_part = slugify(competition_slug)
    suffix = config["slug"]["suffix"]
    return f"{home_slug}-{away_slug}-{competition_part}-{target_date.year}-{suffix}"


def news_same_match(
    item: dict[str, Any],
    *,
    match: dict[str, Any],
    target_date: date,
    config: dict[str, Any],
) -> bool:
    expected_date = target_date.strftime("%d/%m/%Y")
    if item.get("date") != expected_date:
        return False
    if item.get("category") != "Futebol":
        return False

    title = item.get("title") if isinstance(item.get("title"), str) else ""
    url = item.get("url") if isinstance(item.get("url"), str) else ""
    haystack = normalize_text(f"{title} {url}")
    if not haystack:
        return False

    home = match.get("home")
    away = match.get("away")
    if not isinstance(home, str) or not isinstance(away, str):
        return False

    home_found = any(variant in haystack for variant in team_search_variants(home, config))
    away_found = any(variant in haystack for variant in team_search_variants(away, config))
    return home_found and away_found


def duplicate_reasons(
    *,
    slug: str,
    match: dict[str, Any],
    target_date: date,
    config: dict[str, Any],
    noticias: list[dict[str, Any]],
    root: Path = ROOT,
) -> list[str]:
    reasons: list[str] = []
    if (root / slug).is_file():
        reasons.append("html_already_exists")

    if any(item.get("url") == slug for item in noticias):
        reasons.append("url_already_in_noticias")

    if any(
        news_same_match(
            item,
            match=match,
            target_date=target_date,
            config=config,
        )
        for item in noticias
    ):
        reasons.append("same_match_already_in_noticias")

    return reasons


def plan_matches(
    matches: list[dict[str, Any]],
    *,
    target_date: date,
    config: dict[str, Any],
    noticias: list[dict[str, Any]],
    root: Path = ROOT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    planned: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    prepare_date = target_date - timedelta(days=1)
    publication = config["publication"]

    for match in matches:
        slug = build_slug(match, target_date, config)
        reasons = duplicate_reasons(
            slug=slug,
            match=match,
            target_date=target_date,
            config=config,
            noticias=noticias,
            root=root,
        )
        if slug in seen_slugs:
            reasons.append("slug_collision_in_batch")
        seen_slugs.add(slug)

        base = {
            "fixture_id": match.get("id"),
            "home": match.get("home"),
            "away": match.get("away"),
            "competition": match.get("competition"),
            "competition_slug": match.get("competition_slug"),
            "kickoff_brasilia": match.get("kickoff_brasilia"),
            "kickoff_time_brasilia": match.get("kickoff_time_brasilia"),
            "monitored_clubs": match.get("monitored_clubs", []),
            "two_monitored_clubs_same_match": bool(
                match.get("two_monitored_clubs_same_match")
            ),
            "slug": slug,
            "article_date": target_date.strftime("%d/%m/%Y"),
            "prepare_at_brasilia": (
                f"{prepare_date.isoformat()}T{publication['prepare_time']}:00-03:00"
            ),
            "target_publish_at_brasilia": (
                f"{target_date.isoformat()}T{publication['target_publish_time']}:00-03:00"
            ),
        }

        if reasons:
            skipped.append({**base, "reasons": sorted(set(reasons))})
        else:
            planned.append(base)

    return planned, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Planeja matérias automáticas de pré-jogo sem publicar nada."
    )
    parser.add_argument(
        "--date",
        help="Data-alvo YYYY-MM-DD. Se omitida, usa amanhã em America/Sao_Paulo.",
    )
    parser.add_argument(
        "--games",
        type=Path,
        help="Relatório jogos-AAAA-MM-DD.json. Se omitido, usa build/pre-jogo/.",
    )
    parser.add_argument(
        "--noticias",
        type=Path,
        default=NOTICIAS_PATH,
        help="Arquivo noticias.json usado somente para checagem de duplicidade.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir apenas o plano no diretório de build.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)

    games_path = args.games
    if games_path is None:
        games_path = DEFAULT_OUTPUT_DIR / f"jogos-{target_date.isoformat()}.json"

    matches = load_selected_matches(games_path, target_date)
    noticias = load_noticias(args.noticias)
    planned, skipped = plan_matches(
        matches,
        target_date=target_date,
        config=config,
        noticias=noticias,
    )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"planos-{target_date.isoformat()}.json"
    if destination.exists() and not args.force:
        fail(
            f"O plano já existe: {destination}. "
            "Use --force somente para substituir esse arquivo de build."
        )

    result = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "source_games": str(games_path),
        "planned_count": len(planned),
        "skipped_count": len(skipped),
        "planned": planned,
        "skipped": skipped,
    }
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: planejamento concluído para {target_date.isoformat()}.")
    print(f"Matérias candidatas: {len(planned)}")
    print(f"Bloqueadas por duplicidade/colisão: {len(skipped)}")
    for item in planned:
        print(
            f'- {item["kickoff_time_brasilia"]} | {item["home"]} x {item["away"]} '
            f'| {item["slug"]}'
        )
    for item in skipped:
        print(
            f'- BLOQUEADO | {item["home"]} x {item["away"]} | '
            f'{", ".join(item["reasons"])}'
        )
    print(
        f"Plano: {destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination}"
    )
    print("Nenhuma matéria ou arquivo publicado foi alterado.")


if __name__ == "__main__":
    main()
