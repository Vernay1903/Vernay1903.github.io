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
            "body_html": {"type": "string", "minLength": 6500},
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
        "Use EXCLUSIVAMENTE os fatos e o contexto presentes no contrato. Não use memória, conhecimento externo, pesquisa, ferramentas ou navegação web. "
        "A ausência de uma informação no contrato NÃO é um fato: omita o assunto. Nunca escreva que algo não foi divulgado, não foi confirmado, "
        "está pendente ou será acrescentado depois, salvo quando essa indisponibilidade estiver explicitamente escrita como fato no contrato. "
        "Não invente desfalques, suspensões, lesões, escalações, jogadores, árbitros, números, resultados, datas, horários, estádios ou cenários. "
        "Não infira estilo de jogo, pressão, posse, transições, estratégia, motivação ou comportamento tático a partir de nomes, escalações, mando ou placares. "
        "Os fatos estruturados são matéria-prima: reescreva-os em linguagem jornalística natural. Nunca exponha linguagem de banco de dados ou API como "
        "'jogos concluídos registrados', 'resultados registrados', 'base considerada' ou 'recorte considerado'. "
        "Produza somente o corpo editorial, sem <html>, <head>, <body>, <article>, imagens, anúncios, scripts ou estilos. "
        "FORMATO OBRIGATÓRIO: body_html deve conter no mínimo cinco subtítulos exatamente no formato <p><strong>...</strong></p>; não use Markdown, <h2> ou <h3>. "
        "Inclua obrigatoriamente uma lista HTML <ul><li>...</li></ul> para os dados de serviço. "
        "A estrutura preferencial é: abertura curta; contexto competitivo se houver fato; Como chega o mandante; Como chega o visitante; "
        "prováveis escalações SOMENTE se os 11 jogadores e técnicos de ambos os clubes estiverem nos fatos; retrospecto proporcional à amostra; Onde assistir SOMENTE se houver emissora ou plataforma confirmada; fechamento somente se houver fato novo. "
        "Use a forma recente de cada time uma única vez. Não repita os mesmos placares ou o balanço de vitórias/empates/derrotas no fechamento. "
        "Se as duas prováveis escalações forem fornecidas, apresente-as em um único bloco de lista, uma entrada por equipe, com 11 jogadores e técnico. Se faltarem, não crie o subtítulo Prováveis escalações nem um aviso sobre a ausência. "
        "Cada entrada deve começar por Provável escalação do nome da equipe, conter os 11 jogadores e o técnico. "
        "Nesse caso é proibido dizer que não há provável escalação; use no máximo uma ressalva curta de que as formações são prováveis. "
        "Se o retrospecto tiver só um ou dois jogos, trate-o em um bloco curto e não transforme a amostra em história ampla ou rivalidade. "
        "Só crie Onde assistir quando houver transmissor confirmado; nesse caso escreva explicitamente cada emissora/plataforma. Caso contrário, não abra essa seção. "
        "Não recapitule serviço, resultados, escalações e retrospecto no encerramento. Limite-se a até oito subtítulos informativos; nunca crie seções chamadas Resumo do encontro, Últimas linhas antes da partida, Informações principais ou Fechamento. Não repita jogos, balanços ou fichas de serviço com palavras diferentes. "
        "Insira exatamente uma vez o link interno aprovado, com âncora textual natural, e não crie nenhum outro link. "
        "É expressamente proibido citar fontes, sites, portais, veículos, consultas ou processos internos. "
        "Declarar um campo em fact_fields_used não basta: todo campo de required_fact_fields deve aparecer de forma visível e inequívoca no body_html. "
        "Busque entre 750 e 900 palavras visíveis, visando o topo da faixa. O mínimo absoluto é 700. "
        "Tags HTML, chaves JSON e fact_fields_used não contam como palavras. Não alongue o texto com generalidades para atingir tamanho. "
        "Se os fatos não sustentarem uma seção, omita a seção; se não sustentarem 700 palavras sem repetição ou inferência, recuse a redação pelo pipeline. "
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
        "Sintetize jornalisticamente os fatos: não copie rótulos técnicos nem transforme cada campo em uma frase isolada. "
        "Todos os campos factuais de required_fact_fields devem aparecer sem alteração de sentido no body_html; listá-los apenas em fact_fields_used não conta. "
        "Ausência de campo não autoriza afirmar que a informação está pendente ou não foi divulgada. "
        "Se houver transmission, cada emissora/plataforma confirmada deve aparecer explicitamente em Onde assistir; caso contrário, omita Onde assistir por completo. "
        "Se houver home_lineup e away_lineup, mostre todos os jogadores e técnicos; se faltarem, não crie seção Prováveis escalações e não explique a ausência. "
        "Alvo editorial: 750 a 900 palavras, sempre sem repetição, preenchimento genérico ou inferência factual; mínimo absoluto de 700. "
        "Antes de finalizar, confira: cinco <p><strong>subtítulos</strong></p>, lista <ul><li>, "
        "exatamente um <a href=...> com competition_internal_link.url e todos os fatos obrigatórios no corpo.\n\n"
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


def generate_validated_draft(contract, provider_config, site_config, *, api_key, audit_path):
    """Até duas chamadas no total, com diagnóstico e custo também das rejeitadas."""
    provider = provider_config["provider"]
    limit = min(int(provider.get("max_attempts", 2)),
                int(provider_config["scope"].get("max_provider_calls_per_article", 2)))
    if not 1 <= limit <= 2:
        fail("Limite total de chamadas por redação inválido.")
    payload = build_request(contract, provider_config)
    attempts = []
    errors = []
    for attempt in range(1, limit + 1):
        response = {}
        draft = None
        retryable = True
        try:
            response = post_json(provider["endpoint"], api_key, payload,
                                 timeout=int(provider.get("timeout_seconds", 120)))
            if response.get("status") == "incomplete":
                reason = (response.get("incomplete_details") or {}).get("reason")
                errors = [f"Resposta incompleta: {reason or 'motivo não informado'}"]
                retryable = reason == "max_output_tokens"
            else:
                try:
                    draft = parse_draft(response)
                    validated, errors = validate.validate_draft(draft, contract, config=site_config)
                except SystemExit:
                    errors = ["Resposta sem JSON editorial completo e utilizável"]
                    retryable = not bool(response.get("error"))
                    if any(c.get("type") == "refusal" for o in response.get("output", [])
                           for c in o.get("content", [])):
                        retryable = False
        except RuntimeError as exc:
            errors = [str(exc)]
            code = response_http_code(exc)
            retryable = code in RETRYABLE_HTTP or code is None
        attempts.append({
            "attempt": attempt, "response_id": response.get("id"),
            "status": response.get("status"),
            "incomplete_details": response.get("incomplete_details"),
            "usage": usage_summary(response),
            "estimated_cost_usd": estimate_usage_cost_usd(response, provider_config),
            "validation_errors": errors,
        })
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps({"slug": contract["slug"], "attempts": attempts,
            "draft_validated": not errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not errors:
            return response, validated, attempts
        print(f"REDAÇÃO {attempt}/{limit} rejeitada: " + "; ".join(errors), flush=True)
        if not retryable or attempt == limit:
            break
        # Corrige a redação usando o contrato como única fonte de fatos.
        payload = build_request(contract, provider_config)
        revision = ""
        if isinstance(draft, dict):
            # Texto gerado é material a revisar, nunca evidência factual.
            payload["input"].append({"role": "assistant", "content": [
                {"type": "output_text", "text": json.dumps(draft, ensure_ascii=False)}]})
            count = validate.word_count(str(draft.get("body_html", "")))
            minimum = int(contract.get("output_contract", {}).get("minimum_words", 700))
            if count < minimum:
                revision = (f" A contagem automática encontrou {count} palavras visíveis. "
                            f"Acrescente ao menos {max(150, 850 - count)} palavras factuais ao texto, "
                            "desenvolvendo resultados, datas, adversários e contexto que constam do contrato "
                            "e ainda não foram apresentados. Preserve os trechos corretos. "
                            "Não repita fatos, não invente cenários e não crie conclusões táticas.")
        payload["input"].append({"role": "user", "content": [{"type": "input_text", "text":
            "O texto anterior é um rascunho NÃO validado, não uma fonte de fatos. "
            "A tentativa anterior foi rejeitada. Redija novamente o objeto completo usando SOMENTE "
            "o contrato original, corrigindo estes erros de validação: " + "; ".join(errors) + revision +
            ". Preserve as travas factuais: não invente fatos nem acrescente texto genérico para atingir 700 palavras."}]})
    fail("Rascunho não aprovado após o limite de chamadas: " + "; ".join(errors))


def extract_output_text(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        fail("Resposta da API inválida.")
    if response.get("error"):
        fail(f"Responses API retornou erro: {response.get('error')}")
    status = response.get("status")
    if status not in {"completed", None}:
        fail(f"Resposta do modelo não foi concluída: status={status!r}; motivo={response.get('incomplete_details')!r}")

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

    response, validated, attempts = generate_validated_draft(
        contract, provider_config, site_config, api_key=api_key,
        audit_path=output_root / "redacao-tentativas" / basename,
    )

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
        "estimated_cost_usd": round(sum(a["estimated_cost_usd"] or 0 for a in attempts), 6),
        "attempts": attempts,
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
