# Pós-jogo — passo 2

Piloto limitado a Flamengo, Real Madrid, Arsenal e Manchester City. Implementa somente seleção de partidas encerradas e triagem de duplicatas. Não há workflow, agendamento, redação, chamada OpenAI ou publicação.

Executar testes:

```sh
python tests/pos-jogo/test_selecao.py
```

Consultar calendários públicos ESPN e imprimir relatório JSON:

```sh
python scripts/selecionar_pos_jogos.py --date 2026-10-21
```

A data é a do início da partida em Brasília. Uma partida que atravessa a meia-noite permanece vinculada à data de início; o futuro agendamento deverá consultar também o dia anterior. `--snapshots arquivo.json` permite repetir a seleção offline com calendários indexados pelos IDs ESPN 819, 86, 359 e 382.

A saída distingue jogos selecionados, bloqueados e erros de coleta. Lista vazia com erro não significa dia sem partidas. Placar e status são apenas dados candidatos de um provedor; `ready_for_publication` permanece falso. A validação factual para redação será uma etapa posterior.

Dois clubes do piloto no mesmo confronto geram um candidato. Divergências entre calendários bloqueiam o evento. A seleção exige status final explícito e completed=true, placares válidos e início no passado. Amistosos são excluídos.

Duplicatas com fixture_id e article_type têm prioridade. Para notícias legadas, nomes completos, data do jogo ou dia seguinte e sinais no título/URL distinguem prévias e resultados; casos ambíguos exigem revisão. Esse reconhecimento conservador não substitui um cadastro histórico de IDs e pode precisar de novos aliases. Revisão da cobertura real dos calendários e enriquecimento de gols, classificação e próximos jogos pertencem às próximas etapas.

Nenhum arquivo da automação de prévias foi alterado. Este piloto reutiliza apenas as constantes e a função pública de consulta de scripts/coletar_competicoes_pre_jogo.py.
