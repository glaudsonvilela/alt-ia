<p align="center">
  <img src="assets/mascote-alt-ia.svg" width="120" height="120" alt="Mascote roxo de dois olhos da Alt-IA">
</p>

<h1 align="center">Alt-IA</h1>

<p align="center">Chat de IA para explorar cenários de blockchain e DeFi no simulador Altside.</p>

<p align="center"><a href="https://ai.bigbanana.io/">Abrir a Alt-IA</a></p>

## Estrutura

- `site/`: interface, animações, fontes, imagens e configuração do Nginx.
- `backend/`: API Python que encaminha as conversas ao modelo NVIDIA Nemotron 120B.

## Desenvolvimento

```bash
cd site
npm ci
npm run build
```

O site usa o `app.js` compilado. Para executar o backend, configure `ALT_IA_KEY_FILE` com o caminho de um arquivo local contendo a chave NVIDIA. A chave não deve entrar no repositório. O backend também aceita `ALT_IA_HOST` e `ALT_IA_PORT`.

As conversas são salvas no navegador. A integração com as funções do simulador Altside ainda está em desenvolvimento.
