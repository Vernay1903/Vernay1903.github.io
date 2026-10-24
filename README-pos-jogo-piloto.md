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

## Passo 8 — apuração automática (piloto)

`--auto-research` em `executar_pos_jogo.py` substitui a apuração cadastrada por descoberta e leitura das fontes para uma partida. O parâmetro usa API mesmo sem `--execute`; sem este último, prepara o pacote, mas não redige. O workflow `pos-jogo-apuracao.yml` exercita essa separação e não publica nem agenda.

A descoberta usa web_search com domínios permitidos. URLs descobertas são abertas diretamente por HTTP, com validação de domínio também em redirecionamentos, limites de tempo/tamanho e remoção de scripts. Falhas e conteúdo indisponível são registrados; snippets não são aceitos como prova. O resumo estruturado ESPN consultado pelo coletor é preservado como fonte distinta, junto de ao menos um relato oficial aberto. URLs internas do Corte dos Esportes não são pesquisadas.

O código divide o conteúdo recebido em trechos identificados. O modelo apenas seleciona IDs existentes; o código anexa o texto original, sem solicitar ao modelo que o recopie. Identidade e placar exigem fontes em dois domínios. Autores, ordem dos gols, estádio e campanha passam por conferência, seguida de uma segunda revisão por modelo contra as fontes. Fatos narrativos sem apoio são omitidos; insuficiência de narrativa, contradição essencial ou revisão reprovada bloqueiam o pacote. Essa revisão não constitui garantia absoluta nem substitui a supervisão editorial.

Limites de teste: uma partida, três chamadas de API e uma busca solicitada, sem repetição automática no mesmo diretório. Paginas, trechos, extração, revisão, falhas e consumo de tokens ficam nos artefatos do Actions por sete dias. Isso não implementa controle mensal compartilhado de gastos.

Limitações atuais: apuração de prorrogação, disputa de pênaltis e gols contra não suportada; campanha estruturada e calendários futuros ainda obrigatórios. No caminho automático, minutos dos gols ficam omitidos; a identidade e ordem dos autores são verificadas separadamente. Fase/rodada podem constar na narrativa somente se encontradas nas fontes. Não há busca de imagens, vídeo ou links internos adicionais. A etapa seguinte define a espera após encerramento; HTML, noticias.json, sitemap e publicação permanecem fora deste passo.


Validação controlada de 23/10/2026: execução 39995915646 aprovada, 65 testes e pacote de Real Madrid x Leipzig preparado com dez fatos narrativos. Busca, abertura e revisão ocorreram sem reutilizar o cadastro manual. Três chamadas de API; nenhuma chamada de redação ou publicação. A aprovação não demonstra ainda cobertura completa dos quatro clubes nem de todas as competições.

## Passo 9 — espera de 50 minutos

Regra aprovada pelo editor: iniciar o processo 50 minutos após o término. O provedor não oferece aqui um instante confiável de apito final: usa-se a primeira observação de status final como referência conservadora, nunca início + duas horas. A espera começa antes da apuração e da redação com API. Consulta feita tarde pode, portanto, atrasar a liberação; não há promessa de execução exata ao minuto.

`config/tempo-pos-jogo.json` define 50 minutos e America/Sao_Paulo. `tempo_pos_jogo.py` registra a primeira confirmação em estado persistente identificado pelo jogo; uma mudança de placar/status reinicia a espera. Retorno ao jogo em andamento invalida a observação anterior. O CLI sem --date consulta ontem e hoje em Brasília, inclusive na virada de mês/ano, com limite compartilhado de uma apuração/matéria por teste. A data da partida permanece a do início, e o instante de liberação pode cair no dia seguinte.

Exemplos testados: encerramento observado às 18h libera às 18h50; às 23h30 libera às 00h20; às 00h libera às 00h50. Um jogo iniciado às 16h e encerrado às 18h14 só libera às 19h04. Teste também impede API aos 49min59s e permite aos 50min.

Estado padrão: build/pos-jogo/estado-tempo.json, substituível por --timing-state. A ativação futura deve restaurar e persistir esse estado entre runners e serializar as execuções; sem restauração, a espera recomeça conservadoramente. Cron e persistência entre runners serão ligados no teste completo de publicação, não neste passo. Os antigos testes pagos dos passos 7/8 agora também respeitam a espera, caso sejam disparados novamente.

Validação: 74 testes aprovados localmente e na execução 39999571859. Não houve chamadas de apuração/redação, publicação nem alteração da agenda ou prévias.

## Passo 10 — HTML padrão fornecido pelo editor (parte HTML)

Em 24/10/2026 o editor forneceu HMTL PADRÃO VALIDADO PARA MATERIAS.txt e autorizou somente campos pertinentes à matéria e distribuição dos anúncios. A cópia em templates/materia-validada.html preserva os bytes do arquivo (BOM, CRLF e conteúdo). Hash esperado em config/html-pos-jogo.json; alterações no padrão bloqueiam o montador até nova validação explícita.

scripts/montar_html_pos_jogo.py muda somente título da página, meta description, título, chamada, data, categoria e suas constantes JS, e conteúdo de articleBody. Preserva CSS, ordem do menu, cabeçalho, agenda completa, compartilhamento, rodapé, scripts e anúncio lateral. Subtítulos seguem p/strong como no modelo. Somente âncoras internas autorizadas são preservadas; outros textos são escapados. Links, vídeos e conteúdo de surf do exemplo não são reaproveitados na nova matéria. Não acrescenta canonical, dados estruturados ou outros componentes não presentes no padrão sem autorização.

Os blocos AdSense do corpo são copiados literalmente do modelo, mantendo cliente e slot. Política inicial de UX: até um bloco entre 600–899 palavras, dois entre 900–1499 e três a partir de 1500. Posicionamento aproximadamente proporcional, com pelo menos 250 palavras antes/entre anúncios e 150 após o último; somente entre parágrafos completos, sem separar subtítulo do texto nem introdução de lista. Usa menos anúncios quando não houver fronteiras adequadas. O anúncio lateral e seu comportamento responsivo permanecem intactos. Essa política é escolha de implementação para UX, não declaração de conformidade ou garantia de receita do AdSense.

A montagem grava somente em build/pos-jogo; não está ligada à publicação. news JSON e sitemap continuam pendentes no passo 10. Execução 40101518666 aprovada: 83 testes, amostra de 689 palavras, título de 58 caracteres e um anúncio no corpo. Estrutura fixa comparada exatamente; nada publicado.
