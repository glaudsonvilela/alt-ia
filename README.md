<p align="center">
  <img src="assets/mascote-alt-ia.svg" width="120" height="120" alt="Mascote roxo de dois olhos da Alt-IA">
</p>

<h1 align="center">Alt-IA</h1>

<p align="center">Chat privado da Altside para explorar cenários de blockchain e DeFi.</p>

<p align="center"><a href="https://ai.bigbanana.io/">Abrir a Alt-IA</a></p>

## Estrutura

- `site/`: interface, animações, fontes, imagens e configuração do Nginx.
- `backend/`: API Python que atende o chat, encaminha perguntas gerais ao NVIDIA Nemotron 120B e consulta o motor Rust do Altside para prévias de simulação.
- `backend/ALT_IA.md`: instruções de tom, clareza e limites das respostas da Alt-IA, carregadas pelo servidor como mensagem de sistema.
- `backend/news_agent.py`: bot de notícias com etapas de planejamento, coleta, revisão e apresentação inspiradas no fluxo do Sherlock. Publica apenas notícias do Altside Research Lab.
- `backend/research_agent.py`: pesquisa pública do Modo Nerd via SearXNG, com revisão de URLs, deduplicação e fontes numeradas. O modelo usa `reasoning_effort: high` nesse modo.
- `backend/wallet_lookup.py` e `backend/wallet_agent.py`: rastreio pontual e somente leitura de endereços públicos, com saldo e movimentações do Altside, saldos de tokens diretos por RPC e preços atuais/históricos do DefiLlama.

## Desenvolvimento

```bash
cd site
npm ci
npm run build
```

O site usa o `app.js` compilado. Para executar o backend, instale `backend/requirements.txt` e configure `ALT_IA_KEY_FILE` com o caminho de um arquivo local contendo a chave NVIDIA. A chave não deve entrar no repositório. O backend também aceita `ALT_IA_HOST`, `ALT_IA_PORT` e `ALTSIDE_API_BASE_URL` (padrão: `https://app.bigbanana.io`).

Em produção, o túnel Cloudflare encaminha `ai.bigbanana.io` para a página Nginx na porta local `8810`. Ao recriar o contêiner `alt-ia-page`, configure a política Docker `restart=unless-stopped`, assim como nos contêineres da API e do túnel. Sem essa política, a página permanece parada após um reinício do servidor e o domínio responde 502.

## Acesso privado

A Alt-IA usa login Google seguido por um código enviado ao mesmo e-mail. O servidor confere o token Google e o e-mail verificado. Contas `@altside.com` também exigem a declaração de domínio Google Workspace (`hd=altside.com`). Domínios adicionais podem ser liberados por `ALT_IA_ADDITIONAL_ALLOWED_EMAIL_DOMAINS`; o código enviado ao e-mail confirma o acesso atual à caixa. O código tem seis dígitos, expira em dez minutos e aceita até cinco tentativas. A sessão dura 12 horas e pode ser encerrada pelo botão **Sair da Alt-IA**. A tela inicial e seus recursos visuais são públicos; o login aparece ao enviar uma mensagem ou clicar em um atalho. Todas as APIs de dados e ações continuam exigindo sessão no backend. A ação iniciada é retomada depois da entrada.

Não é necessário cadastrar cartão no Cloudflare Zero Trust, e o servidor da Alt-IA pode continuar local. O cliente OAuth web já criado deve ter `https://ai.bigbanana.io` como **origem JavaScript autorizada**. Para enviar o código sem senha de aplicativo nem acesso ao administrador do Google Workspace, use a API do Gmail com a conta `glaudson@altside.com`. Essa autorização pede apenas `gmail.send` (envio; sem leitura da caixa).

1. No [Google Cloud Console](https://console.cloud.google.com/apis/library/gmail.googleapis.com), selecione o projeto do cliente OAuth de envio e ative a **Gmail API**. No [Google Auth Platform](https://console.cloud.google.com/auth/scopes), adicione o escopo `https://www.googleapis.com/auth/gmail.send`. O cliente usado para login precisa aceitar contas **Externas** para que outro domínio consiga entrar. Se o projeto atual for **Interno**, crie um cliente web em um projeto **Externo** separado para o login; mantenha o cliente interno e seu token renovável para o envio. Use `ALT_IA_GOOGLE_CLIENT_ID` para o cliente de login e `ALT_IA_GMAIL_CLIENT_ID` para o cliente de envio. Não mude o projeto do remetente para Externo em modo de teste: o token renovável de `gmail.send` poderá expirar em sete dias.
2. No [cliente OAuth web](https://console.cloud.google.com/auth/clients), adicione `http://127.0.0.1:8765/callback` como **URI de redirecionamento autorizado**. Baixe o JSON do cliente e guarde-o fora do repositório, no computador onde vai executar o comando abaixo. O navegador que fizer a autorização deve estar nessa mesma máquina.
3. Instale `backend/requirements.txt`. Execute a autorização uma vez, entre com `glaudson@altside.com` e aceite a permissão de **enviar e-mails**. Não cole o JSON nem o token no chat.

Se o Google Workspace bloquear a autorização de `gmail.send` por política da empresa, essa permissão depende do administrador; a aplicação não tenta contornar esse bloqueio. Nesse caso, escolha um serviço de e-mail transacional autorizado para o domínio como alternativa ao Gmail.

```bash
python3 backend/authorize_gmail.py \
  --client-secret /run/secrets/alt-ia-google-client.json \
  --output /run/secrets/alt-ia-gmail-refresh-token
```

O comando imprime um link para abrir no navegador e salva o token renovável em arquivo local com permissão `0600`. Proteja também o JSON do cliente com `chmod 600`. O diretório `/run/secrets` é um exemplo: use um caminho persistente e privado acessível ao processo do backend, inclusive após reiniciar. Se a autorização for feita em outro computador, mova os dois arquivos para o servidor por um canal seguro.

```text
ALT_IA_AUTH_REQUIRED=1
ALT_IA_GOOGLE_CLIENT_ID=802613256116-h6vv32v9egbdk29gqf558j03mqcmiup9.apps.googleusercontent.com
# Configure ALT_IA_GMAIL_CLIENT_ID com o cliente atual se o login usar outro cliente.
ALT_IA_ALLOWED_EMAIL_DOMAIN=altside.com
ALT_IA_ADDITIONAL_ALLOWED_EMAIL_DOMAINS=criptomaniacos.io
ALT_IA_MAIL_PROVIDER=gmail_api
ALT_IA_GMAIL_CLIENT_SECRET_FILE=/run/secrets/alt-ia-google-client.json
ALT_IA_GMAIL_REFRESH_TOKEN_FILE=/run/secrets/alt-ia-gmail-refresh-token
ALT_IA_SMTP_FROM=Alt-IA <glaudson@altside.com>
```

SMTP permanece disponível como alternativa com `ALT_IA_MAIL_PROVIDER=smtp`, `ALT_IA_SMTP_HOST`, `ALT_IA_SMTP_PORT`, `ALT_IA_SMTP_MODE`, `ALT_IA_SMTP_USER` e `ALT_IA_SMTP_PASSWORD_FILE`. O backend falha ao iniciar se o remetente escolhido não estiver configurado; `ALT_IA_AUTH_REQUIRED=0` é exclusivo para desenvolvimento local. O endpoint `/healthz` permanece disponível localmente. Sessões e códigos ficam apenas na memória do processo: uma reinicialização exige novo login. O histórico de conversas permanece no navegador, separado por conta; dados antigos do armazenamento local não são importados.

Implante backend e site juntos depois de configurar as variáveis e o remetente. Confira com uma conta corporativa real, uma conta de outro domínio, código incorreto/expirado, saída e API anônima. Não publique somente o frontend: o backend atualizado deve estar ativo para bloquear chamadas diretas à API.

O simulador de lending oferece mercados Aave V3, vaults simples da Fluid, três mercados isolados Morpho Blue e pools Kamino Lend na Solana. As taxas, preços e parâmetros são consultados nas APIs públicas oficiais ao abrir o mercado e os resultados são calculados no servidor. Em todos os protocolos, a pessoa monta a posição manualmente e pode gerar um endereço fictício para a simulação. Grupos de elevação da Kamino, vaults inteligentes da Fluid, incentivos, limites de liquidez e custos de transação não entram no cálculo.

As conversas são salvas no navegador. Pedidos de swap USDC/WETH na Ethereum e entrada nas 13 pools do catálogo usam dados públicos de leitura do Altside. As seis pools canônicas e Robinhood usam suas rotas próprias; WETH/USDC na Ethereum usa a rota legada; as três pools Orca usam o orçamento indicativo do motor Solana. As duas pools HyperEVM mostram alocação geométrica indicativa calculada pela Alt-IA a partir de preço e tick canônicos do Altside, sem cotação de execução. A origem e os limites de cada prévia são identificados no resultado. Se faltarem valor ou par, o chat pede os dados necessários; as demais perguntas seguem para o modelo. Nenhuma rota de carteira ou execução de transação é chamada.

Para entradas em pools, a interface oferece uma janela de configuração com pool, capital, faixa em ticks e slippage. O gráfico de preço mostra velas históricas reais da própria pool obtidas pelas rotas do Altside, com intervalos de 15 minutos a 1 dia e linhas arrastáveis de piso e teto. SOL/USDC usa a rota Orca dedicada. O preço atual e o bloco ou slot vêm separadamente do snapshot canônico; o histórico via GeckoTerminal é informativo e pode estar defasado. Os limites explícitos, alinhados ao espaçamento da pool, são enviados ao motor quando aceitos pela rota. Se o histórico ou o snapshot estiver indisponível, o campo numérico continua disponível; prévias analíticas e Orca exigem snapshot atual. As opções vêm do catálogo atual do Altside; a seleção é enviada como parâmetros estruturados e validada novamente no backend. A mesma janela abre quando um pedido em texto deixa parâmetros de pool pendentes.

Após a prévia canônica de entrada, o backend mostra uma tabela ilustrativa de sensibilidade para quedas e altas de 10% e 20% no preço do token base. O valor da posição usa a matemática contínua de liquidez concentrada, ancorada na alocação e nos limites retornados pelo motor Altside. São hipóteses instantâneas, sem taxas futuras de LP, gás, slippage efetivo ou impostos; não são previsão nem cotação de saída. O chat sempre encerra a resposta com uma pergunta relacionada ao assunto.

O botão **News** envia diretamente ao chat um pedido de resumo das notícias publicadas no dia, no horário de Brasília. O bot seleciona destaques de cripto e macro, sintetiza títulos e resumos com o Nemotron e mostra as fontes originais em cartões clicáveis. Pedidos por uma moeda usam a busca pública do Research Lab e aceitam somente resultados classificados como `noticia`; documentos de casas de research e Basecamp são descartados. A chave do gateway do Sherlock não é usada nem publicada. Se a síntese do modelo falhar, as manchetes verificadas continuam disponíveis.

O botão **+** do compositor ativa ou desativa o **Modo Nerd** por conversa. A tela passa a oferecer **Estratégias** e **Research**, com mascote, fontes e ícone azul no histórico. Nesse modo, o agente consulta a web por um SearXNG privado, filtra fontes públicas e entrega os resultados numerados ao Nemotron para uma resposta mais aprofundada. A instância de produção `alt-ia-search` escuta apenas na interface Docker do servidor; o backend a acessa por `ALT_IA_SEARCH_URL` (padrão `http://172.17.0.1:8888/search`). A busca não usa a chave NVIDIA para consultar a web. Os links externos continuam visíveis para conferência do usuário.

O botão **Rastrear wallet** abre uma janela para Bitcoin, Ethereum ou Solana. A Alt-IA consulta o endereço público no Altside; para Ethereum tenta incluir USDC, USDT, WETH, WBTC e DAI diretos via RPC, e para Solana tenta incluir USDC direto. Saldos com preço recente e confiável do DefiLlama compõem o gráfico de alocação. Os cartões de 24 horas, 7 e 30 dias calculam a variação de preço **com as quantidades atuais fixas**; não são lucro/prejuízo real, pois fluxos e operações passadas não são reconstituídos. Outros tokens, NFTs e posições DeFi podem ficar fora. A síntese da Alt-IA recebe apenas esses dados filtrados, enquanto o cartão numérico é calculado no servidor. Não há conexão, assinatura, transação ou monitoramento contínuo da carteira.

No **Modo Agente**, a janela do navegador fica ao lado do chat. A captura enviada ao site usa 1280 × 720 pixels. A consulta periódica de estado não varre o conteúdo da página, e uma nova captura é pedida somente após navegação ou ação; durante a reprodução de vídeo, a captura fica suspensa. O vídeo incorporado do YouTube escolhe sua própria qualidade. O player pede volume máximo e som ativo, mas a política de reprodução automática do navegador pode exigir um toque no vídeo. Para abrir a mini janela ao trocar para outra aba do Chrome ou Edge, instale a [extensão própria](extension/README.md). Ela observa apenas a aba da Alt-IA, abre a janela quando a aba deixa de estar ativa, mostra o vídeo atual quando houver um e fecha ao voltar. O navegador temporário permanece em um contêiner sem capacidades extras, com sistema de arquivos somente de leitura, perfil seccomp e proxy que bloqueia endereços privados. Nesta VM, o Chromium novo só inicia com o sandbox interno desativado; a segurança da sessão depende dessas barreiras do contêiner.

```bash
python3 -m unittest discover -s backend -p 'test_*.py' -v
```
# Basecamp: conhecimento interno

O importador em `backend/basecamp_import.py` usa a autorização por dispositivo da API oficial do Basecamp, com escopo de leitura e renovação para sincronizações futuras. Ele não copia cookies do navegador. A autorização e a base SQLite com índice de busca são arquivos criptografados com AES-GCM; a chave de 32 bytes deve ficar em um caminho privado e separado da base. O servidor só consulta essa base para contas do domínio definido em `ALT_IA_KNOWLEDGE_ALLOWED_DOMAINS` (padrão: `altside.com`).

No servidor, instale `backend/requirements.txt`, defina `ALT_IA_KNOWLEDGE_KEY_FILE` e execute:

```sh
python backend/basecamp_import.py --state-dir /var/lib/alt-ia/knowledge init
python backend/basecamp_import.py --state-dir /var/lib/alt-ia/knowledge authorize
python backend/basecamp_import.py --state-dir /var/lib/alt-ia/knowledge accounts
python backend/basecamp_import.py --state-dir /var/lib/alt-ia/knowledge list --account ID_DA_CONTA
python backend/basecamp_import.py --state-dir /var/lib/alt-ia/knowledge select --account ID_DA_CONTA ID_DO_PROJETO [OUTROS_IDS...]
python backend/basecamp_import.py --state-dir /var/lib/alt-ia/knowledge sync --account ID_DA_CONTA
```

`authorize` mostra um endereço e código para aprovar na própria conta. `select` limita os projetos autorizados. `sync` percorre pastas e a listagem paginada de registros ativos/arquivados: documentos, uploads, mensagens, comentários, cartões, tarefas, respostas de check-ins e agenda. Registros arquivados mantêm essa indicação. Notícias e perguntas/respostas preservam data, autor e discussão de origem; não são promovidas automaticamente a políticas atuais.

O importador inclui `content_attachments` e `description_attachments`, mantendo os arquivos vinculados aos pais. A paginação truncada interrompe a publicação, evitando remoções baseadas numa listagem parcial. Anexos suportados entram numa fila criptografada para leitura visual/transcrição; formatos desconhecidos e documentos acima de 32 MiB ficam explicitamente identificados como não extraídos.

O chat interpreta até 40 mensagens, a última pesquisa assinada e o documento aberto. Uma chamada de planejamento consulta o catálogo dos documentos, candidatos de discussões e buscas locais complementares. Comentários recuperam também a pergunta/documento de origem. Até 14 fontes e 36 mil caracteres de evidência são usados para formular a explicação. Documentos longos informam cobertura parcial; não é necessário enviar toda a base em cada pergunta. Respostas são transmitidas progressivamente por SSE, sem expor raciocínio interno; somente a resposta final validada entra no histórico.

Catálogo e evidências são dados não confiáveis, separados das instruções. IDs retornados pelo modelo são validados; ele não recebe ferramenta para executar código, modificar dados ou buscar URLs arbitrárias. Se o planejamento falhar, a busca textual usa o contexto recente e informa sua limitação ao modelo. Uma recuperação vazia nunca comprova que uma política ou estratégia não existe. O histórico anterior do assistente também não é fonte documental. As chamadas de planejamento e síntese entram no consumo de tokens da conta; a seleção de documentos não significa que todo o arquivo foi lido nem que houve pesquisa na web.

Para ativar a consulta no servidor, defina `ALT_IA_KNOWLEDGE_DB=/var/lib/alt-ia/knowledge/knowledge.enc` e `ALT_IA_KNOWLEDGE_KEY_FILE=/run/secrets/alt-ia-knowledge-key`. Mantenha o diretório de dados e o arquivo da chave acessíveis apenas ao serviço. A API não deve expor esses arquivos pela página web. Se a autorização for revogada no Basecamp, a sincronização para; para descartar também a cópia local, remova a seleção e a base criptografada.


## PDFs dentro da conversa

`knowledge_delivery.py` exige uma resposta estruturada com explicação, pergunta de continuidade e IDs de até três PDFs/vídeos pertinentes. O servidor valida esses IDs contra os arquivos associados às evidências. A resposta interna não mostra links do Basecamp. O histórico da conta preserva os cartões dos documentos para outros navegadores.

O importador mantém os PDFs originais criptografados com AES-GCM em `documents/<sha256>.enc`, ao lado da base criptografada. Metadados e vínculo com a fonte ficam dentro do SQLite criptografado. A sincronização também preenche os originais ausentes sem repetir a extração de texto. Os bytes são descriptografados em memória e servidos por `/api/knowledge/documents/<id>` somente após validar a sessão e o domínio de acesso à base. O endpoint usa `no-store`, não aceita URLs e deixa de servir arquivos removidos da seleção. Cópias criptografadas antigas podem permanecer no diretório de dados; ao descartar a base, descarte também esse diretório.

O frontend carrega PDF.js somente quando uma miniatura entra na tela ou a pessoa abre o leitor. A primeira página fornece a capa real; o leitor exibe páginas, zoom e texto acessível, sem executar scripts ou links do PDF. Até 24 capas ficam em memória durante a sessão, sem IndexedDB ou armazenamento persistente. Os recursos do PDF.js são locais e gerados por `npm run build`; publique `pdf-reader.js`, `pdf.worker.js` e `pdf-assets/` junto da página. O diálogo compartilha as animações e formas geométricas das janelas dos atalhos, respeitando redução de movimento.


## Memória multimodal e processamento em segundo plano

`knowledge_worker.py` consome `content_jobs`, preservando o conteúdo e o progresso no mesmo SQLite criptografado. Cada gravação recarrega o snapshot sob `sync.lock`; um resultado de versão antiga ou fonte revogada não pode recolocar dados removidos. `worker.lock` impede consumidores duplicados. Cache visual é identificado por hash do conteúdo e versão do extrator. O worker alterna imagens, vídeos e documentos; vídeos longos cedem a fila após um minuto processado e retomam do ponto salvo.

- **Imagens, tabelas e rankings:** Nemotron visual lê a imagem completa e ampliações, preservando seções/relações e sinalizando nomes ilegíveis. A saída estruturada é convertida em texto pesquisável.
- **PDFs:** texto de todas as páginas; páginas com imagens ou pouco texto também são renderizadas pelo Poppler e lidas visualmente. Arquivos temporários ficam exclusivamente em `/dev/shm`, são privados e removidos ao terminar.
- **DOCX/PPTX/XLSX:** texto, tabelas, notas e imagens incorporadas, com localização da imagem no documento. Fórmulas de planilha usam o valor salvo, sem executar macros ou fórmulas.
- **Vídeos:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcreve áudio em blocos de RAM; [PySceneDetect](https://www.scenedetect.com/api/) detecta mudanças numa amostragem de 2fps e seleciona quadros adicionais a cada 30s. Nemotron interpreta esses quadros. O texto guarda a linha do tempo e indica a cobertura visual parcial. Nomes e números transcritos podem precisar de conferência. A transcrição local evita depender da disponibilidade de serviços externos de voz.

Nenhum vídeo ou arquivo de áudio é salvo em disco. O worker usa um proxy efêmero em loopback para permitir leitura por intervalos ao FFmpeg, sem colocar credenciais Basecamp nos argumentos. Modelos de transcrição são cacheados separadamente; são pesos públicos, não mídia da empresa. O player também transmite por `/api/knowledge/videos/<id>` com Range, sessão e ACL. URLs assinadas e tokens nunca chegam ao navegador.

### Operação

Construa `backend/Dockerfile.knowledge` como `alt-ia-knowledge:20261128` e execute `sh backend/run_knowledge_worker.sh` no host, com os caminhos de produção. O worker fica sem portas públicas, filesystem de sistema somente leitura, limite de 2 CPUs e 4 GiB. A API web continua na imagem leve existente. A sincronização diária enfileira novos arquivos/versões, sem fazer OCR durante as perguntas.

`basecamp_import.py ... status` mostra contagens por tipo e estado (`pending`, `processing`, `retry`, `failed`, `complete`). Logs do worker contêm somente IDs, contagens e classes de erro. Após três falhas o item fica `failed`, nunca é anunciado como lido. Para reprocessar, uma operação administrativa pode reabrir o item da fila após resolver a causa. `--once --source ID` permite validar uma fonte específica sem alterar a seleção de projetos.

Limites explícitos: não há garantia de leitura perfeita; quadros transitórios entre amostras podem escapar, links para plataformas externas não concedem acesso ao conteúdo, formatos não suportados permanecem sinalizados, e uma extração concluída não transforma material de referência em política oficial. A memória documental é separada do histórico privado de cada usuário. A transcrição e o OCR ainda pendentes aparecem na cobertura entregue ao modelo.
