// A tiny opt-in runner. One canvas, no assets/network and no idle animation.
import { advanceBody, coinTouchesBody, makeObstacle, makeCoinTrail, obstacleTouchesBody } from './runner-physics.js';
export function createThinkingGame(signal) {
  const element = document.createElement('section');
  element.className = 'thinking-game';
  element.setAttribute('aria-label', 'Mini game enquanto a Alt-IA pensa');
  element.innerHTML = `<div class="thinking-game-heading"><span>Um pulo enquanto penso</span><div class="thinking-game-scores"><span>Pulos <output data-score aria-label="Obstáculos superados">00</output></span><span class="thinking-game-btc">₿ <output data-coins aria-label="Moedas BTC coletadas">00</output></span></div></div>
    <button type="button" class="thinking-game-play" aria-label="Jogar: toque ou pressione espaço para pular os obstáculos"><canvas aria-hidden="true"></canvas></button>
    <div class="thinking-game-hint" aria-live="polite">Espaço ou ↑ para jogar · toque também funciona</div>`;
  const button = element.querySelector('button');
  const canvas = element.querySelector('canvas');
  const scoreLabel = element.querySelector('[data-score]');
  const coinLabel = element.querySelector('[data-coins]');
  const hint = element.querySelector('.thinking-game-hint');
  const ctx = canvas.getContext('2d');
  if (!ctx) return { element: document.createElement('span'), destroy() {} };
  const width = 420, height = 132, ground = 106, size = 30, x = 52;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * ratio; canvas.height = height * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const body = {y: ground - size, velocity: 0, squash: 0, squashVelocity: 0};
  let score = 0, collected = 0, distance = 0, coins = [], particles = [], effects = [];
  let obstacles = [], spawn = 0.85, coinSpawn = 0.5, lastKind = "", shake = 0, running = false, dead = false;
  let visible = false, disposed = false, frame = 0, last = 0;
  let appearanceTime = 0, nextPaint = 0;
  const frameInterval = 1000 / 60;
  const palette = [[249,163,179], [244,154,118], [181,134,207], [119,167,235], [102,203,169]];
  let colorIndex = 0, colorTime = 1, bodyColor = [...palette[0]], colorFrom = [...palette[0]];
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
    ctx.fillStyle = `rgb(${bodyColor.map(Math.round).join(',')})`;
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
  function emit(px, py, smoke) {
    for (let i = 0; i < (smoke ? 8 : 6); i++) {
      const side = i % 2 ? 1 : -1;
      particles.push({x: px + (smoke ? side * (9 + Math.random() * 8) : 0), y: py,
        vx: side * (16 + Math.random() * 35), vy: -(12 + Math.random() * 32),
        age: 0, life: smoke ? 0.6 + Math.random() * 0.35 : 0.45,
        radius: 2 + Math.random() * 2, smoke, color: smoke ? [...bodyColor] : [244,174,123]});
    }
    // Small bounded particle pool, no blur filters or offscreen canvases.
    if (particles.length > 42) particles.splice(0, particles.length - 42);
  }
  function effect(px, py, kind) {
    effects.push({x:px,y:py,kind,age:0,life:kind === 'coin' ? 0.6 : 0.38});
    if (effects.length > 18) effects.shift();
  }
  function drawObstacle(o) {
    ctx.fillStyle=o.color; ctx.strokeStyle='#ffffff50'; ctx.lineWidth=1;
    if (o.kind === 'block') {
      rounded(o.x,ground-o.h,o.w,o.h,5,o.color);
      rounded(o.x+4,ground-o.h+4,o.w-8,2,1,'#ffffff45');
    } else if (o.kind === 'orb') {
      ctx.beginPath();ctx.arc(o.x+o.w/2,ground-o.h/2,o.h/2,0,Math.PI*2);ctx.fill();
      ctx.beginPath();ctx.arc(o.x+o.w/2,ground-o.h/2,o.h/2-4,Math.PI,Math.PI*1.65);ctx.stroke();
    } else if (o.kind === 'steps') {
      rounded(o.x,ground-o.h*.5,o.w,o.h*.5,3,o.color);
      rounded(o.x+o.w*.45,ground-o.h,o.w*.55,o.h,3,o.color);
      rounded(o.x+o.w*.45+3,ground-o.h+4,o.w*.55-6,1,1,'#ffffff50');
    } else {
      ctx.beginPath();ctx.moveTo(o.x+o.w/2,ground-o.h);
      if(o.kind === 'crystal') {
        ctx.lineTo(o.x+o.w,ground-o.h/2);ctx.lineTo(o.x+o.w/2,ground);ctx.lineTo(o.x,ground-o.h/2);
      } else {ctx.lineTo(o.x+o.w,ground);ctx.lineTo(o.x,ground);}
      ctx.closePath();ctx.fill();
      ctx.beginPath();ctx.moveTo(o.x+o.w/2,ground-o.h+5);ctx.lineTo(o.x+o.w*.7,ground-o.h*.36);ctx.stroke();
    }
  }
  function landing() {
    emit(x + size / 2, ground - 2, true);
    effect(x+size/2,ground+1,"landing");
    colorFrom = [...bodyColor]; colorIndex = (colorIndex + 1) % palette.length; colorTime = 0;
  }
  function draw() {
    ctx.clearRect(0, 0, width, height);
    ctx.save();ctx.translate(Math.sin(appearanceTime*95)*shake*12,0);
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#b586cf38';
    ctx.beginPath(); ctx.moveTo(16, ground + 1); ctx.lineTo(width - 16, ground + 1); ctx.stroke();
    for (let i = 0; i < 7; i++) {
      const gx = i * 78 - distance * 0.6 % 78;
      rounded(gx, ground + 9, 15, 2, 1, '#b586cf28');
    }
    ctx.fillStyle = '#b586cf16';
    ctx.beginPath(); ctx.ellipse(x + 15, ground + 2, 17 - (ground - size - body.y) * 0.08, 3, 0, 0, Math.PI * 2); ctx.fill();
    for (const p of particles) {
      const fade = 1 - p.age / p.life;
      ctx.fillStyle = `rgba(${p.color.map(Math.round).join(',')},${fade * (p.smoke ? 0.24 : 0.8)})`;
      if (p.smoke) {
        ctx.beginPath(); ctx.arc(p.x, p.y, p.radius + p.age * 11, 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.age * 4);
        ctx.fillRect(-2, -2, 4, 4); ctx.restore();
      }
    }
    for (const f of effects) {
      const t=f.age/f.life;ctx.save();ctx.globalAlpha=1-t;
      ctx.strokeStyle=f.kind === 'coin' ? '#efaa7d' : '#c3a5dd';ctx.lineWidth=1;
      ctx.beginPath();ctx.ellipse(f.x,f.y,5+t*22,f.kind === 'landing' ? 2+t*3 : 5+t*22,0,0,Math.PI*2);ctx.stroke();
      if(f.kind === 'coin') {ctx.fillStyle='#ffd2a1';ctx.font='bold 10px system-ui';ctx.textAlign='center';ctx.fillText('+1',f.x,f.y-12-t*17);}
      ctx.restore();
    }
    if(running && body.y < ground-size-4) {
      for(let i=1;i<=3;i++) {
        ctx.fillStyle=`rgba(${bodyColor.map(Math.round).join(',')},${.12-i*.025})`;
        ctx.beginPath();ctx.arc(x+size/2-i*12,body.y+size/2+i*2,7-i,0,Math.PI*2);ctx.fill();
      }
    }
    for (const coin of coins) {
      ctx.save(); ctx.translate(coin.x, coin.y);
      ctx.scale(0.8 + 0.2 * Math.cos(appearanceTime * 3 + coin.phase), 1);
      ctx.fillStyle = '#efaa7d'; ctx.strokeStyle = '#ffe0ba'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(0, 0, 10, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.strokeStyle = '#9f603e70'; ctx.beginPath(); ctx.arc(0, 0, 7.4, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = '#553445'; ctx.font = 'bold 13px system-ui'; ctx.textAlign = 'center';
      ctx.fillText('₿', 0, 4.5); ctx.restore();
      const sparkle=Math.max(0,Math.sin(appearanceTime*2.5+coin.phase));
      if(sparkle>.75){ctx.strokeStyle=`rgba(255,224,186,${(sparkle-.75)*3})`;ctx.beginPath();
        ctx.moveTo(coin.x+9,coin.y-14);ctx.lineTo(coin.x+9,coin.y-6);
        ctx.moveTo(coin.x+5,coin.y-10);ctx.lineTo(coin.x+13,coin.y-10);ctx.stroke();}
    }
    // Anchor at the feet: squashing widens the body without sinking into the floor.
    const stretch = body.y < ground - size ? Math.min(Math.abs(body.velocity) / 3200, 0.12) : 0;
    const scaleY = Math.max(0.60, Math.min(1.2, 1 - body.squash + stretch));
    ctx.save(); ctx.translate(x + size / 2, body.y + size);
    ctx.scale(1 / scaleY, scaleY); ctx.translate(0, -size / 2);
    ctx.rotate(Math.max(-0.1, Math.min(0.1, body.velocity / 3200)));
    drawBody();
    for (const eye of [-7, 6]) {
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.ellipse(eye, -2, 6, 9, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#24202d'; ctx.beginPath(); ctx.ellipse(eye + 1.5, 0, 2.8, dead ? 1.4 : 4.5, 0, 0, Math.PI * 2); ctx.fill();
    }
    ctx.strokeStyle = '#633749'; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(1, 7, 3, 0.1, Math.PI - 0.1); ctx.stroke(); ctx.restore();
    for (const o of obstacles) drawObstacle(o);
    if (!running) {
      ctx.fillStyle = '#c0b3cd'; ctx.font = '12px system-ui'; ctx.textAlign = 'center';
      ctx.fillText(dead ? 'Mais uma tentativa?' : 'Vamos pular?', width / 2 + 24, 58);
    }
    ctx.restore();
  }
  function tick(now) {
    frame = 0;
    if (disposed || !visible || document.hidden) { last = 0; return; }
    // Follow the display clock, capped at 60 paints/s on high-refresh screens.
    if (now + 0.75 < nextPaint) { schedule(); return; }
    const dt = last ? Math.min((now - last) / 1000, 0.035) : 0;
    last = now;
    nextPaint = Math.max(nextPaint + frameInterval, now);
    appearanceTime += dt;
    shake=Math.max(0,shake-dt);
    for(const f of effects)f.age+=dt;
    effects=effects.filter(f=>f.age<f.life);
    colorTime = Math.min(1, colorTime + dt / 0.24);
    const colorBlend = colorTime * colorTime * (3 - 2 * colorTime);
    bodyColor = colorFrom.map((v, i) => v + (palette[colorIndex][i] - v) * colorBlend);
    const impact = advanceBody(body, dt, ground - size);
    if (impact > 40) landing();
    for (const p of particles) {
      p.age += dt; p.x += p.vx * dt; p.y += p.vy * dt;
      p.vx *= Math.exp(-2 * dt); p.vy -= (p.smoke ? 8 : -50) * dt;
    }
    particles = particles.filter(p => p.age < p.life);
    if (!running) { draw(); schedule(); return; }
    const speed = Math.min(190 + score * 5, 260);
    distance += speed * dt;
    spawn -= dt;
    if (spawn <= 0) {
      const obstacle=makeObstacle(width+10,lastKind);lastKind=obstacle.kind;obstacles.push(obstacle);
      spawn = 1.15 + Math.random() * 0.9;
    }
    coinSpawn -= dt;
    if(coinSpawn <= 0) {
      coins.push(...makeCoinTrail(width+12,ground));
      coinSpawn=0.8+Math.random()*1.5;
    }
    for (const o of obstacles) {
      o.x -= speed * dt;
      // Inset hit boxes make the little rounded shapes forgiving on touch.
      if (obstacleTouchesBody(o,body,x,size,ground)) {
        running = false; dead = true;shake=.18;
        emit(x+size/2,body.y+size/2,false);effect(x+size/2,body.y+size/2,"hit");
        hint.textContent = `${collected} moeda${collected === 1 ? "" : "s"} ₿ · espaço / ↑ para tentar de novo`;
        button.setAttribute('aria-label', 'Tentar novamente');
        break;
      }
      if (!o.counted && o.x + o.w < x) {
        o.counted = true; score += 1; scoreLabel.value = String(score).padStart(2, '0');
      }
    }
    obstacles = obstacles.filter(o => o.x + o.w > 0);
    coins = coins.filter(coin => {
      coin.x -= speed * dt;
      if (running && coinTouchesBody(coin, body, x, size)) {
        collected += 1; coinLabel.value = String(collected).padStart(2, '0');
        emit(coin.x, coin.y, false); effect(coin.x,coin.y,"coin"); return false;
      }
      return coin.x > -12;
    });
    draw(); schedule();
  }
  function schedule() {
    const settling = effects.length || shake || particles.length || Math.abs(body.squash) > 0.001 || Math.abs(body.squashVelocity) > 0.01 || body.y < ground - size;
    if (!frame && !disposed && (running || settling) && visible && !document.hidden) frame = requestAnimationFrame(tick);
  }
  function jump() {
    if (disposed) return;
    if (!running) {
      obstacles = []; particles = []; effects = []; shake=0; lastKind=""; collected = 0; coinLabel.value = '00';
      coins = makeCoinTrail(145,ground);coinSpawn=.7+Math.random();
      score = 0; distance = 0; spawn = 0.85;
      Object.assign(body, {y:ground - size, velocity:0, squash:0, squashVelocity:0});
      running = true; dead = false; last = 0; nextPaint = 0; scoreLabel.value = '00';
      hint.textContent = 'Pule as formas e colete ₿ · toque / espaço / ↑';
      button.setAttribute('aria-label', 'Pular obstáculo');
    }
    if (body.y >= ground - size - 0.5) body.velocity = -390;
    schedule();
  }
  function key(event) {
    if (event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey
      || disposed || !visible || !element.isConnected || document.hidden) return;
    const target = event.target;
    const playingButton = target === button;
    if (!playingButton && target instanceof Element && target.closest(
      'input,textarea,select,button,a,[contenteditable]:not([contenteditable="false"]),[role="dialog"],[role="textbox"]')) return;
    if ([' ', 'ArrowUp'].includes(event.key) || playingButton && event.key === 'Enter') {
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
  document.addEventListener('keydown', key);
  document.addEventListener('visibilitychange', visibility);
  function destroy() {
    if (disposed) return;
    disposed = true; cancelAnimationFrame(frame); observer.disconnect();
    document.removeEventListener('visibilitychange', visibility);
    button.removeEventListener('click', jump); document.removeEventListener('keydown', key);
    signal?.removeEventListener('abort', destroy);
    element.remove();
  }
  signal?.addEventListener('abort', destroy, {once: true});
  draw();
  return {element, destroy};
}
