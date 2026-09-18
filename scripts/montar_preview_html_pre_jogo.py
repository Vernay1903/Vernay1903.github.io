#!/usr/bin/env python3
"""Monta a prévia HTML completa do Passo 27 sem publicar nada.

Entrada:
- rascunho real já validado no Passo 26;
- contrato editorial limpo do Passo 25.

Saída:
- somente build/pre-jogo/previews/;
- metadados somente em build/pre-jogo/preview-metadata/.

Este script NÃO escreve na raiz do site, NÃO altera noticias.json, sitemap.xml,
agenda.json ou qualquer HTML publicado.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import gerar_pre_jogo as page_builder  # noqa: E402
from scripts import validar_rascunho_pre_jogo as draft_validator  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"
ADS = [
    ROOT / "templates" / "anuncios" / "01-artigo-topo.html",
    ROOT / "templates" / "anuncios" / "02-artigo-meio.html",
    ROOT / "templates" / "anuncios" / "03-artigo-fim.html",
]
HEADING_RE = re.compile(
    r"<p\s*>\s*<strong\s*>(.*?)</strong>\s*</p\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[a-z0-9À-ÿ]+", flags=re.IGNORECASE)
FORBIDDEN_PREEXISTING_AD_RE = re.compile(
    r"(?:data-ad-slot\s*=|class=[\"'][^\"']*adsbygoogle|ANÚNCIO\s*\(ARTIGO)",
    flags=re.IGNORECASE,
)
STOPWORDS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos", "e", "em",
    "no", "nos", "na", "nas", "o", "os", "para", "pela", "pelo", "por", "que",
    "sera", "sao", "um", "uma", "foi", "foram",
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


def normalize_text(value: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def token_set(value: str) -> set[str]:
    return {
        token.casefold()
        for token in WORD_RE.findall(normalize_text(value))
        if len(token) >= 2 and token.casefold() not in STOPWORDS
    }


def fact_items(contract: dict[str, Any], requirement_id: str) -> list[dict[str, str]]:
    groups = contract.get("facts_by_requirement")
    if not isinstance(groups, list):
        fail("Contrato sem facts_by_requirement válido.")
    for group in groups:
        if not isinstance(group, dict) or group.get("id") != requirement_id:
            continue
        facts = group.get("facts")
        if not isinstance(facts, list):
            break
        result: list[dict[str, str]] = []
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            text = fact.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            row = {"text": text.strip()}
            field = fact.get("field")
            if isinstance(field, str) and field.strip():
                row["field"] = field.strip()
            result.append(row)
        if result:
            return result
        break
    fail(f"Contrato sem fatos para o requisito {requirement_id}.")


def fact_texts(contract: dict[str, Any], requirement_id: str) -> list[str]:
    return [item["text"] for item in fact_items(contract, requirement_id)]


def record_mentions_team(record: dict[str, Any], team: str) -> bool:
    wanted = {
        token
        for token in token_set(team)
        if token not in {"fc", "cf", "sc", "ac", "afc", "1"}
    }
    if not wanted:
        wanted = token_set(team)
    return bool(wanted & token_set(str(record.get("text", ""))))


H2H_HEADING_MARKERS = (
    "retrospecto",
    "historico",
    "histórico",
    "confrontos",
    "confronto direto",
    "head to head",
    "duelos",
    "bilanz",
)


def h2h_section_index(records: list[dict[str, Any]], contract: dict[str, Any]) -> int:
    for record in records:
        heading = str(record.get("heading", ""))
        if any(normalize_text(marker) in heading for marker in H2H_HEADING_MARKERS):
            return int(record["index"])

    # Fallback conservador para títulos criativos: a seção precisa conter um
    # marcador explícito de retrospecto além de sobrepor os fatos numéricos.
    h2h_facts = fact_texts(contract, "competition_specific_head_to_head")
    candidates: list[tuple[int, int]] = []
    for record in records:
        text = str(record.get("text", ""))
        if not any(normalize_text(marker) in text for marker in H2H_HEADING_MARKERS):
            continue
        score = sum(len(token_set(fact) & token_set(text)) for fact in h2h_facts)
        candidates.append((int(record["index"]), score))
    if not candidates:
        fail("Não foi possível localizar a seção de retrospecto/H2H no rascunho.")
    return max(candidates, key=lambda item: item[1])[0]


def load_ad_blocks() -> list[str]:
    blocks = []
    for path in ADS:
        try:
            block = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            fail(f"Bloco fixo de anúncio não encontrado: {path}")
        if block.count('data-ad-slot="8702501261"') != 1:
            fail(f"Bloco de anúncio inválido: {path}")
        if 'data-ad-client="ca-pub-4145492637375431"' not in block:
            fail(f"Cliente AdSense inesperado em {path}")
        if 'data-full-width-responsive="false"' not in block:
            fail(f"Bloco de anúncio fora do padrão mestre: {path}")
        blocks.append(block)
    return blocks


def section_records(body: str) -> list[dict[str, Any]]:
    matches = list(HEADING_RE.finditer(body))
    if len(matches) < 5:
        fail("Rascunho sem subtítulos suficientes para posicionar os anúncios editorialmente.")

    records: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        chunk = body[match.start():end]
        records.append(
            {
                "index": index,
                "start": match.start(),
                "end": end,
                "heading": normalize_text(match.group(1)),
                "text": normalize_text(chunk),
            }
        )
    return records


def best_section_for_fact(records: list[dict[str, Any]], fact: str) -> tuple[int, int]:
    wanted = token_set(fact)
    if not wanted:
        fail(f"Fato sem tokens úteis para posicionamento editorial: {fact}")

    best_index = -1
    best_score = -1
    for record in records:
        score = len(wanted & token_set(record["text"]))
        if score > best_score:
            best_score = score
            best_index = int(record["index"])

    minimum = 2 if len(wanted) <= 4 else 3
    if best_score < minimum:
        fail(f"Não foi possível localizar semanticamente no rascunho o fato: {fact}")
    return best_index, best_score


def first_qualifying_section_for_fact(
    records: list[dict[str, Any]], fact: str, *, start_index: int = 0
) -> tuple[int, int]:
    """Localiza a primeira seção editorial que já resolve o fato.

    Isso evita que uma recapitulação no fim da matéria, por repetir o fato com
    palavras mais próximas do contrato, seja confundida com a seção principal.
    """
    wanted = token_set(fact)
    if not wanted:
        fail(f"Fato sem tokens úteis para posicionamento editorial: {fact}")

    minimum = 2 if len(wanted) <= 4 else 3
    best_score = -1
    for record in records:
        index = int(record["index"])
        if index < start_index:
            continue
        score = len(wanted & token_set(record["text"]))
        best_score = max(best_score, score)
        if score >= minimum:
            return index, score

    fail(
        "Não foi possível localizar a primeira seção editorial do fato: "
        f"{fact} (melhor pontuação={best_score})."
    )


def placement_points(body: str, contract: dict[str, Any]) -> tuple[list[int], dict[str, Any]]:
    records = section_records(body)

    # Anúncio 1: depois da abertura e da primeira seção substantiva.
    first_point = int(records[0]["end"])

    # Primeiro fixamos a seção real de H2H pela semântica do subtítulo. Números
    # isolados como 3, 1 e 5 aparecem em forma recente e não podem puxar o anúncio
    # final para a seção errada.
    h2h_index = h2h_section_index(records, contract)

    # Anúncio 2: somente depois de os DOIS times terem sua forma recente tratada.
    # Usa o field do contrato para exigir que a seção também mencione a equipe
    # correspondente e só procura antes do H2H.
    context = contract.get("match_context") if isinstance(contract.get("match_context"), dict) else {}
    home = context.get("home")
    away = context.get("away")
    form_items = fact_items(contract, "recent_form_both_teams")
    form_matches: list[tuple[int, int]] = []

    for item in form_items:
        fact = item["text"]
        field = item.get("field")
        team = home if field == "home_recent_form" else away if field == "away_recent_form" else None
        wanted = token_set(fact)
        minimum = 2 if len(wanted) <= 4 else 3
        matched: tuple[int, int] | None = None
        best_score = -1
        for record in records:
            index = int(record["index"])
            if index < 1 or index >= h2h_index:
                continue
            if isinstance(team, str) and team.strip() and not record_mentions_team(record, team):
                continue
            score = len(wanted & token_set(str(record["text"])))
            best_score = max(best_score, score)
            if score >= minimum:
                matched = (index, score)
                break
        if matched is None:
            fail(
                "Não foi possível localizar a forma recente antes do H2H para "
                f"{team or field or fact} (melhor pontuação={best_score})."
            )
        form_matches.append(matched)

    form_last_index = max(index for index, _score in form_matches)
    second_point = int(records[form_last_index]["end"])

    # Anúncio 3: depois do retrospecto específico da competição e antes da seção seguinte.
    third_point = int(records[h2h_index]["end"])
    if third_point >= len(body):
        fail("O retrospecto ficou como última seção; o anúncio final precisa anteceder uma seção conclusiva.")

    points = [first_point, second_point, third_point]
    if len(set(points)) != 3 or points != sorted(points):
        fail(
            "A ordem editorial do rascunho não permite os três anúncios sem colisão: "
            f"pontos={points}. O rascunho deve manter abertura/seção inicial, forma recente e H2H em ordem."
        )

    metadata = {
        "first_after_heading": records[0]["heading"],
        "recent_form_sections": [records[index]["heading"] for index, _score in form_matches],
        "h2h_section": records[h2h_index]["heading"],
        "points": points,
    }
    return points, metadata


def inject_ads(body: str, contract: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if FORBIDDEN_PREEXISTING_AD_RE.search(body):
        fail("O rascunho já contém anúncio; o Passo 27 exige corpo editorial limpo.")

    blocks = load_ad_blocks()
    points, metadata = placement_points(body, contract)
    enriched = body
    for point, block in sorted(zip(points, blocks), key=lambda item: item[0], reverse=True):
        enriched = enriched[:point].rstrip() + "\n\n" + block + "\n\n" + enriched[point:].lstrip()

    if enriched.count('data-ad-slot="8702501261"') != 3:
        fail("A prévia precisa conter exatamente três anúncios dentro do artigo.")
    return enriched, metadata


def ensure_output_dir(output_dir: Path) -> Path:
    allowed = (ROOT / "build" / "pre-jogo").resolve()
    resolved = output_dir.resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError:
        fail("Passo 27 só pode gravar dentro de build/pre-jogo/.")
    return resolved


def validate_source_draft(
    draft: dict[str, Any], contract: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    if draft.get("draft_validated") is not True:
        fail("O rascunho de origem não está marcado como validado pelo Passo 26.")
    if draft.get("draft_validation_errors") not in ([], None):
        fail("O rascunho de origem contém erros de validação registrados.")
    if draft.get("ready_for_html") is not False or draft.get("publication_unlocked") is not False:
        fail("O rascunho de origem não preservou as travas de HTML/publicação.")

    validated, errors = draft_validator.validate_draft(draft, contract, config=config)
    if errors:
        fail("Rascunho não passou na revalidação do Passo 27: " + "; ".join(errors))
    return validated


def build_preview(
    *, draft: dict[str, Any], contract: dict[str, Any], rotation_offset: int = 0
) -> tuple[str, dict[str, Any]]:
    config = page_builder.load_config()
    validated = validate_source_draft(draft, contract, config)

    title = page_builder.require_text(contract, "title")
    excerpt = page_builder.require_text(contract, "excerpt")
    date = page_builder.require_text(contract, "date")
    slug = page_builder.require_text(contract, "slug")
    page_builder.validate_date(date)
    page_builder.validate_slug(slug, config)

    body = page_builder.require_text(validated, "body_html")
    body_with_ads, ad_metadata = inject_ads(body, contract)

    image_index = page_builder.choose_image_index(config, rotation_offset)
    image_block = page_builder.load_image_block(config, image_index)
    selected_image = page_builder.image_items(config)[image_index]["filename"]

    rendered = page_builder.render(
        config=config,
        title=title,
        excerpt=excerpt,
        date=date,
        body_html=body_with_ads,
        image_block=image_block,
    )

    if rendered.count('data-ad-slot="8702501261"') != 3:
        fail("HTML final da prévia não preservou os três anúncios internos.")
    if rendered.count('data-ad-slot="5521804159"') != 1:
        fail("HTML final da prévia não preservou exatamente um anúncio de sidebar.")
    if rendered.count(f'<img src="{selected_image}"') != 1:
        fail("HTML final da prévia não contém exatamente uma tag <img> com a imagem selecionada.")
    if "{{" in rendered or "}}" in rendered:
        fail("HTML final da prévia contém placeholder não resolvido.")

    metadata = {
        "step": 27,
        "slug": slug,
        "source_draft_validated": True,
        "source_word_count": validated.get("word_count"),
        "selected_image": selected_image,
        "image_rotation_index": image_index,
        "in_body_ads": 3,
        "in_body_ad_slot": "8702501261",
        "sidebar_ad_slot": "5521804159",
        "ad_placement": ad_metadata,
        "preview_only": True,
        "ready_for_publication": False,
        "noticias_json_touched": False,
        "sitemap_xml_touched": False,
        "published_html_touched": False,
    }
    return rendered, metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monta prévia HTML completa do Passo 27 sem publicar.")
    parser.add_argument("--draft", required=True, type=Path, help="Rascunho real validado do Passo 26.")
    parser.add_argument("--contract", required=True, type=Path, help="Contrato editorial limpo do Passo 25.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rotation-offset", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = ensure_output_dir(args.output_dir)
    draft = load_json(args.draft)
    contract = load_json(args.contract)
    if not isinstance(draft, dict) or not isinstance(contract, dict):
        fail("Rascunho ou contrato inválido.")

    rendered, metadata = build_preview(
        draft=draft,
        contract=contract,
        rotation_offset=args.rotation_offset,
    )
    slug = metadata["slug"]
    preview_path = output_root / "previews" / slug
    metadata_path = output_root / "preview-metadata" / Path(slug).with_suffix(".json").name

    for path in (preview_path, metadata_path):
        if path.exists() and not args.force:
            fail(f"Saída do Passo 27 já existe: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    preview_path.write_text(rendered, encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("OK: prévia HTML completa do Passo 27 montada somente em build/.")
    print(f"Prévia: {preview_path.relative_to(ROOT)}")
    print(f"Imagem da rotação: {metadata['selected_image']}")
    print("Anúncios internos: 3")
    print("noticias.json alterado: não")
    print("sitemap.xml alterado: não")
    print("HTML publicado alterado: não")
    print("Publicação liberada: não")


if __name__ == "__main__":
    main()
