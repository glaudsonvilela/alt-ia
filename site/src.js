import { animate, stagger } from 'motion';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';

const intro = document.querySelector('#intro');
const site = document.querySelector('.site');
const skip = document.querySelector('.intro-skip');
const chatForm = document.querySelector('#chat-form');
const chatInput = document.querySelector('#chat-input');
const chatMessages = document.querySelector('#chat-messages');
const welcome = document.querySelector('#welcome');
const modePlus = document.querySelector('#mode-plus');
const modeMenu = document.querySelector('#mode-menu');
const nerdToggle = document.querySelector('#nerd-toggle');
const agentToggle = document.querySelector('#agent-toggle');
const agentIntro = document.querySelector('#agent-intro');
const agentWindow = document.querySelector('#agent-window');
const agentWindowHome = agentWindow?.parentElement;
const agentStatus = document.querySelector('#agent-status');
const agentUrl = document.querySelector('#agent-url');
const agentImage = document.querySelector('#agent-image');
const agentMedia = document.querySelector('#agent-media');
const agentPrivacy = document.querySelector('.agent-privacy');
const agentCursor = document.querySelector('#agent-cursor');
const modeBadge = document.querySelector('#mode-badge');
const nerdGrid = document.querySelector('#nerd-grid');
const agentGrid = document.querySelector('#agent-grid');
const agentShortcutStatus = document.querySelector('#agent-shortcut-status');
const normalGrid = document.querySelector('.prompt-grid');
const composerNote = document.querySelector('#composer-note');
const historyNav = document.querySelector('#conversation-history');
const newChatButton = document.querySelector('#new-chat');
const sidebar = document.querySelector('#sidebar');
const sidebarOverlay = document.querySelector('#sidebar-overlay');
const mobileMenu = document.querySelector('#mobile-menu');
const sidebarClose = document.querySelector('#sidebar-close');
const poolDialog = document.querySelector('#pool-dialog');
const lendingDialog = document.querySelector('#lending-dialog');
const walletDialog = document.querySelector('#wallet-dialog');
const walletForm = document.querySelector('#wallet-config-form');
const walletNetwork = document.querySelector('#wallet-network');
const walletAddress = document.querySelector('#wallet-address');
const walletFormError = document.querySelector('#wallet-form-error');
const lendingForm = document.querySelector('#lending-config-form');
const lendingMarketSelect = document.querySelector('#lending-market-select');
const lendingProtocolButtons = [...document.querySelectorAll('[data-lending-protocol]')];
const lendingSupplies = document.querySelector('#lending-supplies');
const lendingBorrows = document.querySelector('#lending-borrows');
const lendingFormError = document.querySelector('#lending-form-error');
const poolDialogClose = document.querySelector('#pool-dialog-close');

function burstShortcutDialog(rect) {
  const burst = document.createElement('div');
  burst.className = 'shortcut-dialog-burst';
  burst.setAttribute('aria-hidden', 'true');
  burst.style.left = `${rect.left}px`;
  burst.style.top = `${rect.top}px`;
  burst.style.width = `${rect.width}px`;
  burst.style.height = `${rect.height}px`;
  const levels = [0.18, 0.39, 0.61, 0.82];
  for (let index = 0; index < 8; index += 1) {
    const side = index < 4 ? -1 : 1;
    const row = index % 4;
    const piece = document.createElement('i');
    piece.className = `shortcut-dialog-piece shortcut-dialog-piece-${index % 6}`;
    piece.style.left = `${side < 0 ? 0 : rect.width}px`;
    piece.style.top = `${Math.round(rect.height * levels[row])}px`;
    piece.style.setProperty('--dx', `${side * (68 + (row % 2) * 24)}px`);
    piece.style.setProperty('--dy', `${Math.round((row - 1.5) * 18)}px`);
    piece.style.setProperty('--spin', `${side * (65 + row * 15)}deg`);
    piece.style.animationDelay = `${row * 20}ms`;
    burst.append(piece);
  }
  document.body.append(burst);
  window.setTimeout(() => burst.remove(), 650);
}

function closeShortcutDialog(dialog) {
  if (!dialog?.open || dialog.classList.contains('is-closing')) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    dialog.close();
    return;
  }
  const rect = dialog.getBoundingClientRect();
  dialog.classList.add('is-closing');
  window.setTimeout(() => {
    dialog.close();
    dialog.classList.remove('is-closing');
    burstShortcutDialog(rect);
  }, 260);
}

for (const dialog of [poolDialog, lendingDialog, walletDialog]) {
  dialog?.addEventListener('cancel', (event) => { event.preventDefault(); closeShortcutDialog(dialog); });
}
const poolForm = document.querySelector('#pool-config-form');
const poolNetwork = document.querySelector('#pool-network');
const poolSelect = document.querySelector('#pool-select');
const poolAvailability = document.querySelector('#pool-availability');
const poolSubmit = poolForm?.querySelector('.pool-submit');
const poolMode = document.querySelector('#pool-mode');
const poolPeriod = document.querySelector('#pool-period');
const poolPeriodField = document.querySelector('#pool-period-field');
const poolModeGrid = document.querySelector('#pool-mode-grid');
const poolCapital = document.querySelector('#pool-capital');
const poolCapitalUnit = document.querySelector('#pool-capital-unit');
const poolRange = document.querySelector('#pool-range');
const poolRangeHint = document.querySelector('#pool-range-hint');
const poolSlippage = document.querySelector('#pool-slippage');
const poolFormError = document.querySelector('#pool-form-error');
const rangeChart = document.querySelector('#range-chart');
const poolPriceCanvas = document.querySelector('#pool-price-canvas');
const poolPricePlot = document.querySelector('#pool-price-plot');
const poolPriceShade = document.querySelector('#pool-price-shade');
const poolFloorHandle = document.querySelector('#pool-floor-handle');
const poolCeilingHandle = document.querySelector('#pool-ceiling-handle');
const poolChartStatus = document.querySelector('#pool-chart-status');
const storageNamespace = window.altIaStorageNamespace;
if (!storageNamespace) throw new Error('Identidade da sessão indisponível.');
const storageKey = `alt-ia-conversations-v2:${storageNamespace}`;
const activeKey = `alt-ia-active-v2:${storageNamespace}`;
const deletedKey = `alt-ia-deleted-v2:${storageNamespace}`;
let poolOptions = null;
let pendingSimulationRequest = null;
let pendingWalletRequest = null;
let poolSnapshot = null;
let selectedRange = null;
let chartRequestSeq = 0;
let marketChart = null;
let marketCandles = null;
let marketLines = {};
let marketInterval = '1h';
let marketRequestSeq = 0;
let marketDrag = null;
let marketHasData = false;

function safeNews(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 7).filter((item) => item && typeof item.title === 'string' && typeof item.url === 'string' && /^https:\/\/[^\s/]+/.test(item.url))
    .map((item) => ({ title: item.title.slice(0, 230), url: item.url.slice(0, 600), source: String(item.source || 'Fonte').slice(0, 65),
      summary: String(item.summary || '').slice(0, 260), published_at: String(item.published_at || '').slice(0, 40), time_known: item.time_known === true }));
}

function safeResearch(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 14).filter((item) => item && typeof item.title === 'string' && typeof item.url === 'string'
    && /^https:\/\/[^\s/]+/.test(item.url)).map((item) => ({ title: item.title.slice(0, 220),
      url: item.url.slice(0, 700), summary: String(item.summary || '').slice(0, 550), source: String(item.source || '').slice(0, 80) }));
}

function safeVideo(value) {
  if (!value || value.provider !== 'youtube' || typeof value.id !== 'string') return null;
  const playlist = value.kind === 'playlist';
  if (playlist ? !/^[A-Za-z0-9_-]{10,80}$/.test(value.id) : !/^[A-Za-z0-9_-]{11}$/.test(value.id)) return null;
  return { provider: 'youtube', kind: playlist ? 'playlist' : 'video', id: value.id,
    title: typeof value.title === 'string' ? value.title.slice(0, 180) : '',
    url: playlist ? `https://www.youtube.com/playlist?list=${value.id}` : `https://www.youtube.com/watch?v=${value.id}` };
}

function agentConversationContext(conversation) {
  const previous = conversation.messages.slice(0, -1);
  const lastMediaMessage = [...previous].reverse().find((message) => message.role === 'ai' && safeVideo(message.video));
  return {
    history: previous.slice(-10).map((message) => ({
      role: message.role === 'ai' ? 'assistant' : 'user',
      content: message.text.slice(0, 450),
      ...(message.role === 'ai' && safeVideo(message.video) ? { video: safeVideo(message.video) } : {})
    })),
    last_media: lastMediaMessage ? safeVideo(lastMediaMessage.video) : null
  };
}

let youtubeApiPromise = null;
const activeVideoPlayers = [];
function ensureYouTubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!youtubeApiPromise) youtubeApiPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    let settled = false;
    const fail = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      script.remove();
      reject(new Error('Player indisponível.'));
    };
    const timer = setTimeout(fail, 12000);
    window.onYouTubeIframeAPIReady = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(window.YT);
    };
    script.src = 'https://www.youtube.com/iframe_api';
    script.onerror = fail;
    document.head.append(script);
  }).catch((error) => { youtubeApiPromise = null; throw error; });
  return youtubeApiPromise;
}

async function startVideoPlayer(frame, hint, track = true) {
  try {
    const YT = await ensureYouTubeApi();
    if (!frame.isConnected) return;
    let mutedFallback = false;
    const player = new YT.Player(frame, { events: {
      onReady: ({ target }) => {
        target.setVolume(100);
        target.unMute();
        target.playVideo();
      },
      onAutoplayBlocked: ({ target }) => {
        if (mutedFallback) return;
        mutedFallback = true;
        target.mute();
        target.playVideo();
        hint.textContent = 'O navegador bloqueou o som automático · toque no vídeo para ativar';
      },
      onStateChange: ({ target, data }) => {
        if (data === YT.PlayerState.PLAYING) {
          if (target.isMuted() && !mutedFallback) target.unMute();
          hint.textContent = target.isMuted() ? 'O navegador bloqueou o som automático · toque no vídeo para ativar' : 'Tocando com som';
        }
      },
      onError: () => { hint.textContent = 'Abra no YouTube para assistir'; }
    } });
    if (track) activeVideoPlayers.push(player);
    return player;
  } catch { hint.textContent = 'Toque no vídeo para iniciar'; }
}

function safePoolRequest(value) {
  if (!value || !['pool', 'historical_pool'].includes(value.kind) || typeof value.pool_id !== 'string'
      || typeof value.capital_quote !== 'string' || !Number.isSafeInteger(value.range_ticks)) return null;
  if (!/^\d+(?:[.,]\d{1,18})?$/.test(value.capital_quote) || value.pool_id.length > 120) return null;
  const result = { kind: value.kind, pool_id: value.pool_id, capital_quote: value.capital_quote, range_ticks: value.range_ticks };
  if (value.kind === 'pool') {
    if (!Number.isSafeInteger(value.slippage_bps)) return null;
    result.slippage_bps = value.slippage_bps;
    if (Number.isSafeInteger(value.tick_lower) && Number.isSafeInteger(value.tick_upper)) {
      result.tick_lower = value.tick_lower;
      result.tick_upper = value.tick_upper;
    }
  } else if (Number.isSafeInteger(value.period_days)) result.period_days = value.period_days;
  return result;
}

function safeLendingRequest(value) {
  if (value?.kind === 'lending' && value.version === 2) {
    const validAssetAddress = (address) => typeof address === 'string' && (/^0x[0-9a-fA-F]{40}$/.test(address) || /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address));
    const validMarketAddress = (address) => validAssetAddress(address) || typeof address === 'string' && /^0x[0-9a-fA-F]{64}$/.test(address);
    const validRow = (row, supply) => row && validAssetAddress(row.asset)
      && typeof row.amount === 'string' && /^\d+(?:\.\d{1,18})?$/.test(row.amount)
      && (!row.price || typeof row.price === 'string' && /^\d+(?:\.\d{1,18})?$/.test(row.price))
      && (!supply || typeof row.collateral === 'boolean');
    if (!Number.isInteger(value.chain_id) || !validMarketAddress(value.market_address)
        || !Array.isArray(value.supplies) || !value.supplies.length || value.supplies.length > 12
        || !Array.isArray(value.borrows) || value.borrows.length > 12
        || !value.supplies.every((row) => validRow(row, true)) || !value.borrows.every((row) => validRow(row, false))
        || !Number.isInteger(value.days) || value.days < 0 || value.days > 3650
        || !value.shock || !Number.isInteger(value.shock.pct) || value.shock.pct < -95 || value.shock.pct > 500
        || typeof value.shock.asset !== 'string') return null;
    return { kind: 'lending', version: 2, chain_id: value.chain_id, market_address: value.market_address,
      supplies: value.supplies, borrows: value.borrows, shock: value.shock, days: value.days };
  }
  if (!value || value.kind !== 'lending' || typeof value.collateral_weth !== 'string' || typeof value.borrow_usdc !== 'string'
      || !/^\d+(?:[.,]\d{1,8})?$/.test(value.collateral_weth) || !/^\d+(?:[.,]\d{1,6})?$/.test(value.borrow_usdc)
      || !Number.isSafeInteger(value.price_drop_pct) || value.price_drop_pct < 0 || value.price_drop_pct > 90) return null;
  return { kind: 'lending', collateral_weth: value.collateral_weth, borrow_usdc: value.borrow_usdc, price_drop_pct: value.price_drop_pct };
}

function safeWalletRequest(value) {
  if (!value || !['bitcoin', 'ethereum', 'solana'].includes(value.network) || typeof value.address !== 'string'
      || value.address.length < 26 || value.address.length > 90 || !/^[a-zA-Z0-9]+$/.test(value.address)) return null;
  return { network: value.network, address: value.address };
}

function safeWallet(value) {
  const request = safeWalletRequest(value);
  if (!request || typeof value.asset !== 'string' || !['BTC', 'ETH', 'SOL'].includes(value.asset)
      || typeof value.balance !== 'string' || !/^[\d.,]+$/.test(value.balance)) return null;
  const money = (item) => typeof item === 'string' && /^[+-]?[\d.,]+$/.test(item) ? item.slice(0, 45) : null;
  return { ...request, asset: value.asset, balance: value.balance.slice(0, 45),
    value_usdc: typeof value.value_usdc === 'string' && /^[\d.,]+$/.test(value.value_usdc) ? value.value_usdc.slice(0, 45) : null,
    total_usdc: money(value.total_usdc),
    scope: typeof value.scope === 'string' ? value.scope.slice(0, 330) : '',
    sources: Array.isArray(value.sources) ? value.sources.filter((item) => typeof item === 'string').slice(0, 5).map((item) => item.slice(0, 35)) : [],
    allocation: Array.isArray(value.allocation) ? value.allocation.slice(0, 7).filter((item) => item && typeof item.symbol === 'string'
      && /^[A-Z0-9]{2,10}$/.test(item.symbol) && money(item.value_usdc) && Number.isFinite(item.percent) && item.percent >= 0 && item.percent <= 100)
      .map((item) => ({ symbol: item.symbol, value_usdc: money(item.value_usdc), percent: item.percent })) : [],
    performance: Array.isArray(value.performance) ? value.performance.slice(0, 3).filter((item) => item && ['day', 'week', 'month'].includes(item.period))
      .map((item) => ({ period: item.period, label: typeof item.label === 'string' ? item.label.slice(0, 25) : '', available: item.available === true,
        change_usdc: money(item.change_usdc), change_pct: money(item.change_pct), direction: ['gain', 'loss', 'flat'].includes(item.direction) ? item.direction : 'flat',
        coverage: Number.isSafeInteger(item.coverage) ? item.coverage : 0, priced: Number.isSafeInteger(item.priced) ? item.priced : 0 })) : [],
    observed_at_unix_ms: Number.isSafeInteger(value.observed_at_unix_ms) ? value.observed_at_unix_ms : null,
    transaction_count: Number.isSafeInteger(value.transaction_count) ? value.transaction_count : null,
    transactions: Array.isArray(value.transactions) ? value.transactions.slice(0, 2).filter((item) => item && typeof item.txid === 'string'
      && /^[a-zA-Z0-9]{20,120}$/.test(item.txid) && ['received', 'sent', 'self_or_other'].includes(item.direction)
      && (item.direction === 'self_or_other' || typeof item.amount === 'string' && /^[\d.,]+$/.test(item.amount)))
      .map((item) => ({ txid: item.txid, direction: item.direction, amount: typeof item.amount === 'string' ? item.amount.slice(0, 45) : null,
        block_time_unix: Number.isSafeInteger(item.block_time_unix) ? item.block_time_unix : null, confirmed: item.confirmed === true })) : [] };
}

function safeSimulation(value) {
  if (!value || !['swap', 'pool', 'historical_pool', 'lending'].includes(value.kind) || !Array.isArray(value.metrics) || !value.source) return null;
  const isHistorical = value.kind === 'historical_pool';
  const clean = (v, max = 160) => typeof v === 'string' ? v.slice(0, max) : '';
  const metrics = value.metrics.slice(0, 6).filter((item) => item && typeof item.label === 'string' && typeof item.value === 'string')
    .map((item) => ({ label: clean(item.label, 60), value: clean(item.value, 80) }));
  if (!metrics.length || (isHistorical
    ? value.source.kind !== 'historical_candles' || !Number.isSafeInteger(value.source.period_start) || !Number.isSafeInteger(value.source.period_end)
    : !Number.isSafeInteger(value.source.block_number) || value.source.block_number <= 0)) return null;
  const scenario = value.scenarios;
  const scenarios = scenario && Array.isArray(scenario.rows)
    ? { unit: clean(scenario.unit, 12), base_symbol: clean(scenario.base_symbol, 12), caption: clean(scenario.caption, 120), note: clean(scenario.note, 280),
        headers: Array.isArray(scenario.headers) && scenario.headers.length === 4 && scenario.headers.every((item) => typeof item === 'string')
          ? scenario.headers.map((item) => clean(item, 40)) : null,
        rows: scenario.rows.slice(0, 7).filter((row) => row && ['gain', 'loss', 'flat'].includes(row.tone)
          && ['label', 'price', 'value', 'pnl'].every((key) => typeof row[key] === 'string'))
          .map((row) => ({ label: clean(row.label, 30), price: clean(row.price, 30), value: clean(row.value, 30), pnl: clean(row.pnl, 30), tone: row.tone })) }
    : null;
  const extraTables = Array.isArray(value.extra_tables) ? value.extra_tables.slice(0, 3).filter((table) => table && Array.isArray(table.rows)
    && Array.isArray(table.headers) && table.headers.length === 4 && table.headers.every((item) => typeof item === 'string'))
    .map((table) => ({ caption: clean(table.caption, 120), note: clean(table.note, 280), headers: table.headers.map((item) => clean(item, 40)),
      rows: table.rows.slice(0, 12).filter((row) => row && ['gain', 'loss', 'flat'].includes(row.tone)
        && ['label', 'price', 'value', 'pnl'].every((key) => typeof row[key] === 'string'))
        .map((row) => ({ label: clean(row.label, 30), price: clean(row.price, 30), value: clean(row.value, 30), pnl: clean(row.pnl, 30), tone: row.tone })) })) : [];
  return {
    kind: value.kind, title: clean(value.title), subtitle: clean(value.subtitle), metrics, scenarios, extra_tables: extraTables,
    source: { engine: isHistorical ? 'Alt-IA · dados Altside' : clean(value.source.engine, 60), kind: isHistorical ? 'historical_candles' : value.source.kind === 'lending_live' ? 'lending_live' : 'live', block_number: isHistorical ? null : value.source.block_number,
      source_label: value.source.source_label === 'Slot' ? 'Slot' : value.source.source_label === 'Dados' ? 'Dados' : 'Bloco',
      period_start: isHistorical ? value.source.period_start : null, period_end: isHistorical ? value.source.period_end : null,
      block_timestamp: Number.isSafeInteger(value.source.block_timestamp) ? value.source.block_timestamp : null,
      captured_at: clean(value.source.captured_at, 40), validity: clean(value.source.validity, 180) },
    assumptions: Array.isArray(value.assumptions) ? value.assumptions.filter((item) => typeof item === 'string').slice(0, 5).map((item) => clean(item)) : [],
    url: 'https://app.bigbanana.io/'
  };
}

if (site) site.style.opacity = '0';

function readConversations() {
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (!Array.isArray(stored)) return [];
    return stored.filter((item) => item && typeof item.id === 'string' && Array.isArray(item.messages))
      .map((item) => ({
        id: item.id,
        title: typeof item.title === 'string' ? item.title : 'Nova conversa',
        pinned: item.pinned === true,
        nerdMode: item.nerdMode === true,
        agentMode: item.agentMode === true,
        nerdTopic: item.nerdTopic === 'strategies' ? 'strategies' : 'research',
        updatedAt: Number(item.updatedAt) || Date.now(),
        messages: item.messages.filter((message) => message && (message.role === 'user' || message.role === 'ai') && typeof message.text === 'string').slice(-100)
          .map((message) => ({ role: message.role, text: message.text, simulation: message.role === 'ai' ? safeSimulation(message.simulation) : null,
            wallet: message.role === 'ai' ? safeWallet(message.wallet) : null,
            news: message.role === 'ai' && !message.text.startsWith('🗞️ Aqui está um resumo das notícias que mostrei:') ? safeNews(message.news) : [],
            newsContext: message.role === 'ai' ? safeNews(message.newsContext || message.news) : [],
            research: message.role === 'ai' ? safeResearch(message.research) : [],
            video: message.role === 'ai' ? safeVideo(message.video) : null,
            nerdQuery: message.role === 'ai' && typeof message.nerdQuery === 'string' ? message.nerdQuery.slice(0, 650) : '',
            mode: message.role === 'ai' && ['news', 'pool', 'historical_pool', 'lending', 'wallet', 'general', 'nerd', 'agent'].includes(message.mode) ? message.mode : '',
            newsTopic: message.role === 'ai' && typeof message.newsTopic === 'string' ? message.newsTopic.slice(0, 30) : '',
            poolRequest: message.role === 'ai' ? safePoolRequest(message.poolRequest) : null,
            lendingRequest: message.role === 'ai' ? safeLendingRequest(message.lendingRequest) : null,
            walletRequest: message.role === 'ai' ? safeWalletRequest(message.walletRequest) : null,
            scenarioToken: message.role === 'ai' && typeof message.scenarioToken === 'string' ? message.scenarioToken.slice(0, 12000) : '',
            followUp: message.role === 'ai' && typeof message.followUp === 'string' ? message.followUp.slice(0, 280) : '' }))
      }));
  } catch {
    return [];
  }
}

const conversations = readConversations();
let deletedHistory = [];
try {
  const savedDeleted = JSON.parse(localStorage.getItem(deletedKey) || '[]');
  if (Array.isArray(savedDeleted)) deletedHistory = savedDeleted.filter((item) => item && typeof item.id === 'string').slice(-250);
} catch { /* The local cache remains usable. */ }
let activeId = localStorage.getItem(activeKey);
if (!conversations.some((item) => item.id === activeId)) {
  activeId = conversations.sort((a, b) => b.updatedAt - a.updatedAt)[0]?.id || null;
}
let draftNerdMode = false;
let draftAgentMode = false;
let draftNerdTopic = 'research';
const agentDesktop = window.matchMedia('(min-width: 900px) and (pointer: fine)');

function currentConversation() { return conversations.find((item) => item.id === activeId); }
function isNerdMode() { return currentConversation()?.nerdMode ?? draftNerdMode; }
function isAgentMode() { return agentDesktop.matches && (currentConversation()?.agentMode ?? draftAgentMode); }
function nerdTopic() { return currentConversation()?.nerdTopic || draftNerdTopic; }

function applyNerdModeUI() {
  const agent = isAgentMode();
  const active = isNerdMode() && !agent;
  const topic = nerdTopic();
  site?.classList.toggle('nerd-mode', active);
  site?.classList.toggle('agent-mode', agent);
  site?.classList.toggle('agent-session-open', agent && agentStarted);
  document.documentElement.dataset.altAgentActive = agentStarted ? 'true' : 'false';
  const mascot = welcome?.querySelector('.welcome-character');
  if (mascot) {
    mascot.style.backgroundColor = active ? '#81a6ed' : '#ad73d8';
    if (agent) mascot.style.setProperty('--fire', '#ef7844');
  }
  if (normalGrid) normalGrid.hidden = active || agent;
  if (nerdGrid) nerdGrid.hidden = !active;
  if (agentGrid) agentGrid.hidden = !agent;
  if (agentShortcutStatus && !agent) agentShortcutStatus.hidden = true;
  if (agentIntro) agentIntro.hidden = !agent;
  if (agentWindow) {
    agentWindow.hidden = !(agent && agentStarted);
    agentWindow.classList.remove('agent-window-inline');
    if (agentWindow.parentElement !== agentWindowHome) agentWindowHome?.append(agentWindow);
  }
  if (agentDock) agentDock.hidden = !agentStarted || agent || Boolean(agentPipWindow && !agentPipWindow.closed);
  const kicker = welcome?.querySelector('.welcome-kicker');
  const title = welcome?.querySelector('h1');
  const description = welcome?.querySelector(':scope > p');
  if (kicker) kicker.textContent = agent ? 'ALT-IA · MODO AGENTE' : active ? 'ALT-IA · MODO NERD' : 'ALT-IA · ALTSIDE';
  if (title) title.textContent = agent ? 'Vamos explorar juntos?' : active ? 'Vamos investigar a fundo?' : 'O que vamos simular hoje?';
  if (description) description.textContent = agent ? 'Peça para explorar um site. A janela aparece quando o agente começa a navegar.' : active
    ? 'Pesquise um tema ou explore uma estratégia. O agente consulta a web, compara fontes e organiza uma resposta detalhada.'
    : 'Descreva um cenário de mercado, uma pool ou uma estratégia. A Alt-IA pode ajudar você a explorar possibilidades.';
  if (chatInput) chatInput.placeholder = agent ? 'Peça ao agente para explorar o site aberto...' : active ? (topic === 'strategies' ? 'Descreva a estratégia que quer analisar...' : 'O que você quer pesquisar?') : 'Descreva o que você quer simular...';
  if (composerNote) composerNote.textContent = agent ? 'Navegador temporário. A sessão é apagada ao encerrar.' : active ? 'O agente consulta fontes públicas na web. Confira as referências antes de decidir.'
    : 'Pools, lending e wallets usam dados do Altside. Nenhuma transação é enviada.';
  if (modeBadge) { modeBadge.hidden = !active && !agent; modeBadge.textContent = agent ? 'Modo Agente' : `Modo Nerd · ${topic === 'strategies' ? 'Estratégias' : 'Research'}`; }
  if (nerdToggle) nerdToggle.setAttribute('aria-checked', String(active));
  if (agentToggle) agentToggle.setAttribute('aria-checked', String(agent));
  nerdGrid?.querySelectorAll('[data-nerd-topic]').forEach((button) => button.classList.toggle('selected', button.dataset.nerdTopic === topic));
  chatMessages?.querySelectorAll('.message-ai').forEach((row) => row.classList.toggle('message-nerd', active));
  syncAgentMediaSurface();
  requestAnimationFrame(positionAgentDock);
}

function closeModeMenu() {
  if (modeMenu) modeMenu.hidden = true;
  modePlus?.setAttribute('aria-expanded', 'false');
}

const historyPending = new Map();
const historyFingerprints = new Map();
const historyDeletePending = new Set(deletedHistory.map((item) => item.id));
let historyTimer = null;
let historyUploading = false;

function scheduleHistoryUpload(delay = 800) {
  if (!window.altIaAuthenticated || historyTimer) return;
  historyTimer = setTimeout(() => { historyTimer = null; void flushHistory(); }, delay);
}

async function flushHistory() {
  if (historyUploading || !window.altIaAuthenticated) return;
  historyUploading = true;
  try {
    while (historyDeletePending.size || historyPending.size) {
      if (historyDeletePending.size) {
        const id = historyDeletePending.values().next().value;
        const response = await fetch('/api/history/delete', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
        if (!response.ok) throw new Error('Não foi possível sincronizar uma exclusão.');
        historyDeletePending.delete(id);
        deletedHistory = deletedHistory.filter((item) => item.id !== id);
        localStorage.setItem(deletedKey, JSON.stringify(deletedHistory));
      } else {
        const [id, conversation] = historyPending.entries().next().value;
        historyPending.delete(id);
        const response = await fetch('/api/history', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ conversations: [conversation] }) });
        if (!response.ok) {
          historyPending.set(id, conversation);
          throw new Error('Não foi possível sincronizar uma conversa.');
        }
      }
    }
  } catch {
    scheduleHistoryUpload(10000);
  } finally { historyUploading = false; }
}

function queueHistoryChanges() {
  if (!window.altIaAuthenticated) return;
  for (const conversation of conversations) {
    const fingerprint = JSON.stringify(conversation);
    if (historyFingerprints.get(conversation.id) !== fingerprint) {
      historyFingerprints.set(conversation.id, fingerprint);
      historyPending.set(conversation.id, conversation);
    }
  }
  scheduleHistoryUpload();
}

function queueHistoryDelete(id) {
  if (!window.altIaAuthenticated) return;
  historyPending.delete(id);
  historyFingerprints.delete(id);
  historyDeletePending.add(id);
  deletedHistory.push({ id, updatedAt: Date.now() });
  deletedHistory = deletedHistory.slice(-250);
  try { localStorage.setItem(deletedKey, JSON.stringify(deletedHistory)); } catch { /* Retry in this tab. */ }
  scheduleHistoryUpload();
}

function persist() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(conversations));
    if (activeId) localStorage.setItem(activeKey, activeId);
    else localStorage.removeItem(activeKey);
    queueHistoryChanges();
  } catch {
    const notice = document.querySelector('#history-status');
    if (notice) { notice.textContent = 'O histórico não pôde ser salvo neste navegador.'; notice.hidden = false; }
  }
}

function titleFrom(text) {
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean.length > 42 ? `${clean.slice(0, 41).trimEnd()}…` : clean;
}

let pendingDeleteId = null;
const pinIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3h8l-1 6 3 3v2H6v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg>';
const deleteIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"/></svg>';
const historyLogoSvg = '<svg viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false"><g transform="rotate(-9 18 18)"><rect x="2" y="2" width="32" height="32" rx="12" fill="#ad73d8"/><ellipse cx="13" cy="17" rx="5.3" ry="8" fill="#fff"/><ellipse cx="23" cy="17" rx="5.3" ry="8" fill="#fff"/><ellipse cx="15" cy="19" rx="2.5" ry="4" fill="#17151a"/><ellipse cx="21" cy="19" rx="2.5" ry="4" fill="#17151a"/></g></svg>';
const historyNerdSvg = '<svg viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false"><rect x="2" y="2" width="32" height="32" rx="12" fill="#81a6ed"/><ellipse cx="13" cy="17" rx="4.4" ry="6.6" fill="#fff"/><ellipse cx="23" cy="17" rx="4.4" ry="6.6" fill="#fff"/><circle cx="14.2" cy="18" r="2.1" fill="#172038"/><circle cx="24.2" cy="18" r="2.1" fill="#172038"/><g fill="none" stroke="#25334f" stroke-width="1.8"><rect x="6.7" y="10.7" width="12.5" height="13" rx="3"/><rect x="18.9" y="10.7" width="12.5" height="13" rx="3"/><path d="M19 16h-1"/></g><path d="M15.5 27h5m-4.3 0v2.6m3.5-2.6v2.6" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>';
const historyAgentSvg = '<svg viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect x="2" y="2" width="32" height="32" rx="12" fill="#9b77cd"/><path d="M8 12 14 7 18 13 23 6 29 12v13H8Z" fill="#ff9d5d"/><ellipse cx="13" cy="19" rx="4" ry="6" fill="#fff1db"/><ellipse cx="23" cy="19" rx="4" ry="6" fill="#fff1db"/><ellipse cx="14" cy="20" rx="2" ry="3" fill="#472b3b"/><ellipse cx="24" cy="20" rx="2" ry="3" fill="#472b3b"/></svg>';

function createHistoryLogo(nerdMode = false, agentMode = false) {
  const icon = document.createElement('span');
  icon.className = `history-item-icon history-logo${nerdMode ? ' history-nerd' : ''}`;
  icon.setAttribute('aria-hidden', 'true');
  icon.innerHTML = agentMode ? historyAgentSvg : nerdMode ? historyNerdSvg : historyLogoSvg;
  return icon;
}

function renderHistory() {
  if (!historyNav) return;
  historyNav.replaceChildren();
  if (!conversations.length) {
    const empty = document.createElement('p');
    empty.className = 'history-empty';
    empty.textContent = 'Suas conversas aparecerão aqui.';
    historyNav.append(empty);
    return;
  }
  [...conversations].sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)) || b.updatedAt - a.updatedAt).forEach((conversation) => {
    const row = document.createElement('div');
    row.className = `history-row${conversation.id === activeId ? ' active' : ''}${conversation.pinned ? ' pinned' : ''}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'history-item';
    button.setAttribute('aria-current', conversation.id === activeId ? 'page' : 'false');
    button.title = conversation.title;
    const icon = createHistoryLogo(conversation.nerdMode, conversation.agentMode);
    const label = document.createElement('span');
    label.className = 'history-item-label';
    label.textContent = conversation.title;
    button.append(icon, label);
    button.addEventListener('click', () => {
      pendingDeleteId = null;
      activeId = conversation.id;
      persist();
      renderHistory();
      renderConversation();
      closeSidebar();
    });
    const actions = document.createElement('div');
    actions.className = 'history-actions';
    const pin = document.createElement('button');
    pin.type = 'button';
    pin.className = `history-action history-action-pin${conversation.pinned ? ' is-pinned' : ''}`;
    pin.innerHTML = pinIcon;
    pin.title = conversation.pinned ? 'Desafixar conversa' : 'Fixar conversa';
    pin.dataset.conversationId = conversation.id;
    pin.setAttribute('aria-label', `${pin.title}: ${conversation.title}`);
    pin.setAttribute('aria-pressed', String(conversation.pinned));
    pin.addEventListener('click', () => {
      pendingDeleteId = null;
      conversation.pinned = !conversation.pinned;
      conversation.updatedAt = Date.now();
      persist();
      renderHistory();
      [...historyNav.querySelectorAll('.history-action-pin')].find((item) => item.dataset.conversationId === conversation.id)?.focus();
    });

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = `history-action history-action-delete${pendingDeleteId === conversation.id ? ' is-confirming' : ''}`;
    remove.innerHTML = pendingDeleteId === conversation.id ? 'Apagar?' : deleteIcon;
    remove.title = pendingDeleteId === conversation.id ? 'Clique novamente para apagar' : 'Apagar conversa';
    remove.dataset.conversationId = conversation.id;
    remove.setAttribute('aria-label', `${pendingDeleteId === conversation.id ? 'Confirmar exclusão' : 'Apagar conversa'}: ${conversation.title}`);
    remove.addEventListener('click', () => {
      if (pendingDeleteId !== conversation.id) {
        pendingDeleteId = conversation.id;
        renderHistory();
        [...historyNav.querySelectorAll('.history-action-delete')].find((item) => item.dataset.conversationId === conversation.id)?.focus();
        return;
      }
      const index = conversations.findIndex((item) => item.id === conversation.id);
      if (index !== -1) conversations.splice(index, 1);
      queueHistoryDelete(conversation.id);
      if (agentStarted && agentOwnerId === conversation.id) void stopAgentSession();
      if (activeId === conversation.id) activeId = null;
      pendingDeleteId = null;
      persist();
      renderHistory();
      renderConversation();
    });
    actions.append(pin, remove);
    row.append(button, actions);
    historyNav.append(row);
  });
}

function createSimulationCard(simulation) {
  const card = document.createElement('section');
  card.className = 'simulation-card';
  card.setAttribute('aria-label', simulation.kind === 'historical_pool' ? 'Reconstituição com dados históricos do Altside' : simulation.kind === 'lending' ? 'Risco de lending calculado com dados do Altside' : 'Prévia calculada pelo Altside');
  const eyebrow = document.createElement('span');
  eyebrow.className = 'simulation-eyebrow';
  eyebrow.textContent = simulation.kind === 'lending' ? 'RISCO · AAVE V3'
    : simulation.kind === 'historical_pool' ? 'HISTÓRICO · DADOS ALTSIDE'
    : simulation.source.engine.startsWith('Alt-IA') ? 'ESTIMATIVA · PREÇO ALTSIDE' : 'PRÉVIA · MOTOR ALTSIDE';
  const title = document.createElement('h3');
  title.textContent = simulation.title;
  const subtitle = document.createElement('p');
  subtitle.className = 'simulation-subtitle';
  subtitle.textContent = simulation.subtitle;
  const grid = document.createElement('dl');
  grid.className = 'simulation-metrics';
  simulation.metrics.forEach((metric) => {
    const cell = document.createElement('div');
    const label = document.createElement('dt');
    label.textContent = metric.label;
    const value = document.createElement('dd');
    value.textContent = metric.value;
    cell.append(label, value);
    grid.append(cell);
  });
  let scenarioBlock = null;
  if (simulation.scenarios?.rows?.length) {
    scenarioBlock = document.createElement('div');
    scenarioBlock.className = 'simulation-scenario-block';
    const table = document.createElement('table');
    table.className = 'simulation-scenarios';
    const caption = document.createElement('caption');
    caption.textContent = simulation.scenarios.caption || `📊 Se o preço de ${simulation.scenarios.base_symbol} mudar · valores em ${simulation.scenarios.unit}`;
    const head = document.createElement('thead');
    const headerRow = document.createElement('tr');
    (simulation.scenarios.headers || [simulation.kind === 'historical_pool' ? 'Data' : 'Cenário', 'Preço', 'Valor', 'Ganho/perda']).forEach((label) => {
      const heading = document.createElement('th');
      heading.scope = 'col';
      heading.textContent = label;
      headerRow.append(heading);
    });
    head.append(headerRow);
    const body = document.createElement('tbody');
    simulation.scenarios.rows.forEach((row) => {
      const tr = document.createElement('tr');
      tr.className = `scenario-${row.tone}`;
      [row.label, row.price, row.value, row.pnl].forEach((value, index) => {
        const cell = document.createElement(index === 0 ? 'th' : 'td');
        if (index === 0) cell.scope = 'row';
        cell.textContent = value;
        tr.append(cell);
      });
      body.append(tr);
    });
    table.append(caption, head, body);
    const note = document.createElement('p');
    note.className = 'simulation-scenario-note';
    note.textContent = simulation.scenarios.note;
    scenarioBlock.append(table, note);
  }
  const provenance = document.createElement('div');
  provenance.className = 'simulation-provenance';
  const block = document.createElement('span');
  block.textContent = simulation.source.kind === 'lending_live' ? 'Mercado atualizado'
    : simulation.source.kind === 'historical_candles'
    ? `Velas ${new Date(simulation.source.period_start * 1000).toLocaleDateString('pt-BR', { timeZone: 'UTC' })}–${new Date(simulation.source.period_end * 1000).toLocaleDateString('pt-BR', { timeZone: 'UTC' })}`
    : `${simulation.source.source_label} #${simulation.source.block_number.toLocaleString('pt-BR')}`;
  const captured = document.createElement('time');
  const capturedDate = new Date(simulation.source.captured_at);
  captured.textContent = Number.isNaN(capturedDate.getTime()) ? 'Captura recente' : `Capturado ${capturedDate.toLocaleString('pt-BR')}`;
  provenance.append(block, captured);
  const notes = document.createElement('p');
  notes.className = 'simulation-notes';
  notes.textContent = [...simulation.assumptions, simulation.source.validity].filter(Boolean).join(' · ');
  const link = document.createElement('a');
  link.className = 'simulation-open';
  link.href = simulation.url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = 'Abrir simulador Altside ↗';
  card.append(eyebrow, title, subtitle, grid);
  if (scenarioBlock) card.append(scenarioBlock);
  for (const extra of simulation.extra_tables || []) {
    if (!extra.rows?.length) continue;
    const section = document.createElement('div'); section.className = 'simulation-scenario-block';
    const table = document.createElement('table'); table.className = 'simulation-scenarios';
    const caption = document.createElement('caption'); caption.textContent = extra.caption; table.append(caption);
    const head = document.createElement('thead'); const headerRow = document.createElement('tr');
    extra.headers.forEach((label) => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; headerRow.append(th); });
    head.append(headerRow); table.append(head);
    const body = document.createElement('tbody');
    extra.rows.forEach((row) => { const tr = document.createElement('tr'); tr.className = `scenario-${row.tone}`;
      [row.label, row.price, row.value, row.pnl].forEach((value, index) => { const cell = document.createElement(index ? 'td' : 'th');
        if (!index) cell.scope = 'row'; cell.textContent = value; tr.append(cell); }); body.append(tr); });
    table.append(body); section.append(table);
    if (extra.note) { const note = document.createElement('p'); note.className = 'simulation-scenario-note'; note.textContent = extra.note; section.append(note); }
    card.append(section);
  }
  card.append(provenance, notes, link);
  return card;
}

function createWalletCard(wallet) {
  const explorers = { bitcoin: 'https://blockstream.info', ethereum: 'https://eth.blockscout.com', solana: 'https://explorer.solana.com' };
  const names = { bitcoin: 'Bitcoin', ethereum: 'Ethereum', solana: 'Solana' };
  const explorer = explorers[wallet.network];
  const displayPercent = (value) => value > 0 && value < 0.05 ? '<0,1%' : `${value.toFixed(1)}%`;
  const card = document.createElement('section');
  card.className = 'wallet-card';
  card.setAttribute('aria-label', 'Consulta pública de endereço no Altside');
  const label = document.createElement('span');
  label.className = 'wallet-card-kicker';
  label.textContent = `◎ WALLET · ${names[wallet.network].toUpperCase()}`;
  const address = document.createElement('h3');
  address.textContent = wallet.address;
  const stats = document.createElement('div');
  stats.className = 'wallet-card-stats';
  const balance = document.createElement('div');
  balance.innerHTML = '<small>Saldo nativo</small>';
  const balanceValue = document.createElement('strong');
  balanceValue.textContent = `${wallet.balance} ${wallet.asset}`;
  balance.append(balanceValue);
  stats.append(balance);
  if (wallet.total_usdc || wallet.value_usdc) {
    const value = document.createElement('div');
    value.innerHTML = `<small>${wallet.total_usdc ? 'Valor monitorado' : 'Referência de valor'}</small>`;
    const valueText = document.createElement('strong');
    valueText.textContent = `US$ ${wallet.total_usdc || wallet.value_usdc}`;
    value.append(valueText);
    stats.append(value);
  }
  card.append(label, address, stats);
  if (wallet.allocation.length) {
    const section = document.createElement('div');
    section.className = 'wallet-allocation';
    const sectionHeading = document.createElement('h4');
    sectionHeading.textContent = 'Alocação monitorada';
    const chartRow = document.createElement('div');
    chartRow.className = 'wallet-allocation-row';
    const chart = document.createElement('div');
    chart.className = 'wallet-donut';
    chart.setAttribute('role', 'img');
    chart.setAttribute('aria-label', wallet.allocation.map((item) => `${item.symbol} ${displayPercent(item.percent)}`).join(', '));
    const colors = ['#80d8ab', '#9085f6', '#ffad79', '#f5a3c3', '#70c5ed', '#ebcd80', '#b7a6ca'];
    let offset = 0;
    const stops = wallet.allocation.map((item, index) => {
      const start = offset;
      offset = Math.min(100, offset + item.percent);
      return `${colors[index]} ${start.toFixed(2)}% ${offset.toFixed(2)}%`;
    });
    chart.style.background = `conic-gradient(${stops.join(', ')})`;
    const center = document.createElement('div');
    center.className = 'wallet-donut-center';
    center.innerHTML = '<small>Monitorado</small>';
    const centerValue = document.createElement('strong');
    centerValue.textContent = wallet.total_usdc ? `US$ ${wallet.total_usdc}` : '—';
    center.append(centerValue);
    chart.append(center);
    const legend = document.createElement('ul');
    legend.className = 'wallet-legend';
    wallet.allocation.forEach((item, index) => {
      const row = document.createElement('li');
      const marker = document.createElement('i');
      marker.style.background = colors[index];
      const name = document.createElement('strong');
      name.textContent = item.symbol;
      const percent = document.createElement('span');
      percent.textContent = displayPercent(item.percent);
      const value = document.createElement('small');
      value.textContent = `US$ ${item.value_usdc}`;
      row.append(marker, name, percent, value);
      legend.append(row);
    });
    chartRow.append(chart, legend);
    section.append(sectionHeading, chartRow);
    card.append(section);
  }
  if (wallet.performance.length) {
    const heading = document.createElement('h4');
    heading.textContent = 'Variação estimada com os saldos atuais';
    const periods = document.createElement('div');
    periods.className = 'wallet-periods';
    wallet.performance.forEach((period) => {
      const box = document.createElement('div');
      box.className = `wallet-period wallet-period-${period.direction}`;
      const title = document.createElement('small');
      title.textContent = period.label;
      const amount = document.createElement('strong');
      amount.textContent = period.available && period.change_usdc ? `${period.change_usdc.startsWith('-') ? '-' : '+'}US$ ${period.change_usdc.replace(/^[+-]/, '')}` : 'Sem dados';
      const pct = document.createElement('span');
      pct.textContent = period.available && period.change_pct ? `${period.change_pct}%` : 'Histórico indisponível';
      if (period.available && period.coverage < period.priced) pct.textContent += ` · ${period.coverage}/${period.priced} ativos`;
      box.append(title, amount, pct);
      periods.append(box);
    });
    const note = document.createElement('p');
    note.className = 'wallet-period-note';
    note.textContent = 'Cenário com as quantidades atuais fixas. Não representa lucro real: depósitos, saques e negociações no período não foram reconstituídos.';
    card.append(heading, periods, note);
  }
  const heading = document.createElement('h4');
  heading.textContent = 'Movimentações recentes';
  card.append(heading);
  if (wallet.transactions.length) {
    const list = document.createElement('ul');
    list.className = 'wallet-transactions';
    wallet.transactions.forEach((transaction) => {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = `${explorer}/tx/${transaction.txid}`;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      const kind = document.createElement('span');
      kind.textContent = transaction.direction === 'received' ? '↙ Entrada' : transaction.direction === 'sent' ? '↗ Saída' : '↔ Transação';
      const amount = document.createElement('strong');
      amount.textContent = transaction.amount ? `${transaction.amount} ${wallet.asset}` : `${transaction.txid.slice(0, 8)}…${transaction.txid.slice(-6)}`;
      const date = document.createElement('small');
      date.textContent = transaction.block_time_unix ? new Date(transaction.block_time_unix * 1000).toLocaleString('pt-BR') : 'Data indisponível';
      link.append(kind, amount, date);
      item.append(link);
      list.append(item);
    });
    card.append(list);
  } else {
    const empty = document.createElement('p');
    empty.className = 'wallet-card-empty';
    empty.textContent = 'Nenhuma movimentação disponível nesta amostra.';
    card.append(empty);
  }
  const footer = document.createElement('div');
  footer.className = 'wallet-card-footer';
  const observed = document.createElement('span');
  observed.textContent = wallet.observed_at_unix_ms ? `Consultado ${new Date(wallet.observed_at_unix_ms).toLocaleString('pt-BR')}` : 'Consulta recente';
  const source = document.createElement('a');
  source.href = `${explorer}/address/${wallet.address}`;
  source.target = '_blank';
  source.rel = 'noopener noreferrer';
  source.textContent = 'Ver no explorador ↗';
  footer.append(observed, source);
  card.append(footer);
  if (wallet.scope) {
    const scope = document.createElement('p');
    scope.className = 'wallet-scope';
    scope.textContent = wallet.scope;
    card.append(scope);
  }
  if (wallet.sources.length) {
    const sources = document.createElement('p');
    sources.className = 'wallet-sources';
    sources.textContent = `Fontes: ${wallet.sources.join(' · ')}`;
    card.append(sources);
  }
  return card;
}

function appendNerdInline(target, text) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  parts.forEach((part) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = part.slice(2, -2);
      target.append(strong);
    } else if (part.startsWith('`') && part.endsWith('`')) {
      const code = document.createElement('code');
      code.textContent = part.slice(1, -1);
      target.append(code);
    } else target.append(document.createTextNode(part));
  });
}

function renderNerdAnswer(body, text) {
  const answer = document.createElement('div');
  answer.className = 'nerd-answer';
  let list = null;
  text.split('\n').forEach((raw) => {
    const line = raw.trim();
    if (!line) { list = null; return; }
    const bullet = line.match(/^(?:[-*]\s+|\d+[.)]\s+)(.*)$/);
    if (bullet) {
      const ordered = /^\d/.test(line);
      if (!list || list.tagName !== (ordered ? 'OL' : 'UL')) {
        list = document.createElement(ordered ? 'ol' : 'ul');
        answer.append(list);
      }
      const item = document.createElement('li');
      appendNerdInline(item, bullet[1]);
      list.append(item);
      return;
    }
    list = null;
    const heading = line.match(/^#{1,3}\s+(.+)$/) || line.match(/^\*\*([^*]+)\*\*$/);
    const element = document.createElement(heading ? 'h3' : 'p');
    appendNerdInline(element, heading ? heading[1] : line);
    answer.append(element);
  });
  body.append(answer);
}

function createMessage(role, text, simulation = null, followUp = '', news = [], wallet = null, research = [], nerdMode = false, video = null) {
  const row = document.createElement('article');
  row.className = `message-row message-${role}${nerdMode && role === 'ai' ? ' message-nerd' : ''}`;
  if (role === 'ai') {
    const avatar = document.createElement('span');
    avatar.className = 'message-avatar eye-pod';
    avatar.setAttribute('aria-hidden', 'true');
    for (let index = 0; index < 2; index += 1) {
      const eye = document.createElement('i');
      eye.className = 'eye-ball';
      const pupil = document.createElement('i');
      pupil.className = 'pupil';
      eye.append(pupil);
      avatar.append(eye);
    }
    const mouth = document.createElement('i');
    mouth.className = 'mascot-mouth';
    avatar.append(mouth);
    row.append(avatar);
  }
  const body = document.createElement('div');
  body.className = 'message-body';
  if (role === 'ai') {
    const author = document.createElement('strong');
    author.textContent = 'Alt-IA';
    body.append(author);
  }
  if (role === 'ai' && research?.length) renderNerdAnswer(body, text);
  else {
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    body.append(paragraph);
  }
  if (role === 'ai' && news?.length) {
    const digest = document.createElement('div');
    digest.className = 'news-digest';
    news.forEach((item, index) => {
      const link = document.createElement('a');
      link.className = 'news-item';
      link.href = item.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      const number = document.createElement('span');
      number.className = 'news-item-number';
      number.textContent = String(index + 1).padStart(2, '0');
      const copy = document.createElement('span');
      const title = document.createElement('strong');
      title.textContent = item.title;
      const meta = document.createElement('small');
      const date = new Date(item.published_at);
      meta.textContent = `${item.source} · ${Number.isNaN(date.getTime()) ? '' : date.toLocaleString('pt-BR', { dateStyle: 'short', ...(item.time_known ? { timeStyle: 'short' } : {}) })}`;
      copy.append(title);
      if (item.summary && item.summary.toLocaleLowerCase() !== item.title.toLocaleLowerCase()) {
        const summary = document.createElement('span');
        summary.className = 'news-item-summary';
        summary.textContent = item.summary;
        copy.append(summary);
      }
      copy.append(meta);
      const arrow = document.createElement('span');
      arrow.className = 'news-item-arrow';
      arrow.textContent = '↗';
      link.append(number, copy, arrow);
      digest.append(link);
    });
    body.append(digest);
  }
  if (role === 'ai' && simulation) body.append(createSimulationCard(simulation));
  if (role === 'ai' && wallet) body.append(createWalletCard(wallet));
  if (role === 'ai' && video && video.kind !== 'playlist') {
    const player = document.createElement('div');
    player.className = 'agent-video';
    const frame = document.createElement('iframe');
    frame.src = `https://www.youtube-nocookie.com/embed/${video.id}?autoplay=0&playsinline=1&rel=0&enablejsapi=1&origin=${encodeURIComponent(location.origin)}`;
    frame.title = video.title || 'Vídeo do YouTube';
    frame.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
    frame.referrerPolicy = 'strict-origin-when-cross-origin';
    frame.allowFullscreen = true;
    player.append(frame);
    const caption = document.createElement('div');
    caption.className = 'agent-video-caption';
    const title = document.createElement('strong');
    title.textContent = video.title || 'Vídeo selecionado';
    const hint = document.createElement('span');
    hint.textContent = 'Iniciando vídeo…';
    const link = document.createElement('a');
    link.href = video.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Abrir no YouTube ↗';
    caption.append(title, hint, link);
    player.append(caption);
    body.append(player);
    hint.textContent = 'Toque para assistir aqui';
  }
  if (role === 'ai' && research?.length) {
    const sources = document.createElement('div');
    sources.className = 'research-sources';
    const heading = document.createElement('strong');
    heading.textContent = 'Fontes consultadas';
    sources.append(heading);
    research.forEach((item, index) => {
      const link = document.createElement('a');
      link.href = item.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      const number = document.createElement('span');
      number.textContent = `[${index + 1}]`;
      const title = document.createElement('span');
      title.textContent = item.title;
      const host = document.createElement('small');
      host.textContent = item.source;
      link.append(number, title, host);
      sources.append(link);
    });
    body.append(sources);
  }
  if (role === 'ai' && followUp) {
    const question = document.createElement('p');
    question.className = 'message-follow-up';
    question.textContent = followUp;
    body.append(question);
  }
  row.append(body);
  return row;
}

function renderConversation() {
  if (!chatMessages) return;
  activeVideoPlayers.splice(0).forEach((player) => { try { player.destroy(); } catch { /* Player already removed. */ } });
  chatMessages.replaceChildren();
  const conversation = conversations.find((item) => item.id === activeId);
  applyNerdModeUI();
  if (!conversation || !conversation.messages.length) {
    if (welcome) chatMessages.append(welcome);
  } else {
    const fragment = document.createDocumentFragment();
  conversation.messages.forEach((message) => fragment.append(createMessage(message.role, message.text, message.simulation, message.followUp, message.news, message.wallet, message.research, conversation.nerdMode, conversation.agentMode ? null : message.video)));
    chatMessages.append(fragment);
  }
  requestAnimationFrame(() => { chatMessages.scrollTop = conversation?.messages.length ? chatMessages.scrollHeight : 0; });
}

function resizeComposer() {
  if (!chatInput) return;
  chatInput.style.height = 'auto';
  chatInput.style.height = `${Math.min(chatInput.scrollHeight, 168)}px`;
}

function closeSidebar() {
  sidebar?.classList.remove('open');
  if (sidebarOverlay) sidebarOverlay.hidden = true;
  mobileMenu?.setAttribute('aria-expanded', 'false');
}

function openSidebar() {
  sidebar?.classList.add('open');
  if (sidebarOverlay) sidebarOverlay.hidden = false;
  mobileMenu?.setAttribute('aria-expanded', 'true');
}

mobileMenu?.addEventListener('click', () => sidebar?.classList.contains('open') ? closeSidebar() : openSidebar());
sidebarClose?.addEventListener('click', closeSidebar);
sidebarOverlay?.addEventListener('click', closeSidebar);
window.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeSidebar(); });

newChatButton?.addEventListener('click', () => {
  pendingDeleteId = null;
  activeId = null;
  draftNerdMode = false;
  draftAgentMode = false;
  draftNerdTopic = 'research';
  closeModeMenu();
  persist();
  renderHistory();
  renderConversation();
  closeSidebar();
  chatInput?.focus();
});
let agentStarted = false;
let agentRefreshing = false;
let agentLastStatePollAt = 0;
let agentWasRunning = false;
let agentLastShotKey = '';
let agentCurrentVideo = null;
let agentStartPromise = null;
let agentOwnerId = null;
let agentPipWindow = null;
let agentPipStatus = null;
let agentPipImage = null;
let agentPipMedia = null;
let agentPipPlayback = null;
let agentPipHasReply = false;
let agentDockBusy = false;
const agentDock = document.createElement('aside');
agentDock.className = 'agent-dock';
agentDock.hidden = true;
agentDock.setAttribute('aria-label', 'Agente ativo');
const agentDockSidekick = document.createElement('span');
agentDockSidekick.className = 'agent-dock-sidekick agent-window-face';
agentDockSidekick.setAttribute('aria-hidden', 'true');
agentDockSidekick.innerHTML = '<span class="agent-face-core"><i class="agent-face-eye"></i><i class="agent-face-eye"></i></span>';
const agentDockHead = document.createElement('button');
agentDockHead.type = 'button';
agentDockHead.textContent = '◉  Agente ativo · abrir conversa';
agentDockHead.title = 'Arraste para mover · clique para abrir conversa';
const agentDockPositionKey = 'alt-ia-agent-dock-position';
let agentDockPosition = null;
try {
  const saved = JSON.parse(localStorage.getItem(agentDockPositionKey) || 'null');
  if (Number.isFinite(saved?.x) && Number.isFinite(saved?.y)) agentDockPosition = saved;
} catch { /* Keep the default position. */ }
let agentDockDrag = null;
let agentDockSuppressClick = false;
function positionAgentDock() {
  if (!agentDockPosition || agentDock.hidden || agentDockDrag) return;
  const rect = agentDock.getBoundingClientRect();
  const minX = Math.min(56, Math.max(12, innerWidth - rect.width));
  const maxX = Math.max(minX, innerWidth - rect.width - 12);
  const maxY = Math.max(12, innerHeight - rect.height - 12);
  agentDock.style.right = 'auto';
  agentDock.style.bottom = 'auto';
  agentDock.style.left = `${minX + Math.min(1, Math.max(0, agentDockPosition.x)) * (maxX - minX)}px`;
  agentDock.style.top = `${12 + Math.min(1, Math.max(0, agentDockPosition.y)) * (maxY - 12)}px`;
}
agentDockHead.addEventListener('pointerdown', (event) => {
  if (event.button !== 0) return;
  const rect = agentDock.getBoundingClientRect();
  agentDockDrag = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY,
    left: rect.left, top: rect.top, width: rect.width, height: rect.height, moved: false };
  agentDockHead.setPointerCapture(event.pointerId);
});
agentDockHead.addEventListener('pointermove', (event) => {
  const drag = agentDockDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const dx = event.clientX - drag.startX;
  const dy = event.clientY - drag.startY;
  if (!drag.moved && Math.hypot(dx, dy) < 5) return;
  drag.moved = true;
  agentDock.classList.add('is-dragging');
  const minX = Math.min(56, Math.max(12, innerWidth - drag.width));
  const maxX = Math.max(minX, innerWidth - drag.width - 12);
  const maxY = Math.max(12, innerHeight - drag.height - 12);
  const x = Math.min(maxX, Math.max(minX, drag.left + dx));
  const y = Math.min(maxY, Math.max(12, drag.top + dy));
  agentDock.style.right = 'auto';
  agentDock.style.bottom = 'auto';
  agentDock.style.left = `${x}px`;
  agentDock.style.top = `${y}px`;
  agentDockPosition = { x: maxX > minX ? (x - minX) / (maxX - minX) : 0,
    y: maxY > 12 ? (y - 12) / (maxY - 12) : 0 };
});
function endAgentDockDrag(event) {
  if (!agentDockDrag || agentDockDrag.pointerId !== event.pointerId) return;
  if (agentDockDrag.moved) {
    agentDockSuppressClick = true;
    try { localStorage.setItem(agentDockPositionKey, JSON.stringify(agentDockPosition)); } catch { /* Position stays in memory. */ }
    setTimeout(() => { agentDockSuppressClick = false; }, 0);
  }
  agentDockDrag = null;
  agentDock.classList.remove('is-dragging');
}
agentDockHead.addEventListener('pointerup', endAgentDockDrag);
agentDockHead.addEventListener('pointercancel', endAgentDockDrag);
window.addEventListener('resize', () => requestAnimationFrame(positionAgentDock));
agentDockHead.addEventListener('click', (event) => {
  if (agentDockSuppressClick) { event.preventDefault(); return; }
  if (agentOwnerId && conversations.some((item) => item.id === agentOwnerId)) {
    activeId = agentOwnerId; persist(); renderHistory(); renderConversation();
  }
});
const agentDockImage = document.createElement('img');
agentDockImage.alt = 'Miniatura do navegador do agente';
const agentDockSpeech = document.createElement('p');
agentDockSpeech.className = 'agent-dock-speech';
agentDockSpeech.setAttribute('aria-live', 'polite');
agentDockSpeech.textContent = 'Estou por aqui. O que exploramos agora? 🔎';
const agentDockMedia = document.createElement('div');
agentDockMedia.className = 'agent-dock-media';
agentDockMedia.hidden = true;
const agentDockPlayback = document.createElement('small');
agentDockPlayback.className = 'agent-mini-playback';
agentDockPlayback.hidden = true;
const agentDockForm = document.createElement('form');
const agentDockInput = document.createElement('input');
agentDockInput.type = 'text';
agentDockInput.maxLength = 1500;
agentDockInput.placeholder = 'Peça algo ao agente…';
agentDockInput.setAttribute('aria-label', 'Mensagem para o agente');
const agentDockSend = document.createElement('button');
agentDockSend.type = 'submit';
agentDockSend.textContent = '↑';
agentDockSend.setAttribute('aria-label', 'Enviar ao agente');
agentDockForm.append(agentDockInput, agentDockSend);
agentDockForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const task = agentDockInput.value.trim();
  if (!task) return;
  agentDockInput.value = '';
  void sendAgentDockTask(task);
});
agentDock.append(agentDockSidekick, agentDockHead, agentDockSpeech, agentDockMedia, agentDockPlayback, agentDockImage, agentDockForm);
document.body.append(agentDock);

function updateAgentDockMedia(video) {
  const media = safeVideo(video);
  agentDockMedia.hidden = !media;
  agentDockPlayback.hidden = !media;
  if (media) agentDockImage.removeAttribute('src');
  requestAnimationFrame(positionAgentDock);
}

async function sendAgentDockTask(task) {
  if (agentDockBusy || !agentStarted || !agentOwnerId) return;
  const conversation = conversations.find((item) => item.id === agentOwnerId);
  if (!conversation) return;
  agentDockBusy = true;
  agentDockInput.disabled = true;
  agentDockSend.disabled = true;
  agentPipHasReply = false;
  if (agentPipStatus) agentPipStatus.textContent = 'Navegando…';
  agentDockSpeech.textContent = 'Estou explorando o que você pediu… 🔎';
  stopAgentMedia();
  updateAgentDockMedia(null);
  conversation.messages.push({ role: 'user', text: task });
  conversation.updatedAt = Date.now();
  persist(); renderHistory();
  if (activeId === conversation.id) renderConversation();
  let resultMedia = null;
  let replyText = '';
  try {
    const data = await agentRequest('run', { task, context: agentConversationContext(conversation) });
    resultMedia = data.video;
    replyText = data.reply;
    conversation.messages.push({ role: 'ai', text: data.reply, speech: String(data.speech || '').slice(0, 220), mode: 'agent', video: safeVideo(data.video) });
    agentPipHasReply = true;
    const speech = String(data.speech || data.reply).slice(0, 220);
    if (agentPipStatus) agentPipStatus.textContent = speech;
    agentDockSpeech.textContent = speech;
  } catch (error) {
    replyText = error.message || 'Não consegui concluir. Tente novamente.';
    conversation.messages.push({ role: 'ai', text: error.message || 'Não consegui concluir. Tente novamente.', mode: 'agent' });
    agentPipHasReply = true;
    if (agentPipStatus) agentPipStatus.textContent = error.message;
    agentDockSpeech.textContent = error.message;
  } finally {
    conversation.updatedAt = Date.now();
    persist(); renderHistory();
    if (activeId === conversation.id) renderConversation();
    showAgentMedia(resultMedia);
    agentDockBusy = false;
    agentDockInput.disabled = false;
    agentDockSend.disabled = false;
  }
  return { reply: replyText, video: safeVideo(resultMedia) };
}

const agentCompanionChannel = new BroadcastChannel('alt-ia-agent-companion');
agentCompanionChannel.addEventListener('message', async ({ data }) => {
  if (data?.type === 'media-request') {
    agentCompanionChannel.postMessage({ type: 'media', video: agentCurrentVideo });
    return;
  }
  if (data?.type !== 'task' || typeof data.task !== 'string' || !agentStarted) return;
  const result = await sendAgentDockTask(data.task.trim());
  agentCompanionChannel.postMessage({ type: 'reply', id: data.id, ...result });
});

function openAgentPip() {
  if (!window.documentPictureInPicture || (agentPipWindow && !agentPipWindow.closed)) return;
  void window.documentPictureInPicture.requestWindow({ width: 380, height: 415 }).then((pip) => {
    agentPipWindow = pip;
    pip.document.title = 'Alt-IA · Agente';
    const css = pip.document.createElement('link');
    css.rel = 'stylesheet';
    css.href = '/agent-pip.css?v=3';
    pip.document.head.append(css);
    const head = pip.document.createElement('header');
    const face = pip.document.createElement('span');
    face.className = 'pip-face';
    face.setAttribute('aria-hidden', 'true');
    face.innerHTML = '<span><i></i><i></i></span>';
    head.append(face, pip.document.createTextNode('Alt-IA · Agente'));
    const image = pip.document.createElement('img');
    image.alt = 'Navegador temporário';
    agentPipImage = image;
    const media = pip.document.createElement('div');
    media.className = 'pip-media';
    media.hidden = true;
    agentPipMedia = media;
    const playback = pip.document.createElement('small');
    playback.className = 'pip-playback';
    playback.hidden = true;
    agentPipPlayback = playback;
    const status = pip.document.createElement('p');
    status.textContent = agentDockSpeech.textContent || 'Estou explorando a página…';
    agentPipStatus = status;
    const form = pip.document.createElement('form');
    const input = pip.document.createElement('input');
    input.type = 'text';
    input.maxLength = 1500;
    input.placeholder = 'Peça algo ao agente…';
    input.setAttribute('aria-label', 'Mensagem para o agente');
    const send = pip.document.createElement('button');
    send.type = 'submit';
    send.textContent = '↑';
    send.setAttribute('aria-label', 'Enviar ao agente');
    form.append(input, send);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const task = input.value.trim();
      if (!task || agentDockBusy) return;
      input.value = '';
      void sendAgentDockTask(task);
    });
    pip.document.body.append(head, status, media, playback, image, form);
    pip.addEventListener('pagehide', () => {
      agentPipWindow = null;
      agentPipStatus = null;
      agentPipImage = null;
      agentPipMedia = null;
      agentPipPlayback = null;
      applyNerdModeUI();
    });
    applyNerdModeUI();
  }).catch(() => { applyNerdModeUI(); });
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden && agentStarted && document.documentElement.dataset.altAgentExtension !== 'true') openAgentPip();
  else if (!document.hidden && agentPipWindow && !agentPipWindow.closed) agentPipWindow.close();
});
async function agentRequest(path, payload = {}, method = 'POST') {
  const response = await fetch(`/api/agent/${path}`, { method, headers: { 'Content-Type': 'application/json' },
    body: method === 'DELETE' ? undefined : JSON.stringify(payload) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Falha no navegador temporário.');
  return data;
}
async function startAgentSession() {
  if (agentStarted || !isAgentMode()) return;
  if (agentStartPromise) return agentStartPromise;
  agentStartPromise = (async () => {
    try {
      if (agentStatus) agentStatus.textContent = 'Iniciando navegador temporário…';
      await agentRequest('start');
      agentStarted = true;
      applyNerdModeUI();
      void refreshAgentWindow(true);
    } catch (error) { if (agentStatus) agentStatus.textContent = error.message; throw error; }
    finally { agentStartPromise = null; }
  })();
  return agentStartPromise;
}
const agentSites = {
  whatsapp: 'https://web.whatsapp.com/',
  x: 'https://x.com/',
  gmail: 'https://mail.google.com/',
  duckduckgo: 'https://duckduckgo.com/',
};
agentGrid?.querySelectorAll('[data-agent-site]').forEach((button) => button.addEventListener('click', async () => {
  if (!isAgentMode() || agentGrid.getAttribute('aria-busy') === 'true') return;
  const url = agentSites[button.dataset.agentSite];
  if (!url) return;
  const label = button.querySelector('strong')?.textContent || 'site';
  agentGrid.setAttribute('aria-busy', 'true');
  agentGrid.querySelectorAll('button').forEach((item) => { item.disabled = true; });
  if (agentShortcutStatus) { agentShortcutStatus.textContent = `Abrindo ${label}…`; agentShortcutStatus.hidden = false; }
  try {
    await startAgentSession();
    if (!isAgentMode() || !agentStarted) return;
    if (agentStatus) agentStatus.textContent = `Abrindo ${label}…`;
    await agentRequest('navigate', { url });
    await refreshAgentWindow(true);
    if (agentShortcutStatus) agentShortcutStatus.hidden = true;
  } catch (error) {
    if (agentShortcutStatus) { agentShortcutStatus.textContent = error.message; agentShortcutStatus.hidden = false; }
    if (agentStatus) agentStatus.textContent = error.message;
  } finally {
    agentGrid.removeAttribute('aria-busy');
    agentGrid.querySelectorAll('button').forEach((item) => { item.disabled = false; });
  }
}));
async function stopAgentSession() {
  stopAgentMedia();
  updateAgentDockMedia(null);
  agentStarted = false;
  agentLastShotKey = '';
  agentLastStatePollAt = 0;
  agentOwnerId = null;
  agentPipHasReply = false;
  if (agentPipWindow && !agentPipWindow.closed) agentPipWindow.close();
  applyNerdModeUI();
  if (agentImage) agentImage.removeAttribute('src');
  if (agentUrl) agentUrl.textContent = 'Sessão isolada · dados apagados ao encerrar';
  try { await agentRequest('session', {}, 'DELETE'); } catch { /* Idle expiration also closes the context. */ }
}
async function refreshAgentWindow(force = false) {
  if (!agentStarted || agentRefreshing || (document.hidden && !agentPipWindow)) return;
  const playing = Boolean(agentCurrentVideo);
  const now = Date.now();
  if (!force && now - agentLastStatePollAt < (playing ? 30000 : agentWasRunning ? 5000 : 20000)) return;
  agentLastStatePollAt = now;
  agentRefreshing = true;
  try {
    const response = await fetch('/api/agent/state', { cache: 'no-store' });
    const state = await response.json();
    if (!response.ok) throw new Error(state.error || 'Sessão encerrada.');
    agentWasRunning = Boolean(state.running);
    if (agentStatus && !playing) agentStatus.textContent = state.running ? 'Navegando e analisando…' : state.status || 'Pronto';
    if (agentPipStatus && (state.running || !agentPipHasReply) && !agentDockBusy) agentPipStatus.textContent = state.running ? 'Navegando e analisando…' : state.status || 'Pronto';
    if (state.running && !agentPipHasReply && state.title) agentDockSpeech.textContent = `Estou vendo “${state.title.slice(0, 90)}” e conferindo os detalhes. 🔎`;
    if (agentUrl && !playing) agentUrl.textContent = state.url === 'about:blank' ? 'Sessão isolada · dados apagados ao encerrar' : state.url;
    const shotKey = `${state.url}:${state.updated}`;
    if (!playing && state.url && state.url !== 'about:blank' && (force || shotKey !== agentLastShotKey)) {
      const imageUrl = `/api/agent/image?t=${Date.now()}`;
      if (agentImage && isAgentMode()) agentImage.src = imageUrl;
      if (agentDockImage && !agentDock.hidden) agentDockImage.src = imageUrl;
      if (agentPipImage) agentPipImage.src = imageUrl;
      agentLastShotKey = shotKey;
    }
    if (agentCursor) {
      agentCursor.hidden = !state.cursor || state.url === 'about:blank';
      if (!agentCursor.hidden) { agentCursor.style.left = `${state.cursor.x / 11}%`; agentCursor.style.top = `${state.cursor.y / 7.2}%`; }
    }
  } catch (error) { if (agentStatus) agentStatus.textContent = error.message; }
  finally { agentRefreshing = false; }
}
setInterval(() => { void refreshAgentWindow(); }, 2400);
document.querySelector('#agent-close')?.addEventListener('click', async () => {
  const conversation = currentConversation();
  if (conversation) conversation.agentMode = false;
  else draftAgentMode = false;
  persist(); renderHistory(); applyNerdModeUI();
  await stopAgentSession();
});
window.addEventListener('pagehide', () => {
  if (agentStarted) fetch('/api/agent/session', { method: 'DELETE', keepalive: true }).catch(() => {});
});
const agentScreen = document.querySelector('.agent-screen');
let agentMediaPlayer = null;
let agentMediaGeneration = 0;
let agentMediaSurface = null;
let agentPlaybackSeconds = 0;
function agentVideoUrl(video, seconds = 0) {
  const start = seconds > 1 ? `&start=${Math.floor(seconds)}` : '';
  return video.kind === 'playlist'
    ? `https://www.youtube-nocookie.com/embed?listType=playlist&list=${video.id}&autoplay=1&playsinline=1&enablejsapi=1&origin=${encodeURIComponent(location.origin)}${start}`
    : `https://www.youtube-nocookie.com/embed/${video.id}?autoplay=1&playsinline=1&rel=0&enablejsapi=1&origin=${encodeURIComponent(location.origin)}${start}`;
}
function syncAgentMediaSurface() {
  if (!agentCurrentVideo) return;
  const surface = document.hidden && agentPipMedia ? 'pip' : isAgentMode() ? 'main' : 'dock';
  if (surface === agentMediaSurface) return;
  if (agentMediaPlayer) {
    try { agentPlaybackSeconds = Math.max(agentPlaybackSeconds, agentMediaPlayer.getCurrentTime() || 0); } catch { /* Player still loading. */ }
    try { agentMediaPlayer.destroy(); } catch { /* Player already stopped. */ }
  }
  agentMediaPlayer = null;
  agentMediaGeneration += 1;
  agentMedia?.replaceChildren();
  agentDockMedia.replaceChildren();
  agentPipMedia?.replaceChildren();
  agentMediaSurface = surface;
  agentScreen?.classList.toggle('is-playing', surface === 'main');
  updateAgentDockMedia(agentCurrentVideo);
  if (agentPipMedia) agentPipMedia.hidden = surface !== 'pip';
  if (agentPipPlayback) agentPipPlayback.hidden = surface !== 'pip';
  if (surface === 'pip') agentPipImage?.removeAttribute('src');
  const host = surface === 'main' ? agentMedia : surface === 'pip' ? agentPipMedia : agentDockMedia;
  const hint = surface === 'main' ? agentStatus : surface === 'pip' ? agentPipPlayback : agentDockPlayback;
  if (!host) return;
  const frame = host.ownerDocument.createElement('iframe');
  frame.src = agentVideoUrl(agentCurrentVideo, agentPlaybackSeconds);
  frame.title = agentCurrentVideo.title || (agentCurrentVideo.kind === 'playlist' ? 'Playlist do YouTube' : 'Vídeo do YouTube');
  frame.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
  frame.referrerPolicy = 'strict-origin-when-cross-origin';
  frame.allowFullscreen = true;
  host.append(frame);
  if (hint) hint.textContent = 'Iniciando vídeo…';
  const generation = agentMediaGeneration;
  void startVideoPlayer(frame, hint, false).then((player) => {
    if (generation === agentMediaGeneration) agentMediaPlayer = player;
    else { try { player?.destroy(); } catch { /* Player already stopped. */ } }
  });
}
function stopAgentMedia() {
  agentMediaGeneration += 1;
  agentCurrentVideo = null;
  agentMediaSurface = null;
  agentPlaybackSeconds = 0;
  agentCompanionChannel.postMessage({ type: 'media', video: null });
  if (agentMediaPlayer) { try { agentMediaPlayer.destroy(); } catch { /* Player already stopped. */ } }
  agentMediaPlayer = null;
  agentMedia?.replaceChildren();
  agentDockMedia.replaceChildren();
  agentPipMedia?.replaceChildren();
  updateAgentDockMedia(null);
  if (agentPipMedia) agentPipMedia.hidden = true;
  if (agentPipPlayback) agentPipPlayback.hidden = true;
  agentScreen?.classList.remove('is-playing');
  if (agentPrivacy) agentPrivacy.textContent = 'Clique e digite na tela. O conteúdo pedido ao agente é enviado à IA.';
}
function showAgentMedia(value) {
  const video = safeVideo(value);
  if (!video || !agentMedia || !agentScreen) return;
  stopAgentMedia();
  agentCurrentVideo = video;
  agentCompanionChannel.postMessage({ type: 'media', video });
  if (isAgentMode() && agentWindow) {
    agentWindow.hidden = false;
    site?.classList.add('agent-session-open');
  }
  syncAgentMediaSurface();
  if (agentUrl) agentUrl.textContent = video.url;
  if (agentPrivacy) agentPrivacy.textContent = 'Vídeo na janela. Se o navegador bloquear o som, toque no vídeo para ativar.';
}
let agentInputQueue = Promise.resolve();
function queueAgentInput(path, payload) {
  agentInputQueue = agentInputQueue.catch(() => {}).then(async () => {
    await agentRequest(path, payload);
    await refreshAgentWindow(true);
  });
  return agentInputQueue;
}
agentScreen?.addEventListener('click', async (event) => {
  if (agentScreen.classList.contains('is-playing')) return;
  agentScreen.focus();
  if (!agentImage?.hasAttribute('src')) return;
  const rect = agentImage.getBoundingClientRect();
  const scale = Math.min(rect.width / 1280, rect.height / 720);
  const x = (event.clientX - rect.left - (rect.width - 1280 * scale) / 2) / scale;
  const y = (event.clientY - rect.top - (rect.height - 720 * scale) / 2) / scale;
  try { await queueAgentInput('manual-click', { x, y }); }
  catch (error) { if (agentStatus) agentStatus.textContent = error.message; }
});
agentScreen?.addEventListener('keydown', async (event) => {
  if (agentScreen.classList.contains('is-playing')) return;
  if (!agentStarted || event.isComposing) return;
  const special = ['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'];
  const key = event.ctrlKey || event.metaKey ? event.key.toLowerCase() === 'a' ? 'ControlOrMeta+A' : null
    : special.includes(event.key) ? event.key : null;
  if (!key && (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey)) return;
  event.preventDefault();
  try {
    if (key) await queueAgentInput('key', { key });
    else await queueAgentInput('type', { value: event.key });
  } catch (error) { if (agentStatus) agentStatus.textContent = error.message; }
});
agentScreen?.addEventListener('paste', async (event) => {
  const value = event.clipboardData?.getData('text/plain')?.slice(0, 500);
  if (!agentStarted || !value) return;
  event.preventDefault();
  try { await queueAgentInput('type', { value }); }
  catch (error) { if (agentStatus) agentStatus.textContent = error.message; }
});
let agentWheelPending = false;
agentScreen?.addEventListener('wheel', async (event) => {
  if (!agentStarted) return;
  event.preventDefault();
  if (agentWheelPending) return;
  agentWheelPending = true;
  try { await queueAgentInput('scroll', { dy: event.deltaY }); }
  catch (error) { if (agentStatus) agentStatus.textContent = error.message; }
  finally { agentWheelPending = false; }
}, { passive: false });

modePlus?.addEventListener('click', () => {
  const show = modeMenu?.hidden;
  if (modeMenu) modeMenu.hidden = !show;
  modePlus.setAttribute('aria-expanded', String(show));
});

function modeMascot() {
  const mascot = welcome?.isConnected
    ? welcome.querySelector('.welcome-character')
    : [...(chatMessages?.querySelectorAll('.message-ai .message-avatar') || [])].at(-1);
  if (!mascot) return null;
  const rect = mascot.getBoundingClientRect();
  return rect.bottom > 0 && rect.top < innerHeight ? mascot : null;
}

function burstMascot(mascot, nerdMode) {
  if (!mascot) return;
  const rect = mascot.getBoundingClientRect();
  const burst = document.createElement('span');
  burst.className = 'mode-mascot-burst';
  burst.style.left = `${rect.left + rect.width / 2}px`;
  burst.style.top = `${rect.top + rect.height / 2}px`;
  const colors = nerdMode ? ['#91b6f7', '#c2d8ff', '#66cadb'] : ['#b584de', '#f2a6c8', '#d9b1f2'];
  for (let index = 0; index < 9; index += 1) {
    const angle = (index / 9) * Math.PI * 2 - Math.PI / 2;
    const distance = 29 + (index % 3) * 8;
    const piece = document.createElement('i');
    piece.style.setProperty('--dx', `${Math.cos(angle) * distance}px`);
    piece.style.setProperty('--dy', `${Math.sin(angle) * distance}px`);
    piece.style.setProperty('--turn', `${index % 2 ? 75 : -75}deg`);
    piece.style.backgroundColor = colors[index % colors.length];
    burst.append(piece);
  }
  document.body.append(burst);
  setTimeout(() => burst.remove(), 580);
}

let modeSwitching = false;
nerdToggle?.addEventListener('click', async () => {
  if (modeSwitching) return;
  modeSwitching = true;
  nerdToggle.disabled = true;
  closeModeMenu();
  const startingId = activeId;
  const oldMode = isNerdMode();
  const mascot = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? null : modeMascot();
  const pop = mascot?.animate([
    { offset: 0, scale: '1 1', opacity: 1 },
    { offset: .44, scale: '1.24 1.2', opacity: 1 },
    { offset: .7, scale: '1.36 1.35', opacity: 1 },
    { offset: 1, scale: '.08 .08', opacity: 0 },
  ], { duration: 285, easing: 'cubic-bezier(.3,0,.65,1)', fill: 'forwards' });
  let landing;
  const welcomeItems = welcome?.isConnected
    ? [welcome.querySelector('.welcome-kicker'), welcome.querySelector('h1'), welcome.querySelector(':scope > p'), isAgentMode() ? agentGrid : oldMode ? nerdGrid : normalGrid].filter(Boolean)
    : [];
  const leaving = welcomeItems.length ? animate(welcomeItems, { opacity: [1, 0], y: [0, -9], filter: ['blur(0px)', 'blur(4px)'] }, { duration: 0.2, ease: 'easeIn' }) : null;
  const noteLeaving = composerNote ? animate(composerNote, { opacity: [1, 0], y: [0, -5] }, { duration: 0.18, ease: 'easeIn' }) : null;
  const badgeLeaving = oldMode && modeBadge ? animate(modeBadge, { opacity: [1, 0], scale: [1, .88] }, { duration: 0.18, ease: 'easeIn' }) : null;
  try {
    await Promise.all([leaving?.finished, noteLeaving?.finished, badgeLeaving?.finished, pop?.finished].filter(Boolean));
    leaving?.cancel();
    noteLeaving?.cancel();
    badgeLeaving?.cancel();
    if (activeId !== startingId) return;
    burstMascot(mascot, oldMode);
    const conversation = currentConversation();
    if (conversation) { conversation.nerdMode = !conversation.nerdMode; conversation.agentMode = false; }
    else { draftNerdMode = !draftNerdMode; draftAgentMode = false; }
    if (agentStarted) void stopAgentSession();
    persist();
    renderHistory();
    applyNerdModeUI();
    if (mascot?.isConnected) {
      landing = mascot.animate([
        { offset: 0, translate: '0 -90px', scale: '.78 1.16', opacity: 0 },
        { offset: .45, translate: '0 0', scale: '1.17 .79', opacity: 1 },
        { offset: .68, translate: '0 -19px', scale: '.94 1.08', opacity: 1 },
        { offset: .85, translate: '0 0', scale: '1.06 .92', opacity: 1 },
        { offset: 1, translate: '0 0', scale: '1 1', opacity: 1 },
      ], { duration: 620, easing: 'ease-out', fill: 'forwards' });
    }
    pop?.cancel();
    const nextItems = welcome?.isConnected
      ? [welcome.querySelector('.welcome-kicker'), welcome.querySelector('h1'), welcome.querySelector(':scope > p'), isNerdMode() ? nerdGrid : normalGrid].filter(Boolean)
      : [];
    const entering = nextItems.length ? animate(nextItems, { opacity: [0, 1], y: [14, 0], filter: ['blur(5px)', 'blur(0px)'] }, { duration: 0.43, ease: 'easeOut' }) : null;
    const noteEntering = composerNote ? animate(composerNote, { opacity: [0, 1], y: [7, 0] }, { duration: 0.34, ease: 'easeOut' }) : null;
    const badgeEntering = isNerdMode() && modeBadge ? animate(modeBadge, { opacity: [0, 1], scale: [.85, 1] }, { duration: 0.4, ease: 'easeOut' }) : null;
    const formPulse = chatForm ? animate(chatForm, { scale: [1, .985, 1] }, { duration: 0.45, ease: 'easeOut' }) : null;
    await Promise.all([entering?.finished, noteEntering?.finished, badgeEntering?.finished, formPulse?.finished, landing?.finished].filter(Boolean));
    entering?.cancel();
    noteEntering?.cancel();
    badgeEntering?.cancel();
    formPulse?.cancel();
  } finally {
    pop?.cancel();
    landing?.cancel();
    modeSwitching = false;
    nerdToggle.disabled = false;
    chatInput?.focus();
  }
});
agentToggle?.addEventListener('click', async () => {
  if (modeSwitching || !agentDesktop.matches) return;
  modeSwitching = true;
  agentToggle.disabled = true;
  closeModeMenu();
  const wasActive = isAgentMode();
  const mascot = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? null : modeMascot();
  const pop = mascot?.animate([{ transform: 'scale(1)', opacity: 1 }, { transform: 'scale(1.36)', opacity: 1 },
    { transform: 'scale(.08)', opacity: 0 }], { duration: 290, easing: 'ease-in', fill: 'forwards' });
  const items = welcome?.isConnected ? [welcome.querySelector('.welcome-kicker'), welcome.querySelector('h1'), welcome.querySelector(':scope > p'), agentGrid, nerdGrid, normalGrid].filter(Boolean) : [];
  const leaving = items.length ? animate(items, { opacity: [1, 0], y: [0, -8] }, { duration: .2 }) : null;
  try {
    await Promise.all([pop?.finished, leaving?.finished].filter(Boolean));
    burstMascot(mascot, false);
    const conversation = currentConversation();
    if (conversation) { conversation.agentMode = !wasActive; conversation.nerdMode = false; }
    else { draftAgentMode = !wasActive; draftNerdMode = false; }
    persist();
    renderHistory();
    applyNerdModeUI();
    if (wasActive) await stopAgentSession();
    pop?.cancel();
    const landing = mascot?.animate([{ translate: '0 -90px', scale: '.8 1.1', opacity: 0 },
      { offset: .48, translate: '0 0', scale: '1.14 .8', opacity: 1 },
      { offset: .72, translate: '0 -16px', scale: '.95 1.06', opacity: 1 },
      { translate: '0 0', scale: '1 1', opacity: 1 }], { duration: 610, easing: 'ease-out' });
    const entering = items.length ? animate(items, { opacity: [0, 1], y: [12, 0] }, { duration: .36, ease: 'easeOut' }) : null;
    await Promise.all([landing?.finished, entering?.finished].filter(Boolean));
    landing?.cancel(); entering?.cancel();
  } finally { pop?.cancel(); leaving?.cancel(); agentToggle.disabled = false; modeSwitching = false; chatInput?.focus(); }
});
agentDesktop.addEventListener('change', () => {
  if (!agentDesktop.matches && agentStarted) void stopAgentSession();
  applyNerdModeUI();
});
document.addEventListener('pointerdown', (event) => {
  if (!modeMenu?.hidden && !modeMenu.contains(event.target) && !modePlus?.contains(event.target)) closeModeMenu();
});
window.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeModeMenu(); });
nerdGrid?.querySelectorAll('[data-nerd-topic]').forEach((button) => button.addEventListener('click', () => {
  const topic = button.dataset.nerdTopic;
  const conversation = currentConversation();
  if (conversation) conversation.nerdTopic = topic;
  else draftNerdTopic = topic;
  persist();
  applyNerdModeUI();
  animate(button, { scale: [1, .96, 1] }, { duration: 0.35, ease: 'easeOut' });
  if (modeBadge && !modeBadge.hidden) animate(modeBadge, { opacity: [.45, 1], y: [5, 0] }, { duration: 0.3, ease: 'easeOut' });
  chatInput?.focus();
}));

document.querySelectorAll('[data-prompt]').forEach((suggestion) => {
  suggestion.addEventListener('click', () => {
    if (!chatInput) return;
    chatInput.value = suggestion.dataset.prompt || '';
    resizeComposer();
    chatInput.focus();
  });
});

document.querySelector('[data-action="news-daily"]')?.addEventListener('click', () => {
  if (!chatInput || isSubmitting) return;
  chatInput.value = 'Resumo das notícias de hoje';
  resizeComposer();
  chatForm?.requestSubmit();
});

let lendingMarkets = [];
let lendingMarketData = null;
let lendingLoadSequence = 0;
const lendingError = (message) => { lendingFormError.textContent = message; lendingFormError.hidden = !message; };
const lendingDemoId = document.querySelector('#lending-demo-id');
const lendingScenarioSummary = document.querySelector('#lending-scenario-summary');
const lendingMarketKey = (item) => `${item.chain_id}:${item.address}`;
const lendingSameAddress = (left, right) => lendingMarketData?.protocol === 'kamino' ? left === right : left.toLowerCase() === right.toLowerCase();
const lendingAsset = (address) => lendingMarketData?.assets.find((asset) => lendingSameAddress(asset.address, address));
function updateLendingScenarioSummary() {
  const pct = Number(document.querySelector('#lending-shock-pct')?.value || 0);
  const days = Number(document.querySelector('#lending-days')?.value || 0);
  const symbol = lendingAsset(document.querySelector('#lending-shock-asset')?.value || '')?.symbol;
  lendingScenarioSummary.textContent = `${symbol ? `${symbol} ` : ''}${pct >= 0 ? '+' : '−'}${Math.abs(pct)}% · ${days} dias`;
}

function lendingRow(side, preset = {}) {
  if (!lendingMarketData) return;
  const container = side === 'supplies' ? lendingSupplies : lendingBorrows;
  const eligible = lendingMarketData.assets.filter((asset) => side === 'supplies' ? asset.can_supply : asset.can_borrow);
  if (!eligible.length || container.children.length >= 12) return;
  const row = document.createElement('div');
  row.className = 'lending-asset-row';
  const select = document.createElement('select');
  select.setAttribute('aria-label', side === 'supplies' ? 'Ativo fornecido' : 'Ativo emprestado');
  eligible.forEach((asset) => { const option = document.createElement('option'); option.value = asset.address; option.textContent = asset.symbol; select.append(option); });
  const preferred = eligible.find((asset) => lendingSameAddress(asset.address, String(preset.asset || '')))
    || eligible.find((asset) => asset.symbol === (side === 'supplies' ? 'WETH' : 'USDC'))
    || (side === 'supplies' ? eligible.find((asset) => asset.can_collateral) : null) || eligible[0];
  select.value = preferred.address;
  const amount = document.createElement('input');
  amount.type = 'text'; amount.inputMode = 'decimal'; amount.placeholder = 'Quantidade'; amount.setAttribute('aria-label', 'Quantidade');
  amount.value = preset.amount || '';
  const price = document.createElement('input');
  price.type = 'text'; price.inputMode = 'decimal'; price.setAttribute('aria-label', 'Preço em dólares');
  const updatePrice = () => { price.value = preset.price || lendingAsset(select.value)?.price || ''; preset.price = ''; updateHint(); updateShockAssets(); };
  const hint = document.createElement('small');
  const updateHint = () => { const asset = lendingAsset(select.value); hint.textContent = asset
    ? `US$ ${Number(price.value).toLocaleString('pt-BR', { maximumFractionDigits: 4 })} · APY ${((Number(side === 'supplies' ? asset.supply_apy : asset.borrow_apy) || 0) * 100).toFixed(2).replace('.', ',')}%`
    : ''; collateral.disabled = !asset?.can_collateral; if (collateral.disabled) collateral.checked = false; };
  const collateral = document.createElement('label');
  collateral.className = 'lending-collateral';
  const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = preset.collateral !== false;
  collateral.append(checkbox, document.createTextNode(' Garantia'));
  Object.defineProperty(collateral, 'checked', { get: () => checkbox.checked, set: (value) => { checkbox.checked = value; } });
  const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'lending-row-remove'; remove.textContent = '×'; remove.setAttribute('aria-label', 'Remover ativo');
  remove.addEventListener('click', () => { row.remove(); updateShockAssets(); });
  select.addEventListener('change', updatePrice); price.addEventListener('input', updateHint);
  row.append(select, amount, price, ...(side === 'supplies' ? [collateral] : []), remove, hint);
  container.append(row); updatePrice();
}

function updateShockAssets() {
  const select = document.querySelector('#lending-shock-asset');
  const previous = select.value;
  select.replaceChildren(new Option('Sem variação', ''));
  const used = new Set();
  [...lendingSupplies.children, ...lendingBorrows.children].forEach((row) => {
    const address = row.querySelector('select')?.value;
    if (!address || used.has(address)) return;
    used.add(address);
    select.add(new Option(lendingAsset(address)?.symbol || 'Ativo', address));
  });
  select.value = used.has(previous) ? previous : (lendingSupplies.querySelector('select')?.value || '');
  updateLendingScenarioSummary();
}

async function loadLendingMarket() {
  const selected = lendingMarkets.find((item) => lendingMarketKey(item) === lendingMarketSelect.value);
  if (!selected) return;
  const sequence = ++lendingLoadSequence;
  lendingMarketData = null;
  lendingError('');
  try {
    const params = new URLSearchParams({ chain_id: selected.chain_id, address: selected.address });
    const response = await fetch(`/api/lending-market?${params}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Mercado indisponível.');
    if (sequence !== lendingLoadSequence) return;
    lendingMarketData = data;
    lendingSupplies.replaceChildren(); lendingBorrows.replaceChildren();
    lendingRow('supplies'); lendingRow('borrows'); updateShockAssets();
    lendingDemoId.textContent = 'Sem carteira real';
    lendingDemoId.removeAttribute('title');
  } catch (error) { if (sequence === lendingLoadSequence) lendingError(error.message); }
}

function showLendingProtocol(protocol, preferredMarket) {
  const available = lendingMarkets.filter((item) => item.protocol === protocol);
  if (!available.length) return;
  lendingProtocolButtons.forEach((button) => {
    button.disabled = !lendingMarkets.some((item) => item.protocol === button.dataset.lendingProtocol);
    button.setAttribute('aria-pressed', String(button.dataset.lendingProtocol === protocol));
  });
  lendingMarketSelect.replaceChildren(...available.map((item) =>
    new Option(item.name.replace(/^(?:Aave V3|Fluid|Morpho|Kamino) · /, ''), lendingMarketKey(item))));
  lendingMarketSelect.value = available.some((item) => lendingMarketKey(item) === preferredMarket)
    ? preferredMarket : lendingMarketKey(available[0]);
}

async function openLendingDialog(prefill = {}) {
  if (!lendingDialog) return;
  lendingError('');
  if (!lendingDialog.open) lendingDialog.showModal();
  if (!lendingMarkets.length) {
    try {
      const response = await fetch('/api/lending-markets', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Mercados indisponíveis.');
      lendingMarkets = data.markets;
      const main = lendingMarkets.find((item) => item.name === 'Aave V3 · Ethereum') || lendingMarkets[0];
      showLendingProtocol(main.protocol, lendingMarketKey(main));
    } catch (error) { lendingError(error.message); return; }
  }
  await loadLendingMarket();
  if (prefill.collateral_weth && prefill.borrow_usdc && lendingMarketData) {
    lendingSupplies.querySelector('input[aria-label="Quantidade"]').value = prefill.collateral_weth;
    lendingBorrows.querySelector('input[aria-label="Quantidade"]').value = prefill.borrow_usdc;
    document.querySelector('#lending-shock-pct').value = -(prefill.price_drop_pct || 20);
    updateLendingScenarioSummary();
  }
}

document.querySelector('[data-action="configure-lending"]')?.addEventListener('click', () => openLendingDialog());
document.querySelector('#lending-dialog-close')?.addEventListener('click', () => closeShortcutDialog(lendingDialog));
lendingDialog?.addEventListener('click', (event) => { if (event.target === lendingDialog) closeShortcutDialog(lendingDialog); });
lendingMarketSelect?.addEventListener('change', loadLendingMarket);
lendingProtocolButtons.forEach((button) => button.addEventListener('click', () => {
  if (button.getAttribute('aria-pressed') === 'true') return;
  showLendingProtocol(button.dataset.lendingProtocol);
  loadLendingMarket();
}));
document.querySelector('#lending-shock-slider')?.addEventListener('input', (event) => { document.querySelector('#lending-shock-pct').value = event.target.value; updateLendingScenarioSummary(); });
document.querySelector('#lending-shock-pct')?.addEventListener('input', (event) => { const slider = document.querySelector('#lending-shock-slider'); slider.value = Math.max(-95, Math.min(100, Number(event.target.value) || 0)); updateLendingScenarioSummary(); });
document.querySelector('#lending-shock-asset')?.addEventListener('change', updateLendingScenarioSummary);
document.querySelector('#lending-days')?.addEventListener('input', updateLendingScenarioSummary);
document.querySelector('#lending-add-supply')?.addEventListener('click', () => { lendingRow('supplies'); updateShockAssets(); });
document.querySelector('#lending-add-borrow')?.addEventListener('click', () => { lendingRow('borrows'); updateShockAssets(); });
document.querySelector('#lending-reset')?.addEventListener('click', () => {
  lendingSupplies.replaceChildren(); lendingBorrows.replaceChildren(); lendingRow('supplies'); updateShockAssets(); lendingError('');
  lendingDemoId.textContent = 'Sem carteira real';
  lendingDemoId.removeAttribute('title');
});
document.querySelector('#lending-generate')?.addEventListener('click', () => {
  const solana = lendingMarketData?.chain_id === 101;
  const bytes = crypto.getRandomValues(new Uint8Array(solana ? 32 : 20));
  let address;
  if (solana) {
    const alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
    let value = bytes.reduce((number, byte) => (number << 8n) + BigInt(byte), 0n);
    address = '';
    while (value > 0n) { address = alphabet[Number(value % 58n)] + address; value /= 58n; }
    for (const byte of bytes) { if (byte !== 0) break; address = '1' + address; }
  } else address = `0x${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
  lendingDemoId.textContent = `Teste: ${address}`;
  lendingDemoId.title = 'Endereço fictício de teste. Não tem chave privada nem saldo na rede.';
  lendingError('');
});
document.querySelector('[data-action="track-wallet"]')?.addEventListener('click', () => {
  walletFormError.hidden = true;
  walletFormError.textContent = '';
  if (!walletDialog.open) walletDialog.showModal();
  walletAddress.focus();
});
document.querySelector('#wallet-dialog-close')?.addEventListener('click', () => closeShortcutDialog(walletDialog));
walletDialog?.addEventListener('click', (event) => { if (event.target === walletDialog) closeShortcutDialog(walletDialog); });
walletForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  if (isSubmitting) return;
  const network = walletNetwork.value;
  const address = walletAddress.value.trim();
  const valid = network === 'ethereum' ? /^0x[0-9a-fA-F]{40}$/.test(address)
    : network === 'bitcoin' ? /^(?:[13][1-9A-HJ-NP-Za-km-z]{25,34}|bc1[023456789acdefghjklmnpqrstuvwxyz]{11,87})$/.test(address)
      : /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address);
  if (!valid) {
    walletFormError.textContent = 'Confira o endereço para a rede selecionada.';
    walletFormError.hidden = false;
    return;
  }
  pendingWalletRequest = { network, address };
  chatInput.value = `Rastreie a wallet ${address} na rede ${walletNetwork.selectedOptions[0].textContent}`;
  resizeComposer();
  closeShortcutDialog(walletDialog);
  chatForm.requestSubmit();
});

lendingForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  if (isSubmitting || !lendingMarketData) return;
  const rows = (container, supply) => [...container.children].map((row) => {
    const inputs = row.querySelectorAll('input');
    const result = { asset: row.querySelector('select').value, amount: inputs[0].value.trim().replace(',', '.'), price: inputs[1].value.trim().replace(',', '.') };
    if (supply) result.collateral = inputs[2].checked;
    return result;
  });
  const supplies = rows(lendingSupplies, true), borrows = rows(lendingBorrows, false);
  const shock = { asset: document.querySelector('#lending-shock-asset').value, pct: Number(document.querySelector('#lending-shock-pct').value) };
  const days = Number(document.querySelector('#lending-days').value);
  const request = { kind: 'lending', version: 2, chain_id: lendingMarketData.chain_id, market_address: lendingMarketData.address,
    supplies, borrows, shock, days };
  if (!safeLendingRequest(request) || supplies.some((row) => Number(row.amount) <= 0 || Number(row.price) <= 0)
      || borrows.some((row) => Number(row.amount) <= 0 || Number(row.price) <= 0)) return lendingError('Confira quantidades e preços dos ativos.');
  lendingError('');
  pendingSimulationRequest = request;
  chatInput.value = `Simule lending em ${lendingMarketData.name}: ${supplies.length} ativo(s) fornecido(s), ${borrows.length} empréstimo(s), ${days} dias`;
  resizeComposer();
  closeShortcutDialog(lendingDialog);
  chatForm.requestSubmit();
});

function showPoolError(message) {
  if (!poolFormError) return;
  poolFormError.textContent = message;
  poolFormError.hidden = !message;
}

function selectedPool() {
  return poolOptions?.find((pool) => pool.id === poolSelect?.value) || null;
}

const formatPrice = (value) => value.toLocaleString('pt-BR', { maximumFractionDigits: 6 });
function tickPrice(pool, tick) {
  const ratio = Math.exp(tick * Math.log(1.0001)) * 10 ** (pool.token0_decimals - pool.token1_decimals);
  return pool.base_is_token0 ? ratio : 1 / ratio;
}
function priceTick(pool, price) {
  const ratio = pool.base_is_token0 ? price : 1 / price;
  return Math.log(ratio / 10 ** (pool.token0_decimals - pool.token1_decimals)) / Math.log(1.0001);
}
function rangePrices() {
  const pool = selectedPool();
  if (!pool || !selectedRange) return null;
  const first = tickPrice(pool, selectedRange.lower);
  const last = tickPrice(pool, selectedRange.upper);
  return { floor: Math.min(first, last), ceiling: Math.max(first, last) };
}
function renderMarketRange() {
  if (poolMode?.value === 'history') return;
  if (!marketCandles || !marketChart || !marketHasData || !poolSnapshot || !selectedRange) return;
  const bounds = rangePrices();
  if (!bounds) return;
  const spot = Number(poolSnapshot.price?.quote_per_base);
  for (const [key, value, title, color] of [['floor', bounds.floor, 'Piso', '#b889df'], ['ceiling', bounds.ceiling, 'Teto', '#f4a4c0'], ['spot', spot, 'Atual', '#ffae72']]) {
    if (!Number.isFinite(value) || value <= 0) continue;
    if (marketLines[key]) marketLines[key].applyOptions({ price: value });
    else marketLines[key] = marketCandles.createPriceLine({ price: value, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title });
  }
  const floorY = marketCandles.priceToCoordinate(bounds.floor);
  const ceilingY = marketCandles.priceToCoordinate(bounds.ceiling);
  const height = marketChart.panes()[0]?.getHeight() || 190;
  if (floorY === null || ceilingY === null) return;
  poolFloorHandle.hidden = false;
  poolCeilingHandle.hidden = false;
  poolPriceShade.hidden = false;
  poolFloorHandle.style.top = `${Math.max(16, Math.min(height - 16, floorY))}px`;
  poolCeilingHandle.style.top = `${Math.max(16, Math.min(height - 16, ceilingY))}px`;
  poolFloorHandle.textContent = `↕ Piso ${formatPrice(bounds.floor)}`;
  poolCeilingHandle.textContent = `↕ Teto ${formatPrice(bounds.ceiling)}`;
  poolPriceShade.style.top = `${Math.max(0, ceilingY)}px`;
  poolPriceShade.style.height = `${Math.max(0, Math.min(height, floorY) - Math.max(0, ceilingY))}px`;
  poolPriceShade.style.width = `${marketChart.timeScale().width()}px`;
}
function ensureMarketChart() {
  if (marketChart || !poolPriceCanvas) return;
  marketChart = createChart(poolPriceCanvas, {
    width: poolPriceCanvas.clientWidth, height: poolPriceCanvas.clientHeight,
    layout: { background: { type: ColorType.Solid, color: '#15141e' }, textColor: '#a99eb3', fontSize: 10, attributionLogo: true },
    grid: { vertLines: { color: '#ffffff10' }, horzLines: { color: '#ffffff10' } },
    localization: { locale: 'pt-BR', priceFormatter: formatPrice },
    rightPriceScale: { borderColor: '#ffffff20', scaleMargins: { top: 0.12, bottom: 0.12 } },
    timeScale: { borderColor: '#ffffff20', timeVisible: true, secondsVisible: false },
    handleScroll: false, handleScale: false,
  });
  marketCandles = marketChart.addSeries(CandlestickSeries, {
    upColor: '#c79de9', downColor: '#ec8cae', wickUpColor: '#c79de9', wickDownColor: '#ec8cae',
    borderVisible: false, priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'price', precision: 6, minMove: 0.000001 },
    autoscaleInfoProvider: (original) => {
      const info = original();
      const bounds = rangePrices();
      if (info?.priceRange && bounds) {
        info.priceRange.minValue = Math.min(info.priceRange.minValue, bounds.floor);
        info.priceRange.maxValue = Math.max(info.priceRange.maxValue, bounds.ceiling);
      }
      return info;
    },
  });
  marketCandles.attachPrimitive({ updateAllViews: () => {
    if (!marketHasData || !selectedRange || !poolSnapshot) return;
    const bounds = rangePrices();
    if (!bounds) return;
    const height = marketChart.panes()[0]?.getHeight() || 190;
    const floorY = marketCandles.priceToCoordinate(bounds.floor);
    const ceilingY = marketCandles.priceToCoordinate(bounds.ceiling);
    if (floorY === null || ceilingY === null) return;
    poolFloorHandle.style.top = `${Math.max(16, Math.min(height - 16, floorY))}px`;
    poolCeilingHandle.style.top = `${Math.max(16, Math.min(height - 16, ceilingY))}px`;
  } });
  new ResizeObserver(() => {
    if (poolPriceCanvas.clientWidth) marketChart.applyOptions({ width: poolPriceCanvas.clientWidth });
    renderMarketRange();
  }).observe(poolPriceCanvas);
}
async function loadPoolChart() {
  const pool = selectedPool();
  const requestSeq = ++marketRequestSeq;
  marketHasData = false;
  poolFloorHandle.hidden = true;
  poolCeilingHandle.hidden = true;
  poolPriceShade.hidden = true;
  poolChartStatus.hidden = false;
  poolChartStatus.textContent = 'Carregando velas reais da pool…';
  document.getElementById('pool-chart-source').textContent = 'Histórico da pool';
  if (!pool) return;
  if (!pool.chart_available) {
    poolChartStatus.textContent = 'O histórico de velas desta rede ainda não está conectado ao Altside.';
    return;
  }
  ensureMarketChart();
  marketChart.applyOptions({ width: poolPriceCanvas.clientWidth });
  for (const line of Object.values(marketLines)) marketCandles.removePriceLine(line);
  marketLines = {};
  marketCandles.setData([]);
  try {
    const response = await fetch(`/api/pool-chart?pool_id=${encodeURIComponent(pool.id)}&interval=${marketInterval}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || data.pool_id !== pool.id || data.interval !== marketInterval || !Array.isArray(data.candles) || !data.candles.length) throw new Error(data.error || 'Histórico indisponível.');
    if (requestSeq !== marketRequestSeq || !poolDialog.open) return;
    const candles = poolMode.value === 'history'
      ? data.candles.filter((item) => item.time >= data.candles.at(-1).time - Number(poolPeriod.value) * 86400)
      : data.candles;
    marketCandles.setData(candles);
    marketHasData = true;
    marketChart.timeScale().fitContent();
    poolChartStatus.hidden = true;
    document.getElementById('pool-chart-source').textContent = data.stale ? 'Último histórico disponível' : 'Histórico atualizado';
    renderMarketRange();
  } catch (error) {
    if (requestSeq !== marketRequestSeq || !poolDialog.open) return;
    poolChartStatus.textContent = 'Histórico indisponível agora. A faixa em ticks continua utilizável.';
  }
}

function renderSelectedRange() {
  if (!poolSnapshot || !selectedRange) return;
  poolRange.value = String(selectedRange.upper - selectedRange.lower);
  const bounds = rangePrices();
  const pool = selectedPool();
  poolRangeHint.textContent = poolMode?.value === 'history'
    ? `Faixa de ${poolRange.value} ticks centrada no primeiro preço histórico do período. Custos e taxas futuras não entram no resultado.`
    : bounds && pool
    ? `Piso ${formatPrice(bounds.floor)} · teto ${formatPrice(bounds.ceiling)} ${pool.quote_symbol}. Limites alinhados aos ticks da pool.`
    : 'Limites ajustados ao espaçamento de ticks da pool.';
  renderMarketRange();
}

function centerRange(width) {
  if (!poolSnapshot) return;
  const spacing = poolSnapshot.tick_spacing;
  const current = poolSnapshot.current_tick;
  const half = Math.max(spacing, width / 2);
  const lower = Math.floor((current - half) / spacing) * spacing;
  const upper = Math.ceil((current + half) / spacing) * spacing;
  selectedRange = { lower, upper };
  renderSelectedRange();
}

async function loadPoolSnapshot() {
  const pool = selectedPool();
  const requestSeq = ++chartRequestSeq;
  poolSnapshot = null;
  selectedRange = null;
  rangeChart.classList.remove('is-ready');
  document.getElementById('range-chart-block').textContent = 'Consultando pool…';
  document.getElementById('range-chart-price').textContent = 'Aguardando preço atual';
  if (!pool) return;
  try {
    const response = await fetch(`/api/pool-snapshot?pool_id=${encodeURIComponent(pool.id)}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || data.pool_id !== pool.id || !Number.isInteger(data.current_tick) || !Number.isInteger(data.tick_spacing)) throw new Error(data.error || 'Estado da pool indisponível.');
    if (requestSeq !== chartRequestSeq || !poolDialog.open) return;
    poolSnapshot = data;
    document.getElementById('range-chart-block').textContent = `${data.source_label === 'Slot' ? 'Slot' : 'Bloco'} ${data.block_number.toLocaleString('pt-BR')}`;
    const price = Number(data.price?.quote_per_base);
    document.getElementById('range-chart-price').textContent = Number.isFinite(price) && price > 0
      ? `${poolMode.value === 'history' ? 'Preço agora' : 'Preço indicativo'} · 1 ${pool.base_symbol} ≈ ${price.toLocaleString('pt-BR', { maximumFractionDigits: 6 })} ${pool.quote_symbol}`
      : 'Preço indicativo indisponível · ajuste pela escala de ticks';
    if (poolMode.value !== 'history') centerRange(Number(poolRange.value) || 1200);
    rangeChart.classList.add('is-ready');
  } catch (error) {
    if (requestSeq !== chartRequestSeq || !poolDialog.open) return;
    document.getElementById('range-chart-block').textContent = 'Sem dados ao vivo';
    document.getElementById('range-chart-price').textContent = 'Use o campo de ticks para configurar a faixa.';
  }
}

function updatePoolFields(ensureMinimum = false) {
  const pool = selectedPool();
  if (!pool) return;
  const historical = poolMode.value === 'history';
  const available = historical ? pool.chart_available : pool.simulation_available;
  poolSubmit.disabled = !available;
  poolAvailability.hidden = available;
  poolAvailability.textContent = available ? '' : historical
    ? `🔎 ${pool.network}: o histórico de velas desta pool ainda não está conectado ao Altside.`
    : `🔎 ${pool.network}: preço ao vivo disponível. A prévia de entrada desta pool ainda não está conectada à Alt-IA.`;
  poolCapitalUnit.textContent = pool.quote_symbol;
  const minimum = pool.tick_spacing * 2;
  poolRange.min = String(minimum);
  if (ensureMinimum && (!Number.isInteger(Number(poolRange.value)) || Number(poolRange.value) < minimum)) poolRange.value = String(Math.max(1200, minimum));
  const ticks = Number(poolRange.value);
  const approximateHalfWidth = (Math.pow(1.0001, ticks / 2) - 1) * 100;
  poolRangeHint.textContent = historical
    ? `Faixa de ${ticks} ticks centrada no primeiro preço histórico do período. Custos e taxas futuras não entram no resultado.`
    : Number.isFinite(approximateHalfWidth)
    ? `Faixa aproximada de ±${approximateHalfWidth.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}% em torno do preço atual. Mínimo: ${minimum} ticks.`
    : `Mínimo para esta pool: ${minimum} ticks.`;
  if (!historical && poolSnapshot && Number.isInteger(ticks) && ticks >= minimum && ticks <= 50000) centerRange(ticks);
}

function updatePoolMode() {
  const historical = poolMode.value === 'history';
  document.getElementById('pool-dialog-title').textContent = historical ? 'Explore o que passou.' : 'Desenhe sua entrada.';
  document.querySelector('.pool-dialog-copy p').textContent = historical
    ? 'Escolha uma pool e reconstrua o valor de uma faixa com preços históricos do Altside.'
    : 'Escolha a pool e ajuste os parâmetros antes de consultar o motor Altside.';
  poolPeriodField.hidden = !historical;
  poolModeGrid.classList.toggle('is-history', historical);
  document.querySelector('.pool-slippage-row').hidden = historical;
  document.getElementById('pool-slippage-hint').textContent = historical
    ? 'Reconstituição com preços históricos de fechamento. Taxas recebidas, gas e execução não são calculados.'
    : 'Prévia somente leitura. Nenhuma transação é enviada.';
  document.getElementById('range-chart-note').textContent = historical
    ? 'Veja os preços passados. A faixa histórica é centrada na primeira vela e sua largura vem do campo de ticks.'
    : 'Arraste piso e teto no gráfico ou ajuste os ticks abaixo · dados Altside/GeckoTerminal';
  document.getElementById('pool-submit-label').textContent = historical ? 'Simular período histórico' : 'Calcular prévia';
  if (historical) {
    marketInterval = ({ '7': '1h', '30': '4h', '90': '1d' })[poolPeriod.value];
    document.querySelectorAll('#pool-chart-intervals [data-interval]').forEach((button) => {
      button.classList.toggle('active', button.dataset.interval === marketInterval);
      button.setAttribute('aria-pressed', button.dataset.interval === marketInterval ? 'true' : 'false');
    });
  }
  document.querySelectorAll('#pool-chart-intervals [data-interval]').forEach((button) => { button.disabled = historical; });
  updatePoolFields();
  loadPoolChart();
}

function renderPoolChoices(preferredPoolId) {
  const candidates = poolOptions.filter((pool) => pool.network === poolNetwork.value);
  poolSelect.replaceChildren(...candidates.map((pool) => new Option(`${pool.pair} · ${pool.protocol}`, pool.id)));
  poolSelect.value = candidates.some((pool) => pool.id === preferredPoolId) ? preferredPoolId : (candidates[0]?.id || '');
  poolSnapshot = null;
  selectedRange = null;
  updatePoolFields(true);
  loadPoolSnapshot();
  loadPoolChart();
}

async function openPoolDialog(prefill = {}) {
  if (!poolDialog) return;
  showPoolError('');
  if (!poolDialog.open) poolDialog.showModal();
  if (!poolOptions) {
    poolNetwork.replaceChildren(new Option('Carregando redes…', ''));
    poolNetwork.disabled = true;
    poolSelect.replaceChildren(new Option('Carregando pools…', ''));
    poolSelect.disabled = true;
    try {
      const response = await fetch('/api/pool-options', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !Array.isArray(data.pools)) throw new Error(data.error || 'Não foi possível carregar as pools.');
      poolOptions = data.pools.filter((pool) => pool && typeof pool.id === 'string' && typeof pool.pair === 'string' && typeof pool.network === 'string' && typeof pool.protocol === 'string' && typeof pool.quote_symbol === 'string' && typeof pool.simulation_available === 'boolean' && typeof pool.chart_available === 'boolean' && Number.isInteger(pool.tick_spacing) && pool.tick_spacing > 0 && typeof pool.base_is_token0 === 'boolean' && Number.isInteger(pool.token0_decimals) && Number.isInteger(pool.token1_decimals));
      if (!poolOptions.length) throw new Error('Não há pools disponíveis para prévia agora.');
    } catch (error) {
      poolOptions = null;
      showPoolError(error.message || 'Não foi possível carregar as pools.');
      poolNetwork.replaceChildren(new Option('Redes indisponíveis', ''));
      poolSelect.replaceChildren(new Option('Pools indisponíveis', ''));
      return;
    } finally {
      poolNetwork.disabled = false;
      poolSelect.disabled = false;
    }
  }
  const defaultPool = poolOptions.find((pool) => pool.pair === 'WETH/USDC' && pool.network.toLowerCase().startsWith('base')) || poolOptions[0];
  const selected = poolOptions.find((pool) => pool.id === prefill.pool_id) || defaultPool;
  poolNetwork.replaceChildren(...[...new Set(poolOptions.map((pool) => pool.network))].map((network) => new Option(network, network)));
  poolNetwork.value = selected.network;
  poolMode.value = prefill.kind === 'historical_pool' ? 'history' : 'live';
  poolPeriod.value = [7, 30, 90].includes(prefill.period_days) ? String(prefill.period_days) : '7';
  poolCapital.value = typeof prefill.capital_quote === 'string' ? prefill.capital_quote : '';
  poolRange.value = Number.isInteger(prefill.range_ticks) ? String(prefill.range_ticks) : '1200';
  poolSlippage.value = Number.isInteger(prefill.slippage_bps) ? String(prefill.slippage_bps / 100).replace('.', ',') : '0,2';
  renderPoolChoices(selected.id);
  updatePoolMode();
  poolSelect.focus();
}

document.querySelector('[data-action="configure-pool"]')?.addEventListener('click', () => openPoolDialog());
poolDialogClose?.addEventListener('click', () => closeShortcutDialog(poolDialog));
poolDialog?.addEventListener('click', (event) => { if (event.target === poolDialog) closeShortcutDialog(poolDialog); });
poolDialog?.addEventListener('close', () => { chartRequestSeq++; marketRequestSeq++; marketDrag = null; });
poolNetwork?.addEventListener('change', () => renderPoolChoices());
poolMode?.addEventListener('change', updatePoolMode);
poolPeriod?.addEventListener('change', updatePoolMode);
poolSelect?.addEventListener('change', () => { poolSnapshot = null; selectedRange = null; updatePoolFields(true); loadPoolSnapshot(); loadPoolChart(); });
poolRange?.addEventListener('change', () => updatePoolFields());
document.querySelectorAll('#pool-chart-intervals [data-interval]').forEach((button) => {
  button.setAttribute('aria-pressed', button.dataset.interval === marketInterval ? 'true' : 'false');
  button.addEventListener('click', () => {
    if (poolMode.value === 'history') return;
    if (button.dataset.interval === marketInterval) return;
    marketInterval = button.dataset.interval;
    document.querySelectorAll('#pool-chart-intervals [data-interval]').forEach((item) => {
      item.classList.toggle('active', item === button);
      item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
    });
    loadPoolChart();
  });
});

function moveMarketEdge(edge, price) {
  const pool = selectedPool();
  if (!pool || !poolSnapshot || !selectedRange || !Number.isFinite(price) || price <= 0) return;
  const spacing = pool.tick_spacing;
  const current = poolSnapshot.current_tick;
  const nativeKind = (edge === 'floor') === pool.base_is_token0 ? 'lower' : 'upper';
  const snapped = Math.round(priceTick(pool, price) / spacing) * spacing;
  if (!Number.isSafeInteger(snapped)) return;
  if (nativeKind === 'lower') selectedRange.lower = Math.max(Math.ceil(-887272 / spacing) * spacing, selectedRange.upper - 50000, Math.min(snapped, Math.floor((current - 1) / spacing) * spacing, selectedRange.upper - 2 * spacing));
  else selectedRange.upper = Math.min(Math.floor(887272 / spacing) * spacing, selectedRange.lower + 50000, Math.max(snapped, Math.ceil((current + 1) / spacing) * spacing, selectedRange.lower + 2 * spacing));
  renderSelectedRange();
}
for (const [button, edge] of [[poolFloorHandle, 'floor'], [poolCeilingHandle, 'ceiling']]) {
  button?.addEventListener('pointerdown', (event) => {
    if (!marketHasData || !selectedRange) return;
    marketDrag = edge;
    button.setPointerCapture(event.pointerId);
    marketChart.priceScale('right').applyOptions({ autoScale: false });
    event.preventDefault();
  });
  button?.addEventListener('pointermove', (event) => {
    if (marketDrag !== edge) return;
    const y = event.clientY - poolPricePlot.getBoundingClientRect().top;
    const price = marketCandles.coordinateToPrice(Math.max(0, Math.min(poolPriceCanvas.clientHeight, y)));
    moveMarketEdge(edge, price);
  });
  const end = () => { if (marketDrag === edge) { marketDrag = null; marketChart.priceScale('right').applyOptions({ autoScale: true }); renderMarketRange(); } };
  button?.addEventListener('pointerup', end);
  button?.addEventListener('pointercancel', end);
  button?.addEventListener('lostpointercapture', end);
  button?.addEventListener('keydown', (event) => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key) || !selectedRange) return;
    event.preventDefault();
    const pool = selectedPool();
    const nativeKind = (edge === 'floor') === pool.base_is_token0 ? 'lower' : 'upper';
    const direction = (event.key === 'ArrowUp' ? 1 : -1) * (pool.base_is_token0 ? 1 : -1);
    moveMarketEdge(edge, tickPrice(pool, selectedRange[nativeKind] + direction * pool.tick_spacing));
  });
}

poolForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  if (isSubmitting) return showPoolError('Aguarde a resposta atual antes de enviar outra simulação.');
  const pool = selectedPool();
  const capital = poolCapital.value.trim().replace(',', '.');
  const ticks = Number(poolRange.value);
  const slippageText = poolSlippage.value.trim().replace(',', '.');
  const slippage = Number(slippageText);
  if (!pool) return showPoolError('Escolha uma pool.');
  const historical = poolMode.value === 'history';
  if (historical && !pool.chart_available) return showPoolError(`O histórico da ${pool.network} ainda não está conectado.`);
  if (!historical && !pool.simulation_available) return showPoolError(`A prévia de entrada da ${pool.network} ainda não está conectada.`);
  if (!/^\d+(?:\.\d{1,18})?$/.test(capital) || Number(capital) <= 0 || Number(capital) > 10_000_000) return showPoolError('Informe um capital válido, maior que zero e até 10 milhões.');
  if (!Number.isInteger(ticks) || ticks < pool.tick_spacing * 2 || ticks > 50000) return showPoolError(`A faixa precisa ter entre ${pool.tick_spacing * 2} e 50000 ticks.`);
  if (!historical && (!/^\d+(?:\.\d{1,2})?$/.test(slippageText) || slippage < 0 || slippage > (pool.simulation_engine === 'robinhood_usdg_entry_preview' ? 1 : 5))) return showPoolError(`O slippage deve estar entre 0% e ${pool.simulation_engine === 'robinhood_usdg_entry_preview' ? 1 : 5}%, com até duas casas decimais.`);
  showPoolError('');
  pendingSimulationRequest = historical
    ? { kind: 'historical_pool', pool_id: pool.id, capital_quote: capital, range_ticks: ticks, period_days: Number(poolPeriod.value) }
    : { kind: 'pool', pool_id: pool.id, capital_quote: capital, range_ticks: ticks, slippage_bps: Math.round(slippage * 100) };
  if (!historical && poolSnapshot?.pool_id === pool.id && selectedRange && selectedRange.upper - selectedRange.lower === ticks) {
    pendingSimulationRequest.tick_lower = selectedRange.lower;
    pendingSimulationRequest.tick_upper = selectedRange.upper;
  }
  chatInput.value = historical
    ? `Simule os últimos ${poolPeriod.value} dias da pool ${pool.pair} na ${pool.network} com ${capital} ${pool.quote_symbol} e faixa de ${ticks} ticks`
    : `Simule entrada de ${capital} ${pool.quote_symbol} na pool ${pool.pair} da ${pool.network} (${pool.protocol}), faixa de ${ticks} ticks e slippage de ${slippage.toLocaleString('pt-BR')}%`;
  resizeComposer();
  closeShortcutDialog(poolDialog);
  chatForm.requestSubmit();
});

chatInput?.addEventListener('input', resizeComposer);
chatInput?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    chatForm?.requestSubmit();
  }
});

let isSubmitting = false;
async function revealFirstMessage(conversationId) {
  if (!welcome?.isConnected || activeId !== conversationId) {
    if (activeId === conversationId) renderConversation();
    return;
  }
  const exit = welcome.animate([
    { opacity: 1, transform: 'translateY(0) scale(1)', filter: 'blur(0px)' },
    { opacity: 0, transform: 'translateY(-28px) scale(.94)', filter: 'blur(7px)' }
  ], { duration: 390, easing: 'cubic-bezier(.32,0,.67,0)', fill: 'forwards' });
  await exit.finished.catch(() => {});
  if (activeId === conversationId) {
    renderConversation();
    const firstRow = chatMessages.querySelector('.message-user');
    if (firstRow) {
      firstRow.classList.add('first-message');
      firstRow.animate([
        { opacity: 0, transform: 'translateY(42px) scale(.94)', filter: 'blur(5px)' },
        { offset: .72, opacity: 1, transform: 'translateY(-4px) scale(1.015)', filter: 'blur(0px)' },
        { opacity: 1, transform: 'translateY(0) scale(1)', filter: 'blur(0px)' }
      ], { duration: 610, easing: 'cubic-bezier(.2,.8,.2,1)' });
    }
  }
  exit.cancel();
}

chatForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = chatInput?.value.trim();
  if (!text || isSubmitting) return;
  const simulationRequest = pendingSimulationRequest;
  pendingSimulationRequest = null;
  const walletRequest = pendingWalletRequest;
  pendingWalletRequest = null;
  let conversation = conversations.find((item) => item.id === activeId);
  if (!conversation) {
    conversation = { id: crypto.randomUUID(), title: titleFrom(text), pinned: false, nerdMode: draftNerdMode, agentMode: draftAgentMode,
      nerdTopic: draftNerdTopic, updatedAt: Date.now(), messages: [] };
    conversations.push(conversation);
    activeId = conversation.id;
  }
  const isFirstMessage = conversation.messages.length === 0;
  const previousAnswer = [...conversation.messages].reverse().find((message) => message.role === 'ai');
  const previousMode = previousAnswer?.mode || (previousAnswer?.news?.length || previousAnswer?.newsContext?.length || previousAnswer?.text?.startsWith('🗞️')
    ? 'news' : previousAnswer?.simulation?.kind || 'general');
  const previousPool = previousMode === 'pool' ? previousAnswer : null;
  conversation.messages.push({ role: 'user', text });
  conversation.updatedAt = Date.now();
  conversation.messages = conversation.messages.slice(-100);
  chatInput.value = '';
  resizeComposer();
  persist();
  renderHistory();
  const conversationId = conversation.id;
  const agentForRequest = conversation.agentMode && agentDesktop.matches;
  if (agentForRequest) {
    agentOwnerId = conversationId;
    agentPipHasReply = false;
    agentDockSpeech.textContent = 'Estou explorando o que você pediu… 🔎';
  }
  isSubmitting = true;
  chatForm.querySelector('button[type="submit"]').disabled = true;
  chatMessages.setAttribute('aria-busy', 'true');
  if (isFirstMessage) await revealFirstMessage(conversationId);
  else renderConversation();
  const pending = createMessage('ai', agentForRequest ? 'Navegando e analisando a página…' : conversation.nerdMode ? 'Pesquisando fontes e analisando…' : walletRequest ? 'Consultando a wallet e organizando os dados…'
    : /\b(news|not[ií]cias?|manchetes)\b/i.test(text) ? 'Buscando notícias…' : 'Pensando…', null, '', [], null, [], conversation.nerdMode);
  pending.classList.add('message-pending');
  if (activeId === conversationId) {
    chatMessages.append(pending);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  let requestedConfig = null;
  try {
    const context = [];
    for (const message of conversation.messages.slice(-20)) {
      if (message.role === 'ai' && message.text.startsWith('Recebi sua mensagem. A API da Alt-IA ainda')) continue;
      const role = message.role === 'ai' ? 'assistant' : 'user';
      const content = message.followUp ? `${message.text}\n\n${message.followUp}` : message.text;
      if (context.at(-1)?.role === role) context.at(-1).content += `\n\n${content}`;
      else context.push({ role, content });
    }
    if (agentForRequest) { stopAgentMedia(); await startAgentSession(); }
    const response = await fetch(agentForRequest ? '/api/agent/run' : '/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: agentForRequest ? JSON.stringify({ task: text, context: agentConversationContext(conversation) }) : JSON.stringify({ messages: context, nerd_mode: conversation.nerdMode, nerd_topic: conversation.nerdTopic, chat_context: {
        mode: previousMode, news_topic: previousAnswer?.newsTopic || '', news: previousMode === 'news' ? previousAnswer?.newsContext || previousAnswer?.news || [] : [],
        nerd_query: previousMode === 'nerd' ? previousAnswer?.nerdQuery || '' : '',
        pool_request: previousMode === 'pool' || previousMode === 'historical_pool' ? previousAnswer?.poolRequest || null : null,
        lending_request: previousMode === 'lending' ? previousAnswer?.lendingRequest || null : null,
        wallet_request: previousMode === 'wallet' ? previousAnswer?.walletRequest || null : null
      }, ...(simulationRequest ? { simulation_request: simulationRequest } : {}),
        ...(walletRequest ? { wallet_request: walletRequest } : {}),
        ...(previousPool?.scenarioToken ? { scenario_token: previousPool.scenarioToken } : {}),
        ...(previousPool?.simulation ? { scenario_context: {
          kind: previousPool.simulation.kind, title: previousPool.simulation.title, subtitle: previousPool.simulation.subtitle,
          metrics: previousPool.simulation.metrics, assumptions: previousPool.simulation.assumptions
        } } : {}) })
    });
    const data = await response.json().catch(() => null);
    if (!data || typeof data !== 'object') {
      throw new Error(response.status >= 500
        ? 'A Alt-IA está temporariamente indisponível. Tente novamente em instantes.'
        : 'A resposta da Alt-IA veio em formato inesperado. Tente novamente.');
    }
    if (!response.ok || typeof data.reply !== 'string') throw new Error(data.error || 'Não foi possível obter uma resposta. Tente novamente.');
    const target = conversations.find((item) => item.id === conversationId);
    if (!target) return;
    target.messages.push({ role: 'ai', text: data.reply, speech: typeof data.speech === 'string' ? data.speech.slice(0, 220) : '',
      simulation: safeSimulation(data.simulation), news: safeNews(data.news), wallet: safeWallet(data.wallet),
      research: safeResearch(data.research), video: safeVideo(data.video), nerdQuery: typeof data.nerd_query === 'string' ? data.nerd_query.slice(0, 650) : '',
      newsContext: safeNews(data.news_context || data.news),
      mode: ['news', 'pool', 'historical_pool', 'lending', 'wallet', 'general', 'nerd', 'agent'].includes(data.mode) ? data.mode : 'general',
      newsTopic: typeof data.news_topic === 'string' ? data.news_topic.slice(0, 30) : '',
      poolRequest: safePoolRequest(data.pool_request),
      lendingRequest: safeLendingRequest(data.lending_request),
      walletRequest: safeWalletRequest(data.wallet_request),
      scenarioToken: typeof data.scenario_token === 'string' ? data.scenario_token.slice(0, 12000) : '',
      followUp: typeof data.follow_up === 'string' ? data.follow_up.slice(0, 280) : '' });
    target.updatedAt = Date.now();
    persist();
    renderHistory();
    if (activeId === conversationId) renderConversation();
    if (agentForRequest) showAgentMedia(data.video);
    if (agentForRequest) {
      agentPipHasReply = true;
      const speech = String(data.speech || data.reply).slice(0, 220);
      agentDockSpeech.textContent = speech;
      if (agentPipStatus) agentPipStatus.textContent = speech;
    }
    if (data.input_request?.kind === 'pool') requestedConfig = data.input_request;
    if (data.input_request?.kind === 'lending') requestedConfig = data.input_request;
  } catch (error) {
    if (activeId === conversationId) {
      renderConversation();
      const notice = createMessage('ai', error.message || 'Falha ao conectar. Tente novamente.');
      notice.classList.add('message-error');
      chatMessages.append(notice);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  } finally {
    isSubmitting = false;
    chatForm.querySelector('button[type="submit"]').disabled = false;
    chatMessages.removeAttribute('aria-busy');
    pending.remove();
    if (requestedConfig && activeId === conversationId) {
      if (requestedConfig.kind === 'lending') openLendingDialog(requestedConfig);
      else openPoolDialog(requestedConfig);
    }
  }
});

renderHistory();
renderConversation();
queueHistoryChanges();

let introFinished = false;
let introTimeline;

function blink() {
  const group = [...document.querySelectorAll('.eye-ball')].filter((eye) => eye.closest(introFinished ? '.site' : '.intro'));
  group.forEach((eye) => eye.classList.add('blink'));
  window.setTimeout(() => group.forEach((eye) => eye.classList.remove('blink')), 145);
  window.setTimeout(blink, 2200 + Math.random() * 2400);
}
window.setTimeout(blink, 1850);

let pointerFrame = 0;
let pointerX = window.innerWidth / 2;
let pointerY = window.innerHeight / 2;
function updateEyes() {
  pointerFrame = 0;
  const updates = [];
  document.querySelectorAll('.eye-pod').forEach((face) => {
    if (!face.getClientRects().length) return;
    const rect = face.getBoundingClientRect();
    const x = Math.max(-3, Math.min(3, (pointerX - rect.left - rect.width / 2) / 80));
    const y = Math.max(-2, Math.min(2, (pointerY - rect.top - rect.height / 2) / 100));
    updates.push([face.querySelectorAll('.pupil'), `translate(${x}px, ${y}px)`]);
  });
  updates.forEach(([pupils, transform]) => pupils.forEach((pupil) => { pupil.style.transform = transform; }));
}
window.addEventListener('pointermove', (event) => {
  pointerX = event.clientX;
  pointerY = event.clientY;
  if (!pointerFrame) pointerFrame = requestAnimationFrame(updateEyes);
}, { passive: true });

function startMascotPhysics() {
  const showcase = welcome?.querySelector('.welcome-showcase');
  const mascot = showcase?.querySelector('.welcome-character');
  const wordmark = showcase?.querySelector('.welcome-wordmark');
  const letters = [...(wordmark?.querySelectorAll('span') || [])];
  if (!showcase || !mascot || !wordmark || letters.length < 2) return;

  const normalLooks = [
    ['#ad73d8', '40% 44% 42% 46%'],
    ['#ff9568', '53% 39% 48% 43% / 46% 52% 43% 55%'],
    ['#77a4ef', '32% 41% 35% 40% / 42% 35% 43% 37%'],
    ['#b08be0', '49% 45% 50% 42% / 41% 54% 43% 52%'],
    ['#65cda5', '43% 52% 46% 51% / 52% 42% 55% 43%'],
    ['#ee91b9', '52% 44% 49% 46% / 44% 53% 42% 55%']
  ];
  const nerdLooks = [
    ['#81a6ed', '38% 42% 38% 44%'],
    ['#6fc8d9', '48% 41% 49% 44%'],
    ['#9a91e8', '42% 51% 43% 50%'],
    ['#80b6ee', '51% 42% 48% 45%'],
    ['#78c9be', '43% 48% 39% 52%']
  ];
  const agentLooks = [
    ['#ef7844', '50%'],
    ['#ef6a3d', '50%'],
    ['#f08844', '50%'],
    ['#e76540', '50%']
  ];
  // Return across the word instead of snapping back to the first letter.
  const stops = [...letters.keys(), ...[...letters.keys()].slice(0, -1).reverse()];
  const flightMs = 650;
  const settleMs = 160;
  const beatMs = flightMs + settleMs;
  const cycleMs = (stops.length - 1) * beatMs;
  let positions = [];
  let landingY = 0;
  let startTime = performance.now();
  let lastLook = -1;
  let pauseStarted = 0;

  function measure() {
    const wordmarkLeft = (showcase.clientWidth - wordmark.offsetWidth) / 2;
    const mascotCenter = mascot.offsetLeft + mascot.offsetWidth / 2;
    positions = letters.map((letter) => wordmarkLeft + letter.offsetLeft + letter.offsetWidth / 2 - mascotCenter);
    landingY = wordmark.offsetTop - mascot.offsetTop - mascot.offsetHeight + 4;
  }

  function impact(index, direction) {
    const looks = isAgentMode() ? agentLooks : isNerdMode() ? nerdLooks : normalLooks;
    const [color, radius] = looks[index % looks.length];
    if (isAgentMode()) mascot.style.setProperty('--fire', color);
    else mascot.style.backgroundColor = color;
    mascot.style.borderRadius = radius;
    letters.forEach((letter, letterIndex) => letter.classList.toggle('is-lit', letterIndex === index));
    if (isAgentMode()) {
      const burned = letters[index];
      mascot.querySelectorAll('.agent-smoke').forEach((puff, puffIndex) => {
        const spread = (puffIndex + .5) / 4;
        puff.style.setProperty('--smoke-x', `${Math.round(10 + spread * 80 + (Math.random() - .5) * 12)}%`);
        puff.style.setProperty('--smoke-y', `${Math.round(-8 + Math.random() * 13)}%`);
        puff.style.setProperty('--smoke-size', `${(11 + Math.random() * 8).toFixed(1)}px`);
        puff.style.setProperty('--smoke-drift', `${Math.round((Math.random() - .5) * 44)}px`);
        puff.style.setProperty('--smoke-rise', `-${Math.round(46 + Math.random() * 36)}px`);
        puff.style.setProperty('--smoke-grow', `${(1.5 + Math.random() * .8).toFixed(2)}`);
        puff.style.setProperty('--smoke-time', `${(1.3 + Math.random() * .8).toFixed(2)}s`);
      });
      burned.classList.add('is-burnt');
      mascot.classList.add('is-impact');
      setTimeout(() => burned.classList.remove('is-burnt'), 2100);
      setTimeout(() => mascot.classList.remove('is-impact'), 680);
    }
    if (lastLook < 0) return;

    const letter = letters[index];
    letter.animate([
      { transform: 'translateY(0) scale(1, 1) rotate(0deg)' },
      { offset: .2, transform: `translateY(4px) scale(1.11, .82) rotate(${direction * 3}deg)` },
      { offset: .48, transform: `translateY(-5px) scale(.95, 1.1) rotate(${-direction * 2}deg)` },
      { offset: .72, transform: `translateY(1px) scale(1.02, .98) rotate(${direction}deg)` },
      { transform: 'translateY(0) scale(1, 1) rotate(0deg)' }
    ], { duration: 540, easing: 'ease-out' });

    for (const neighborIndex of [index - 1, index + 1]) {
      if (!letters[neighborIndex]) continue;
      letters[neighborIndex].animate([
        { transform: 'translateY(0) rotate(0deg)' },
        { offset: .35, transform: `translateY(2px) rotate(${(neighborIndex - index) * 2}deg)` },
        { offset: .7, transform: 'translateY(-2px) rotate(0deg)' },
        { transform: 'translateY(0) rotate(0deg)' }
      ], { duration: 470, delay: 45, easing: 'ease-out' });
    }
  }

  function frame(now) {
    if (!welcome?.isConnected) {
      // The landing mascot is removed while a conversation is open. Avoid a
      // 60 fps JavaScript loop behind the agent browser and video player.
      setTimeout(() => requestAnimationFrame(frame), 250);
      startTime = now;
      lastLook = -1;
      pauseStarted = 0;
      return;
    }
    requestAnimationFrame(frame);
    if (document.hidden) {
      startTime = now;
      lastLook = -1;
      pauseStarted = 0;
      return;
    }
    if (modeSwitching) {
      if (!pauseStarted) pauseStarted = now;
      return;
    }
    if (pauseStarted) {
      startTime += now - pauseStarted;
      pauseStarted = 0;
    }
    const elapsed = (now - startTime) % cycleMs;
    const segment = Math.floor(elapsed / beatMs);
    const phase = elapsed - segment * beatMs;
    const from = stops[segment];
    const to = stops[segment + 1];
    const direction = Math.sign(to - from);
    let x;
    let y;
    let scaleX;
    let scaleY;
    let rotation;
    let look;

    if (phase < flightMs) {
      const t = phase / flightMs;
      const travel = t * t * (3 - 2 * t);
      const arc = 4 * 39 * t * (1 - t);
      const launch = Math.max(0, 1 - t / .13);
      const approach = Math.max(0, (t - .87) / .13);
      x = positions[from] + (positions[to] - positions[from]) * travel;
      y = landingY - arc;
      scaleX = 1 - .045 * Math.abs(1 - 2 * t) + .17 * launch + .16 * approach;
      scaleY = 1 + .075 * Math.abs(1 - 2 * t) - .22 * launch - .22 * approach;
      rotation = direction * 6 * Math.sin(Math.PI * t);
      look = from;
    } else {
      const settle = (phase - flightMs) / settleMs;
      const spring = Math.exp(-5 * settle) * Math.cos(10 * settle);
      x = positions[to];
      y = landingY + 2 * Math.exp(-6 * settle) * Math.sin(11 * settle);
      scaleX = 1 + .16 * spring;
      scaleY = 1 - .15 * spring;
      rotation = direction * 3 * spring;
      look = to;
    }

    mascot.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0) rotate(${rotation.toFixed(2)}deg) scale(${scaleX.toFixed(3)}, ${scaleY.toFixed(3)})`;
    if (look !== lastLook) {
      impact(look, direction);
      lastLook = look;
    }
  }

  measure();
  new ResizeObserver(measure).observe(showcase);
  document.fonts.ready.then(measure);
  requestAnimationFrame(frame);
}

function finishIntro() {
  if (introFinished) return;
  introFinished = true;
  startMascotPhysics();
  document.body.classList.remove('is-loading');
  intro?.remove();
  if (site) {
    animate(site, { opacity: [0, 1] }, { duration: 0.46, ease: 'easeOut' });
    animate('.sidebar', { opacity: [0, 1] }, { duration: 0.58, ease: 'easeOut' });
    animate('.workspace-header', { opacity: [0, 1], y: [-18, 0] }, { duration: 0.58, ease: 'easeOut' });
    animate('.welcome-showcase, .welcome-kicker, .welcome h1, .welcome > p', { opacity: [0, 1], y: [22, 0], filter: ['blur(8px)', 'blur(0px)'] }, { delay: stagger(0.1), duration: 0.67, ease: 'easeOut' });
    animate('.prompt-grid button', { opacity: [0, 1], y: [18, 0] }, { delay: stagger(0.07, { startDelay: 0.4 }), duration: 0.54, ease: 'easeOut' });
    animate('.composer-area', { opacity: [0, 1], y: [24, 0] }, { duration: 0.73, ease: 'easeOut' });
  }
}

if (intro) {
  introTimeline = animate([
    ['.seed-one', { opacity: [0, 1], scale: [0, 1] }, { duration: 0.44, ease: 'backOut' }],
    ['.seed-two', { opacity: [0, 1], x: [0, -83], y: [0, -31], scale: [0, 1] }, { at: 0.37, duration: 0.52, ease: 'backOut' }],
    ['.seed-three', { opacity: [0, 1], x: [0, 87], y: [0, 36], scale: [0, 1] }, { at: 0.48, duration: 0.52, ease: 'backOut' }],
    ['.intro-seeds', { opacity: [1, 0], scale: [1, 0.4] }, { at: 1.08, duration: 0.22 }],
    ['.intro-letter', { opacity: [0, 1], y: [70, 0], scale: [0.45, 1], rotate: [-18, 0] }, { at: 1.02, delay: stagger(0.07), duration: 0.72, type: 'spring', bounce: 0.47 }],
    ['.intro-eyes', { opacity: [0, 1], scale: [0.2, 1], rotate: [-35, -11] }, { at: 1.52, duration: 0.57, type: 'spring', bounce: 0.55 }],
    ['.intro-pill', { opacity: [0, 1], y: [24, 0], scale: [0.5, 1] }, { at: 1.82, duration: 0.55, type: 'spring', bounce: 0.36 }],
    ['.intro-shape', { opacity: [0, 1], scale: [0.15, 1], rotate: [-22, 0] }, { at: 1.91, delay: stagger(0.055), duration: 0.68, type: 'spring', bounce: 0.53 }],
    ['.intro-caption', { opacity: [0, 1], y: [18, 0] }, { at: 2.47, duration: 0.42, ease: 'easeOut' }],
    ['.intro-core', { opacity: [1, 0], scale: [1, 1.07] }, { at: 4.12, duration: 0.38, ease: 'easeIn' }],
    ['.intro-shape', { opacity: [1, 0], scale: [1, 0.72] }, { at: 4.14, duration: 0.36, ease: 'easeIn' }],
    ['.intro-final-star', { opacity: [0, 1, 0], scale: [0.25, 1.45, 0.25] }, { at: 4.28, duration: 0.65, ease: 'easeInOut' }],
    [intro, { opacity: [1, 0] }, { at: 4.96, duration: 0.32, ease: 'easeOut' }]
  ]);
  introTimeline.finished.then(finishIntro).catch(() => {});
  skip?.addEventListener('click', () => { introTimeline?.cancel(); finishIntro(); });
} else {
  finishIntro();
}
