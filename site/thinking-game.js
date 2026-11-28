// A tiny opt-in runner. One canvas, no assets/network and no idle animation.
export function createThinkingGame(signal) {
  const element = document.createElement('section');
  element.className = 'thinking-game';
  element.setAttribute('aria-label', 'Mini game enquanto a Alt-IA pensa');
  element.innerHTML = `<div class="thinking-game-heading"><span>Um pulo enquanto penso</span><output aria-label="Pontos">00</output></div>
    <button type="button" class="thinking-game-play" aria-label="Jogar: toque ou pressione espaço para pular os obstáculos"><canvas aria-hidden="true"></canvas></button>
    <div class="thinking-game-hint" aria-live="polite">Toque para jogar · espaço ou ↑ para pular</div>`;
  const button = element.querySelector('button');
  const canvas = element.querySelector('canvas');
  const scoreLabel = element.querySelector('output');
  const hint = element.querySelector('.thinking-game-hint');
  const ctx = canvas.getContext('2d');
  if (!ctx) return { element: document.createElement('span'), destroy() {} };
  const width = 420, height = 132, ground = 106, size = 30, x = 52;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * ratio; canvas.height = height * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  let y = ground - size, velocity = 0, score = 0, distance = 0;
  let obstacles = [], spawn = 0.85, running = false, dead = false;
  let visible = false, disposed = false, frame = 0, last = 0;
  let appearanceTime = 0, nextPaint = 0;
  const frameInterval = 1000 / 60;
  const palette = [[249,163,179], [244,154,118], [181,134,207], [119,167,235], [102,203,169]];
  // Precompute the geometry once. Each frame only interpolates 48 points.
  const outlines = [2, 4, 1.5, 3].map(exponent => Array.from({length:48}, (_, i) => {
    const angle = i * Math.PI * 2 / 48;
    const c = Math.cos(angle), s = Math.sin(angle);
    const radius = 15 / Math.pow(Math.abs(c) ** exponent + Math.abs(s) ** exponent, 1 / exponent);
    return [radius * c, radius * s];
  }));

  function drawBody() {
    const phase = appearanceTime / 1.5;
    const index = Math.floor(phase);
    const fraction = phase - index;
    const blend = fraction * fraction * (3 - 2 * fraction);
    const from = outlines[index % outlines.length], to = outlines[(index + 1) % outlines.length];
    const first = palette[index % palette.length], second = palette[(index + 1) % palette.length];
    ctx.fillStyle = `rgb(${first.map((v, i) => Math.round(v + (second[i] - v) * blend)).join(',')})`;
    ctx.beginPath();
    for (let i = 0; i < from.length; i++) {
      const px = from[i][0] + (to[i][0] - from[i][0]) * blend;
      const py = from[i][1] + (to[i][1] - from[i][1]) * blend;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.closePath(); ctx.fill();
  }

  function rounded(px, py, w, h, radius, color) {
    ctx.fillStyle = color; ctx.beginPath(); ctx.roundRect(px, py, w, h, radius); ctx.fill();
  }
  function draw() {
    ctx.clearRect(0, 0, width, height);
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#b586cf38';
    ctx.beginPath(); ctx.moveTo(16, ground + 1); ctx.lineTo(width - 16, ground + 1); ctx.stroke();
    for (let i = 0; i < 7; i++) {
      const gx = i * 78 - distance * 0.6 % 78;
      rounded(gx, ground + 9, 15, 2, 1, '#b586cf28');
    }
    ctx.fillStyle = '#b586cf16';
    ctx.beginPath(); ctx.ellipse(x + 15, ground + 2, 17 - (ground - size - y) * 0.08, 3, 0, 0, Math.PI * 2); ctx.fill();
    ctx.save(); ctx.translate(x + size / 2, y + size / 2);
    ctx.rotate(Math.max(-0.14, Math.min(0.14, velocity / 2500)));
    drawBody();
    for (const eye of [-7, 6]) {
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.ellipse(eye, -2, 6, 9, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#24202d'; ctx.beginPath(); ctx.ellipse(eye + 1.5, 0, 2.8, dead ? 1.4 : 4.5, 0, 0, Math.PI * 2); ctx.fill();
    }
    ctx.strokeStyle = '#633749'; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(1, 7, 3, 0.1, Math.PI - 0.1); ctx.stroke(); ctx.restore();
    for (const o of obstacles) {
      rounded(o.x, ground - o.h, o.w, o.h, 5, o.color);
      rounded(o.x + 4, ground - o.h + 4, o.w - 8, 2, 1, '#ffffff45');
    }
    if (!running) {
      ctx.fillStyle = '#c0b3cd'; ctx.font = '12px system-ui'; ctx.textAlign = 'center';
      ctx.fillText(dead ? 'Mais uma tentativa?' : 'Vamos pular?', width / 2 + 24, 58);
    }
  }
  function tick(now) {
    frame = 0;
    if (disposed || !running || !visible || document.hidden) { last = 0; return; }
    // Follow the display clock, capped at 60 paints/s on high-refresh screens.
    if (now + 0.75 < nextPaint) { schedule(); return; }
    const dt = last ? Math.min((now - last) / 1000, 0.035) : 0;
    last = now;
    nextPaint = Math.max(nextPaint + frameInterval, now);
    appearanceTime += dt;
    const speed = Math.min(190 + score * 5, 260);
    distance += speed * dt;
    velocity += 1150 * dt; y = Math.min(ground - size, y + velocity * dt);
    if (y >= ground - size) velocity = 0;
    spawn -= dt;
    if (spawn <= 0) {
      obstacles.push({x: width + 10, w: 18 + Math.random() * 7, h: 19 + Math.random() * 10,
        color: score % 2 ? '#b586cf' : '#f49a76', counted: false});
      spawn = 1.25 + Math.random() * 0.55;
    }
    for (const o of obstacles) {
      o.x -= speed * dt;
      // Inset hit boxes make the little rounded shapes forgiving on touch.
      if (x + size - 5 > o.x + 3 && x + 5 < o.x + o.w - 3 && y + size - 4 > ground - o.h + 3) {
        running = false; dead = true;
        hint.textContent = `${score} ${score === 1 ? 'pulo' : 'pulos'} · toque para tentar de novo`;
        button.setAttribute('aria-label', 'Tentar novamente');
        break;
      }
      if (!o.counted && o.x + o.w < x) {
        o.counted = true; score += 1; scoreLabel.value = String(score).padStart(2, '0');
      }
    }
    obstacles = obstacles.filter(o => o.x + o.w > 0);
    draw(); schedule();
  }
  function schedule() {
    if (!frame && !disposed && running && visible && !document.hidden) frame = requestAnimationFrame(tick);
  }
  function jump() {
    if (disposed) return;
    if (!running) {
      obstacles = []; score = 0; distance = 0; spawn = 0.85; y = ground - size;
      running = true; dead = false; last = 0; nextPaint = 0; scoreLabel.value = '00';
      hint.textContent = 'Toque ou pressione espaço / ↑ para pular';
      button.setAttribute('aria-label', 'Pular obstáculo');
    }
    if (y >= ground - size - 0.5) velocity = -420;
    schedule();
  }
  function key(event) {
    if ([' ', 'ArrowUp', 'Enter'].includes(event.key)) {
      event.preventDefault(); if (!event.repeat) jump();
    }
  }
  function visibility() {
    cancelAnimationFrame(frame); frame = 0; last = 0; nextPaint = 0; schedule();
  }
  const observer = new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting; visibility();
  }, {threshold: 0.1});
  observer.observe(element);
  button.addEventListener('click', jump);
  button.addEventListener('keydown', key);
  document.addEventListener('visibilitychange', visibility);
  function destroy() {
    if (disposed) return;
    disposed = true; cancelAnimationFrame(frame); observer.disconnect();
    document.removeEventListener('visibilitychange', visibility);
    button.removeEventListener('click', jump); button.removeEventListener('keydown', key);
    signal?.removeEventListener('abort', destroy);
    element.remove();
  }
  signal?.addEventListener('abort', destroy, {once: true});
  draw();
  return {element, destroy};
}
