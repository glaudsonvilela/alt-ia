const pendingKey = 'alt-ia-pending-action';

function loadChat() {
  const script = document.createElement('script');
  script.src = '/app.js?v=89';
  script.onload = () => {
    if (!window.altIaAuthenticated) return;
    let pending;
    try { pending = JSON.parse(sessionStorage.getItem(pendingKey) || 'null'); }
    catch { pending = null; }
    sessionStorage.removeItem(pendingKey);
    if (!pending || typeof pending !== 'object') return;
    document.querySelector('.intro-skip')?.click();
    if (pending.kind === 'message' && typeof pending.value === 'string') {
      const input = document.querySelector('#chat-input');
      input.value = pending.value.slice(0, 4000);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('#chat-form')?.requestSubmit();
    } else if (pending.kind === 'shortcut' && typeof pending.value === 'string') {
      const button = [...document.querySelectorAll('[data-action], [data-nerd-topic], [data-agent-site]')]
        .find((item) => item.dataset.action === pending.value || item.dataset.nerdTopic === pending.value || item.dataset.agentSite === pending.value);
      button?.click();
    }
  };
  document.head.append(script);
}

function openLogin(pending) {
  sessionStorage.setItem(pendingKey, JSON.stringify(pending));
  const dialog = document.querySelector('#auth-dialog');
  if (!dialog.open) dialog.showModal();
  if (dialog.dataset.loaded) return;
  dialog.dataset.loaded = 'true';
  const google = document.createElement('script');
  google.src = 'https://accounts.google.com/gsi/client';
  google.async = true;
  document.head.append(google);
  const login = document.createElement('script');
  login.src = '/login.js?v=7';
  document.head.append(login);
}

function installGuestGate() {
  document.body.classList.add('guest-session');
  const dialog = document.querySelector('#auth-dialog');
  dialog.querySelector('.auth-dialog-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => sessionStorage.removeItem(pendingKey));
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action], [data-nerd-topic], [data-agent-site]');
    if (!button || dialog.contains(button)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openLogin({ kind: 'shortcut', value: button.dataset.action || button.dataset.nerdTopic || button.dataset.agentSite });
  }, true);
  document.querySelector('#chat-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    const value = document.querySelector('#chat-input')?.value.trim();
    if (value) openLogin({ kind: 'message', value });
  }, true);
}

function installAccountPanel(name, email) {
  const trigger = document.querySelector('#account-state');
  const panel = document.querySelector('#account-panel');
  const roleInput = document.querySelector('#account-role');
  const roleStatus = document.querySelector('#account-role-status');
  const format = (value) => new Intl.NumberFormat('pt-BR').format(value);
  let closeTimer;
  document.querySelector('#panel-name').textContent = name;
  document.querySelector('#panel-email').textContent = email;
  document.querySelector('#panel-initials').textContent = document.querySelector('#account-initials').textContent;
  const burst = (rect) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'shortcut-dialog-burst';
    wrapper.setAttribute('aria-hidden', 'true');
    Object.assign(wrapper.style, { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px` });
    for (let index = 0; index < 8; index += 1) {
      const side = index < 4 ? -1 : 1;
      const row = index % 4;
      const piece = document.createElement('i');
      piece.className = `shortcut-dialog-piece shortcut-dialog-piece-${index % 6}`;
      piece.style.left = `${side < 0 ? 0 : rect.width}px`;
      piece.style.top = `${Math.round(rect.height * [0.18, 0.39, 0.61, 0.82][row])}px`;
      piece.style.setProperty('--dx', `${side * (48 + (row % 2) * 16)}px`);
      piece.style.setProperty('--dy', `${Math.round((row - 1.5) * 12)}px`);
      piece.style.setProperty('--spin', `${side * (65 + row * 15)}deg`);
      piece.style.animationDelay = `${row * 20}ms`;
      wrapper.append(piece);
    }
    document.body.append(wrapper);
    window.setTimeout(() => wrapper.remove(), 650);
  };
  const close = () => {
    if (panel.hidden || panel.classList.contains('is-closing')) return;
    trigger.setAttribute('aria-expanded', 'false');
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      panel.hidden = true;
      return;
    }
    const rect = panel.getBoundingClientRect();
    panel.classList.add('is-closing');
    closeTimer = window.setTimeout(() => {
      panel.hidden = true;
      panel.classList.remove('is-closing');
      burst(rect);
      closeTimer = undefined;
    }, 260);
  };
  const refresh = async () => {
    try {
      const response = await fetch('/api/account', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error('Dados indisponíveis');
      const data = await response.json();
      if (document.activeElement !== roleInput) roleInput.value = data.role || '';
      if (data.usage && Number.isSafeInteger(data.usage.total_tokens)) {
        document.querySelector('#account-tokens').textContent = format(data.usage.total_tokens);
        document.querySelector('#account-prompt-tokens').textContent = format(data.usage.prompt_tokens);
        document.querySelector('#account-completion-tokens').textContent = format(data.usage.completion_tokens);
        document.querySelector('#account-usage-prompt-bar').style.width = `${data.usage.total_tokens ? Math.max(0, Math.min(100, data.usage.prompt_tokens / data.usage.total_tokens * 100)) : 50}%`;
      }
      document.querySelector('#account-usage-note').textContent = 'Uso registrado nas respostas do modelo desde a ativação desta versão.';
    } catch {
      document.querySelector('#account-usage-note').textContent = 'Não foi possível atualizar o consumo agora.';
    }
  };
  trigger.addEventListener('click', () => {
    if (!panel.hidden && !panel.classList.contains('is-closing')) return close();
    window.clearTimeout(closeTimer);
    panel.classList.remove('is-closing');
    panel.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    refresh();
  });
  document.querySelector('#account-panel-close').addEventListener('click', () => { close(); trigger.focus(); });
  document.addEventListener('click', (event) => {
    if (!panel.hidden && !panel.contains(event.target) && !trigger.contains(event.target)) close();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) { close(); trigger.focus(); }
  });
  document.querySelector('#account-role-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector('button');
    button.disabled = true;
    roleStatus.textContent = 'Salvando…';
    try {
      const response = await fetch('/api/account/role', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: roleInput.value }),
      });
      if (!response.ok) throw new Error('Falha ao salvar');
      const data = await response.json();
      roleInput.value = data.role;
      roleStatus.textContent = 'Função salva na sua conta.';
    } catch { roleStatus.textContent = 'Não foi possível salvar. Tente novamente.'; }
    finally { button.disabled = false; }
  });
  document.querySelector('#logout-link').addEventListener('click', async () => {
    try { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }); }
    finally { window.location.replace('/'); }
  });
}

async function loadAccountHistory(namespace) {
  const note = document.querySelector('#history-status');
  const storageKey = `alt-ia-conversations-v2:${namespace}`;
  const deletedKey = `alt-ia-deleted-v2:${namespace}`;
  let local = [];
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (Array.isArray(stored)) local = stored;
  } catch { /* A damaged local cache must not block login. */ }
  try {
    const response = await fetch('/api/history', {
      credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) throw new Error('Histórico indisponível');
    const remote = await response.json();
    const byId = new Map();
    for (const item of Array.isArray(remote.conversations) ? remote.conversations : []) {
      if (item && typeof item.id === 'string') byId.set(item.id, item);
    }
    const deleted = new Map((Array.isArray(remote.deleted) ? remote.deleted : [])
      .filter((item) => item && typeof item.id === 'string').map((item) => [item.id, Number(item.updatedAt) || 0]));
    try {
      const localDeleted = JSON.parse(localStorage.getItem(deletedKey) || '[]');
      if (Array.isArray(localDeleted)) {
        for (const item of localDeleted) {
          if (item && typeof item.id === 'string') deleted.set(item.id, Math.max(deleted.get(item.id) || 0, Number(item.updatedAt) || 0));
        }
      }
    } catch { /* Ignore damaged deletion markers. */ }
    for (const item of local) {
      if (!item || typeof item.id !== 'string') continue;
      const timestamp = Number(item.updatedAt) || 0;
      if (timestamp <= (deleted.get(item.id) || 0)) continue;
      if (!byId.has(item.id) || timestamp > (Number(byId.get(item.id).updatedAt) || 0)) byId.set(item.id, item);
    }
    for (const [id, timestamp] of deleted) {
      if ((Number(byId.get(id)?.updatedAt) || 0) <= timestamp) byId.delete(id);
    }
    localStorage.setItem(storageKey, JSON.stringify([...byId.values()]));
    if (note) { note.textContent = 'Histórico sincronizado com sua conta.'; note.hidden = false; }
  } catch {
    if (note) { note.textContent = 'Sincronização temporariamente indisponível.'; note.hidden = false; }
  }
}

(async () => {
  let profile = null;
  const verifiedAt = Number(sessionStorage.getItem('alt-ia-auth-just-verified'));
  const justVerified = verifiedAt > 0 && Date.now() - verifiedAt < 30000;
  const attempts = justVerified ? 10 : 3;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch('/api/me', { credentials: 'same-origin', cache: 'no-store' });
      if (response.ok) {
        const candidate = await response.json();
        if (typeof candidate?.email === 'string' && candidate.email.includes('@')) {
          profile = candidate;
          break;
        }
      }
    } catch { /* A short retry handles a connection interrupted during the login redirect. */ }
    if (attempt < attempts - 1) await new Promise((resolve) => setTimeout(resolve, Math.min(250 * (attempt + 1), 1000)));
  }
  const email = profile?.email;
  if (typeof email === 'string' && email.includes('@')) {
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email.toLowerCase()));
    window.altIaStorageNamespace = Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join('');
    window.altIaAuthenticated = true;
    sessionStorage.removeItem('alt-ia-auth-just-verified');
    await loadAccountHistory(window.altIaStorageNamespace);
    const name = typeof profile.name === 'string' && profile.name.trim() ? profile.name.trim() : email.split('@')[0];
    document.querySelector('#account-name').textContent = name;
    document.querySelector('#account-email').textContent = email;
    document.querySelector('#account-initials').textContent = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('pt-BR');
    document.querySelector('#account-state').removeAttribute('hidden');
    installAccountPanel(name, email);
    if (typeof profile.picture === 'string' && profile.picture.startsWith('https://lh3.googleusercontent.com/')) {
      const image = document.querySelector('#account-picture');
      const panelImage = document.querySelector('#panel-picture');
      image.onload = () => {
        image.removeAttribute('hidden');
        panelImage.src = image.src;
        panelImage.removeAttribute('hidden');
        document.querySelector('#account-initials').hidden = true;
        document.querySelector('#panel-initials').hidden = true;
      };
      image.src = profile.picture;
    }
  } else {
    window.altIaStorageNamespace = 'guest';
    window.altIaAuthenticated = false;
    installGuestGate();
  }
  loadChat();
})().catch(() => {
  document.querySelector('#intro')?.remove();
  document.body.classList.remove('is-loading');
  const message = document.createElement('main');
  message.className = 'auth-error';
  message.textContent = 'Não foi possível abrir a Alt-IA. Recarregue a página.';
  document.body.append(message);
});
