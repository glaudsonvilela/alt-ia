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
