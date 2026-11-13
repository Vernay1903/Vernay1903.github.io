# Teste manual de um Story — eventos restantes
O workflow Instagram - publicar 1 Story de teste publica somente a primeira tela dos eventos restantes de 13/11/2026. O proprietário deve marcar publicar e executar na main. Não há agendamento.

A prévia do run 43526681096 selecionou oito eventos posteriores às 20h23 em São Paulo, em duas páginas. O teste publica SOMENTE a primeira: Indiana Pacers x New York Knicks (21h), Orlando Magic x Milwaukee Bucks (21h), Osasco x Sesi Vôlei Bauru (21h) e Chicago Bulls x Atlanta Hawks (22h), com as descrições completas do agenda.json. A imagem mantém o layout aprovado. A seleção usa o conteúdo do site; não é uma nova apuração do calendário esportivo.

A data, a identidade da conta, o hash da agenda e a igualdade com o conteúdo servido no site são conferidos. A imagem pública está fixada por commit e SHA-256. O início do teste e a chamada final de publicação exigem horário anterior às 21h em America/Sao_Paulo, inclusive após o processamento pela Meta.

A imagem fica na branch instagram-story-media, separada do site. Mantemos o MESMO registro diário state/17841446409607682/2026-11-13-story-01.json para evitar duplicação entre a tentativa anterior e esta. A tentativa da tarde falhou na consulta da conta e não chegou a criar esse registro ou mídia.

Registro existente bloqueia outra tentativa. A intenção é persistida antes do POST media_publish; timeout deixa o registro para revisão manual, sem nova publicação automática. Não remover registros antes de verificar o Instagram e o contêiner. Tokens permanecem nos secrets, nunca nos arquivos públicos.

A publicação diária e o envio das demais páginas ainda não estão ativos. Depois do teste, conferir aparência no Instagram.

Fontes técnicas: https://developers.facebook.com/documentation/instagram-platform/content-publishing e https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media
