#!/usr/bin/env python3
"""Gera rascunho de pré-jogo via OpenAI usando somente o contrato limpo do Passo 25.

Passo 26:
- recebe exclusivamente o contrato de redação limpo;
- não envia proveniência, fontes, consultas ou URLs externas ao modelo;
- chama a Responses API somente com --execute explícito;
- exige OPENAI_API_KEY em variável de ambiente;
- valida o rascunho com as travas do Passo 25;
- grava somente em build/pre-jogo/;
- nunca gera HTML final nem libera publicação.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import preparar_redacao_pre_jogo as prepare  # noqa: E402
from scripts import validar_rascunho_pre_jogo as validate  # noqa: E402

PROVIDER_CONFIG_PATH = ROOT / "config" / "redacao-pre-jogo.json"
SITE_CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"

RETRYABLE_HTTP = {408, 409, 429, 500, 502, 503, 504}


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


def load_provider_config() -> dict[str, Any]:
    config = load_json(PROVIDER_CONFIG_PATH)
    if not isinstance(config, dict):
        fail("config/redacao-pre-jogo.json deve conter um objeto JSON.")

    provider = config.get("provider")
    scope = config.get("scope")
    safety = config.get("safety")
    if not isinstance(provider, dict) or not isinstance(scope, dict) or not isinstance(safety, dict):
        fail("Configuração de redação incompleta.")

    required = {
        "name": "openai-responses",
        "endpoint": "https://api.openai.com/v1/responses",
        "api_key_env": "OPENAI_API_KEY",
        "execute_requires_explicit_flag": True,
    }
    for key, expected in required.items():
        if provider.get(key) != expected:
            fail(f"Configuração do provedor inválida em provider.{key}.")

    safety_required_false = [
        "sources_available_to_model",
        "provenance_available_to_model",
        "external_urls_allowed",
        "research_process_mentions_allowed",
        "source_attribution_allowed",
        "html_generation_allowed",
        "publication_unlock_allowed",
    ]
    for key in safety_required_false:
        if safety.get(key) is not False:
            fail(f"Trava obrigatória inválida em safety.{key}.")

    if scope.get("allow_web_search") is not False or scope.get("allow_tools") is not False:
        fail("O redator não pode receber ferramentas ou pesquisa web.")

    budget = config.get("budget")
    if not isinstance(budget, dict):
        fail("Configuração de orçamento do redator ausente.")
    if float(budget.get("monthly_target_usd", 0)) > 10:
        fail("O teto mensal configurado para a OpenAI não pode ultrapassar US$ 10.")
    if int(budget.get("max_articles_per_day", 0)) != 10:
        fail("A trava diária deve permanecer em no máximo 10 matérias.")
    if int(budget.get("max_contract_chars", 0)) > 20000:
        fail("Contrato máximo acima do limite de custo aprovado.")
    if scope.get("input_contract_step") != 25 or scope.get("input_must_be_clean") is not True:
        fail("O redator deve consumir somente o contrato limpo do Passo 25.")
    return config


def validate_contract_for_model(contract: dict[str, Any], site_config: dict[str, Any]) -> None:
    if contract.get("step") != 25:
        fail("O redator aceita somente contratos do Passo 25.")
    if contract.get("ready_for_model") is not True:
        fail("Contrato ainda não está pronto para o modelo.")
    if contract.get("ready_for_html") is not False:
        fail("Contrato não pode estar liberado para HTML.")
    if contract.get("publication_unlocked") is not False:
        fail("Contrato não pode estar liberado para publicação.")
    if contract.get("drafting_provider_connected") is not False:
        fail("O contrato base deve permanecer independente do provedor.")

    leaked = prepare.scan_forbidden_keys(contract)
    if leaked:
        fail("Contrato vazou campos internos: " + ", ".join(leaked))

    external = prepare.editorial_package.scan_external_urls(
        contract, site_config["article"]["internal_link_domain"]
    )
    if external:
        fail("Contrato contém URL externa: " + ", ".join(external))


def output_schema(contract: dict[str, Any]) -> dict[str, Any]:
    slug = contract.get("slug")
    fields = contract.get("required_fact_fields")
    if not isinstance(slug, str) or not slug.endswith(".html"):
        fail("Contrato sem slug HTML válido.")
    if not isinstance(fields, list) or not fields or not all(isinstance(x, str) and x for x in fields):
        fail("Contrato sem required_fact_fields válido.")

    unique_fields = list(dict.fromkeys(fields))
    if len(unique_fields) != len(fields):
        fail("required_fact_fields contém duplicatas.")

    return {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "enum": [slug]},
            "body_html": {"type": "string", "minLength": 5500},
            "fact_fields_used": {
                "type": "array",
                "items": {"type": "string", "enum": unique_fields},
                "minItems": len(unique_fields),
                "maxItems": len(unique_fields),
            },
        },
        "required": ["slug", "body_html", "fact_fields_used"],
        "additionalProperties": False,
    }


def system_instructions() -> str:
    return (
        "Você é o redator automático de pré-jogo do Corte dos Esportes. "
        "Escreva em português do Brasil com tom jornalístico direto, fluido, factual e natural. "
        "Use EXCLUSIVAMENTE os fatos e o contexto presentes no contrato recebido. "
        "Não use conhecimento externo, memória, inferências factuais, pesquisa, ferramentas ou navegação web. "
        "Quando uma informação não estiver no contrato, omita-a em vez de completar. "
        "É expressamente proibido citar ou atribuir fontes de pesquisa, sites, portais, veículos, consultas ou processos internos. "
        "A menção a uma emissora/plataforma é permitida apenas quando ela própria é o fato de transmissão fornecido. "
        "Não diga 'segundo', 'conforme' ou 'de acordo com' para atribuir informação pesquisada. "
        "Não invente escalações, jogadores, árbitros, números, resultados, datas, horários, estádios, cidades, cenários ou retrospectos. "
        "Produza somente o corpo editorial da matéria, sem <html>, <head>, <body>, <article>, imagens, anúncios, scripts ou estilos. "
        "Use subtítulos no formato <p><strong>...</strong></p> e listas <ul><li> quando melhorarem a UX. "
        "As escalações, quando fornecidas, devem ser apresentadas como prováveis e nunca como oficiais. "
        "O retrospecto deve permanecer específico da competição indicada. "
        "Insira exatamente uma vez o link interno aprovado no contrato, com âncora textual natural. "
        "Não crie nenhum outro link. "
        "Evite bloco mecânico repetindo serviço logo após a abertura; distribua as informações naturalmente. "
        "A matéria deve ter no mínimo absoluto 800 palavras e preferencialmente entre 900 e 1100 palavras; nunca encerre o texto abaixo de 800 palavras. "
        "Retorne somente o objeto JSON exigido pelo schema."
    )


def user_payload(contract: dict[str, Any]) -> str:
    provider_config = load_provider_config()
    limit = int(provider_config["budget"]["max_contract_chars"])
    serialized = json.dumps(contract, ensure_ascii=False, indent=2)
    if len(serialized) > limit:
        fail(f"Contrato excede o limite de orçamento: {len(serialized)} > {limit} caracteres.")
    return (
        "Redija a matéria utilizando somente este contrato editorial limpo. "
        "Todos os campos factuais listados em required_fact_fields devem ser usados sem alterar seu sentido. "
        "O validador editorial rejeita qualquer matéria abaixo de 700 palavras; entregue pelo menos 800 palavras para manter margem de segurança.\n\n"
        + serialized
    )


def build_request(contract: dict[str, Any], provider_config: dict[str, Any]) -> dict[str, Any]:
    provider = provider_config["provider"]
    return {
        "model": provider["model"],
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_instructions()}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_payload(contract)}],
            },
        ],
        "reasoning": {"effort": provider.get("reasoning_effort", "low")},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "pre_jogo_draft",
                "schema": output_schema(contract),
                "strict": True,
            }
        },
        "max_output_tokens": int(provider.get("max_output_tokens", 7000)),
        "store": bool(provider.get("store", False)),
    }


def post_json(endpoint: str, api_key: str, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        detail = raw[:800]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de rede: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("A Responses API devolveu JSON inválido.") from exc


def response_http_code(error: RuntimeError) -> int | None:
    match = __import__("re").match(r"HTTP\s+(\d+):", str(error))
    return int(match.group(1)) if match else None


def call_responses_api(
    contract: dict[str, Any],
    provider_config: dict[str, Any],
    *,
    api_key: str,
) -> dict[str, Any]:
    provider = provider_config["provider"]
    attempts = int(provider.get("max_attempts", 3))
    timeout = int(provider.get("timeout_seconds", 120))
    payload = build_request(contract, provider_config)

    last_error: RuntimeError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return post_json(provider["endpoint"], api_key, payload, timeout=timeout)
        except RuntimeError as exc:
            last_error = exc
            code = response_http_code(exc)
            retryable = code in RETRYABLE_HTTP or code is None
            if attempt >= attempts or not retryable:
                break
            time.sleep(min(2 ** (attempt - 1), 8))

    fail(f"Falha ao chamar o redator OpenAI após {attempts} tentativa(s): {last_error}")


def extract_output_text(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        fail("Resposta da API inválida.")
    if response.get("error"):
        fail(f"Responses API retornou erro: {response.get('error')}")
    status = response.get("status")
    if status not in {"completed", None}:
        fail(f"Resposta do modelo não foi concluída: status={status!r}")

    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    if not texts:
        fail("A resposta não contém output_text utilizável.")
    return "\n".join(texts)


def parse_draft(response: dict[str, Any]) -> dict[str, Any]:
    text = extract_output_text(response)
    try:
        draft = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"O modelo não devolveu JSON válido: {exc}")
    if not isinstance(draft, dict):
        fail("O JSON do redator deve ser um objeto.")
    return draft


def estimate_usage_cost_usd(response: dict[str, Any], provider_config: dict[str, Any]) -> float | None:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        budget = provider_config["budget"]
        cost = (
            input_tokens * float(budget["input_usd_per_million_tokens"])
            + output_tokens * float(budget["output_usd_per_million_tokens"])
        ) / 1_000_000
        return round(cost, 6)
    except (TypeError, ValueError, KeyError):
        return None


def usage_summary(response: dict[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}
    allowed = {"input_tokens", "output_tokens", "total_tokens"}
    return {key: usage.get(key) for key in allowed if key in usage}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera rascunho controlado via OpenAI sem publicar.")
    parser.add_argument("--contract", required=True, type=Path, help="Contrato limpo do Passo 25.")
    parser.add_argument("--execute", action="store_true", help="Autoriza explicitamente a chamada real à API.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída dentro de build/pre-jogo/.",
    )
    parser.add_argument("--force", action="store_true", help="Permite substituir somente saídas do Passo 26 em build/.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider_config = load_provider_config()
    site_config = load_json(SITE_CONFIG_PATH)
    if not isinstance(site_config, dict):
        fail("config/pre-jogo.json inválido.")

    contract = load_json(args.contract)
    if not isinstance(contract, dict):
        fail("Contrato de redação inválido.")
    validate_contract_for_model(contract, site_config)

    if provider_config["provider"].get("execute_requires_explicit_flag") is True and not args.execute:
        fail("Chamada real bloqueada: use --execute explicitamente.")

    env_name = provider_config["provider"]["api_key_env"]
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        fail(f"Variável de ambiente {env_name} não configurada.")

    response = call_responses_api(contract, provider_config, api_key=api_key)
    draft = parse_draft(response)
    validated, errors = validate.validate_draft(draft, contract, config=site_config)
    if errors:
        fail("Rascunho do modelo rejeitado pelas travas: " + "; ".join(errors))

    slug = contract.get("slug")
    assert isinstance(slug, str)
    basename = Path(slug).with_suffix(".json").name
    output_root = args.output_dir.resolve()
    draft_path = output_root / "rascunhos-modelo" / basename
    metadata_path = output_root / "redacao-modelo-metadata" / basename
    for path in (draft_path, metadata_path):
        if path.exists() and not args.force:
            fail(f"Saída já existe: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    validated["drafting_provider"] = provider_config["provider"]["name"]
    validated["drafting_model"] = provider_config["provider"]["model"]
    validated["ready_for_html"] = False
    validated["publication_unlocked"] = False
    draft_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    metadata = {
        "step": 26,
        "slug": slug,
        "provider": provider_config["provider"]["name"],
        "model": provider_config["provider"]["model"],
        "response_id": response.get("id"),
        "response_status": response.get("status"),
        "usage": usage_summary(response),
        "estimated_cost_usd": estimate_usage_cost_usd(response, provider_config),
        "monthly_target_usd": provider_config["budget"]["monthly_target_usd"],
        "generated_at": datetime.now(ZoneInfo(site_config["timezone"])).isoformat(),
        "sources_sent_to_model": False,
        "provenance_sent_to_model": False,
        "web_search_enabled": False,
        "tools_enabled": False,
        "draft_validated": True,
        "ready_for_html": False,
        "publication_unlocked": False,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: rascunho real do modelo gerado e validado somente em build/.")
    print(f"Modelo: {metadata['model']}")
    print(f"Palavras: {validated['word_count']}")
    print(f"Custo estimado desta redação: US$ {metadata['estimated_cost_usd'] if metadata['estimated_cost_usd'] is not None else 'n/d'}")
    print(f"Subtítulos fortes: {validated['strong_subheading_count']}")
    print("Fontes/proveniência enviadas ao modelo: não")
    print("Pesquisa web/ferramentas do modelo: não")
    print("HTML liberado: não")
    print("Publicação liberada: não")


if __name__ == "__main__":
    main()
