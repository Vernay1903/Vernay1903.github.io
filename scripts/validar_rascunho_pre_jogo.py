#!/usr/bin/env python3
"""Valida um rascunho editorial do Passo 25 e o mantém somente em build/.

A aprovação aqui NÃO libera HTML nem publicação. O objetivo é garantir contrato
editorial, extensão, link interno, subtítulos, listas e ausência de atribuição de
fontes antes de uma validação factual final do texto corrido.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validar_politica_editorial as editorial_policy  # noqa: E402

CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"
TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"\b[\wÀ-ÿ]+(?:[-’'][\wÀ-ÿ]+)*\b", re.UNICODE)
SUBHEADING_RE = re.compile(r"<p\s*>\s*<strong\s*>.+?</strong>\s*</p\s*>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
FORBIDDEN_TAG_RE = re.compile(
    r"<(?:html|head|body|article|script|style|iframe|img|ins|aside|header|footer|nav)\b",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")


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
        fail("config/pre-jogo.json inválido.")
    if config.get("timezone") != "America/Sao_Paulo":
        fail('O timezone deve permanecer "America/Sao_Paulo".')
    return config


def visible_text(body_html: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", body_html)).split())


def word_count(body_html: str) -> int:
    return len(WORD_RE.findall(visible_text(body_html)))


def folded_text(value: str) -> str:
    value = html.unescape(TAG_RE.sub(" ", value))
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", value.casefold()).split())


def required_service_body_errors(body: str, contract: dict[str, Any]) -> list[str]:
    """Confere presença real dos fatos prometidos, não só fact_fields_used."""
    title = folded_text(str(contract.get("title") or "") + " " + str(contract.get("excerpt") or ""))
    body_folded = folded_text(body)
    facts: dict[str, str] = {}
    for requirement in contract.get("facts_by_requirement", []):
        if not isinstance(requirement, dict) or requirement.get("status") != "verified":
            continue
        for fact in requirement.get("facts", []):
            if isinstance(fact, dict) and isinstance(fact.get("field"), str) and isinstance(fact.get("text"), str):
                facts[fact["field"]] = fact["text"]

    errors: list[str] = []
    if "transmissao" in title or "onde assistir" in title:
        transmission = facts.get("transmission", "")
        value = folded_text(transmission.split(":", 1)[-1].rstrip("."))
        if not value or value not in body_folded:
            errors.append("chamada promete transmissão, mas a emissora/plataforma confirmada não aparece no corpo")

    if "arbitragem" in title or "arbitro" in title:
        referee = facts.get("referee", "")
        value = folded_text(referee.split(":", 1)[-1].rstrip("."))
        if not value or value not in body_folded:
            errors.append("chamada promete arbitragem, mas o árbitro confirmado não aparece no corpo")

    if "escalac" in title:
        for field in ("home_lineup", "away_lineup"):
            lineup = facts.get(field, "")
            text = lineup.split(":", 1)[-1].rstrip(".")
            players = [
                re.sub(r"\\s*\\([^)]*\\)", "", p).strip()
                for p in re.split(r"[;,]", text)
                if p.strip()
            ]
            if len(players) < 11:
                errors.append(f"chamada promete escalações, mas {field} não contém 11 nomes")
                continue
            missing = [name for name in players if len(folded_text(name)) >= 3 and folded_text(name) not in body_folded]
            if missing:
                errors.append(f"escalação {field} incompleta no texto: {', '.join(missing[:4])}")
        for field in ("home_coach", "away_coach"):
            coach = facts.get(field, "")
            value = folded_text(coach.split(":", 1)[-1].rstrip("."))
            if not value or value not in body_folded:
                errors.append(f"técnico {field} não aparece no corpo")

        # Exigir duas listas identificáveis, além do texto visível dos nomes.
        items = re.findall(r"<li\\b[^>]*>(.*?)</li\\s*>", body, flags=re.IGNORECASE | re.DOTALL)
        probable_items = [item for item in items if "provav" in folded_text(item)]
        if len(probable_items) < 2:
            errors.append("prováveis escalações devem aparecer em duas entradas de lista identificadas")
    return errors


def validate_draft(
    draft: dict[str, Any],
    contract: dict[str, Any],
    *,
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    slug = draft.get("slug")
    if slug != contract.get("slug"):
        errors.append("slug do rascunho não corresponde ao contrato")

    body = draft.get("body_html")
    if not isinstance(body, str) or not body.strip():
        return deepcopy(draft), ["body_html ausente ou vazio"]
    body = body.strip()

    if FORBIDDEN_TAG_RE.search(body):
        errors.append("body_html contém estrutura, mídia, anúncio ou script proibido nesta etapa")
    if PLACEHOLDER_RE.search(body):
        errors.append("body_html contém placeholder não resolvido")

    count = word_count(body)
    minimum = int(contract.get("output_contract", {}).get("minimum_words", 700))
    if count < minimum:
        errors.append(f"rascunho tem {count} palavras; mínimo exigido é {minimum}")

    headings = SUBHEADING_RE.findall(body)
    minimum_headings = int(contract.get("output_contract", {}).get("minimum_strong_subheadings", 5))
    if len(headings) < minimum_headings:
        errors.append(
            f"rascunho tem {len(headings)} subtítulos <p><strong>; mínimo exigido é {minimum_headings}"
        )
    if config.get("editorial", {}).get("approved_pre_match_model"):
        forbidden = {
            "informacoes confirmadas para a partida",
            "o que observar no confronto",
            "resumo do pre jogo",
        }
        for heading in headings:
            if folded_text(heading) in forbidden:
                errors.append("subtítulo genérico repetitivo proibido pelo modelo aprovado: " + visible_text(heading))
        seen_paragraphs = set()
        for paragraph in re.findall(r"<p\\b[^>]*>(.*?)</p\\s*>", body, flags=re.IGNORECASE | re.DOTALL):
            normalized = folded_text(paragraph)
            if len(normalized) < 100:
                continue
            if normalized in seen_paragraphs:
                errors.append("o texto repete parágrafo inteiro para alongar a matéria")
                break
            seen_paragraphs.add(normalized)

    internal_link = contract.get("competition_internal_link")
    allowed_url = internal_link.get("url") if isinstance(internal_link, dict) else None
    links = HREF_RE.findall(body)
    if not isinstance(allowed_url, str) or not allowed_url:
        errors.append("contrato sem URL interna permitida")
    else:
        hrefs = [href.strip() for href, _anchor in links]
        if hrefs.count(allowed_url) != 1 or len(hrefs) != 1:
            errors.append("o corpo deve conter exatamente um link e ele deve ser o link interno aprovado")
        if links:
            anchor_visible = visible_text(links[0][1])
            if not anchor_visible or anchor_visible == allowed_url or len(anchor_visible.split()) < 2:
                errors.append("o link interno deve usar âncora textual natural, não URL crua")

    text = visible_text(body)
    if re.search(r"https?://", text, flags=re.IGNORECASE):
        errors.append("URL crua não pode aparecer no texto visível")

    policy_errors = editorial_policy.validate_body_policy(body, config)
    errors.extend(policy_errors)
    if config.get("editorial", {}).get("approved_pre_match_model"):
        errors.extend(required_service_body_errors(body, contract))

    if "<ul" not in body.lower() or "<li" not in body.lower():
        errors.append("o rascunho deve usar ao menos uma lista com bolinhas (<ul><li>)")

    required_fields = contract.get("required_fact_fields")
    used_fields = draft.get("fact_fields_used")
    if not isinstance(required_fields, list) or not all(isinstance(x, str) for x in required_fields):
        errors.append("contrato sem required_fact_fields válido")
        required_fields = []
    if not isinstance(used_fields, list) or not all(isinstance(x, str) for x in used_fields):
        errors.append("fact_fields_used ausente ou inválido")
        used_fields = []

    required_set = set(required_fields)
    used_set = set(used_fields)
    missing = sorted(required_set - used_set)
    unknown = sorted(used_set - required_set)
    if missing:
        errors.append("campos factuais declarados como não usados: " + ", ".join(missing))
    if unknown:
        errors.append("fact_fields_used contém campos não fornecidos pelo contrato: " + ", ".join(unknown))

    context = contract.get("match_context")
    if isinstance(context, dict):
        for key in ("home", "away"):
            value = context.get(key)
            if isinstance(value, str) and value.strip() and value.casefold() not in text.casefold():
                errors.append(f"o texto não menciona a equipe {value}")

    lineup_fields = {"home_lineup", "away_lineup"}
    if lineup_fields.issubset(required_set):
        if len(re.findall(r"<ul\b", body, flags=re.IGNORECASE)) < 2:
            errors.append("com escalações disponíveis, o rascunho deve ter pelo menos duas listas com bolinhas")

    validated = deepcopy(draft)
    validated["body_html"] = body
    validated["word_count"] = count
    validated["strong_subheading_count"] = len(headings)
    validated["internal_link_count"] = len(links)
    validated["draft_validation_errors"] = errors
    validated["draft_validated"] = not errors
    validated["ready_for_html"] = False
    validated["publication_unlocked"] = False
    validated["next_required_step"] = "semantic_factual_review_before_html"
    return validated, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida rascunho editorial sem gerar HTML ou publicar.")
    parser.add_argument("--contract", required=True, type=Path, help="Contrato de redação do Passo 25.")
    parser.add_argument("--draft", required=True, type=Path, help="Resposta JSON do redator.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída dentro de build/pre-jogo/.",
    )
    parser.add_argument("--force", action="store_true", help="Permite substituir rascunho validado em build/.")
    return parser.parse_args()


def main() -> None:
    args = parser_args = parse_args()
    config = load_config()
    contract = load_json(parser_args.contract)
    draft = load_json(parser_args.draft)
    if not isinstance(contract, dict) or not isinstance(draft, dict):
        fail("Contrato ou rascunho inválido.")

    validated, errors = validate_draft(draft, contract, config=config)
    if errors:
        fail("Rascunho rejeitado: " + "; ".join(errors))

    slug = validated.get("slug")
    if not isinstance(slug, str) or not slug.endswith(".html"):
        fail("Rascunho sem slug HTML válido.")
    destination = args.output_dir.resolve() / "rascunhos-validados" / Path(slug).with_suffix(".json").name
    if destination.exists() and not args.force:
        fail(f"Rascunho validado já existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: rascunho editorial aprovado nas travas estruturais do Passo 25.")
    print(f"Palavras: {validated['word_count']}")
    print(f"Subtítulos fortes: {validated['strong_subheading_count']}")
    print("Revisão factual semântica ainda necessária: sim")
    print("HTML liberado: não")
    print("Publicação liberada: não")


if __name__ == "__main__":
    main()
