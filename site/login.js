const googleStep = document.querySelector('#google-step');
const codeStep = document.querySelector('#code-step');
const message = document.querySelector('#login-message');
const codeInput = document.querySelector('#code');

function showMessage(value) { message.textContent = value; }

async function post(path, body) {
  const response = await fetch(path, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível entrar.');
  return result;
}

async function onGoogle(result) {
  showMessage('Enviando o código...');
  try {
    const { email } = await post('/api/auth/google', { credential: result.credential });
    document.querySelector('#email-label').textContent = email;
    googleStep.hidden = true;
    codeStep.hidden = false;
    codeInput.focus();
    showMessage('');
  } catch (error) { showMessage(error.message); }
}

let verifiedEmail = null;

async function confirmSession(email) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      const response = await fetch('/api/me', { credentials: 'same-origin', cache: 'no-store' });
      if (response.ok) {
        const profile = await response.json();
        if (profile.email?.toLowerCase() === email.toLowerCase()) return;
      }
    } catch { /* A conexão pode ser interrompida durante a criação da sessão. */ }
    if (attempt < 7) await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
  }
  throw new Error('O código foi aceito, mas a sessão ainda não foi confirmada. Tente continuar novamente.');
}

codeStep.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = codeStep.querySelector('button');
  button.disabled = true;
  showMessage('');
  try {
    if (!verifiedEmail) {
      const result = await post('/api/auth/verify', { code: codeInput.value.trim() });
      verifiedEmail = result.email;
    }
    showMessage('Confirmando sua sessão...');
    await confirmSession(verifiedEmail);
    sessionStorage.setItem('alt-ia-auth-just-verified', String(Date.now()));
    window.location.replace('/');
  } catch (error) {
    showMessage(error.message);
    button.disabled = false;
    if (verifiedEmail) button.textContent = 'Tentar continuar';
    else codeInput.select();
  }
});

async function setup() {
  const session = await fetch('/api/me', {credentials: 'same-origin', cache: 'no-store'});
  if (session.ok) { window.location.replace('/'); return; }
  const config = await fetch('/api/auth/config', {cache: 'no-store'});
  if (!config.ok) throw new Error('Acesso ainda não configurado no servidor.');
  const { google_client_id: clientId } = await config.json();
  for (let tries = 0; !window.google?.accounts?.id && tries < 100; tries += 1) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  if (!window.google?.accounts?.id) throw new Error('Não foi possível carregar o login Google.');
  google.accounts.id.initialize({client_id: clientId, callback: onGoogle, hd: 'altside.com'});
  const button = document.querySelector('#google-button');
  const revealButton = () => {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      button.classList.add('is-ready');
      button.setAttribute('aria-busy', 'false');
      showMessage('');
    }));
  };
  const observer = new MutationObserver(() => {
    const frame = button.querySelector('iframe');
    if (!frame) return;
    observer.disconnect();
    frame.addEventListener('load', revealButton, { once: true });
  });
  observer.observe(button, { childList: true, subtree: true });
  google.accounts.id.renderButton(button, {
    theme: 'outline', size: 'large', shape: 'pill', text: 'signin_with', width: Math.floor(button.clientWidth),
  });
  window.setTimeout(() => {
    if (!button.classList.contains('is-ready')) showMessage('O botão Google demorou para carregar. Verifique a conexão e tente atualizar a página.');
  }, 10000);
}
setup().catch((error) => showMessage(error.message));
