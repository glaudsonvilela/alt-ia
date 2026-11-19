import { animate, stagger } from 'motion';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';

const intro = document.querySelector('#intro');
const site = document.querySelector('.site');
const skip = document.querySelector('.intro-skip');
const chatForm = document.querySelector('#chat-form');
const chatInput = document.querySelector('#chat-input');
const chatMessages = document.querySelector('#chat-messages');
const welcome = document.querySelector('#welcome');
const historyNav = document.querySelector('#conversation-history');
const newChatButton = document.querySelector('#new-chat');
const sidebar = document.querySelector('#sidebar');
const sidebarOverlay = document.querySelector('#sidebar-overlay');
const mobileMenu = document.querySelector('#mobile-menu');
const sidebarClose = document.querySelector('#sidebar-close');
const poolDialog = document.querySelector('#pool-dialog');
const lendingDialog = document.querySelector('#lending-dialog');
const lendingForm = document.querySelector('#lending-config-form');
const lendingCollateral = document.querySelector('#lending-collateral');
const lendingDebt = document.querySelector('#lending-debt');
const lendingDrop = document.querySelector('#lending-drop');
const lendingDropValue = document.querySelector('#lending-drop-value');
const lendingFormError = document.querySelector('#lending-form-error');
const poolDialogClose = document.querySelector('#pool-dialog-close');
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
const storageKey = 'alt-ia-conversations-v1';
const activeKey = 'alt-ia-active-v1';
let poolOptions = null;
let pendingSimulationRequest = null;
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
  if (!value || value.kind !== 'lending' || typeof value.collateral_weth !== 'string' || typeof value.borrow_usdc !== 'string'
      || !/^\d+(?:[.,]\d{1,8})?$/.test(value.collateral_weth) || !/^\d+(?:[.,]\d{1,6})?$/.test(value.borrow_usdc)
      || !Number.isSafeInteger(value.price_drop_pct) || value.price_drop_pct < 0 || value.price_drop_pct > 90) return null;
  return { kind: 'lending', collateral_weth: value.collateral_weth, borrow_usdc: value.borrow_usdc, price_drop_pct: value.price_drop_pct };
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
  const scenarios = scenario && typeof scenario.unit === 'string' && typeof scenario.base_symbol === 'string' && Array.isArray(scenario.rows)
    ? { unit: clean(scenario.unit, 12), base_symbol: clean(scenario.base_symbol, 12), caption: clean(scenario.caption, 120), note: clean(scenario.note, 280),
        headers: Array.isArray(scenario.headers) && scenario.headers.length === 4 && scenario.headers.every((item) => typeof item === 'string')
          ? scenario.headers.map((item) => clean(item, 40)) : null,
        rows: scenario.rows.slice(0, 7).filter((row) => row && ['gain', 'loss', 'flat'].includes(row.tone)
          && ['label', 'price', 'value', 'pnl'].every((key) => typeof row[key] === 'string'))
          .map((row) => ({ label: clean(row.label, 30), price: clean(row.price, 30), value: clean(row.value, 30), pnl: clean(row.pnl, 30), tone: row.tone })) }
    : null;
  return {
    kind: value.kind, title: clean(value.title), subtitle: clean(value.subtitle), metrics, scenarios,
    source: { engine: isHistorical ? 'Alt-IA · dados Altside' : clean(value.source.engine, 60), kind: isHistorical ? 'historical_candles' : 'live', block_number: isHistorical ? null : value.source.block_number,
      source_label: value.source.source_label === 'Slot' ? 'Slot' : 'Bloco',
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
        updatedAt: Number(item.updatedAt) || Date.now(),
        messages: item.messages.filter((message) => message && (message.role === 'user' || message.role === 'ai') && typeof message.text === 'string').slice(-100)
          .map((message) => ({ role: message.role, text: message.text, simulation: message.role === 'ai' ? safeSimulation(message.simulation) : null,
            news: message.role === 'ai' && !message.text.startsWith('🗞️ Aqui está um resumo das notícias que mostrei:') ? safeNews(message.news) : [],
            newsContext: message.role === 'ai' ? safeNews(message.newsContext || message.news) : [],
            mode: message.role === 'ai' && ['news', 'pool', 'historical_pool', 'lending', 'general'].includes(message.mode) ? message.mode : '',
            newsTopic: message.role === 'ai' && typeof message.newsTopic === 'string' ? message.newsTopic.slice(0, 30) : '',
            poolRequest: message.role === 'ai' ? safePoolRequest(message.poolRequest) : null,
            lendingRequest: message.role === 'ai' ? safeLendingRequest(message.lendingRequest) : null,
            scenarioToken: message.role === 'ai' && typeof message.scenarioToken === 'string' ? message.scenarioToken.slice(0, 12000) : '',
            followUp: message.role === 'ai' && typeof message.followUp === 'string' ? message.followUp.slice(0, 280) : '' }))
      }));
  } catch {
    return [];
  }
}

const conversations = readConversations();
let activeId = localStorage.getItem(activeKey);
if (!conversations.some((item) => item.id === activeId)) {
  activeId = conversations.sort((a, b) => b.updatedAt - a.updatedAt)[0]?.id || null;
}

function persist() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(conversations));
    if (activeId) localStorage.setItem(activeKey, activeId);
    else localStorage.removeItem(activeKey);
  } catch {
    const notice = document.querySelector('.sidebar-bottom small');
    if (notice) notice.textContent = 'O histórico não pôde ser salvo neste navegador.';
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

function createHistoryLogo() {
  const icon = document.createElement('span');
  icon.className = 'history-item-icon history-logo';
  icon.setAttribute('aria-hidden', 'true');
  icon.innerHTML = historyLogoSvg;
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
    const icon = createHistoryLogo();
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
  block.textContent = simulation.source.kind === 'historical_candles'
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
  card.append(provenance, notes, link);
  return card;
}

function createMessage(role, text, simulation = null, followUp = '', news = []) {
  const row = document.createElement('article');
  row.className = `message-row message-${role}`;
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
  const paragraph = document.createElement('p');
  paragraph.textContent = text;
  body.append(paragraph);
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
  chatMessages.replaceChildren();
  const conversation = conversations.find((item) => item.id === activeId);
  if (!conversation || !conversation.messages.length) {
    if (welcome) chatMessages.append(welcome);
  } else {
    const fragment = document.createDocumentFragment();
  conversation.messages.forEach((message) => fragment.append(createMessage(message.role, message.text, message.simulation, message.followUp, message.news)));
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
  persist();
  renderHistory();
  renderConversation();
  closeSidebar();
  chatInput?.focus();
});

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

function openLendingDialog(prefill = {}) {
  if (!lendingDialog) return;
  lendingFormError.hidden = true;
  lendingFormError.textContent = '';
  lendingCollateral.value = typeof prefill.collateral_weth === 'string' ? prefill.collateral_weth : '';
  lendingDebt.value = typeof prefill.borrow_usdc === 'string' ? prefill.borrow_usdc : '';
  lendingDrop.value = Number.isInteger(prefill.price_drop_pct) && prefill.price_drop_pct <= 80 ? String(prefill.price_drop_pct) : '20';
  lendingDropValue.value = `${lendingDrop.value}%`;
  if (!lendingDialog.open) lendingDialog.showModal();
  (lendingCollateral.value ? lendingDebt : lendingCollateral).focus();
}

document.querySelector('[data-action="configure-lending"]')?.addEventListener('click', () => openLendingDialog());
document.querySelector('#lending-dialog-close')?.addEventListener('click', () => lendingDialog?.close());
lendingDialog?.addEventListener('click', (event) => { if (event.target === lendingDialog) lendingDialog.close(); });
lendingDrop?.addEventListener('input', () => { lendingDropValue.value = `${lendingDrop.value}%`; });

lendingForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  if (isSubmitting) return;
  const collateral = lendingCollateral.value.trim().replace(',', '.');
  const debt = lendingDebt.value.trim().replace(',', '.');
  if (!/^\d+(?:\.\d{1,8})?$/.test(collateral) || Number(collateral) <= 0 || Number(collateral) > 1_000_000
      || !/^\d+(?:\.\d{1,6})?$/.test(debt) || Number(debt) <= 0 || Number(debt) > 10_000_000_000) {
    lendingFormError.textContent = 'Informe valores positivos para WETH e USDC.';
    lendingFormError.hidden = false;
    return;
  }
  pendingSimulationRequest = { kind: 'lending', collateral_weth: collateral, borrow_usdc: debt, price_drop_pct: Number(lendingDrop.value) };
  chatInput.value = `Simule lending: ${collateral} WETH de garantia, ${debt} USDC emprestados, queda de ${lendingDrop.value}% no WETH`;
  resizeComposer();
  lendingDialog.close();
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
document.querySelector('[data-action="historical-pool"]')?.addEventListener('click', () => openPoolDialog({ kind: 'historical_pool' }));
poolDialogClose?.addEventListener('click', () => poolDialog?.close());
poolDialog?.addEventListener('click', (event) => { if (event.target === poolDialog) poolDialog.close(); });
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
  poolDialog.close();
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
  let conversation = conversations.find((item) => item.id === activeId);
  if (!conversation) {
    conversation = { id: crypto.randomUUID(), title: titleFrom(text), pinned: false, updatedAt: Date.now(), messages: [] };
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
  isSubmitting = true;
  chatForm.querySelector('button[type="submit"]').disabled = true;
  chatMessages.setAttribute('aria-busy', 'true');
  if (isFirstMessage) await revealFirstMessage(conversationId);
  else renderConversation();
  const pending = createMessage('ai', /\b(news|not[ií]cias?|manchetes)\b/i.test(text) ? 'Buscando notícias…' : 'Pensando…');
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
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: context, chat_context: {
        mode: previousMode, news_topic: previousAnswer?.newsTopic || '', news: previousMode === 'news' ? previousAnswer?.newsContext || previousAnswer?.news || [] : [],
        pool_request: previousMode === 'pool' || previousMode === 'historical_pool' ? previousAnswer?.poolRequest || null : null,
        lending_request: previousMode === 'lending' ? previousAnswer?.lendingRequest || null : null
      }, ...(simulationRequest ? { simulation_request: simulationRequest } : {}),
        ...(previousPool?.scenarioToken ? { scenario_token: previousPool.scenarioToken } : {}),
        ...(previousPool?.simulation ? { scenario_context: {
          kind: previousPool.simulation.kind, title: previousPool.simulation.title, subtitle: previousPool.simulation.subtitle,
          metrics: previousPool.simulation.metrics, assumptions: previousPool.simulation.assumptions
        } } : {}) })
    });
    const data = await response.json();
    if (!response.ok || typeof data.reply !== 'string') throw new Error(data.error || 'Não foi possível obter uma resposta. Tente novamente.');
    const target = conversations.find((item) => item.id === conversationId);
    if (!target) return;
    target.messages.push({ role: 'ai', text: data.reply, simulation: safeSimulation(data.simulation), news: safeNews(data.news),
      newsContext: safeNews(data.news_context || data.news),
      mode: ['news', 'pool', 'historical_pool', 'lending', 'general'].includes(data.mode) ? data.mode : 'general',
      newsTopic: typeof data.news_topic === 'string' ? data.news_topic.slice(0, 30) : '',
      poolRequest: safePoolRequest(data.pool_request),
      lendingRequest: safeLendingRequest(data.lending_request),
      scenarioToken: typeof data.scenario_token === 'string' ? data.scenario_token.slice(0, 12000) : '',
      followUp: typeof data.follow_up === 'string' ? data.follow_up.slice(0, 280) : '' });
    target.updatedAt = Date.now();
    persist();
    renderHistory();
    if (activeId === conversationId) renderConversation();
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
  document.querySelectorAll('.eye-pod').forEach((face) => {
    const rect = face.getBoundingClientRect();
    const x = Math.max(-3, Math.min(3, (pointerX - rect.left - rect.width / 2) / 80));
    const y = Math.max(-2, Math.min(2, (pointerY - rect.top - rect.height / 2) / 100));
    face.querySelectorAll('.pupil').forEach((pupil) => { pupil.style.transform = `translate(${x}px, ${y}px)`; });
  });
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

  const looks = [
    ['#ad73d8', '40% 44% 42% 46%'],
    ['#ff9568', '53% 39% 48% 43% / 46% 52% 43% 55%'],
    ['#77a4ef', '32% 41% 35% 40% / 42% 35% 43% 37%'],
    ['#b08be0', '49% 45% 50% 42% / 41% 54% 43% 52%'],
    ['#65cda5', '43% 52% 46% 51% / 52% 42% 55% 43%'],
    ['#ee91b9', '52% 44% 49% 46% / 44% 53% 42% 55%']
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

  function measure() {
    const wordmarkLeft = (showcase.clientWidth - wordmark.offsetWidth) / 2;
    const mascotCenter = mascot.offsetLeft + mascot.offsetWidth / 2;
    positions = letters.map((letter) => wordmarkLeft + letter.offsetLeft + letter.offsetWidth / 2 - mascotCenter);
    landingY = wordmark.offsetTop - mascot.offsetTop - mascot.offsetHeight + 4;
  }

  function impact(index, direction) {
    const [color, radius] = looks[index % looks.length];
    mascot.style.backgroundColor = color;
    mascot.style.borderRadius = radius;
    letters.forEach((letter, letterIndex) => letter.classList.toggle('is-lit', letterIndex === index));
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
    requestAnimationFrame(frame);
    if (!welcome?.isConnected || document.hidden) {
      startTime = now;
      lastLook = -1;
      return;
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
