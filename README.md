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

```bash
python3 -m unittest discover -s backend -p 'test_*.py' -v
```
