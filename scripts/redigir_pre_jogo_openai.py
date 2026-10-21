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
import html
import re
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
from scripts import qualidade_editorial_pre_jogo as editorial_quality  # noqa: E402

PROVIDER_CONFIG_PATH = ROOT / "config" / "redacao-pre-jogo.json"
SITE_CONFIG_PATH = ROOT / "config" / "pre-jogo.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "pre-jogo"
PERSONA_EDITORIAL_PATH = ROOT / "config" / "persona-criador-de-materias-prejogo.txt"

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
    if contract.get("editorial_build_fingerprint") != prepare.editorial_build_fingerprint():
        fail("Contrato gerado com outra versão de redator, prompt ou validadores.")
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
    allowed = contract.get("allowed_fact_fields", unique_fields)
    if not isinstance(allowed, list) or not all(isinstance(x, str) for x in allowed):
        fail("allowed_fact_fields inválidos.")
    allowed = list(dict.fromkeys(allowed))
    if not set(unique_fields).issubset(allowed):
        fail("Fatos obrigatórios não estão presentes no conjunto permitido.")

    return {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "enum": [slug]},
            "body_html": {"type": "string", "minLength": 4400},
            "fact_fields_used": {
                "type": "array",
                "items": {"type": "string", "enum": allowed},
                "minItems": len(unique_fields),
                "maxItems": len(allowed),
            },
        },
        "required": ["slug", "body_html", "fact_fields_used"],
        "additionalProperties": False,
    }


def editorial_persona_instructions() -> str:
    """Carrega a personalidade fixada pelo editor, sem acessar GPTs ou fontes externos."""
    try:
        personality = PERSONA_EDITORIAL_PATH.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, UnicodeError) as exc:
        fail(f"Personalidade editorial obrigatória indisponível: {type(exc).__name__}")
    if len(personality) < 1800 or "CRIADOR DE MATÉRIAS" not in personality:
        fail("Personalidade editorial ausente, incompleta ou inválida.")
    return personality


def system_instructions() -> str:
    return (
        "Você é o redator automático de pré-jogo do Corte dos Esportes. "
        "PERSONALIDADE EDITORIAL PRIORITÁRIA (respeitando os requisitos técnicos e factuais do contrato):\n"
        + editorial_persona_instructions()
        + "\nFIM DA PERSONALIDADE; mantenha também as travas específicas a seguir. "
        "Use os nomes populares match_context.display_home e match_context.display_away no texto, "
        "subtítulos e serviços. Nunca adicione FC, SC, Clube de Regatas, Sport Club ou outros "
        "sufixos jurídicos quando o nome habitual for simples, como Liverpool, Flamengo "
        "ou Corinthians. Não reintroduza informações do jogo ou informações do confronto "
        "na chamada editorial quando só o horário estiver confirmado. "
        "Escreva em português do Brasil com tom jornalístico direto, fluido, factual e natural. "
        "REFERÊNCIA DE QUALIDADE APROVADA EM 14/10/2026: o texto revisto de Manchester City x PSG exemplifica a intenção editorial, não fornece fatos reutilizáveis. Construir uma narrativa que explique por que a partida importa: situação na competição, preparação específica de cada clube, protagonistas e um antecedente histórico relevante e datado, quando sustentados nos fatos. Integrar estatísticas a esse contexto em vez de comentar o conjunto de dados. Usar subtítulos descritivos, parágrafos com uma ideia central e listas para informações que realmente ganham clareza, sobretudo escalações. A quantidade e a ordem dos blocos devem acompanhar a pauta, sem obrigar seções de história, tática ou protagonistas em todos os jogos. Não copiar extensão nem criar excesso de parágrafos de uma frase; unir ideias relacionadas quando melhorar a fluidez. Contextualizar sem recontar os mesmos títulos, retornos ou resultados. O fechamento relaciona o confronto ao objetivo confirmado de cada equipe com concisão. Preservar serviços completos, imagem e linkagem previstos pelo fluxo. Toda afirmação factual ou tática exige suporte nos fatos da partida vigente; nunca importar nomes, títulos, treinadores ou estatísticas do exemplo. "
        "GUIA CONCRETO DE PROGRESSÃO DO MODELO APROVADO (não é fonte factual): " 
        "PRIMEIRO, o lide informa o fato atual e a consequência específica da partida; o segundo parágrafo aprofunda a situação, em vez de reformular data, fase e estádio. "
        "DEPOIS, um subtítulo com assunto real e verificável explica por que o encontro tem peso: vantagem, trajetória, liderança, recuperação, decisão ou outro gancho que de fato conste nos dados. "
        "Em seguida, mostre como CADA clube chegou até ali, distinguindo seus resultados relevantes, jogadores que condicionam a formação e notícias específicas de preparação. "
        "Nos modelos aprovados, episódios de confrontos anteriores aparecem com ano, placar e consequência esportiva; não basta dizer que há duas vitórias ou que o histórico é curto. "
        "Protagonistas só merecem bloco quando houver informação individual concreta; tática só entra quando o contrato confirmar características de jogo. "
        "Inclua as escalações em um único local, transmissão confirmada e um parágrafo final com efeito esportivo real, sem recontar a ficha do jogo. "
        "Se faltar um desses assuntos, NÃO fabrique o bloco: reestruture com os fatos existentes; se eles não formarem reportagem consistente, aceite a reprovação editorial. "
        "Critério por parágrafo: ou apresenta um episódio/fato novo ou explica sua consequência demonstrável; se repetir o lide ou apenas afirmar relevância, apague. "
        "Este guia resume a técnica de composição do modelo publicado LDU x Palmeiras (16/09) e do texto revisado City x PSG (14/10), e nenhum resultado ou atleta daqueles jogos pode ser reutilizado. "
        
        "RETROSPECTO: diferencie explicitamente os últimos N confrontos do histórico completo. Diga 'nos cinco encontros mais recentes', quando esse for o limite dos fatos, e não sugira que só houve cinco jogos. Informe o balanço uma única vez, omita categorias com zero e não traduza a ausência de empates em 'não há resultados iguais'. Não deduza 'equilíbrio competitivo' apenas das contagens nem explique que 'a amostra é exclusivamente continental'. Um episódio marcante deve trazer temporada/data confirmada e aparecer uma única vez, no bloco histórico. Não encerre o retrospecto repetindo retornos e dúvidas médicas já tratados. ENCERRAMENTO: planeje desde o início um parágrafo final curto de prosa, após os blocos de serviço, sem subtítulo 'Fechamento'. Reserve para ele um desdobramento esportivo confirmado: objetivo na tabela, cenário da eliminatória, próximo compromisso ou significado concreto da rodada. Não termine somente com uma lista de data, horário e local, nem repita essa lista em prosa. Não invente classificação ou consequência; use um fato pertinente do contrato e distribua-o para que o último parágrafo acrescente informação. Se não houver um desdobramento novo, encerre com o contexto competitivo confirmado mais relevante, reorganizando o texto para não repeti-lo. "
        "Nunca publique referências ao material interno de redação: 'o contrato não fornece uma escalação confirmada', 'o contrato não informa' e variantes são vazamentos do processo editorial, não notícias. Não anuncie a própria escrita com 'a notícia de elenco é igualmente direta'. Informe o retorno ou a disponibilidade do jogador diretamente; não acrescente 'amplia as opções do grupo', 'dá mais alternativas' ou outra consequência genérica apenas para prolongar o parágrafo. Uma consequência esportiva específica só entra se estiver sustentada nos fatos, sem suposição. Não confunda provável escalação com escalação oficial confirmada e não use a ausência desta para qualificar ou desvalorizar as informações disponíveis. "
        "META EDITORIAL: mínimo 80/100 pela qualidade dos fatos, cobertura dos dois clubes, profundidade útil, histórico pertinente e conclusão sem repetição — NÃO por títulos fixos ou cotas por seção. A composição, a ordem e o enfoque são decisões do jornalista. Nunca invente dados para melhorar a nota. "
        "NATURALIDADE E INFORMAÇÃO NOVA: não comente a organização dos dados com frases como 'esse resultado aparece como o antecedente continental mais recente do conjunto de partidas apresentado', 'ajuda a localizar a equipe' ou 'sequência que reúne compromissos nacionais e europeus'. Informe diretamente o resultado relevante, sua competição e a data somente quando necessária. Depois de informar uma vitória, não acrescente uma frase apenas para dizer que ela consta no recorte ou é um antecedente. Não retome em outro parágrafo uma vitória já citada, como a partida mais recente, apenas para reapresentar adversário, placar ou proximidade temporal. O intervalo entre partidas só merece destaque quando houver relevância factual específica, sem inferir desgaste, recuperação ou efeito físico. Use como critério informação nova e utilidade para compreender o confronto, não uma fórmula fixa nem número obrigatório de frases. Se retirar uma frase não eliminar informação esportiva relevante, prefira cortá-la. "
        "Apresente notícias de elenco diretamente, com sujeito e ação: quem retorna, quem é dúvida e por qual motivo confirmado. Não introduza esses fatos com rótulos como 'duas equipes com notícias distintas de elenco' ou comparações artificiais entre situações sem relação. Não transforme ausência de informação sobre lesões em afirmação de que não há novas baixas. Um episódio histórico específico deve informar a temporada (AAAA/AA), o ano ou a data confirmados e explicar objetivamente o que aconteceu e sua relação com o confronto. Se a referência temporal não estiver nos fatos, omita o episódio; nunca complete pela memória nem use 'na ocasião recordada' ou 'em uma lembrança ligada a' para esconder a falta de data. Não use metáforas ou comentários sobre a própria narrativa, como 'o passado serve como moldura' ou 'a preparação atual coloca a condição física dos jogadores no centro da véspera'. Não imponha ligação causal entre um resultado antigo e a preparação atual. Preserve a abertura factual que funciona, acrescente apenas contexto concreto e deixe os detalhes de elenco para o bloco de cada equipe quando alongarem a introdução. "
        "O contrato contém editorial_storyline, se for clássico ou rivalidade reconhecida. "
        "NESSE CASO a primeira frase ou primeiro parágrafo deve mencionar pelo nome o "
        "clássico (Gre-Nal, Fla-Flu, Derby Paulista etc.) e apresentar logo um fato ATUAL "
        "específico daquele jogo. Não basta encaixar uma palavra isolada: faça o texto "
        "fluir como cobertura da rivalidade real. Use established_background somente "
        "como fato histórico estável; não transforme isso em notícia nova. "
        "Os primeiros dois parágrafos devem estabelecer por que ESTE encontro importa, "
        "o que acontece com as equipes e o principal gancho factual verificado. "
        "Tratar Liverpool x Manchester City como rivalidade de Premier League, "
        "não como dérbi regional. "
        "Não use o mesmo molde de redação para todos os jogos e NÃO narre a lista "
        "dos cinco placares na abertura: selecione um ou dois jogos quando eles "
        "ajudarem a explicar um desfalque, sequência ou preparação. "
        "Use EXCLUSIVAMENTE os fatos e o contexto presentes no contrato. Não use memória, conhecimento externo, pesquisa, ferramentas ou navegação web. "
        "A ausência de uma informação no contrato NÃO é um fato: omita o assunto. Nunca escreva que algo não foi divulgado, não foi confirmado, "
        "está pendente ou será acrescentado depois, salvo quando essa indisponibilidade estiver explicitamente escrita como fato no contrato. "
        "Não invente desfalques, suspensões, lesões, escalações, jogadores, árbitros, números, resultados, datas, horários, estádios ou cenários. "
        "Não infira estilo de jogo, pressão, posse, transições, estratégia, motivação ou comportamento tático a partir de nomes, escalações, mando ou placares. "
        "CRÍTICO: não misture futebol profissional com Sub-20, Sub-17, equipes femininas ou categorias de base; "
        "notícias de outra categoria não descrevem o elenco profissional da partida. "
        "Se um título de reportagem trouxer um terceiro clube (por exemplo, Flamengo vence Fluminense), "
        "extraia somente a consequência efetiva para o clube da pauta: NUNCA mencione escalação ou titularidade "
        "de jogadores desse terceiro clube, nem atribua sua liderança ao time derrotado. "
        "É proibido explicar a seleção editorial ou usar expressões 'no pacote', 'informações fornecidas', "
        "'a amostra serve', 'principais fatos verificados', 'não há confrontos disponíveis'. "
        "Um parágrafo sobre cinco resultados não pode justificar repetição de serviço, estatísticas ou "
        "generalidades; caso a pauta seja curta, prefira conteúdo conciso fundamentado. "
        "REGRAS DE FLUIDEZ TESTADAS EM 21/10/2026: a publicação tem de soar como reportagem de um jornalista, não como relatório de extração. Nunca transforme rótulos internos, como 'Situação competitiva verificada do Arsenal' ou 'Contexto esportivo atual verificado do Real Madrid', em início de frase. Evite construir estatísticas com a fórmula 'nos últimos 2 jogos registrados nessa competição, 1 vitória, 1 empate e 0 derrotas': trata-se de uma amostra limitada de um provedor, não obrigatoriamente de todos os compromissos da temporada. Não copie expressões como 'jogos registrados', 'recorte consultado', '0 empates' ou '0 derrotas'. Se um balanço completo for útil, identifique o período e escreva apenas os resultados não nulos, de forma natural; na terceira rodada de uma competição, a análise pode mencionar os dois jogos ANTERIORES somente quando ambos estiverem efetivamente confirmados. Prefira destacar placar e adversário verificados ou uma notícia atual de preparação. Um episódio histórico começando por 'Na ocasião' não deve abrir o texto nem o resumo sem ano, adversário e relação clara com o jogo. Preserve a factualidade, escalações, emissoras e fatos de elenco que já funcionaram. "
        "Os fatos estruturados são matéria-prima: reescreva-os em linguagem jornalística natural. Nunca exponha linguagem de banco de dados ou API como "
        "'jogos concluídos registrados', 'resultados registrados', 'base considerada' ou 'recorte considerado'. "
        "Produza somente o corpo editorial, sem <html>, <head>, <body>, <article>, imagens, anúncios, scripts ou estilos. "
        "FORMATO TÉCNICO: subtítulos jornalísticos em <p><strong>...</strong></p>, com pelo menos output_contract.minimum_strong_subheadings e no máximo oito. Escolha livremente assuntos, ordem e títulos conforme os fatos; editorial_section_plan não obriga blocos. Não copie '(subtítulo específico a definir)' nem abra seção só para repetir serviço. Não use Markdown, <h2> ou <h3>. "
        "Inclua obrigatoriamente uma lista HTML <ul><li>...</li></ul> para os dados de serviço. "
        "MODELO JORNALÍSTICO APROVADO: a prévia LDU x Palmeiras (16/09/2026) abriu com a situação da eliminatória e seus desdobramentos, explicou a preparação específica dos clubes, incorporou retornos/desfalques ao contexto de cada equipe, reuniu escalações uma única vez, contextualizou o histórico, informou transmissão e fechou com consequência esportiva. " "PADRÃO NARRATIVO: no modelo aprovado, o início já explica POR QUE a partida é relevante, o próximo parágrafo entrega um desdobramento confirmado, e os blocos seguintes aprofundam com fatos diferentes. Compare mentalmente cada parágrafo com a abertura: se repetir o placar, horário, estádio, fase, ou a mesma notícia de elenco, reescreva ou retire. Nomeie o episódio histórico apenas quando houver data e resultado comprovados. A seção Como chega deve priorizar preparo/esporte, não logística de arquibancadas. Não crie um bloco apenas para informação de horário já presente no primeiro parágrafo. O padrão não é uma lista de checagem com 700 palavras: é uma reportagem orgânica em que cada parágrafo acrescenta um fato verificável ou explica seu impacto esportivo. " "NÃO copie fatos nem datas dessa referência: ela define apenas estilo e profundidade, e todos os fatos novos devem vir do contrato. " "A estrutura preferencial é: abertura curta; contexto competitivo se houver fato; Como chega o mandante; Como chega o visitante; "
        "prováveis escalações SOMENTE se os 11 jogadores e técnicos de ambos os clubes estiverem nos fatos; retrospecto proporcional à amostra; Onde assistir SOMENTE se houver emissora ou plataforma confirmada; fechamento somente se houver fato novo. "
        "ECONOMIA NA FORMA RECENTE: quando todos os jogos do recorte tiverem o mesmo resultado, informe apenas esse resultado e o total. 'Cinco vitórias nos últimos cinco jogos' já informa que não houve empates nem derrotas; nunca acrescente 'sem empates e sem derrotas', '100% de aproveitamento' ou outra reformulação equivalente à mesma informação. A mesma regra vale para sequências só de empates ou só de derrotas. Em campanhas mistas, omita categorias com zero e escreva apenas as contagens relevantes. Depois do balanço, selecione preferencialmente um resultado recente relevante e no máximo dois quando o segundo acrescentar contexto distinto; não desfile três, quatro ou cinco adversários e placares. Desenvolva o restante do bloco com notícias atuais confirmadas de preparação, retornos, dúvidas ou desfalques, sem repetir fatos da abertura e sem inventar material para completar extensão. "
        "REGRAS DE REPETIÇÃO: o balanço de vitórias, empates e derrotas de cada clube deve aparecer "
        "EXATAMENTE UMA VEZ, dentro do bloco Como chega daquele clube; não repita esse balanço "
        "na abertura, no contexto, no histórico nem na conclusão. Se apresentar um placar, "
        "não reescreva o mesmo placar em outra seção. "
        "A decisão de poupar titulares ou usar time misto deve ser explicada uma vez na abertura "
        "e no máximo uma vez no bloco do clube; jamais em quatro parágrafos com palavras trocadas. "
        "Para desenvolver 700 palavras, priorize fatos diferentes sobre jogadores, treinadores, "
        "recuperação, retornos, marcas individuais, situação de classificação e antecedentes "
        "efetivamente verificados em editorial_fact_hierarchy; não crie explicações genéricas. "
        "Siga editorial_fact_hierarchy do contrato: opening_hook_fields contém a notícia verificada "
        "prioritária para os dois primeiros parágrafos; use os fatos dos campos indicados literalmente "
        "como base, em linguagem própria. As seções Como chega precisam aprofundar os campos "
        "home_specific_preparation_fields e away_specific_preparation_fields, respectivamente. "
        "Os campos background_only_fields servem de apoio, nunca de pauta. "
        "Nos blocos Como chega, integre notícias verificadas sobre cada equipe quando o contrato as fornecer, "
        "independentemente de haver escalações completas. "
        "Se houver apenas os dez placares recentes e o confronto direto, não se trata de reportagem: "
        "a automação deve reprovar antes da redação, e o redator não deve encher páginas de estatísticas. "
        "Nunca use no texto as palavras 'contrato editorial', 'no contrato', 'contrato da partida' ou "
        "'esta matéria tem como compromisso': são comentários sobre o processo, não sobre futebol. "
        "Não retome a mesma decisão de poupar titulares em mais de dois parágrafos: contextualize-a "
        "uma vez na abertura e aprofunde-a uma vez no bloco da equipe com fatos diferentes. "
        "Se não houver notícia nova suficiente, não invente detalhes para cumprir 700 palavras. "
        "CRÍTICO: ao tratar dos cinco jogos anteriores, sintetize o balanço e cite no máximo duas partidas específicas de cada clube, com datas somente quando necessárias. "
        "É proibido enumerar quatro ou cinco resultados com suas datas em um único parágrafo; isso produz uma cronologia, não uma reportagem. "
        "Não repita essa sequência em um segundo bloco de retrospecto; se houver retrospecto, use exclusivamente confronto DIRETO verificado. "
        "Evite reutilizar cinco placares de meses atrás como prova de momento atual quando a notícia recente oferecer contexto específico. "
        "Não acrescente frases repetitivas para alcançar a contagem de palavras. " "Não transforme frases de divulgação do site-fonte em notícias de elenco. " "Use a forma recente de cada time uma única vez. Não repita os mesmos placares ou o balanço de vitórias/empates/derrotas no fechamento. "
        "Se as duas prováveis escalações forem fornecidas, apresente-as em um único bloco de lista, uma entrada por equipe, com 11 jogadores e técnico. Se faltarem, não crie o subtítulo Prováveis escalações nem um aviso sobre a ausência. "
        "Cada entrada deve começar por Provável escalação do nome da equipe, conter os 11 jogadores e o técnico. "
        "Nesse caso é proibido dizer que não há provável escalação; use no máximo uma ressalva curta de que as formações são prováveis. "
        "ATENÇÃO: cada escalação completa dos 11 atletas aparece EXATAMENTE UMA vez e somente em "
        "Prováveis escalações. NÃO repita qualquer lista integral de titulares em texto corrido, "
        "outra lista, abertura ou conclusão. Pode mencionar individualmente jogadores "
        "somente quando o contrato tiver informação específica sobre eles. "
        "Se o retrospecto tiver só um ou dois jogos, trate-o em um bloco curto e não transforme a amostra em história ampla ou rivalidade. "
        "Só crie Onde assistir quando houver transmissor confirmado; nesse caso escreva explicitamente cada emissora/plataforma. Caso contrário, não abra essa seção. "
        "Não recapitule serviço, resultados, escalações e retrospecto no encerramento. Cada parágrafo precisa trazer informação nova comprovada. "
        "São proibidos os subtítulos Fechamento, Resumo do encontro, Dados do confronto, "
        "Informações principais, Serviço do jogo, Últimas linhas antes da partida; use "
        "apenas seção com informação verificável, sem um resumo artificial. " "Máximo oito subtítulos informativos; proíba Resumo do encontro, Dados do confronto, Últimas linhas antes da partida, Informações principais, Serviço do jogo ou Fechamento. " "Uma escalação completa só pode aparecer dentro do bloco Prováveis escalações. " "Onde assistir deve ser curto, com emissoras confirmadas e horário, sem repetir data/estádio em várias seções. " "Não repita jogos, balanços ou fichas de serviço com palavras diferentes. "
        "Insira exatamente uma vez o link interno aprovado, com âncora textual natural, e não crie nenhum outro link. "
        "É expressamente proibido citar fontes, sites, portais, veículos, consultas ou processos internos. "
        "Os required_fact_fields são obrigatórios; os allowed_fact_fields adicionais são opcionais e só devem entrar se realmente acrescentarem informação. "
        "Não copie a lista de dez placares nem cada dado histórico só para preencher espaço. "
        "Declarar um campo em fact_fields_used não basta: todo campo de required_fact_fields deve aparecer de forma visível e inequívoca no body_html. "
        "Quando houver fatos suficientes, busque a profundidade do modelo aprovado (em geral, 950 a 1.250 palavras), sem atingir a faixa por enchimento ou repetições. O mínimo editorial técnico continua 700, mas não é selo de qualidade. "
        "Planeje a matéria conforme a relevância e a quantidade dos fatos de cada equipe, sem cotas fixas de palavras por seção. Não estique retrospectos curtos nem transforme cinco resultados em cinco assuntos. "
        "Tags HTML, chaves JSON e fact_fields_used não contam como palavras. Não alongue o texto com generalidades para atingir tamanho. "
        "Se o contrato trouxer apenas placares, retrospecto, escalações e serviço, não é reportagem completa: o pipeline deve bloquear antes da redação. Não preencha com generalidades. "
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
        "Leia editorial_fact_hierarchy antes de compor a abertura: use um fato atual do mandante "
        "e um do visitante, nunca o mesmo gancho duas vezes; toda contagem de vitórias, empates "
        "e derrotas aparece apenas no bloco Como chega da equipe correspondente. "
        "Dê prioridade a notícias individuais concretas sobre o momento atual, especialmente "
        "quando se referirem ao próximo jogo da Libertadores. "
        "Destaque os fatos verificáveis "
        "indicados por opening_hook_fields, preserve o protagonismo de cada time e trate os "
        "últimos cinco resultados como pano de fundo, não como notícia. "
        "PRIMEIRO decida o enfoque do confronto vigente usando editorial_storyline "
        "e os fatos atuais; se for clássico, use seu nome próprio já na abertura, "
        "e trate uma consequência esportiva concreta como a notícia, não uma soma "
        "de resultados. NÃO transfira dados de LDU x Palmeiras para o confronto. "
        "Sintetize jornalisticamente os fatos: não copie rótulos técnicos nem transforme cada campo em uma frase isolada. " "O modelo aprovado é reconhecível por contexto e progressão jornalística. Se só puder repetir situação do jogo, cinco resultados, uma notícia de escalação e serviço, NÃO simule uma reportagem de fôlego: a trava editorial rejeitará material insuficiente. "
        "Todos os campos factuais de required_fact_fields devem aparecer sem alteração de sentido no body_html; listá-los apenas em fact_fields_used não conta. "
        "Ausência de campo não autoriza afirmar que a informação está pendente ou não foi divulgada. "
        "Se houver transmission, cada emissora/plataforma confirmada deve aparecer explicitamente em Onde assistir; caso contrário, omita Onde assistir por completo. "
        "Se houver home_lineup e away_lineup, mostre todos os jogadores e técnicos; se faltarem, não crie seção Prováveis escalações e não explique a ausência. "
        "Alvo editorial: 950 a 1.250 palavras somente com material factual suficiente; mínimo técnico de 700 NÃO garante aprovação, e a ausência de pauta rica deve bloquear. "
        "Desenvolva Como chega com fatos atuais distintos de cada equipe, sem cotas por bloco ou enumeração dos cinco resultados. Nunca inclua um bloco sem fatos nem substitua detalhes por generalidades. "
        "editorial_section_plan contém apenas sugestões de assuntos, sem determinar cabeçalhos, ordem nem quantidade de blocos. Escolha a linha narrativa como editor: comece pelo fato esportivo mais importante e organize livremente os temas verificados. "
        "Use pelo menos output_contract.minimum_strong_subheadings e no máximo oito subtítulos <p><strong> realmente úteis, com nomes jornalísticos originais. Desenvolva os fatos "
        "de ambos os clubes sem obrigar duas seções Como chega: uma reportagem pode integrar assuntos quando isso melhorar a leitura. Retrospecto só quando pertinente; dados de serviço continuam claros. "
        "Só inclua blocos de transmissão e escalações se os respectivos fatos estiverem verificados. "
        "Nunca crie seções Fechamento, Resumo do encontro nem listas integrais de titulares fora da seção própria. "
        "Antes de finalizar, confira a quantidade de <p><strong>subtítulos</strong></p> exigida pelo contrato, lista <ul><li>, "
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


def build_revision_request(
    contract: dict[str, Any],
    provider_config: dict[str, Any],
    *,
    errors: list[str],
    previous_draft: dict[str, Any] | None,
) -> dict[str, Any]:
    """Segunda tentativa limpa: nunca devolve o texto inteiro rejeitado ao modelo."""
    payload = build_request(contract, provider_config)
    count = (
        validate.word_count(str(previous_draft.get("body_html", "")))
        if isinstance(previous_draft, dict) else 0
    )
    minimum = int(contract.get("output_contract", {}).get("minimum_words", 700))
    short = (
        f" A primeira tentativa ficou em {count} palavras, abaixo do mínimo de {minimum}. "
        "Replaneje o desenvolvimento conforme os fatos disponíveis, sem cotas de palavras por bloco. Não amplie retrospecto ou serviço por preenchimento. "
        "Detalhe datas, adversários, resultados e notícias concretas AINDA não contextualizados, "
        "sem listar placares repetidamente e sem inventar dados."
    ) if count and count < minimum else ""
    payload["input"].append({
        "role": "user",
        "content": [{
            "type": "input_text",
            "text": (
                "A resposta anterior foi rejeitada, mas não é enviada novamente nem constitui "
                "evidência. Produza um JSON editorial COMPLETO e novo utilizando SOMENTE "
                "os fatos do contrato. Corrija: " + "; ".join(errors) + ". " + short +
                focused_revision_guidance(errors) +
                " Reescreva com a profundidade suportada pelos fatos, mirando 950 a 1.250 palavras sem repetição, fontes externas ou "
                "inferências factuais. Trate editorial_section_plan como pauta OPCIONAL: escolha livremente ordem, subtítulos e extensão conforme a notícia, sem cumprir um índice mecânico. "
                "Não substitua o desenvolvimento esportivo dos dois clubes por generalidades da abertura. "
                "Use no máximo oito subtítulos e exatamente um link interno. "
                "Escreva os onze titulares de cada time uma única vez, dentro de Prováveis escalações, "
                "e evite a linguagem 'dados fornecidos', 'recorte considerado' ou 'registro'. "
                "Caso tenha saído incompleta por max_output_tokens, finalize o JSON respeitando 700 palavras sem preencher com generalidades, "
                "sem repetir conteúdo e sem novos dados."
            ),
        }],
    })
    return payload



def repair_verified_transmission(
    draft: dict[str, Any] | None,
    contract: dict[str, Any],
) -> dict[str, Any] | None:
    """Inclui somente serviço já validado caso a redação omita a emissora.

    Não cria transmissão, não altera escalações, placares ou contexto. O texto
    continua sujeito a TODOS os validadores antes de receber aprovação.
    """
    if not isinstance(draft, dict) or not isinstance(draft.get("body_html"), str):
        return None
    transmission = None
    for requirement in contract.get("facts_by_requirement", []):
        if not isinstance(requirement, dict) or requirement.get("status") != "verified":
            continue
        for fact in requirement.get("facts", []):
            if isinstance(fact, dict) and fact.get("field") == "transmission":
                raw = fact.get("text")
                if isinstance(raw, str) and raw.strip():
                    transmission = raw.strip()
                break
    if not transmission or len(transmission) > 350:
        return None
    body = draft["body_html"]
    # Serviço fica imediatamente antes do fechamento; não altera sua redação.
    paragraph = "<p>" + html.escape(transmission, quote=False) + "</p>"
    heading_match = re.search(
        r"<p\s*>\s*<strong\s*>(?:Onde assistir|Transmissão)</strong>\s*</p\s*>",
        body, flags=re.IGNORECASE,
    )
    if heading_match:
        at = heading_match.end()
        repaired = body[:at] + paragraph + body[at:]
    else:
        headings = len(re.findall(r"<p\s*>\s*<strong\s*>.*?</strong>\s*</p\s*>", body, re.I | re.S))
        if headings >= 8:
            return None
        entries = list(re.finditer(r"<p\b[^>]*>", body, flags=re.IGNORECASE))
        if not entries:
            return None
        at = entries[-1].start()
        repaired = body[:at] + "<p><strong>Onde assistir</strong></p>" + paragraph + body[at:]
    if repaired == body:
        return None
    result = dict(draft)
    result["body_html"] = repaired
    fields = draft.get("fact_fields_used")
    if isinstance(fields, list) and all(isinstance(f, str) for f in fields):
        result["fact_fields_used"] = list(dict.fromkeys([*fields, "transmission"]))
    return result


def focused_revision_guidance(errors: list[str]) -> str:
    """Retorno específico dos validadores; só instruções, nunca fatos inventados."""
    parts: list[str] = []
    if any("cronologia extensa de placares e datas" in error for error in errors):
        parts.append(
            "Uma falha foi a CRONOLOGIA: cite no máximo DOIS resultados anteriores "
            "concretos por clube, preferencialmente um único por parágrafo. "
            "Nunca agrupe três ou mais datas/placares na mesma passagem, "
            "não enumere os cinco jogos e não repita o calendário no retrospecto. "
            "Desenvolva a situação competitiva ATUAL e as notícias verificadas."
        )
    if any("balanço de vitórias, empates e derrotas é repetido" in error for error in errors):
        parts.append(
            "Informe o balanço V-E-D uma única vez por equipe dentro do respectivo "
            "Como chega; suprima balanços do lide, histórico e encerramento."
        )
    if any("linguagem de preenchimento ou metadados de cobertura" in error for error in errors):
        parts.append(
            "O rascunho tem linguagem mecânica: elimine 'jogos registrados', "
            "'o retrospecto considerado', balanços com zero, inclusive 'nenhum empate' "
            "ou 'nenhuma derrota', e frases genéricas sobre o peso da história. "
            "Use apenas o período efetivamente confirmado, sem tratar uma "
            "amostra parcial como campanha completa. Cite um resultado ou "
            "notícia de preparação concreta, sem acrescentar fatos novos."
        )
    if any("mesma pontuação de um clube repetida" in error for error in errors):
        parts.append(
            "A pontuação do mesmo clube foi recontada em muitos parágrafos. "
            "Apresente a posição e os pontos no contexto competitivo uma vez, "
            "sem repeti-los na abertura, Como chega e fechamento. Mantenha apenas "
            "fatos verificados que acrescentem informação."
        )
    if any("nota editorial" in error for error in errors):
        parts.append(
            "A matéria não atingiu 80/100 na régua editorial: melhore a abertura "
            "com notícia esportiva já verificada, desenvolva fatos específicos "
            "e distintos dos DOIS clubes e evite blocos só de serviço. "
            "Se existir retrospecto, use confronto concreto com ano/placar "
            "já validado; se houver apenas balanços agregados comprovados, "
            "não invente episódio histórico. Nunca encha o texto para obter nota."
        )
    if any("fechamento repetitivo" in error for error in errors):
        parts.append(
            "Reescreva o parágrafo final para acrescentar uma consequência "
            "esportiva verificável não repetida na abertura, como objetivo "
            "na classificação, cenário da eliminatória ou próximo jogo confirmado. "
            "Não copie a ficha de jogo, pontuação ou resultado recente já citado."
        )
    if any("chamada promete transmissão" in error for error in errors):
        parts.append(
            "A manchete promete transmissão: é obrigatório escrever literalmente "
            "a emissora/plataforma já verificada no campo transmission dos fatos "
            "em um parágrafo curto sob Onde assistir. Nunca deduza transmissora."
        )
    return " ".join(parts)


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
        validated = None
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
                    if any("chamada promete transmissão" in error for error in errors):
                        repaired = repair_verified_transmission(draft, contract)
                        if repaired is not None:
                            candidate, repair_errors = validate.validate_draft(
                                repaired, contract, config=site_config,
                            )
                            if not repair_errors:
                                draft, validated, errors = repaired, candidate, []
                                print("REPARO VERIFICADO: transmissão factual inserida e revalidada.", flush=True)
                    if not errors:
                        # Não desperdiçar matéria tecnicamente válida que a
                        # trava narrativa rejeitaria depois: tentar corrigir
                        # na segunda chamada, ANTES de gravar como aprovada.
                        errors = editorial_quality.draft_quality_errors(
                            validated["body_html"], contract,
                        )
                        if errors:
                            validated["draft_validated"] = False
                            validated["draft_validation_errors"] = errors
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
            "editorial_scorecard": (
                editorial_quality.editorial_scorecard(validated["body_html"], contract)
                if isinstance(validated, dict) and validated.get("body_html")
                else None
            ),
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
        # Tenta novo texto completo SEM devolver o rascunho anterior no contexto.
        # Reenviar milhares de tokens da resposta reprovada fez a segunda chamada
        # estourar max_output_tokens. O contrato permanece a única fonte factual.
        payload = build_revision_request(
            contract, provider_config, errors=errors, previous_draft=draft,
        )
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
