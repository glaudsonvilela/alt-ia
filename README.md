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

## Acesso privado

A Alt-IA usa login Google corporativo seguido por um código enviado ao mesmo e-mail. O servidor confere o token Google, a declaração de domínio Google Workspace (`hd=altside.com`) e o e-mail verificado. O código tem seis dígitos, expira em dez minutos e aceita até cinco tentativas. A sessão dura 12 horas e pode ser encerrada pelo botão **Sair da Alt-IA**. A tela inicial e seus recursos visuais são públicos; o login aparece ao enviar uma mensagem ou clicar em um atalho. Todas as APIs de dados e ações continuam exigindo sessão no backend. A ação iniciada é retomada depois da entrada.

Não é necessário cadastrar cartão no Cloudflare Zero Trust, e o servidor da Alt-IA pode continuar local. O cliente OAuth web já criado deve ter `https://ai.bigbanana.io` como **origem JavaScript autorizada**. Para enviar o código sem senha de aplicativo nem acesso ao administrador do Google Workspace, use a API do Gmail com a conta `glaudson@altside.com`. Essa autorização pede apenas `gmail.send` (envio; sem leitura da caixa).

1. No [Google Cloud Console](https://console.cloud.google.com/apis/library/gmail.googleapis.com), selecione o projeto desse cliente OAuth e ative a **Gmail API**. No [Google Auth Platform](https://console.cloud.google.com/auth/scopes), adicione o escopo `https://www.googleapis.com/auth/gmail.send`. Mantenha o público **Interno**.
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
ALT_IA_ALLOWED_EMAIL_DOMAIN=altside.com
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
