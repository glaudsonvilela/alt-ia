const pendingKey = 'alt-ia-pending-action';

function loadChat() {
  const script = document.createElement('script');
  script.src = '/app.js?v=88';
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
  login.src = '/login.js?v=4';
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
  document.querySelector('#panel-name').textContent = name;
  document.querySelector('#panel-email').textContent = email;
  const close = () => {
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
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
      }
      document.querySelector('#account-usage-note').textContent = 'Uso registrado nas respostas do modelo desde a ativação desta versão.';
    } catch {
      document.querySelector('#account-usage-note').textContent = 'Não foi possível atualizar o consumo agora.';
    }
  };
  trigger.addEventListener('click', () => {
    if (!panel.hidden) return close();
    panel.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    refresh();
  });
  document.querySelector('#account-panel-close').addEventListener('click', close);
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
    if (!response.ok) return;
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
    const note = document.querySelector('.sidebar-bottom small');
    if (note) note.textContent = 'Histórico sincronizado com sua conta.';
  } catch { /* Use the local cache while the server is unavailable. */ }
}

(async () => {
  let profile = null;
  try {
    const response = await fetch('/api/me', { credentials: 'same-origin', cache: 'no-store' });
    if (response.ok) profile = await response.json();
  } catch { /* The login dialog handles an unavailable server. */ }
  const email = profile?.email;
  if (typeof email === 'string' && email.includes('@')) {
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email.toLowerCase()));
    window.altIaStorageNamespace = Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join('');
    window.altIaAuthenticated = true;
    await loadAccountHistory(window.altIaStorageNamespace);
    const name = typeof profile.name === 'string' && profile.name.trim() ? profile.name.trim() : email.split('@')[0];
    document.querySelector('#account-name').textContent = name;
    document.querySelector('#account-email').textContent = email;
    document.querySelector('#account-initials').textContent = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('pt-BR');
    document.querySelector('#account-state').removeAttribute('hidden');
    installAccountPanel(name, email);
    if (typeof profile.picture === 'string' && profile.picture.startsWith('https://lh3.googleusercontent.com/')) {
      const image = document.querySelector('#account-picture');
      image.onload = () => {
        image.removeAttribute('hidden');
        document.querySelector('#account-initials').hidden = true;
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
