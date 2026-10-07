#!/usr/bin/env python3
"""Prepara o contrato de redação a partir do pacote editorial limpo do Passo 24.

Esta etapa NÃO chama nenhum modelo de linguagem. Ela define exatamente o que um
redator automático poderá receber e produzir. Proveniência, consultas e URLs
externas permanecem fora do contrato.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import montar_pacote_editorial as editorial_package  # noqa: E402

CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

FORBIDDEN_DRAFTER_KEYS = {
    "sources",
    "source_candidates",
    "publisher",
    "source_type",
    "checked_at",
    "discovered_at",
    "query",
    "queries",
    "query_base",
    "evidence_segments",
    "page_evidence",
    "extracted_claims",
    "validator_source",
    "supporting_sources",
    "evidence_sha256",
    "content_sha256",
    "provenance",
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
    article = config.get("article")
    if not isinstance(article, dict) or int(article.get("min_words", 0)) < 700:
        fail("O mínimo editorial deve permanecer em pelo menos 700 palavras.")
    policy = config.get("editorial", {}).get("source_attribution_policy")
    if not isinstance(policy, dict):
        fail("Política editorial de fontes ausente.")
    if policy.get("research_sources_are_internal_only") is not True:
        fail("Fontes de pesquisa devem permanecer internas.")
    if policy.get("forbid_source_names_in_article_body") is not True:
        fail("Atribuição de fontes deve permanecer proibida no corpo.")
    return config


def scan_forbidden_keys(value: Any, path: str = "root") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_DRAFTER_KEYS:
                errors.append(f"{path}.{key}")
            errors.extend(scan_forbidden_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            errors.extend(scan_forbidden_keys(item, f"{path}[{idx}]"))
    return errors


def collect_fact_fields(clean_package: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for requirement in clean_package.get("facts_by_requirement", []):
        if not isinstance(requirement, dict):
            continue
        for fact in requirement.get("facts", []):
            if not isinstance(fact, dict):
                continue
            field = fact.get("field")
            if isinstance(field, str) and field.strip() and field.strip() not in seen:
                seen.add(field.strip())
                fields.append(field.strip())
    return fields


def build_contract(clean_package: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
    if clean_package.get("ready_for_drafting") is not True:
        fail("O pacote editorial ainda não está liberado para redação.")
    if clean_package.get("ready_for_html") is not False:
        fail("O Passo 25 não pode receber pacote já liberado para HTML.")
    if clean_package.get("publication_unlocked") is not False:
        fail("O Passo 25 não pode receber pacote com publicação liberada.")
    if clean_package.get("provenance_available_to_drafter") is not False:
        fail("A proveniência não pode estar disponível ao redator.")

    leaked = scan_forbidden_keys(clean_package)
    if leaked:
        fail("Pacote de redação contém campos internos proibidos: " + ", ".join(leaked))

    internal_link = clean_package.get("competition_internal_link")
    if not isinstance(internal_link, dict):
        fail("Pacote sem link interno da competição.")
    link_url = internal_link.get("url")
    if not isinstance(link_url, str) or not link_url.startswith(config["article"]["internal_link_domain"]):
        fail("Link interno da competição inválido.")

    context = clean_package.get("match_context")
    if not isinstance(context, dict):
        fail("Pacote sem contexto da partida.")

    fact_fields = collect_fact_fields(clean_package)
    if not fact_fields:
        fail("Pacote editorial sem fatos estruturados para redação.")

    contract = {
        "step": 25,
        "mode": "draft_contract_only",
        "slug": clean_package.get("slug"),
        "title": clean_package.get("title"),
        "excerpt": clean_package.get("excerpt"),
        "date": clean_package.get("date"),
        "match_context": deepcopy(context),
        "facts_by_requirement": deepcopy(clean_package.get("facts_by_requirement", [])),
        "competition_internal_link": deepcopy(internal_link),
        "required_fact_fields": fact_fields,
        "output_contract": {
            "format": "json",
            "required_fields": ["slug", "body_html", "fact_fields_used"],
            "body_html_scope": "article_body_only",
            "minimum_words": int(config["article"]["min_words"]),
            "preferred_word_range": [750, 900],
            "minimum_strong_subheadings": 5,
            "internal_link_exactly_once": True,
            "unordered_lists_for_service_blocks": True,
        },
        "editorial_rules": {
            "language": "pt-BR",
            "tone": "jornalístico direto, fluido e factual",
            "seo": "natural, sem repetição artificial de palavras-chave",
            "opening": (
                "Abrir em um ou dois parágrafos com confronto, data, horário de Brasília, estádio, competição "
                "e um gancho esportivo concreto já presente nos fatos. Não despejar estatísticas nem antecipar "
                "toda a ficha de serviço na abertura."
            ),
            "approved_model": (
                "Seguir a estrutura da prévia aprovada LDU x Palmeiras: abertura factual curta; contexto da partida "
                "somente quando houver fato verificável; Como chega o mandante; Como chega o visitante; prováveis "
                "escalações em bloco; retrospecto proporcional ao tamanho real da amostra; Onde assistir; e fechamento "
                "apenas se houver uma consequência, cenário ou próximo jogo realmente fornecido no contrato."
            ),
            "journalistic_synthesis": (
                "Os fatos estruturados são matéria-prima, não frases para copiar. Converter linguagem de API/banco de dados "
                "em português jornalístico natural. Preferir 'nos cinco jogos mais recentes' a expressões como "
                "'jogos concluídos registrados', 'resultados registrados', 'base considerada' ou 'recorte considerado'."
            ),
            "absence_is_not_fact": (
                "Ausência de dado no contrato não é um fato publicável. Nunca escrever que uma informação não foi divulgada, "
                "não foi confirmada, será acrescentada depois ou está pendente, a menos que essa indisponibilidade apareça "
                "explicitamente como fato textual no contrato. Não mencionar desfalques, suspensões ou lesões sem fato específico."
            ),
            "editorial_depth": (
                "Priorizar fatos concretos: resultados recentes, situação competitiva, jogadores e eventos explicitamente fornecidos. "
                "Não inferir estilo de jogo, posse, pressão, transições, estratégia, motivação, comportamento tático ou efeito psicológico "
                "a partir de nomes, escalações, mando de campo ou resultados."
            ),
            "recent_form": (
                "Tratar a forma recente de cada equipe em seu próprio bloco, de maneira natural e sem repetir os mesmos placares, "
                "balanços de vitórias/empates/derrotas ou sequências no fechamento."
            ),
            "non_repetition": (
                "Cada bloco deve acrescentar informação concreta nova. Um mesmo balanço recente, placar, retrospecto ou serviço "
                "não deve ser recontado em outra seção. Não criar os blocos genéricos Informações confirmadas, O que observar, "
                "Resumo do pré-jogo ou O cenário antes da bola rolar."
            ),
            "subheadings": "Usar <p><strong>...</strong></p> ao longo da matéria.",
            "lineups": (
                "Prováveis escalações dos dois times e técnicos devem aparecer em um único bloco/lista visível. "
                "Se home_lineup e away_lineup existem, é proibido dizer que não há provável escalação disponível. "
                "Usar no máximo uma ressalva curta de que as formações são prováveis e podem mudar até a confirmação oficial."
            ),
            "head_to_head": (
                "O retrospecto deve ser proporcional à amostra disponível. Se houver apenas um ou dois jogos no conjunto fornecido, "
                "usar um bloco curto — um parágrafo ou lista — e deixar claro apenas que se trata de uma amostra limitada, sem "
                "transformá-la em narrativa histórica ou rivalidade ampla. Nunca expandir números pequenos para preencher texto."
            ),
            "where_to_watch": (
                "Concentrar a emissora/plataforma confirmada no bloco Onde assistir. Não repetir toda a ficha de serviço antes e depois."
            ),
            "closing": (
                "Fechar em um parágrafo curto somente se houver fato novo de consequência esportiva ou próximo jogo. "
                "Não recapitular resultados recentes, escalações, transmissão ou retrospecto no encerramento."
            ),
            "internal_link": (
                "Inserir exatamente uma vez o link interno fornecido, de forma natural no texto; "
                "nenhum outro URL deve ser criado."
            ),
            "source_policy": (
                "É expressamente proibido citar fontes, sites, portais, veículos ou consultas internas; "
                "escrever os fatos aprovados diretamente."
            ),
            "fact_policy": (
                "Usar somente os fatos fornecidos no pacote. Não completar lacunas com conhecimento externo, "
                "suposições ou inferências factuais."
            ),
            "ads": "Não inserir anúncios, imagens, scripts ou estrutura da página nesta etapa.",
        },
        "drafting_provider_connected": False,
        "ready_for_model": True,
        "ready_for_html": False,
        "publication_unlocked": False,
    }

    if editorial_package.scan_external_urls(contract, config["article"]["internal_link_domain"]):
        fail("Contrato contém URL externa.")
    if scan_forbidden_keys(contract):
        fail("Contrato final contém metadados de proveniência proibidos.")
    return contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepara contrato limpo para o redator automático.")
    parser.add_argument("--package", required=True, type=Path, help="Pacote editorial limpo do Passo 24.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída dentro de build/pre-jogo/.",
    )
    parser.add_argument("--force", action="store_true", help="Permite substituir somente contrato em build/.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    clean_package = load_json(args.package)
    if not isinstance(clean_package, dict):
        fail("Pacote editorial limpo inválido.")
    contract = build_contract(clean_package, config=config)

    slug = contract.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html"):
        fail("Contrato sem slug HTML válido.")
    destination = args.output_dir.resolve() / "contratos-redacao" / Path(slug).with_suffix(".json").name
    if destination.exists() and not args.force:
        fail(f"Contrato já existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    now = datetime.now(ZoneInfo(config["timezone"])).isoformat()
    print(f"OK: contrato de redação preparado em {now}.")
    print(f"Campos factuais disponíveis: {len(contract['required_fact_fields'])}")
    print("Proveniência disponível ao redator: não")
    print("Provedor de redação conectado: não")
    print("HTML e publicação permanecem bloqueados.")


if __name__ == "__main__":
    main()
