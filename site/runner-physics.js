// Ballistic motion plus a damped spring for a soft, area-preserving landing.
export function advanceBody(body, elapsed, floor) {
  let impact = 0;
  let remaining = Math.min(Math.max(elapsed, 0), 0.05);
  while (remaining > 0.000001) {
    const dt = Math.min(remaining, 1 / 120);
    remaining -= dt;
    if (body.y < floor || body.velocity < 0) {
      body.y += body.velocity * dt + 575 * dt * dt;
      body.velocity += 1150 * dt;
      if (body.y >= floor && body.velocity > 0) {
        impact = body.velocity;
        body.y = floor; body.velocity = 0;
        body.squashVelocity += Math.min(impact * 0.022, 10);
      }
    }
    body.squashVelocity += (-220 * body.squash - 13 * body.squashVelocity) * dt;
    body.squash += body.squashVelocity * dt;
  }
  return impact;
}

export function coinTouchesBody(coin, body, x, size) {
  const nearX = Math.max(x + 3, Math.min(coin.x, x + size - 3));
  const nearY = Math.max(body.y + 3, Math.min(coin.y, body.y + size - 3));
  return (coin.x - nearX) ** 2 + (coin.y - nearY) ** 2 <= 11 ** 2;
}


export function makeObstacle(x, previousKind, random = Math.random) {
  const kinds = ['block', 'spike', 'orb', 'steps', 'crystal'].filter(kind => kind !== previousKind);
  const kind = kinds[Math.floor(random() * kinds.length)];
  const h = 20 + random() * 12;
  const w = kind === 'steps' ? 32 + random() * 6 : kind === 'orb' ? h : 19 + random() * 11;
  return {x, w, h, kind, color: ['#b586cf','#f49a76','#77a7eb','#66cba9'][Math.floor(random()*4)], counted:false};
}

export function makeCoinTrail(x, ground, random = Math.random) {
  const count = Math.floor(random() * 6); // Empty stretches, singles and groups of 2–5.
  const spacing = 24 + random() * 10;
  const pattern = Math.floor(random() * 3), base = 24 + random() * 18;
  return Array.from({length:count}, (_, index) => ({
    x: x + index * spacing,
    y: ground - base - (pattern === 0 ? 0 : pattern === 1
      ? Math.sin((index + 1) / (count + 1) * Math.PI) * 30 : index % 2 * 24),
    phase: random() * Math.PI * 2
  }));
}

export function obstacleTouchesBody(o, body, x, size, ground) {
  const left=x+5, right=x+size-5, top=body.y+4, bottom=body.y+size-4;
  const ox=o.x+2, ow=o.w-4, oh=o.h-3, oy=ground-oh;
  if (right <= ox || left >= ox+ow || bottom <= oy || top >= ground) return false;
  if (o.kind === 'orb') {
    const radius=Math.min(ow,oh)/2, cx=ox+ow/2, cy=ground-radius;
    const nx=Math.max(left,Math.min(cx,right)), ny=Math.max(top,Math.min(cy,bottom));
    return (nx-cx)**2+(ny-cy)**2 < radius**2;
  }
  if (o.kind === 'spike' || o.kind === 'crystal') {
    const cy=ground-oh/2;
    const nearestY=o.kind === 'spike' ? Math.min(bottom,ground) : Math.max(top,Math.min(cy,bottom));
    const half=ow/2*(o.kind === 'spike' ? (nearestY-oy)/oh : 1-Math.abs(nearestY-cy)/(oh/2));
    return right > ox+ow/2-half && left < ox+ow/2+half;
  }
  if (o.kind === 'steps') return bottom > ground-oh*.5 || right > ox+ow*.45;
  return true;
}
