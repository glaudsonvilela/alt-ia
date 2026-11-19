import http from 'node:http';
import net from 'node:net';
import dns from 'node:dns/promises';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const token = readFileSync('/run/secrets/browser-token', 'utf8').trim();
const sessions = new Map();
const MAX_SESSIONS = 4;
const IDLE_MS = 12 * 60 * 1000;
const PORT = 8822;

function publicIPv4(ip) {
  if (net.isIP(ip) !== 4) return false;
  const [a, b, c] = ip.split('.').map(Number);
  return !(a === 0 || a === 10 || a === 127 || a >= 224 || a === 169 && b === 254 ||
    a === 172 && b >= 16 && b <= 31 || a === 192 && (b === 168 || b === 0 && c === 0 || b === 0 && c === 2) ||
    a === 100 && b >= 64 && b <= 127 || a === 198 && (b === 18 || b === 19 || b === 51 && c === 100) ||
    a === 203 && b === 0 && c === 113);
}

async function resolvePublic(host) {
  if (!host || host.length > 253 || host === 'localhost' || host.endsWith('.local') || host.endsWith('.internal')) throw Error('Endereço privado bloqueado.');
  const { address } = await dns.lookup(host, { family: 4 });
  if (!publicIPv4(address)) throw Error('Endereço privado bloqueado.');
  return address;
}

async function safeUrl(raw) {
  const url = new URL(raw);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || !url.hostname || raw.length > 1600) throw Error('URL inválida.');
  await resolvePublic(url.hostname);
  return url.href;
}

// All browser traffic passes through this proxy. It resolves once and connects to the vetted IP.
const proxy = http.createServer(async (req, res) => {
  try {
    const target = new URL(req.url);
    const ip = await resolvePublic(target.hostname);
    const upstream = http.request({ host: ip, port: Number(target.port) || 80, path: target.pathname + target.search,
      method: req.method, headers: { ...req.headers, host: target.host }, timeout: 15000 }, response => {
      res.writeHead(response.statusCode, response.headers); response.pipe(res);
    });
    upstream.on('error', () => res.writeHead(502).end());
    req.pipe(upstream);
  } catch { res.writeHead(403).end(); }
});
proxy.on('connect', async (req, socket, head) => {
  try {
    const [host, portText] = req.url.split(':');
    const port = Number(portText);
    if (![80, 443].includes(port)) throw Error('Porta bloqueada.');
    const ip = await resolvePublic(host);
    const upstream = net.connect(port, ip, () => {
      socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      if (head.length) upstream.write(head);
      socket.pipe(upstream); upstream.pipe(socket);
    });
    upstream.setTimeout(20000);
    upstream.on('timeout', () => upstream.destroy());
    upstream.on('error', () => socket.destroy());
    socket.on('error', () => upstream.destroy());
  } catch { socket.end('HTTP/1.1 403 Forbidden\r\n\r\n'); }
});
await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
const proxyPort = proxy.address().port;
const chromeProcess = spawn('xvfb-run', ['-a', chromium.executablePath(),
  '--user-data-dir=/tmp/alt-ia-chrome', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=9223',
  '--no-sandbox',
  '--no-first-run', '--no-default-browser-check', '--disable-dev-shm-usage', '--window-size=1100,720',
  `--proxy-server=http://127.0.0.1:${proxyPort}`, '--proxy-bypass-list=<-loopback>', 'about:blank'],
{ stdio: ['ignore', 'ignore', 'inherit'] });
process.once('exit', () => chromeProcess.kill('SIGTERM'));
let browser;
for (let attempt = 0; attempt < 40 && !browser; attempt += 1) {
  try { browser = await chromium.connectOverCDP('http://127.0.0.1:9223', { timeout: 1000 }); }
  catch { await new Promise(resolve => setTimeout(resolve, 300)); }
}
if (!browser) throw Error('Navegador temporário não iniciou.');

function json(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}
async function input(req) {
  let raw = '';
  for await (const chunk of req) { raw += chunk; if (raw.length > 12000) throw Error('Entrada muito longa.'); }
  return raw ? JSON.parse(raw) : {};
}
async function snapshot(session) {
  const page = session.page;
  return { url: page.url(), title: (await page.title().catch(() => '')).slice(0, 200),
    text: (await page.locator('body').innerText({ timeout: 5000 }).catch(() => '')).slice(0, 11000),
    elements: await page.locator('a,button,input,textarea,[role="button"]').evaluateAll(nodes => nodes.slice(0, 100).map((el, index) => {
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (box.width < 4 || box.height < 4 || style.visibility === 'hidden' || style.display === 'none' || box.bottom < 0 || box.top > innerHeight) return null;
      const kind = el.tagName.toLowerCase();
      const label = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().slice(0, 100);
      const inputType = el.getAttribute('type') || '';
      const safeButton = /^(menu|buscar|pesquisar|search|próximo|next|voltar|back|abrir|open|filtro|filter|mais|more)$/i.test(label);
      const risky = (kind === 'button' || el.getAttribute('role') === 'button') &&
        (inputType === 'submit' || !!el.closest('form') || !safeButton) ||
        /enviar|comprar|vender|confirmar|apagar|excluir|transferir|pagar|publicar|salvar|send|buy|sell|delete|transfer|pay|publish|save/i.test(label);
      return { index, kind, label, inputType, x: Math.round(box.left + box.width / 2), y: Math.round(box.top + box.height / 2), risky, url: kind === 'a' ? el.href : '' };
    }).filter(Boolean)).catch(() => []),
    status: session.status, updated: session.updated, cursor: session.cursor || null };
}
async function moveCursor(page, x, y) {
  await page.evaluate(({ x, y }) => {
    let cursor = document.getElementById('alt-ia-agent-cursor');
    if (!cursor) {
      cursor = document.createElement('span'); cursor.id = 'alt-ia-agent-cursor';
      cursor.style.cssText = 'position:fixed;width:17px;height:17px;border:2px solid #fff;background:#ff8647;border-radius:50%;box-shadow:0 0 0 3px #ff864766;z-index:2147483647;pointer-events:none;transition:left .16s,top .16s;';
      document.documentElement.append(cursor);
    }
    cursor.style.left = `${x}px`; cursor.style.top = `${y}px`;
  }, { x, y }).catch(() => {});
  await page.mouse.move(x, y, { steps: 6 });
}
async function closeSession(id) {
  const session = sessions.get(id);
  if (!session) return;
  sessions.delete(id);
  await session.context.close().catch(() => {});
}
setInterval(() => { for (const [id, session] of sessions) if (Date.now() - session.updated > IDLE_MS) void closeSession(id); }, 30000).unref();

http.createServer(async (req, res) => {
  if (req.headers['x-browser-token'] !== token) return json(res, 403, { error: 'Acesso negado.' });
  const parts = new URL(req.url, 'http://worker').pathname.split('/').filter(Boolean);
  try {
    if (req.method === 'POST' && parts.length === 1 && parts[0] === 'sessions') {
      if (sessions.size >= MAX_SESSIONS) return json(res, 429, { error: 'Navegadores ocupados. Tente novamente em instantes.' });
      const context = await browser.newContext({ viewport: { width: 1100, height: 720 }, deviceScaleFactor: 2 / 3,
        acceptDownloads: false, serviceWorkers: 'block', permissions: [] });
      await context.route('**/*', async route => {
        const url = route.request().url();
        if (url === 'about:blank' || url.startsWith('data:') && route.request().resourceType() === 'image') return route.continue();
        try { await safeUrl(url); await route.continue(); } catch { await route.abort(); }
      });
      const page = await context.newPage();
      page.setDefaultTimeout(12000);
      page.on('download', download => download.cancel());
      const id = crypto.randomBytes(24).toString('hex');
      const session = { context, page, status: 'Pronto para abrir um site.', updated: Date.now(), cursor: null };
      context.on('page', popup => {
        if (popup === session.page) return;
        session.page = popup;
        popup.setDefaultTimeout(12000);
        popup.on('download', download => download.cancel());
        session.status = 'Abrindo nova página';
      });
      sessions.set(id, session);
      return json(res, 200, { id });
    }
    const session = sessions.get(parts[1]);
    if (parts[0] !== 'sessions' || !session) return json(res, 404, { error: 'Sessão encerrada.' });
    session.updated = Date.now();
    if (req.method === 'DELETE' && parts.length === 2) { await closeSession(parts[1]); return json(res, 200, { closed: true }); }
    if (req.method === 'GET' && parts[2] === 'snapshot') return json(res, 200, await snapshot(session));
    if (req.method === 'GET' && parts[2] === 'image') {
      const image = await session.page.screenshot({ type: 'jpeg', quality: 48, scale: 'device', timeout: 8000 });
      res.writeHead(200, { 'Content-Type': 'image/jpeg', 'Cache-Control': 'no-store', 'Content-Length': image.length });
      return res.end(image);
    }
    if (req.method !== 'POST') return json(res, 404, { error: 'Ação desconhecida.' });
    const data = await input(req);
    const action = parts[2];
    if (action === 'navigate') {
      const url = await safeUrl(String(data.url || ''));
      session.status = `Abrindo ${new URL(url).hostname}`;
      try {
        const response = await session.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
        session.status = response?.ok() ? 'Pronto para navegar' : response ? `Site indisponível (${response.status()}).` : 'Página aberta.';
      } catch { session.status = 'Não foi possível carregar esta página.'; }
    } else if (action === 'click') {
      const index = Number(data.index);
      if (!Number.isInteger(index) || index < 0 || index > 99) throw Error('Elemento inválido.');
      const elements = (await snapshot(session)).elements;
      const element = elements.find(item => item.index === index);
      if (!element) throw Error('Elemento não encontrado.');
      if (element.risky) throw Error('Essa ação precisa ser feita por você na mini janela.');
      if (element.url) await safeUrl(element.url);
      session.status = `Clicando em ${element.label || element.kind}`;
      session.cursor = { x: element.x, y: element.y };
      const beforeUrl = session.page.url();
      await moveCursor(session.page, element.x, element.y);
      await session.page.mouse.click(element.x, element.y);
      await session.page.waitForLoadState('domcontentloaded', { timeout: 5000 }).catch(() => {});
      if (session.page.url() === beforeUrl && element.url) {
        await session.page.goto(element.url, { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {});
      }
    } else if (action === 'fill') {
      const index = Number(data.index), value = String(data.value || '');
      const element = (await snapshot(session)).elements.find(item => item.index === index);
      if (!element || !['input', 'textarea'].includes(element.kind) || ['password', 'hidden', 'file'].includes(element.inputType) || value.length > 200) throw Error('Campo inválido.');
      session.status = `Digitando em ${element.label || 'campo'}`;
      session.cursor = { x: element.x, y: element.y };
      await moveCursor(session.page, element.x, element.y);
      await session.page.mouse.click(element.x, element.y);
      await session.page.keyboard.press('ControlOrMeta+A');
      await session.page.keyboard.type(value, { delay: 12 });
    } else if (action === 'agent-scroll') {
      const dy = Math.max(-600, Math.min(600, Number(data.dy) || 450));
      session.status = 'Rolando a página';
      await session.page.mouse.wheel(0, dy);
    } else if (action === 'manual-click') {
      const x = Number(data.x), y = Number(data.y);
      if (![x, y].every(Number.isFinite) || x < 0 || x > 1100 || y < 0 || y > 720) throw Error('Clique inválido.');
      await session.page.mouse.click(x, y);
      session.status = 'Clique manual';
      session.cursor = { x, y };
    } else if (action === 'type') {
      const value = String(data.value || '');
      if (value.length > 500) throw Error('Texto muito longo.');
      await session.page.keyboard.type(value, { delay: 7 });
      session.status = 'Texto digitado manualmente';
    } else if (action === 'key') {
      if (!['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'ControlOrMeta+A'].includes(data.key)) throw Error('Tecla inválida.');
      await session.page.keyboard.press(data.key);
      session.status = 'Navegação manual';
    } else if (action === 'scroll') {
      await session.page.mouse.wheel(0, Math.max(-800, Math.min(800, Number(data.dy) || 560)));
      session.status = 'Rolando a página';
    } else { return json(res, 404, { error: 'Ação desconhecida.' }); }
    session.updated = Date.now();
    return json(res, 200, await snapshot(session));
  } catch (error) { return json(res, 400, { error: String(error.message || 'Falha no navegador').slice(0, 180) }); }
}).listen(PORT, '0.0.0.0');
