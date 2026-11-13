# Agenda em Stories — etapa de prévia

Este workflow **não publica** no Instagram, não cria mídia na Meta e não altera a agenda, o site ou workflows existentes. Não há schedule. O teste de conexão faz somente GET e só executa manualmente na main.

A prévia usa o conteúdo exato de agenda.json e o logo-mobile.webp original. Gera JPEG 1080 × 1920 com até quatro eventos por página, divisão automática por altura, numeração e margem para interface dos Stories. As imagens não dependem de IA paga. O manifest permite conferir que todos os eventos foram incluídos na ordem.

O arquivo agenda.json não contém data. Para a prévia, a data vem do último commit do arquivo. Isso não prova a data dos eventos; antes de habilitar publicação automática é necessário validar a origem do dia e conferir o conteúdo servido no site. O renderer recebe uma data explícita e não deve ser usado como publicador.

## Validação

O PR gera o artefato `previa-stories-agenda`. Após aprovação/merge, executar `Instagram agenda - previa e conexao` com `verificar_conexao` marcado. Requer INSTAGRAM_ACCESS_TOKEN e INSTAGRAM_USER_ID nos repository secrets. A consulta usa o host graph.facebook.com do login unificado e exige identidade @cortedosesportes. Não imprime token ou corpo de erro.

Uma consulta bem-sucedida não valida a permissão instagram_content_publish nem a validade futura da credencial. Publicação real, hospedagem das imagens, controle persistente de duplicação/retomada e disparo diário serão implementados após validar esta etapa. O link clicável no perfil ainda precisa ser cadastrado pelo proprietário antes de publicar a chamada “link na bio”.

## Referências

- https://developers.facebook.com/documentation/instagram-platform/content-publishing
- https://developers.facebook.com/docs/graph-api/

## Local

Instalar Playwright 1.58.2 e Chromium. Rodar `node --test tests/instagram/renderer.test.cjs` e `AGENDA_DATE=YYYY-MM-DD node scripts/instagram/render.cjs`. CHROMIUM_PATH permite escolher um executável local. Saídas em out/instagram (não versionadas).
