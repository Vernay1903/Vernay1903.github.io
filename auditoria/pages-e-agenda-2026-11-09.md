# Auditoria de publicacao - 09/11/2026

## Pages

- O commit da agenda 5b0a873cf753af10cab12d2ccb66c1b6b2bec6f1 foi mesclado pelo PR #120.
- Pages build: concluido, artefato `github-pages` com 694.839.211 bytes (run 42604140556).
- Pages deploy (primeira tentativa): timeout de 10 minutos, preso em `syncing_files`.
- Pages deploy (segunda tentativa): novo timeout de 10 minutos. Nao foi falha da coleta nem de Jekyll.
- Implantacao posterior com sucesso: run 42614626649.
- Arvore versionada (09/11): 1.676 arquivos, cerca de 722,9 MB, sendo aproximadamente 692,5 MB de formatos de imagem (JPG/JPEG/PNG/WebP/AVIF). Sao arquivos originais; esta mudanca NAO remove ou altera fotografias.
- Pastas de automacao/teste nao fazem parte do site publicado: `.github`, `auditoria`, `config`, `scripts`, `templates`, `tests`. O `_config.yml` as exclui somente do produto de Jekyll/Pages, sem retira-las do Git, sem alterar URLs publicas de materias, imagens e JSON e sem desativar automacoes.
- Ganho potencial conservador: cerca de 1,8 MB de arquivos versionados nao publicos; nao e suficiente, isoladamente, para assegurar que o timeout nao se repita. As imagens representam a grande maioria do volume. Qualquer exclusao adicional de imagem demanda identificacao de referencias em TODAS as paginas e validacao de credito/licenca.

## Disparos do publicador da agenda

O workflow `.github/workflows/publicar-agenda-validada.yml` continua habilitado com `schedule` entre 00:01 e 03:57, `timezone: America/Sao_Paulo`; sintaxe de cron e timezone compativeis com a documentacao oficial. Nenhum horario foi alterado.

Primeira execucao `schedule` registrada por dia (America/Sao_Paulo), conforme GET /actions/runs?event=schedule&created=YYYY-MM-DD:

| Data | Horario |
| --- | --- |
| 03/11 | 07:35 |
| 04/11 | 07:39 |
| 05/11 | 07:31 |
| 06/11 | 07:35 |
| 07/11 | 06:46 |
| 08/11 | 06:58 |
| 09/11 | 08:06 |

As execucoes `schedule` apareceram varias horas apos a janela configurada. Assim, o atraso NAO foi um episodio exclusivo de 09/11. O GitHub documenta que o evento agendado pode atrasar ou ser descartado em momentos de carga elevada. As execucoes com conclusao `success` confirmam o processamento quando efetivamente iniciam, nao a pontualidade do scheduler.

Em 09/11, a reexecucao do job do publicador (run 42474746140, tentativa 2) coletou as 13 competicoes de futebol, criou a branch `agenda-auto-2026-11-09` e o PR #120. O Guard do run 42604042438 aprovou o HEAD. O merge atualizou a `main` para 10 jogos. Isso comprova que a cadeia coleta/PR/Guard/merge funcionou quando iniciada.

## Decisao operacional

- Nao modificar horario, workflow da agenda, token, workflows de materias, controles do Guard ou `agenda.json` nesta proposta.
- Manter as conferencias e recuperacoes diarias, mas nao depender apenas de `schedule` do GitHub para pontualidade.
- Em um segundo passo, identificar imagens sem nenhuma referencia e duplicatas EXATAS no site, sem editar originais, e validar links antes de qualquer exclusao. Nao foi realizada exclusao de imagem por inferencia.

Evidencias:
- https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/42604140556
- https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/42614626649
- https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/42474746140
- https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/42604042438
- https://github.com/Vernay1903/Vernay1903.github.io/pull/120
