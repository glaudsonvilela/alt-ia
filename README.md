<p align="center">
  <img src="assets/mascote-alt-ia.svg" width="120" height="120" alt="Mascote roxo de dois olhos da Alt-IA">
</p>

<h1 align="center">Alt-IA</h1>

<p align="center">Chat de IA para explorar cenários de blockchain e DeFi no simulador Altside.</p>

<p align="center"><a href="https://ai.bigbanana.io/">Abrir a Alt-IA</a></p>

## Estrutura

- `site/`: interface, animações, fontes, imagens e configuração do Nginx.
- `backend/`: API Python que atende o chat, encaminha perguntas gerais ao NVIDIA Nemotron 120B e consulta o motor Rust do Altside para prévias de simulação.

## Desenvolvimento

```bash
cd site
npm ci
npm run build
```

O site usa o `app.js` compilado. Para executar o backend, configure `ALT_IA_KEY_FILE` com o caminho de um arquivo local contendo a chave NVIDIA. A chave não deve entrar no repositório. O backend também aceita `ALT_IA_HOST`, `ALT_IA_PORT` e `ALTSIDE_API_BASE_URL` (padrão: `https://app.bigbanana.io`).

As conversas são salvas no navegador. Pedidos de swap USDC/WETH na Ethereum e entrada nas pools canônicas suportadas usam as rotas públicas de leitura do Altside. O servidor valida o tipo de resposta, o bloco canônico e o caráter somente leitura antes de exibir os valores. Se faltarem valor ou par, o chat pede os dados necessários; as demais perguntas seguem para o modelo. Nenhuma rota de carteira ou execução de transação é chamada.

Para entradas em pools, a interface oferece uma janela de configuração com pool, capital, faixa em ticks e slippage. O gráfico da faixa consulta o tick e o bloco atuais da pool; suas bordas e o centro podem ser arrastados, e os limites explícitos alinhados ao espaçamento da pool são enviados ao motor Rust. A escala representa ticks matemáticos, não um histórico de preços. Se o snapshot estiver indisponível, o campo numérico continua disponível e o motor calcula a faixa pelo modo de largura. As opções vêm do catálogo atual do Altside; a seleção é enviada como parâmetros estruturados e validada novamente no backend. A mesma janela abre quando um pedido em texto deixa parâmetros de pool pendentes.

```bash
python3 -m unittest discover -s backend -p 'test_*.py' -v
```
