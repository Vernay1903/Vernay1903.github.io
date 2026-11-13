# Teste manual de um Story

O workflow `Instagram - publicar 1 Story de teste` publica somente a primeira imagem aprovada de 13/11/2026. Não tem agendamento. O campo `publicar` vem desmarcado; somente a execução manual na main com esse campo marcado pode publicar.

A imagem é idêntica ao artefato aprovado no run 43481389326. Está fixada por commit e SHA-256 na branch `instagram-story-media`, separada do site. O script exige o dia correto em America/Sao_Paulo, os mesmos bytes de agenda.json na main e a mesma agenda JSON no site. A data foi aprovada pelo proprietário na prévia; não é inferida de um commit. Esse teste não pesquisa nem certifica os resultados esportivos.

Antes de criar mídia na Meta, confere a identidade de @cortedosesportes e grava um registro exclusivo em `state/17841446409607682/2026-11-13-story-01.json` na branch de mídia. Registro existente bloqueia outra tentativa. Grava a intenção antes de chamar media_publish; timeout ou cancelamento deixa o registro bloqueado para revisão humana. Não apagar o registro nem repetir uma publicação inconclusiva antes de verificar o Instagram e o contêiner na Meta.

As únicas escritas em execução são a atualização desse registro e a criação/publicação de um Story pela Meta. Token não entra em imagens, URLs públicas, arquivos ou logs. O workflow usa os secrets já cadastrados. O GITHUB_TOKEN só tem contents:write no job manual; os testes de PR não recebem os secrets.

Depois de uma publicação confirmada pela API, conferir visualmente no Instagram. Ativação diária, publicação das demais páginas e renovação/diagnóstico de credenciais são etapas posteriores.

Fontes: https://developers.facebook.com/documentation/instagram-platform/content-publishing e https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media
