<p align="center">
  <img src="assets/mascote-alt-ia.svg" width="120" height="120" alt="Mascote roxo de dois olhos da Alt-IA">
</p>

<h1 align="center">Alt-IA</h1>

<p align="center">Chat de IA para explorar cenários de blockchain e DeFi no simulador Altside.</p>

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

O site usa o `app.js` compilado. Para executar o backend, configure `ALT_IA_KEY_FILE` com o caminho de um arquivo local contendo a chave NVIDIA. A chave não deve entrar no repositório. O backend também aceita `ALT_IA_HOST`, `ALT_IA_PORT` e `ALTSIDE_API_BASE_URL` (padrão: `https://app.bigbanana.io`).

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
