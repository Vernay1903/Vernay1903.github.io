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
    "será", "sera", "são", "sao", "um", "uma", "pela", "pelo", "foi", "foram",
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


def fact_texts(contract: dict[str, Any], requirement_id: str) -> list[str]:
    groups = contract.get("facts_by_requirement")
    if not isinstance(groups, list):
        fail("Contrato sem facts_by_requirement válido.")
    for group in groups:
        if not isinstance(group, dict) or group.get("id") != requirement_id:
            continue
        facts = group.get("facts")
        if not isinstance(facts, list):
            break
        result = []
        for fact in facts:
            if isinstance(fact, dict) and isinstance(fact.get("text"), str) and fact["text"].strip():
                result.append(fact["text"].strip())
        if result:
            return result
        break
    fail(f"Contrato sem fatos para o requisito {requirement_id}.")


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
                "raw": chunk,
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
        available = token_set(record["text"])
        score = len(wanted & available)
        if score > best_score:
            best_score = score
            best_index = int(record["index"])

    minimum = 2 if len(wanted) <= 4 else 3
    if best_score < minimum:
        fail(f"Não foi possível localizar semanticamente no rascunho o fato: {fact}")
    return best_index, best_score


def placement_points(body: str, contract: dict[str, Any]) -> tuple[list[int], dict[str, Any]]:
    records = section_records(body)

    # Anúncio 1: depois da abertura e da primeira seção substantiva.
    first_point = int(records[0]["end"])

    # Anúncio 2: depois de os dois momentos recentes terem sido tratados.
    form_facts = fact_texts(contract, "recent_form_both_teams")
    form_matches = [best_section_for_fact(records, fact) for fact in form_facts]
    form_last_index = max(index for index, _score in form_matches)
    second_point = int(records[form_last_index]["end"])

    # Anúncio 3: depois do retrospecto específico da competição e antes da seção seguinte.
    h2h_facts = fact_texts(contract, "competition_specific_head_to_head")
    h2h_matches = [best_section_for_fact(records, fact) for fact in h2h_facts]
    score_by_section: dict[int, int] = {}
    for index, score in h2h_matches:
        score_by_section[index] = score_by_section.get(index, 0) + score
    h2h_index = max(score_by_section, key=score_by_section.get)
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
    if rendered.count(selected_image) != 1:
        fail("HTML final da prévia não contém exatamente a imagem selecionada.")
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
