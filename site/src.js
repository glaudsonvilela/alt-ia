import { animate, stagger } from 'motion';

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
const storageKey = 'alt-ia-conversations-v1';
const activeKey = 'alt-ia-active-v1';

function safeSimulation(value) {
  if (!value || !['swap', 'pool'].includes(value.kind) || !Array.isArray(value.metrics) || !value.source) return null;
  const clean = (v, max = 160) => typeof v === 'string' ? v.slice(0, max) : '';
  const metrics = value.metrics.slice(0, 6).filter((item) => item && typeof item.label === 'string' && typeof item.value === 'string')
    .map((item) => ({ label: clean(item.label, 60), value: clean(item.value, 80) }));
  if (!metrics.length || !Number.isSafeInteger(value.source.block_number) || value.source.block_number <= 0) return null;
  return {
    kind: value.kind, title: clean(value.title), subtitle: clean(value.subtitle), metrics,
    source: { engine: 'Altside · Rust', block_number: value.source.block_number,
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
          .map((message) => ({ role: message.role, text: message.text, simulation: message.role === 'ai' ? safeSimulation(message.simulation) : null }))
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
  card.setAttribute('aria-label', 'Prévia calculada pelo Altside');
  const eyebrow = document.createElement('span');
  eyebrow.className = 'simulation-eyebrow';
  eyebrow.textContent = 'PRÉVIA · MOTOR ALTSIDE';
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
  const provenance = document.createElement('div');
  provenance.className = 'simulation-provenance';
  const block = document.createElement('span');
  block.textContent = `Bloco #${simulation.source.block_number.toLocaleString('pt-BR')}`;
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
  card.append(eyebrow, title, subtitle, grid, provenance, notes, link);
  return card;
}

function createMessage(role, text, simulation = null) {
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
  if (role === 'ai' && simulation) body.append(createSimulationCard(simulation));
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
    conversation.messages.forEach((message) => fragment.append(createMessage(message.role, message.text, message.simulation)));
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
  let conversation = conversations.find((item) => item.id === activeId);
  if (!conversation) {
    conversation = { id: crypto.randomUUID(), title: titleFrom(text), pinned: false, updatedAt: Date.now(), messages: [] };
    conversations.push(conversation);
    activeId = conversation.id;
  }
  const isFirstMessage = conversation.messages.length === 0;
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
  const pending = createMessage('ai', 'Pensando…');
  pending.classList.add('message-pending');
  if (activeId === conversationId) {
    chatMessages.append(pending);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  try {
    const context = [];
    for (const message of conversation.messages.slice(-20)) {
      if (message.role === 'ai' && message.text.startsWith('Recebi sua mensagem. A API da Alt-IA ainda')) continue;
      const role = message.role === 'ai' ? 'assistant' : 'user';
      if (context.at(-1)?.role === role) context.at(-1).content += `\n\n${message.text}`;
      else context.push({ role, content: message.text });
    }
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: context })
    });
    const data = await response.json();
    if (!response.ok || typeof data.reply !== 'string') throw new Error(data.error || 'Não foi possível obter uma resposta. Tente novamente.');
    const target = conversations.find((item) => item.id === conversationId);
    if (!target) return;
    target.messages.push({ role: 'ai', text: data.reply, simulation: safeSimulation(data.simulation) });
    target.updatedAt = Date.now();
    persist();
    renderHistory();
    if (activeId === conversationId) renderConversation();
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
