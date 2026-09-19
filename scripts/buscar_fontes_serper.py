#!/usr/bin/env python3
"""Descobre fontes candidatas via Serper sem validar fatos nem publicar conteúdo."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"


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
    discovery = config.get("research", {}).get("discovery")
    if not isinstance(discovery, dict):
        fail('Configuração "research.discovery" ausente ou inválida.')
    provider = discovery.get("search_provider")
    if not isinstance(provider, dict):
        fail("Provedor de busca não configurado.")
    expected = {
        "name": "serper",
        "base_url": "https://google.serper.dev",
        "endpoint": "/search",
        "method": "POST",
        "api_key_env": "SERPER_API_KEY",
        "auth_header": "X-API-KEY",
    }
    for key, value in expected.items():
        if provider.get(key) != value:
            fail(f'Configuração Serper inválida em "{key}".')
    if provider.get("execute_requires_explicit_flag") is not True:
        fail("A execução do Serper deve exigir flag explícita.")
    if discovery.get("publication_unlock_allowed") is not False:
        fail("A descoberta de fontes não pode liberar publicação.")
    return config


def parse_target_date(raw: str | None, tz: ZoneInfo) -> date:
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            fail("--date deve usar o formato YYYY-MM-DD.")
    return datetime.now(tz).date() + timedelta(days=1)


def load_collection_manifest(path: Path, target_date: date) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        fail("O manifesto de coleta deve ser um objeto JSON.")
    if data.get("target_date") != target_date.isoformat():
        fail("A data do manifesto de coleta não coincide com a data-alvo.")
    plans = data.get("plans")
    if not isinstance(plans, list):
        fail('O manifesto de coleta deve conter um array "plans".')
    return [item for item in plans if isinstance(item, dict)]


def normalize_domain(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def domain_matches(host: str, allowed_domain: str) -> bool:
    allowed = allowed_domain.strip().lower().rstrip(".")
    if allowed.startswith("www."):
        allowed = allowed[4:]
    return host == allowed or host.endswith("." + allowed)


def build_query(query: str, domains: list[str]) -> str:
    clean = query.strip()
    if not clean:
        fail("Consulta vazia para o Serper.")
    unique: list[str] = []
    seen: set[str] = set()
    for domain in domains:
        value = domain.strip().lower()
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    if not unique:
        return clean
    domain_filter = " OR ".join(f"site:{domain}" for domain in unique)
    return f"{clean} ({domain_filter})"


def build_payload(query: str, *, provider: dict[str, Any]) -> dict[str, Any]:
    num = provider.get("results_per_query", 10)
    if not isinstance(num, int) or not 1 <= num <= 20:
        fail("search_provider.results_per_query deve ficar entre 1 e 20.")
    payload: dict[str, Any] = {"q": query, "num": num}
    gl = provider.get("gl")
    hl = provider.get("hl")
    if isinstance(gl, str) and gl.strip():
        payload["gl"] = gl.strip()
    if isinstance(hl, str) and hl.strip():
        payload["hl"] = hl.strip()
    return payload


def normalize_serper_response(
    payload: dict[str, Any],
    *,
    allowed_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    organic = payload.get("organic", [])
    if not isinstance(organic, list):
        return []
    allowed = [item.strip().lower() for item in (allowed_domains or []) if item.strip()]
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in organic:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        link = item.get("link")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(link, str) or not link.startswith("https://"):
            continue
        host = normalize_domain(link)
        if not host:
            continue
        if allowed and not any(domain_matches(host, domain) for domain in allowed):
            continue
        if link in seen_urls:
            continue
        seen_urls.add(link)
        position = item.get("position")
        if not isinstance(position, int):
            position = len(results) + 1
        results.append(
            {
                "title": title.strip(),
                "url": link,
                "domain": host,
                "snippet": item.get("snippet") if isinstance(item.get("snippet"), str) else "",
                "position": position,
                "published_hint": item.get("date") if isinstance(item.get("date"), str) else None,
            }
        )
    return results


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.casefold()
    folded = re.sub(r"[^a-z0-9]+", " ", folded)
    return " ".join(folded.split())


def canonical_monitored_club(team: str, config: dict[str, Any]) -> dict[str, Any] | None:
    needle = normalize_text(team)
    for club in config.get("monitored_clubs", []):
        if not isinstance(club, dict):
            continue
        variants = [club.get("name"), str(club.get("slug", "")).replace("-", " "), *club.get("aliases", [])]
        if any(normalize_text(item) == needle for item in variants if isinstance(item, str)):
            return club
    return None


def team_variants(team: str, config: dict[str, Any]) -> list[str]:
    raw: list[str] = [team]
    club = canonical_monitored_club(team, config)
    if club:
        raw.extend([str(club.get("name", "")), str(club.get("slug", "")).replace("-", " ")])
        raw.extend(str(item) for item in club.get("aliases", []) if isinstance(item, str))

    normalized = normalize_text(team)
    tokens = normalized.split()
    generic_stop = {"1", "fc", "cf", "sc", "ac", "afc", "sv", "club", "clube"}
    meaningful = [token for token in tokens if token not in generic_stop]
    if meaningful:
        raw.append(" ".join(meaningful))
        if len(meaningful) >= 2:
            raw.append(" ".join(meaningful[-2:]))

    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = normalize_text(item)
        if len(value) >= 4 and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def candidate_haystack(candidate: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            str(candidate.get(key, ""))
            for key in ("title", "snippet", "url")
        )
    )


def candidate_title_url_haystack(candidate: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(str(candidate.get(key, "")) for key in ("title", "url"))
    )


def candidate_matches_team(candidate: dict[str, Any], team: str, config: dict[str, Any]) -> bool:
    haystack = candidate_haystack(candidate)
    return any(variant in haystack for variant in team_variants(team, config))


def candidate_matches_team_strict(candidate: dict[str, Any], team: str, config: dict[str, Any]) -> bool:
    """Para H2H, o clube precisa aparecer no título/URL, não só em snippet lateral."""
    haystack = candidate_title_url_haystack(candidate)
    return any(variant in haystack for variant in team_variants(team, config))


def competition_matches_candidate(candidate: dict[str, Any], context: dict[str, Any], config: dict[str, Any]) -> bool:
    competition = normalize_text(context.get("competition"))
    slug = normalize_text(str(context.get("competition_slug", "")).replace("-", " "))
    haystack = candidate_haystack(candidate)
    if competition and competition in haystack:
        return True
    if slug and slug in haystack:
        return True

    domain = str(candidate.get("domain", "")).strip().lower()
    competition_slug = context.get("competition_slug")
    official = config.get("research", {}).get("discovery", {}).get("official_domains", {}).get("competitions", {})
    domains = official.get(competition_slug, []) if isinstance(official, dict) else []
    return any(domain_matches(domain, str(item)) for item in domains if isinstance(item, str))


def recent_form_candidate_has_result_signal(candidate: dict[str, Any]) -> bool:
    """Rejeita páginas genéricas de clube/tabela que não sustentam forma recente."""
    text = candidate_haystack(candidate)
    outcome_signals = (
        " win ", " wins ", " won ", " victory ", " draw ", " draws ", " unbeaten ",
        " defeat ", " loss ", " lost ", " vitoria ", " vitorias ", " venceu ",
        " empate ", " empates ", " derrota ", " perdeu ", " points ", " pontos ",
    )
    time_signals = (
        " recent ", " form ", " last ", " latest ", " matchday ", " season ",
        " games ", " matches ", " ultimos ", " ultimo ", " rodada ", " temporada ",
        " jogos ", " partidas ", " 2026 ",
    )
    padded = f" {text} "
    return any(signal in padded for signal in outcome_signals) and any(
        signal in padded for signal in time_signals
    )


def filter_results_for_requirement(
    requirement_id: str,
    results: list[dict[str, Any]],
    *,
    context: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Passos 34.5/34.6: evita páginas laterais e páginas genéricas antes da leitura."""
    if requirement_id not in {"recent_form_both_teams", "competition_specific_head_to_head"}:
        return results

    home = context.get("home")
    away = context.get("away")
    if not isinstance(home, str) or not isinstance(away, str):
        return []

    if requirement_id == "competition_specific_head_to_head":
        return [
            item for item in results
            if candidate_matches_team_strict(item, home, config)
            and candidate_matches_team_strict(item, away, config)
            and competition_matches_candidate(item, context, config)
        ]

    relevant = [
        item for item in results
        if recent_form_candidate_has_result_signal(item)
        and (candidate_matches_team(item, home, config) or candidate_matches_team(item, away, config))
    ]
    home_rows = [item for item in relevant if candidate_matches_team(item, home, config)]
    away_rows = [item for item in relevant if candidate_matches_team(item, away, config)]
    if not home_rows or not away_rows:
        # Uma etapa que só cobre um dos clubes não resolve um requisito explicitamente bilateral.
        return []

    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pool in (home_rows[:1], away_rows[:1], relevant):
        for item in pool:
            url = str(item.get("url", ""))
            if url and url not in seen:
                seen.add(url)
                ordered.append(item)
    return ordered


def expanded_queries(
    requirement_id: str,
    queries: list[Any],
    context: dict[str, Any],
    article_date: str | None = None,
) -> list[str]:
    result: list[str] = [item.strip() for item in queries if isinstance(item, str) and item.strip()]
    home = context.get("home")
    away = context.get("away")
    competition = context.get("competition")
    if not all(isinstance(item, str) and item.strip() for item in (home, away, competition)):
        return result

    year = ""
    if isinstance(article_date, str):
        match = re.match(r"(\d{4})-", article_date)
        if match:
            year = match.group(1)

    extras: list[str] = []
    if requirement_id == "recent_form_both_teams":
        extras = [
            f'"{home}" "{competition}" recent form results last matches {year}'.strip(),
            f'"{away}" "{competition}" recent form results last matches {year}'.strip(),
            f'"{home}" "{competition}" últimos jogos resultados {year}'.strip(),
            f'"{away}" "{competition}" últimos jogos resultados {year}'.strip(),
            f'"{home}" "{competition}" latest result matchday {year}'.strip(),
            f'"{away}" "{competition}" latest result matchday {year}'.strip(),
        ]
    elif requirement_id == "competition_specific_head_to_head":
        extras = [
            f'"{home}" "{away}" "{competition}" head to head record',
            f'"{home}" "{away}" "{competition}" previous meetings results',
        ]

    seen = set(result)
    for query in extras:
        if query not in seen:
            seen.add(query)
            result.append(query)
    return result


def classify_serper_error_body(raw: str) -> str:
    """Retorna apenas categorias seguras; nunca registra a chave da API."""
    try:
        payload = json.loads(raw)
        detail = str(payload.get("message") or payload.get("error") or "")
    except (ValueError, AttributeError, TypeError):
        detail = raw
    folded = detail.casefold()
    if "credit" in folded and any(term in folded for term in ("not enough", "insufficient", "exhaust", "no ", "out of")):
        return "créditos insuficientes na conta Serper; recarregue o saldo no painel"
    if "api key" in folded and any(term in folded for term in ("invalid", "missing", "inactive")):
        return "chave de API ausente, inválida ou inativa"
    if "rate limit" in folded or "too many requests" in folded:
        return "limite de requisições atingido"
    if "query" in folded and any(term in folded for term in ("invalid", "too long", "exceed")):
        return "consulta recusada pelo provedor"
    return "razão não classificada; confira a conta e os parâmetros no painel Serper"


def request_serper(
    *,
    query: str,
    domains: list[str],
    config: dict[str, Any],
    timeout: int = 20,
    retries: int = 2,
) -> tuple[str, dict[str, Any]]:
    # Pesquisa gratuita de RSS com leitura independente: não toca nos endpoints Serper.
    if os.environ.get("CDE_FREE_RESEARCH") == "1":
        from scripts import pesquisa_publica_gratuita as free
        return free.search_rss(query, domains, config)

    discovery = config["research"]["discovery"]
    if discovery.get("external_search_enabled") is not True:
        fail("Busca externa está desligada em config/pre-jogo.json.")

    provider = discovery["search_provider"]
    env_name = provider["api_key_env"]
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        fail(f"Secret/variável {env_name} não configurado.")

    final_query = build_query(query, domains)
    request_payload = build_payload(final_query, provider=provider)
    body = json.dumps(request_payload).encode("utf-8")
    url = provider["base_url"].rstrip("/") + provider["endpoint"]
    headers = {
        provider["auth_header"]: api_key,
        "Content-Type": provider.get("content_type", "application/json"),
        "Accept": "application/json",
        "User-Agent": "Corte-dos-Esportes-pre-jogo/1.0",
    }

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    fail("Resposta inesperada do Serper: JSON não é objeto.")
                return final_query, data
        except HTTPError as exc:
            last_error = exc
            # Lê só a mensagem de erro; nunca registra request headers/API key.
            error_reason = classify_serper_error_body(exc.read().decode("utf-8", errors="replace"))
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                fail(f"Serper retornou HTTP {exc.code}: {error_reason}.")
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= retries:
                fail(f"Falha ao consultar Serper: {exc}")
        time.sleep(1 + attempt)

    fail(f"Falha ao consultar Serper: {last_error}")


def discover_candidates_for_plan(
    plan: dict[str, Any],
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        fail("Plano de coleta sem tarefas válidas.")
    context = plan.get("match_context") if isinstance(plan.get("match_context"), dict) else {}
    article_date = plan.get("date") if isinstance(plan.get("date"), str) else None

    discovered_tasks: list[dict[str, Any]] = []
    query_count = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        requirement_id = task.get("requirement_id")
        queries = task.get("queries")
        stages = task.get("stages")
        if not isinstance(requirement_id, str) or not isinstance(queries, list) or not isinstance(stages, list):
            continue
        queries = expanded_queries(requirement_id, queries, context, article_date)

        selected_stage: dict[str, Any] | None = None
        selected_results: list[dict[str, Any]] = []
        executed_queries: list[str] = []

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            domains = stage.get("domains", [])
            if not isinstance(domains, list):
                domains = []
            stage_results: list[dict[str, Any]] = []
            seen_urls: set[str] = set()
            for query in queries:
                if not isinstance(query, str) or not query.strip():
                    continue
                final_query, raw = request_serper(
                    query=query,
                    domains=[str(item) for item in domains],
                    config=config,
                )
                query_count += 1
                executed_queries.append(final_query)
                normalized = normalize_serper_response(
                    raw,
                    allowed_domains=[str(item) for item in domains] if domains else None,
                )
                for result in normalized:
                    if result["url"] not in seen_urls:
                        seen_urls.add(result["url"])
                        stage_results.append(result)

                # Evita gastar todas as variantes quando a evidência já basta.
                # Forma recente mantém a exigência de cobrir os DOIS clubes;
                # H2H continua exigindo ambos no título/URL e competição.
                qualifying = filter_results_for_requirement(
                    requirement_id,
                    stage_results,
                    context=context,
                    config=config,
                )
                if qualifying:
                    selected_stage = stage
                    selected_results = qualifying
                    break
            if selected_results:
                break

        discovered_tasks.append(
            {
                "requirement_id": requirement_id,
                "search_status": "candidates_found" if selected_results else "no_candidates",
                "selected_source_type": selected_stage.get("source_type") if selected_stage else None,
                "dynamic_relevance_required": bool(selected_stage.get("dynamic_relevance_required")) if selected_stage else False,
                "executed_queries": executed_queries,
                "candidates": selected_results,
                "passo34_5_relevance_filter": requirement_id in {"recent_form_both_teams", "competition_specific_head_to_head"},
                "passo34_6_quality_filter": requirement_id in {"recent_form_both_teams", "competition_specific_head_to_head"},
                "facts_verified": False,
                "ready_for_drafting": False,
            }
        )

    return {
        "title": plan.get("title"),
        "slug": plan.get("slug"),
        "date": plan.get("date"),
        "fixture_id": plan.get("fixture_id"),
        "provider": "serper",
        "external_search_performed": True,
        "query_count": query_count,
        "tasks": discovered_tasks,
        "ready_for_drafting": False,
        "ready_for_html": False,
        "publication_unlocked": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa descoberta de fontes candidatas via Serper sem validar fatos ou publicar."
    )
    parser.add_argument("--date", help="Data-alvo YYYY-MM-DD. Vazio = amanhã em Brasília.")
    parser.add_argument(
        "--collection",
        type=Path,
        help="Manifesto coleta-fontes-AAAA-MM-DD.json. Se omitido, usa build/pre-jogo/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída. Padrão: build/pre-jogo/.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Obrigatório para permitir chamadas reais ao Serper.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir apenas arquivos de descoberta dentro de build/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    if not args.execute:
        fail("Execução externa bloqueada. Use --execute somente após configurar o Secret SERPER_API_KEY.")

    tz = ZoneInfo(config["timezone"])
    target_date = parse_target_date(args.date, tz)
    collection_path = args.collection or DEFAULT_OUTPUT_DIR / f"coleta-fontes-{target_date.isoformat()}.json"
    plans = load_collection_manifest(collection_path, target_date)

    results = [discover_candidates_for_plan(plan, config=config) for plan in plans]
    output_dir = args.output_dir.resolve()
    destination = output_dir / f"fontes-candidatas-{target_date.isoformat()}.json"
    if destination.exists() and not args.force:
        fail(f"Arquivo já existe: {destination}. Use --force apenas em build/.")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(tz).isoformat(),
        "target_date": target_date.isoformat(),
        "timezone": config["timezone"],
        "provider": "serper",
        "external_search_performed": True,
        "article_count": len(results),
        "query_count": sum(item["query_count"] for item in results),
        "results": results,
        "ready_for_drafting_count": 0,
        "ready_for_html_count": 0,
        "publication_unlocked": False,
    }
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: descoberta Serper concluída para {target_date.isoformat()}.")
    print(f"Matérias pesquisadas: {len(results)}")
    print(f"Consultas executadas: {manifest['query_count']}")
    print("Passo 34.6: forma recente exige sinais de resultado e H2H exige os dois clubes no título/URL.")
    print("Nenhum fato foi validado por este script.")
    print("Redação, HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
