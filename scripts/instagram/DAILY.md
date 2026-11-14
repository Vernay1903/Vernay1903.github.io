# Stories diários

Autorizado em 14/11/2026: agenda completa às 00h40 de Brasília, recuperação dentro da janela até 01h00. Modelo aprovado com escudo no topo e data no mesmo azul dos horários.

Workflow `instagram-daily.yml`: disparos 00h40, 00h45, 00h50 e 00h55, fuso America/Sao_Paulo. Nenhuma nova requisição de publicação a partir de 00h59, reservando um minuto para resposta da Meta. GitHub e Meta podem atrasar ou falhar; o agendamento não é garantia de entrega. Execuções atrasadas são ignoradas, não publicam ao longo do dia.

Somente a agenda publicada pelo fluxo validado do dia é aceita: data explícita do commit, data local, PR mesclado da branch agenda-auto-DATA, SHA de merge, conteúdo idêntico à main. Antes de publicar também exige a mesma agenda servida no site e a identidade @cortedosesportes. Se a agenda não ficou pronta, tenta no próximo disparo; nunca usa a agenda de ontem. A data do commit sozinha não é suficiente. Um dia sem agenda ou uma edição manual sem esse comprovante exige revisão e não gera postagem automática.

Todas as páginas, na ordem dos horários, são publicadas. Imagens ficam na branch separada instagram-story-media, com URL de commit imutável. Estado diário em `state/17841446409607682/AAAA-MM-DD-daily.json`: páginas publicadas são ignoradas; contêineres em processamento são retomados. Uma resposta inconclusiva após o envio não é repetida: somente status PUBLISHED do mesmo contêiner permite confirmar automaticamente. Mudança de agenda após iniciar o plano bloqueia novas páginas para revisão. Não apagar estado para forçar nova publicação.

Execução manual tem publicar=false por padrão: gera artefato e simula sem escrever estado, subir imagens ou chamar Meta. Push do workflow ou daily.py na main também só simula. Testes de PR não acessam secrets. Publicar=true continua limitado à janela e conta aprovadas.

Secrets existentes: INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID. Não colocar tokens em arquivos, logs, artefatos ou prompts. GITHUB_TOKEN escreve apenas mídia/estado na branch separada; nenhum código do site ou agenda é alterado por este fluxo. Não modifica horários ou funcionamento das automações existentes.

Diagnóstico: conferir resumo e artefato no Actions. Falhas antes de media_publish podem recuperar nos próximos disparos. Estado publishing sem confirmação PUBLISHED requer conferência manual no Instagram para evitar duplicação. Nunca repetir o teste fixo de 13/11 para substituir o fluxo diário.
