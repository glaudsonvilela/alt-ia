const channel = new BroadcastChannel('alt-ia-agent-companion');
const preview = document.querySelector('#preview');
const videoFrame = document.querySelector('#video');
const placeholder = document.querySelector('#placeholder');
const status = document.querySelector('#status');
const speech = document.querySelector('#speech');
const form = document.querySelector('#form');
const taskInput = document.querySelector('#task');
const send = form.querySelector('button');
let pendingId = null;
let showingVideo = false;
let lastShotKey = '';
let lastPollAt = 0;
let wasRunning = false;
let currentVideoKey = '';

function showVideo(value) {
  const playlist = value?.kind === 'playlist';
  const id = typeof value?.id === 'string' ? value.id : '';
  const valid = value?.provider === 'youtube' && (playlist ? /^[A-Za-z0-9_-]{10,80}$/.test(id) : /^[A-Za-z0-9_-]{11}$/.test(id));
  if (!valid) {
    showingVideo = false;
    currentVideoKey = '';
    videoFrame.removeAttribute('src');
    videoFrame.hidden = true;
    void refresh(true);
    return;
  }
  const videoKey = `${playlist ? 'playlist' : 'video'}:${id}`;
  if (currentVideoKey === videoKey) return;
  currentVideoKey = videoKey;
  showingVideo = true;
  preview.hidden = true;
  placeholder.hidden = true;
  videoFrame.hidden = false;
  videoFrame.src = playlist
    ? `https://www.youtube-nocookie.com/embed/videoseries?list=${id}&autoplay=1&playsinline=1&mute=1`
    : `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&playsinline=1&rel=0&mute=1`;
  videoFrame.title = value.title || 'Vídeo do YouTube';
}

channel.addEventListener('message', ({ data }) => {
  if (data?.type === 'media') { showVideo(data.video); return; }
  if (data?.type !== 'reply' || data.id !== pendingId) return;
  pendingId = null;
  taskInput.disabled = false;
  send.disabled = false;
  speech.textContent = data.reply || 'Não consegui concluir. Tente novamente.';
  status.textContent = 'Pronto para continuar';
  showVideo(data.video);
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
  showVideo(null);
  status.textContent = 'Navegando…';
  speech.textContent = 'Estou explorando o que você pediu… 🔎';
  channel.postMessage({ type: 'task', id: pendingId, task });
});

async function refresh(force = false) {
  const now = Date.now();
  if (!force && now - lastPollAt < (showingVideo ? 30000 : wasRunning ? 5000 : 20000)) return;
  lastPollAt = now;
  try {
    const response = await fetch('/api/agent/state', { cache: 'no-store' });
    if (!response.ok) throw Error('Sessão encerrada');
    const state = await response.json();
    wasRunning = Boolean(state.running);
    if (!pendingId) status.textContent = state.running ? 'Navegando…' : 'Pronto para continuar';
    if (!showingVideo && state.url && state.url !== 'about:blank') {
      preview.hidden = false;
      placeholder.hidden = true;
      const shotKey = `${state.url}:${state.updated}`;
      if (force || shotKey !== lastShotKey) {
        preview.src = `/api/agent/image?t=${Date.now()}`;
        lastShotKey = shotKey;
      }
      preview.alt = state.title || 'Prévia do navegador do agente';
    }
  } catch { status.textContent = 'Sessão encerrada'; }
}
void refresh(true);
channel.postMessage({ type: 'media-request' });
setInterval(() => { void refresh(); }, 2500);
