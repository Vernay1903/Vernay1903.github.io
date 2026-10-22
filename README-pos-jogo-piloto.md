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

## Passo 3 — base factual

`preparar_fatos_pos_jogo.py` recebe um candidato selecionado, consulta o resumo e calendários ESPN com `--execute`, ou repete a leitura de snapshots com `--snapshots`. Exige uma conferência editorial externa explícita em `--review`; a descoberta e interpretação dessas fontes ainda não são automáticas. O comando somente imprime JSON.

```sh
python tests/pos-jogo/test_fatos.py
python scripts/preparar_fatos_pos_jogo.py --selection tests/pos-jogo/fixtures/real-leipzig-20261021/selection.json --fixture-id espn-401915313 --review tests/pos-jogo/fixtures/revisao-real-leipzig-20261021.json --snapshots tests/pos-jogo/fixtures/real-leipzig-20261021
```

O pacote de auditoria em `auditoria/pos-jogo/fatos-real-leipzig-20261021.json` registra o resultado desta conferência. Snapshots reduzidos preservam os campos usados nos testes. A campanha foi conferida na tabela estruturada ESPN (com consistência aritmética); placar, autores, ordem dos gols e estádio foram confrontados com Real Madrid e DFB. As fontes não têm o mesmo escopo de comprovação: o campo `supports` documenta cada uma.

Conflito real: primeiro gol em 43 minutos na ficha ESPN/DFB e em 44 no relato do Real Madrid. O minuto fica nulo no pacote liberado, com os valores divergentes somente na auditoria. Não há inferência automática de domínio, posição definitiva ou classificação. Próximos jogos vêm de calendários identificados; horários sem confirmação são omitidos. Revalidar calendários e duplicatas antes de qualquer publicação.

`ready_for_drafting` significa apenas que a base factual deste passo está completa; não aprova estilo, extensão, linkagem, imagem ou publicação. Esses controles pertencem às etapas seguintes. Prorrogação, disputa de pênaltis e gols contra são bloqueados até haver tratamento específico, sem confundir esses casos com dia sem jogos.

Validação: 11 testes de fatos e 13 testes de seleção. Nenhuma chamada de redação nem workflow de publicação foi adicionado.
