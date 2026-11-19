const channel = new BroadcastChannel('alt-ia-agent-companion');
const preview = document.querySelector('#preview');
const placeholder = document.querySelector('#placeholder');
const status = document.querySelector('#status');
const speech = document.querySelector('#speech');
const form = document.querySelector('#form');
const taskInput = document.querySelector('#task');
const send = form.querySelector('button');
let pendingId = null;
let showingVideo = false;

channel.addEventListener('message', ({ data }) => {
  if (data?.type !== 'reply' || data.id !== pendingId) return;
  pendingId = null;
  taskInput.disabled = false;
  send.disabled = false;
  speech.textContent = data.reply || 'Não consegui concluir. Tente novamente.';
  status.textContent = 'Pronto para continuar';
  if (data.video?.provider === 'youtube') {
    showingVideo = true;
    preview.hidden = true;
    placeholder.hidden = false;
    placeholder.textContent = `▶ ${data.video.title || 'Vídeo aberto na Alt-IA'}`;
  } else showingVideo = false;
});

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const task = taskInput.value.trim();
  if (!task || pendingId) return;
  pendingId = crypto.randomUUID();
  taskInput.value = '';
  taskInput.disabled = true;
  send.disabled = true;
  showingVideo = false;
  status.textContent = 'Navegando…';
  speech.textContent = 'Estou explorando o que você pediu… 🔎';
  channel.postMessage({ type: 'task', id: pendingId, task });
});

async function refresh() {
  try {
    const response = await fetch('/api/agent/state', { cache: 'no-store' });
    if (!response.ok) throw Error('Sessão encerrada');
    const state = await response.json();
    if (!pendingId) status.textContent = state.running ? 'Navegando…' : 'Pronto para continuar';
    if (!showingVideo && state.url && state.url !== 'about:blank') {
      preview.hidden = false;
      placeholder.hidden = true;
      preview.src = `/api/agent/image?t=${Date.now()}`;
      preview.alt = state.title || 'Prévia do navegador do agente';
    }
  } catch { status.textContent = 'Sessão encerrada'; }
}
void refresh();
setInterval(refresh, 9000);
