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
    # Os campos estruturados incluem dez placares, métricas correlatas e
    # fatos históricos opcionais. Exigir TODOS no texto obrigava repetição
    # e promovia notícias periféricas. Somente os fatos de serviço, gancho
    # competitivo, síntese recente e pelo menos um fato de CADA clube
    # devem aparecer. Os demais continuam disponíveis, mas são opcionais.
    high_priority = (
        "stadium", "referee", "transmission", "qualification_scenario",
        "home_lineup", "away_lineup", "home_coach", "away_coach",
        "home_recent_form", "away_recent_form",
    )
    required_fact_fields = [x for x in high_priority if x in fact_fields]
    for side in ("home", "away"):
        specific = next((
            field for field in fact_fields
            if field.startswith((f"{side}_team_news_", f"{side}_stakes_"))
        ), None)
        if specific and specific not in required_fact_fields:
            required_fact_fields.append(specific)
    if not required_fact_fields:
        required_fact_fields = fact_fields[:2]

    # Define um roteiro conforme os dados reais; a referência editorial é
    # estrutura de escrita, jamais uma fonte de fatos de outro confronto.
    verified_facts = {
        item.get("field"): str(item.get("text", ""))
        for req in clean_package.get("facts_by_requirement", [])
        if isinstance(req, dict) and req.get("status") == "verified"
        for item in req.get("facts", [])
        if isinstance(item, dict) and isinstance(item.get("field"), str)
    }
    has_team_news = any(key.startswith(("home_team_news_", "away_team_news_"))
                        for key in verified_facts)
    has_results = all(verified_facts.get(key) for key in (
        "home_recent_matches", "away_recent_matches",
    ))
    narrative_mode = (
        "preparacao_com_elenco" if has_team_news else
        "pauta_competitiva" if any(k.startswith(("home_stakes_", "away_stakes_")) for k in verified_facts) else
        "historico_factual_de_resultados" if has_results else
        "fatos_confirmados_da_partida"
    )
    # Curadoria determinística: é a notícia verificada, não o placar médio,
    # que define a abertura. Referenciar campos, sem duplicar texto/proveniência.
    home_news_fields = sorted(k for k in verified_facts if k.startswith("home_team_news_"))
    away_news_fields = sorted(k for k in verified_facts if k.startswith("away_team_news_"))
    home_stakes_fields = sorted(k for k in verified_facts if k.startswith("home_stakes_"))
    away_stakes_fields = sorted(k for k in verified_facts if k.startswith("away_stakes_"))
    other_stakes = sorted(k for k in verified_facts
                          if k.startswith(("stakes_", "qualification_"))
                          or k in {"competitive_context", "standings_context", "qualification_scenario"})
    # O or anterior parava se houvesse notícia de apenas UM clube,
    # apagando do gancho de abertura os fatos atuais do adversário.
    def relevant_stakes(fields: list[str]) -> list[str]:
        opponent = str(context.get("away") or "")
        def rank(field: str) -> tuple[int, int, str]:
            value = str(verified_facts.get(field) or "").casefold()
            health = any(token in value for token in (
                "lesion", "exame", "dúvida", "duvida", "trein", "retorn",
                "poup", "suspens", "desfal"
            ))
            continent = "semifinal" in value or "libertadores" in value
            other_classic = "clássico contra" in value or "classico contra" in value
            return (0 if health else 1 if continent else 3 if other_classic else 2,
                    0 if "individual" in field else 1, field)
        return sorted(fields, key=rank)
    home_priority = relevant_stakes(home_stakes_fields)
    away_priority = relevant_stakes(away_stakes_fields)
    hook_fields = (
        (home_news_fields[:1] or home_priority[:1])
        + (away_news_fields[:1] or away_priority[:1])
    ) or other_stakes[:1]
    editorial_fact_hierarchy = {
        "opening_hook_fields": hook_fields,
        "home_specific_preparation_fields": home_news_fields[:2] + home_priority[:3],
        "away_specific_preparation_fields": away_news_fields[:2] + away_priority[:3],
        "match_stakes_fields": other_stakes[:2],
        "background_only_fields": ["home_recent_matches", "away_recent_matches",
                                  "home_recent_form", "away_recent_form",
                                  "h2h_games", "h2h_home_wins", "h2h_away_wins", "h2h_draws"],
        "editorial_rule": (
            "Começar pela notícia atual priorizada e pelas características específicas da partida. "
            "Usar a cronologia de resultados apenas como apoio, nunca como enredo principal. "
            "Cada bloco traz fatos diferentes, sem duplicar a abertura."
        ),
    }

    popular_home = str(context.get("display_home") or context.get("home") or "mandante")
    popular_away = str(context.get("display_away") or context.get("away") or "visitante")
    competition = str(context.get("competition") or "competição")
    rivalry = context.get("editorial_rivalry")
    rivalry = rivalry if isinstance(rivalry, dict) else None
    section_plan = [
        (f"{rivalry['name']}: contexto do confronto" if rivalry else "Contexto do confronto"),
        f"Como chega o {popular_home}",
        f"Como chega o {popular_away}",
    ]
    has_direct_history = any(
        key.startswith(("h2h_", "games", "home_wins", "away_wins", "draws"))
        for key in verified_facts
    )
    if has_direct_history:
        section_plan.append(f"Retrospecto entre {popular_home} e {popular_away}")
    # A forma recente pertence aos blocos Como chega; criar outra seção
    # só para cumprir cinco subtítulos obrigava recontar V/E/D e placares.
    # Melhor quatro seções informativas do que cinco com duplicação.
    if all(verified_facts.get(field) for field in (
        "home_lineup", "away_lineup", "home_coach", "away_coach",
    )):
        section_plan.append("Prováveis escalações")
    section_plan.append("Horário e local da partida")
    if verified_facts.get("transmission"):
        section_plan.append("Onde assistir")
    # Nunca abrir seções vazias para satisfazer contagens artificiais.
    # Cabe ao redator desenvolver apenas fatos que existam no contrato.
    contract = {
        "editorial_quality_revision": "classicos-contextuais-2026-10-11-v1",
        "editorial_section_plan": section_plan,
        "editorial_fact_hierarchy": editorial_fact_hierarchy,
        "editorial_storyline": (
            {
                "rivalry_name": rivalry["name"],
                "rivalry_kind": rivalry["kind"],
                "established_background": rivalry["background"],
                "editorial_angle": rivalry["angle"],
                "required_opening_reference": rivalry["name"],
                "require_verified_current_news": True,
                "warning": (
                    "O apelido e a natureza da rivalidade são contexto histórico estável. "
                    "Nada aqui autoriza inventar gols, tabelas, personagens, resultados ou notícias de vestiário."
                ),
            } if rivalry else None
        ),
        "editorial_narrative_mode": narrative_mode,
        "step": 25,
        "mode": "draft_contract_only",
        "slug": clean_package.get("slug"),
        "title": clean_package.get("title"),
        "excerpt": clean_package.get("excerpt"),
        "date": clean_package.get("date"),
        "match_context": deepcopy(context),
        "facts_by_requirement": deepcopy(clean_package.get("facts_by_requirement", [])),
        "competition_internal_link": deepcopy(internal_link),
        "required_fact_fields": required_fact_fields,
        "allowed_fact_fields": fact_fields,
        "output_contract": {
            "format": "json",
            "required_fields": ["slug", "body_html", "fact_fields_used"],
            "body_html_scope": "article_body_only",
            "minimum_words": int(config["article"]["min_words"]),
            "preferred_word_range": [750, 900],
            "maximum_words": 1400,
            "minimum_strong_subheadings": min(5, max(4, len(section_plan))),
            "internal_link_exactly_once": True,
            "unordered_lists_for_service_blocks": True,
        },
        "editorial_rules": {
            "language": "pt-BR",
            "team_names": (
                "Usar sempre o nome jornalístico mais comum de cada clube. "
                "No título, no texto e nos subtítulos, preferir match_context.display_home "
                "e match_context.display_away, quando existirem. "
                "Exemplos: Liverpool, Flamengo, Fluminense, Internacional e Corinthians; "
                "não Liverpool FC, Clube de Regatas do Flamengo, Fluminense FC, "
                "SC Internacional ou SC Corinthians Paulista. "
                "A identificação formal do provedor não deve aparecer na prosa."
            ),
            "tone": "jornalístico direto, fluido e factual",
            "rivalry": (
                "Se editorial_storyline estiver presente, o PRIMEIRO parágrafo deve nomear "
                "naturalmente a rivalidade (Gre-Nal, Fla-Flu, Derby Paulista, El Clásico etc.) "
                "e relacioná-la ao dado ATUAL verificado mais relevante para a partida. "
                "A abertura precisa parecer uma reportagem sobre ESTE clássico, nunca sobre "
                "dois clubes quaisquer. Explique a natureza da rivalidade em no máximo um "
                "trecho curto: história geral não substitui fatos de preparação atuais. "
                "Nunca trate Liverpool x Manchester City como clássico de Merseyside ou "
                "Dérbi de Manchester. Não invente episódios históricos."
            ),
            "seo": "natural, sem repetição artificial de palavras-chave",
            "opening": (
                "Abrir em um ou dois parágrafos com confronto, data, horário de Brasília, estádio, competição "
                "e um gancho esportivo concreto já presente nos fatos. Não despejar estatísticas nem antecipar "
                "toda a ficha de serviço na abertura."
            ),
            "approved_model": (
                "Seguir a estrutura da prévia aprovada LDU x Palmeiras (16/09/2026), que explicou a eliminatória, preparação específica e alterações dos times: abertura factual curta; contexto da partida "
                "somente quando houver fato verificável; Como chega o mandante; Como chega o visitante; prováveis "
                "escalações em bloco apenas com 11 nomes por time verificados; retrospecto proporcional ao tamanho real da amostra; Onde assistir apenas com transmissão confirmada; e fechamento "
                "apenas se houver uma consequência, cenário ou próximo jogo realmente fornecido no contrato."
            ),
            "concrete_prose_and_dated_history": "Apresente notícias de elenco diretamente, com sujeito e ação: quem retorna, quem é dúvida e por qual motivo confirmado. Não introduza esses fatos com rótulos como 'duas equipes com notícias distintas de elenco' ou comparações artificiais entre situações sem relação. Não transforme ausência de informação sobre lesões em afirmação de que não há novas baixas. Um episódio histórico específico deve informar a temporada (AAAA/AA), o ano ou a data confirmados e explicar objetivamente o que aconteceu e sua relação com o confronto. Se a referência temporal não estiver nos fatos, omita o episódio; nunca complete pela memória nem use 'na ocasião recordada' ou 'em uma lembrança ligada a' para esconder a falta de data. Não use metáforas ou comentários sobre a própria narrativa, como 'o passado serve como moldura' ou 'a preparação atual coloca a condição física dos jogadores no centro da véspera'. Não imponha ligação causal entre um resultado antigo e a preparação atual. Preserve a abertura factual que funciona, acrescente apenas contexto concreto e deixe os detalhes de elenco para o bloco de cada equipe quando alongarem a introdução.",
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
                "Reproduzir a ESTRUTURA jornalística aprovada com os fatos da partida vigente. "
                "Se editorial_narrative_mode=preparacao_com_elenco, inserir notícias de elenco verificadas "
                "nas seções de cada clube. Em qualquer modo, seguir editorial_fact_hierarchy: "
                "notícia de preparação atual e contexto competitivo antes de forma recente. "
                "Os dez placares recentes NUNCA são enredo principal, nem justificam 700 palavras; "
                "apenas ilustram fatos esportivos, sem virar cronologia maçante. "
                "Separar casa/fora apenas quando explicitamente mostrado nos placares "
                "e tratar o retrospecto direto em um único "
                "bloco proporcional à amostra. Não transformar os dez placares em dez parágrafos iguais. "
                "Nunca reutilizar informações da matéria LDU x Palmeiras como se fossem deste jogo. "
                "Não inferir estilo de jogo, posse, pressão, transições, estratégia, motivação, comportamento "
                "tático ou efeito psicológico a partir de nomes, escalações, mando ou resultados. "
                "Se os dados não sustentarem 700 palavras sem redundância, falhar a validação, não completar com imaginação."
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
                "Se home_lineup e away_lineup não existem com 11 jogadores e técnicos verificados, omitir o bloco por completo sem falar de informações ausentes. Se existem, é proibido dizer que não há provável escalação disponível. "
                "Usar no máximo uma ressalva curta de que as formações são prováveis e podem mudar até a confirmação oficial."
            ),
            "head_to_head": (
                "O retrospecto deve ser proporcional à amostra disponível. Se houver apenas um ou dois jogos no conjunto fornecido, "
                "usar um bloco curto — um parágrafo ou lista — e deixar claro apenas que se trata de uma amostra limitada, sem "
                "transformá-la em narrativa histórica ou rivalidade ampla. Nunca expandir números pequenos para preencher texto."
            ),
            "where_to_watch": (
                "Concentrar a emissora/plataforma confirmada no bloco Onde assistir. Se não houver plataforma confirmada, omitir esse bloco. Não repetir toda a ficha de serviço antes e depois."
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
