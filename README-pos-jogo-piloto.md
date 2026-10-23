# Pós-jogo — piloto de quatro clubes

Piloto limitado a Flamengo, Real Madrid, Arsenal e Manchester City. Integra seleção, triagem de duplicatas, preparação factual e redação com revisão pela API. Ainda exige apuração externa cadastrada por jogo. Há workflows de teste na branch do piloto; não há agendamento nem publicação. As seções abaixo registram a evolução por etapa.

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

## Passo 4 — modelo editorial

Prompt em `prompts/pos-jogo-editorial.txt`: instruções do editor incorporadas com mínimo de 600 palavras e título de até 70 caracteres (espaços e pontuação incluídos, Unicode NFC). Liberdade narrativa, fatos comprovados e somente links fornecidos pelo usuário. O exemplo Bayern x Arsenal é referência de composição, não fonte factual de outro jogo.

`editorial_pos_jogo.py` prepara o pacote para redação e valida a estrutura de uma amostra. Não chama API. O pacote exclui valores conflitantes e proveniência do conteúdo enviado ao redator; a auditoria conserva as fontes. A validação de formato NÃO comprova exatidão factual ou qualidade jornalística.

Amostra Real x Leipzig redigida pelo assistente no chat e armazenada como referência de teste; NÃO é saída de execução do modelo via API. O ambiente não disponibilizou OPENAI_API_KEY. Geração automática e validação editorial independente continuam pendentes, assim como aprovação do editor. Nenhuma publicação ou mudança de cron foi realizada.

Apuração narrativa acrescentou páginas abertas do relato do Real, declarações de Courtois, ficha DFB, clássico e Bundesliga. O relatório registra a origem assistida. Link interno foi fornecido explicitamente pelo usuário nesta conversa; não foi buscado no site. A entrega ao editor é texto comum no chat, sem download ou arquivo de leitura.

Verificação do passo: 8 testes de formato/proveniência; amostra com 58 caracteres no título e 689 palavras no corpo. A contagem de extensão não é nota de qualidade. Não promete aproveitamento editorial de 80% sem avaliação humana.

## Passos 5 e 6 — redação e revisão pela API

O teste de API usa o Secret OPENAI_API_KEY no GitHub Actions, com conteúdo somente de leitura e saídas em build/pos-jogo/api. Não publica HTML, não atualiza notícias e não tem agendamento. O gatilho push está restrito à branch do piloto, ao arquivo do workflow e à mensagem exata de execução. Os relatórios anteriores preservam reprovações; sucesso técnico de uma chamada não significa aprovação editorial.

A configuração config/redacao-pos-jogo.json é própria do piloto. O fluxo valida o revisor com duas contradições conhecidas e uma informação correta, gera a matéria e revisa todas as unidades contra o pacote factual previamente conferido. Revisão incompleta, evidências inexistentes ou aprovação inconsistente bloqueiam o teste. Correções são aplicadas somente às unidades reprovadas, com conferência de que nenhuma outra foi alterada. Cada versão volta à validação de formato e à revisão semântica. Limite de sete chamadas por execução (calibração e até três ciclos de redação/correção e revisão), sem repetição automática de erro HTTP.

A revisão por modelo reduz erros, mas não prova veracidade absoluta. A apuração de Real Madrid x Leipzig continua sendo a base previamente revisada pelo assistente; este teste não automatiza descoberta e leitura das fontes de todos os jogos. Publicação, integração com o site e cron permanecem bloqueados. O número de chamadas é limitado, mas não existe ainda um contador mensal de gastos compartilhado com as prévias.

## Passo 7 — integração controlada

`scripts/executar_pos_jogo.py` consulta os quatro calendários e usa as notícias atuais da main somente para detectar duplicatas. Coleta resumo e próximos jogos, conserva snapshots e exige entrada em `config/apuracoes-pos-jogo.json`. A apuração cadastrada deve corresponder ao jogo, ter menos de 24 horas e continuar compatível com os calendários consultados. Atualmente apenas Real Madrid x Leipzig tem apuração cadastrada.

Sem apuração, o evento fica `needs_source_review`, sem chamada de redação. Coleta incompleta bloqueia o lote. O modo somente coleta registra pendências editoriais sem tratá-las como erro de conexão; o modo de execução termina com erro quando há pendências. Partidas com pênaltis/prorrogação continuam sem suporte para redação.

A execução permite uma matéria e até sete chamadas por teste, sem publicação. O revisor só pode referenciar IDs efetivamente enviados; correções preservam as unidades não apontadas e recebem a contagem de palavras necessária para manter o mínimo editorial. A revisão por modelo não substitui apuração nem aprovação humana.

O workflow pos-jogo-integracao lê a main, mas só grava saídas temporárias e artefatos do Actions. Não altera notícias, HTML, agenda nem automação de prévias. O teste com dados ao vivo cobre coleta, duplicata já publicada, pendência de apuração e redação da partida previamente conferida. A descoberta automática de fontes para partidas novas e a publicação seguem fora desta etapa.

Resultado controlado em 23/10/2026: execução 39951024418 aprovada, 53 testes, uma matéria de 606 palavras e título de 55 caracteres. A redação passou após duas correções, dentro de sete chamadas. A coleta também registrou Flamengo pendente de apuração e bloqueou Bayern x Arsenal já publicado. O texto mantém revisão humana obrigatória; não se trata de liberação para publicação automática.
