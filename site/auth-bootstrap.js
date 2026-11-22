const pendingKey = 'alt-ia-pending-action';

function loadChat() {
  const script = document.createElement('script');
  script.src = '/app.js?v=87';
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
  login.src = '/login.js?v=3';
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

(async () => {
  let email = '';
  try {
    const response = await fetch('/api/me', { credentials: 'same-origin', cache: 'no-store' });
    if (response.ok) ({ email } = await response.json());
  } catch { /* The login dialog handles an unavailable server. */ }
  if (typeof email === 'string' && email.includes('@')) {
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email.toLowerCase()));
    window.altIaStorageNamespace = Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join('');
    window.altIaAuthenticated = true;
    document.querySelector('#logout-link')?.removeAttribute('hidden');
    document.querySelector('#logout-link')?.addEventListener('click', async (event) => {
      event.preventDefault();
      try { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }); }
      finally { window.location.replace('/'); }
    });
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
