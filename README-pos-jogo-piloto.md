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

Correção autorizada em 24/10/2026: o arquivo HTML PADRÃO MATERIA USAR ESSE.txt substitui integralmente o modelo anterior, preservando seus bytes. Tênis agora aparece antes de Vôlei e Vôlei de Praia. As únicas outras diferenças são linhas em branco no corpo. Hash atualizado; execução 40104740646 aprovada com 83 testes e montagem da amostra. Regras de anúncios e campos variáveis preservadas; nenhuma publicação.

## Passo 10 — pacote HTML, noticias.json e sitemap

Regras aprovadas em 26/10/2026 implementadas em scripts/preparar_publicacao_pos_jogo.py. Recebe artigo, fatos do jogo, links autorizados, instante explícito da redação com fuso, notícias e sitemap existentes. Data única convertida para Brasília; HTML e JSON usam DD/MM/AAAA, sitemap AAAA-MM-DD. O instante do teste é simulado: a amostra antiga não foi novamente redigida.

Nome do arquivo: mandante-visitante-competicao-ano-do-jogo-resultado.html, sem acentos. Título e chamada copiados sem reescrita. Nova notícia na primeira posição, exatamente cinco campos e categoria Futebol. Inserção textual preserva os registros anteriores e sua formatação. Sitemap insere URL absoluta, mesma data e prioridade 0.9 após o marcador MATÉRIAS, preservando o restante. URL existente no JSON, sitemap ou HTML bloqueia o pacote, inclusive colisões de dois confrontos no mesmo ano; não adiciona sufixo não autorizado nem sobrescreve matéria.

CLI grava somente em pasta nova de build/pos-jogo e prepara tudo antes de gravar. Não publica nem altera os arquivos originais. A etapa não liga o pacote ao redator: a integração seguinte deve registrar o instante real da redação, reaproveitá-lo em tentativas posteriores e reler os arquivos de destino antes de qualquer publicação concorrente.

Validação: 93 testes locais e execução 40355305916 aprovada no GitHub. Teste local adicional utilizou cópias atuais de noticias.json e sitemap.xml da main. Cobertos virada de dia/ano em Brasília, preservação, correspondência de campos, duplicatas em cada destino, normalização e entradas inválidas. Publicação segue desativada.

## Passo 11 — redator conectado ao pacote de teste

executar_pos_jogo.py aceita --site-root junto com --execute. Após o redator aprovar o texto, empacotar_redacao_pos_jogo.py relê noticias.json, sitemap.xml e nomes HTML do checkout de destino e monta publicacao-teste. Não grava no site. metadata.json registra written_at real da última versão redigida/corrigida, aprovação de formato/revisão e hashes do artigo e pacote editorial. O empacotador reconstrói o pacote e bloqueia alterações posteriores. Reempacotamento sem API preserva a data original; pacote idêntico é reutilizado, divergência preserva a versão anterior e bloqueia. Uma pasta temporária é renomeada somente após completar todos os arquivos.

Teste controlado scripts/testar_fluxo_pos_jogo.py: calendários reconstruídos da ficha arquivada, relógio histórico simulado, primeira observação bloqueada e segunda liberada aos 50 minutos, preparação factual cadastrada e redação REAL via API. A descoberta automática de fontes não é exercitada neste replay. Destinos são checkout atual da main somente para leitura. O texto de teste contém próximos jogos históricos e NÃO pode ser publicado como notícia atual.

Execução inicial 40356248183 bloqueada pelo revisor após sete chamadas. Orientação do redator reforçada para preservar o alcance de declarações e evitar comparações/qualificações sem suporte; critérios do revisor mantidos. Execução 40356893002 aprovada: 109 testes, cinco chamadas de API, uma correção, 605 palavras, título de 54 caracteres, um anúncio no corpo. Data real da versão final: 26/10/2026 em Brasília, igual no HTML/JSON/sitemap. Nenhuma mudança nos arquivos do site. Resultados completos em auditoria/pos-jogo/resultado-passo11.json.

Próxima etapa ainda precisa validar uma partida com apuração recente e preparar persistência entre runners, concorrência, custos e publicação autorizada. Este passo não ativa cron, não publica e não garante cobertura dos quatro clubes em produção.

## Passo 12 — controle de custo validado; operação contínua pendente

O teste recente 40358859504 respeitou a espera real de 50 minutos, mas foi bloqueado em uma correção vazia. Custou US$0,2895742 estimados e não publicou. Esse histórico permanece intacto.

Em 26/10, o editor definiu US$0,10 por matéria, incluindo apuração, redação, revisão e correções. O controlador agora soma cobranças da mesma matéria entre chamadas, reinícios e meses. Usa a contagem de tokens da API antes da geração sem ferramentas e reserva a maior tarifa aplicável. Para uma busca, reserva duas janelas de busca completas de 128 mil tokens, com tarifa de contexto longo, saída máxima e custo da ferramenta. Cobrança incerta mantém a reserva e bloqueia novas chamadas. Apuração e redação pagas exigem o controlador persistente.

Configuração final: GPT-6 Luna para apuração/revisão e GPT-5.6 Terra para redação. Saída máxima de 4.000 tokens para redigir e 1.500 para correções localizadas. Exclusões de blocos precisam ser explícitas e passam novamente pela validação de extensão e revisão factual. O limite operacional continua dez chamadas, além do teto financeiro.

A avaliação histórica de Real Madrid x Leipzig usou os runs 40410687634, 40411772773 e 40412269029. A primeira redação econômica foi reprovada; a continuação usou Terra. Uma correção foi bloqueada antes da API por reserva acima do saldo; reduzido seu limite de saída, a correção localizada passou. Todas as quinze chamadas da avaliação compartilharam o mesmo saldo: US$0,062876675, sem apagar gastos anteriores. As duas continuações são instrumentos únicos de teste, não repetição automática operacional.

Run final 40412269029: sucesso, 135 testes, matéria de 615 palavras, título de 55 caracteres, HTML com estrutura fixa preservada, um anúncio no corpo, noticiaJSON na primeira posição e datas consistentes no sitemap. Auditoria durável em auditoria/pos-jogo/resultado-passo12.json e validacao-custo-20261026.json.

IMPORTANTE: coleta/calendários do replay representam 22/10; os próximos jogos desse texto são históricos. O pacote é apenas teste e não pode ser publicado como notícia atual. Data real da redação final: 26/10/2026. Ainda falta validar o fluxo econômico com partida recente antes da ativação contínua.

Estado permanece em estado-pos-jogo-piloto/estado.json, com SHA condicional e concorrência serializada. Não houve modificação da main, da agenda ou das prévias. Publicação e cron permanecem desativados.

O teto mensal US$10 cobre somente chamadas do controlador do piloto. Consumo das prévias e testes anteriores não está conciliado: não constitui teto global comprovado da conta OpenAI. Preços têm validade operacional até 25/11/2026. Antes de ativar operação contínua, resolver a conciliação e a validação recente.


## Passo 13 — validado em partida recente

A execução 40610075120 aprovou o pacote de Flamengo x Atlético-MG: 606 palavras, título de 51 caracteres, HTML com estrutura fixa preservada, um anúncio no corpo, notícia na primeira posição e datas coerentes no HTML/noticias.json/sitemap (27/10/2026 em Brasília). Custo acumulado do mesmo fixture, incluindo todas as tentativas e correções: US$ 0,097975160. Nenhum débito foi zerado.

A apuração passou a conservar detalhes úteis das fontes, e textos curtos são corrigidos antes de gastar com revisão semântica. A primeira revisão abrange o texto inteiro; correções posteriores são verificadas contra as mesmas evidências e o contexto completo, mantendo apenas aprovações de unidades literalmente inalteradas. Mudança de evidências ou estrutura impede esse reaproveitamento. Há hashes e cadeia de revisão na auditoria.

148 testes passaram. A rotina contínua e a publicação continuam desativadas. A validação é de uma partida recente, não uma garantia de sucesso para todas. O passo 14 aguarda autorização: conciliação do orçamento compartilhado e ativação controlada do piloto agendado para os quatro clubes, em modo de rascunho. As automações de agenda e prévias não foram alteradas.

Relatórios duráveis: `auditoria/pos-jogo/resultado-passo13.json` e `auditoria/pos-jogo/validacao-recente-flamengo-20261027.json`.


## Passo 14 — agendamento autorizado

Acionador próprio em main executa código fixado por SHA da branch do piloto. Consulta a cada dez minutos, nos minutos 03, 13, 23, 33, 43 e 53 UTC. Considera ontem e hoje em Brasília e exige pelo menos 50 minutos desde a primeira confirmação de encerramento. Filas/atrasos do GitHub podem postergar o início; nunca antecipa a espera. Processa no máximo uma matéria por ciclo; as demais continuam elegíveis nos ciclos seguintes.

Modo exclusivo de rascunhos: gera pacote de HTML/noticias.json/sitemap em build e disponibiliza artefato por 30 dias apenas quando há rascunho ou erro. Não altera páginas, agenda, prévias, noticias.json nem sitemap na branch principal. Estado, histórico de custos e marcador de execução ficam em estado-pos-jogo-piloto/estado.json. Uma partida tentada não é cobrada de novo automaticamente. Erros factuais exigem revisão e a chave operation.enabled=false pausa o piloto sem mexer nas outras automações.

A conferência de orçamento constatou controles separados. O teto persistente é US$ 0,10 por matéria (todas as tentativas) e US$ 10/mês somente para o pós-jogo. Não há teto global da conta comprovado, nem consolidação com a prévia; nenhuma configuração de prévia foi alterada. Conferência em auditoria/pos-jogo/conferencia-orcamento-passo14.json. Tarifas devem ser revalidadas ao vencer a validade configurada; cobrança incerta impede novo consumo.

Ativação efetivada no commit 07a0136c557c6603e6d1eb4522fe4d4727d3e6dc da main, adicionando somente o acionador. Execução inicial 40611435664 aprovada. Execução agendada 40643743077 comprovou acionamento e preservação do relógio entre dias, com 158 testes aprovados, mas terminou needs_review: partida espn-401921835 em STATUS_FINAL_PEN bloqueada pelo suporte ainda ausente a prorrogação/pênaltis. Nenhuma chamada paga nova e nenhuma publicação. Total histórico do piloto preservado em US$ 0,450426035. Primeiro rascunho por cron ainda não validado; a frequência configurada não garante pontualidade do serviço. Resultado completo em auditoria/pos-jogo/resultado-passo14.json.


## Passo 15 — validado e habilitado

Prorrogação e pênaltis têm desfecho separado dos gols da partida, sem inferir placar aos 90 minutos. Resultado dos pênaltis alterado reinicia a espera de 50 minutos. Campanha ausente e próximo jogo de copa indisponível são omitidos. Fontes incluem a EFL, com leitura do corpo embutido sem executar JavaScript, e Sky Sports como complemento. O desfecho exige apuração e revisão independente.

181 testes passaram. Validação real assistida de Fleetwood Town x Arsenal concluída no run 40743571734: 664 palavras, título de 55 caracteres, HTML fixo preservado, um anúncio no corpo, notícia na primeira posição e datas 28/10/2026 no HTML/JSON e 2026-10-28 no sitemap. Custo acumulado de todas as 14 chamadas: US$ 0.037242410. A validação teve continuações únicas autorizadas; o limite normal permanece 12 chamadas e US$ 0,10 por partida. Não houve publicação.

A main carrega o código cbb4300b9a9e29489def916d75c5b83e61eaa95f pelo acionador; verificação do run 40687749206 aprovada. Prorrogação foi coberta por testes, pênaltis por partida real. A descoberta de fontes e a conclusão editorial desse teste tiveram assistência: o primeiro rascunho totalmente autônomo por agendamento ainda precisa ser validado. Auditoria durável: auditoria/pos-jogo/validacao-final-passo15.json e resultado-passo15.json.


## Passo 16 — verificação autônoma ativada; resultado esportivo pendente

Verificador sem chamadas de IA instalado no acionador, código 0fc209cefbe5b522869775e9491475c1d2c74eb9. Os 192 testes e a execução de instalação 40777391918 passaram. Somente eventos schedule podem aprovar a etapa: exige descoberta nova de fontes, revisão aprovada, pacote reconstruído idêntico, espera de 50 minutos, chamadas liquidadas da mesma execução e teto acumulado US$ 0,10. Continuações assistidas e execução manual não qualificam. Registro persistente em validation_step16 na branch de estado; artefato passo16.json acompanha o ciclo. A primeira aprovação é preservada.

Manchester City x Brighton (espn-401921834) observado encerrado em 28/10 às 19:06:52 -03:00; elegível após 19:56:52 -03:00. A execução depende do próximo ciclo real do GitHub. Instalação sem novas chamadas pagas; nada publicado. A etapa permanece aguardando o primeiro rascunho autônomo e não é declarada concluída.
