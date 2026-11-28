const playIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 11 7-11 7Z" fill="currentColor" stroke="none"/></svg>';
const pauseIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14"/></svg>';
const clock = seconds => Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` : '0:00';

export function openKnowledgePlayer(dialog, item, close) {
  if (dialog.open || !/^[a-f0-9]{64}$/.test(item.id)) return;
  const abort = new AbortController();
  const video = dialog.querySelector('video');
  const play = dialog.querySelector('[data-media="play"]');
  const seek = dialog.querySelector('[data-media="seek"]');
  const volume = dialog.querySelector('[data-media="volume"]');
  const rate = dialog.querySelector('[data-media="rate"]');
  const time = dialog.querySelector('.media-time');
  const status = dialog.querySelector('.media-status');
  const mute = dialog.querySelector('[data-media="mute"]');
  let seeking = false;
  const on = (target, event, fn) => target.addEventListener(event, fn, { signal: abort.signal });
  const update = () => {
    play.innerHTML = video.paused ? playIcon : pauseIcon;
    play.setAttribute('aria-label', video.paused ? 'Reproduzir' : 'Pausar');
    if (!seeking) seek.value = video.duration ? String(1000 * video.currentTime / video.duration) : '0';
    seek.disabled = !Number.isFinite(video.duration) || !video.duration;
    seek.setAttribute('aria-valuetext', `${clock(video.currentTime)} de ${clock(video.duration)}`);
    time.textContent = `${clock(video.currentTime)} / ${clock(video.duration)}`;
  };
  const toggle = () => {
    if (!video.paused) video.pause();
    else video.play().catch(() => { status.textContent = 'Toque em reproduzir para começar.'; status.hidden = false; });
  };
  dialog.querySelector('h2').textContent = item.title;
  status.textContent = 'Conectando ao Basecamp…'; status.hidden = false;
  seek.value = '0'; seek.disabled = true; volume.value = '1'; rate.value = '1';
  video.volume = 1; video.muted = false; video.playbackRate = 1;
  mute.setAttribute('aria-pressed', 'false');
  on(play, 'click', toggle);
  on(video, 'click', toggle);
  on(video, 'keydown', event => {
    if (event.key === ' ' || event.key === 'k') { event.preventDefault(); toggle(); }
    if (['ArrowLeft', 'ArrowRight'].includes(event.key) && Number.isFinite(video.duration)) {
      event.preventDefault(); video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + (event.key === 'ArrowRight' ? 5 : -5)));
    }
  });
  for (const event of ['timeupdate', 'play', 'pause', 'ended', 'loadedmetadata', 'durationchange']) on(video, event, update);
  for (const event of ['playing', 'loadeddata', 'seeked']) on(video, event, () => { status.hidden = true; });
  on(video, 'waiting', () => { status.textContent = 'Carregando vídeo…'; status.hidden = false; });
  on(video, 'error', () => { status.textContent = 'Não foi possível reproduzir este vídeo. Feche e tente abrir novamente.'; status.hidden = false; });
  on(seek, 'input', () => { seeking = true; });
  on(seek, 'change', () => { if (Number.isFinite(video.duration)) video.currentTime = Number(seek.value) / 1000 * video.duration; seeking = false; });
  on(volume, 'input', () => { video.volume = Number(volume.value); video.muted = false; mute.setAttribute('aria-pressed', 'false'); });
  on(mute, 'click', () => { video.muted = !video.muted; mute.setAttribute('aria-pressed', String(video.muted)); mute.setAttribute('aria-label', video.muted ? 'Ativar som' : 'Silenciar'); });
  on(rate, 'change', () => { video.playbackRate = Number(rate.value); });
  on(dialog.querySelector('[data-media="full"]'), 'click', () => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    else if (dialog.requestFullscreen) void dialog.requestFullscreen().catch(() => {});
    else video.webkitEnterFullscreen?.();
  });
  const dismiss = () => { video.pause(); close(dialog); };
  on(dialog.querySelector('.pool-dialog-close'), 'click', dismiss);
  on(dialog, 'cancel', event => { event.preventDefault(); dismiss(); });
  on(dialog, 'click', event => { if (event.target === dialog) dismiss(); });
  dialog.addEventListener('close', () => {
    abort.abort(); video.pause(); video.removeAttribute('src'); video.load();
    if (document.fullscreenElement === dialog) void document.exitFullscreen().catch(() => {});
  }, { once: true });
  dialog.showModal(); update();
  video.src = `/api/knowledge/videos/${item.id}`;
  video.play().catch(() => { status.textContent = 'Toque em reproduzir para começar.'; status.hidden = false; });
}
