// The world view: a turning wireframe globe drawn from real coastlines.
// It is decoration with one bit of meaning: it turns faster the more data is
// moving, and goes dim when this computer has no link.

let lines = null;  // each coastline as [lon, lat, lon, lat, ...] in degrees, loaded once

async function coastlines() {
  if (!lines) {
    try {
      lines = await (await fetch(new URL("../vendor/world/land.json", import.meta.url))).json();
    } catch {
      lines = [];  // no map: the grid lines alone still make a globe
    }
  }
  return lines;
}

/** Starts the globe on a canvas. Returns update(online, activity 0..1). */
export function initGlobe(canvas) {
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const RAD = Math.PI / 180, TILT = 18 * RAD, sinT = Math.sin(TILT), cosT = Math.cos(TILT);
  let turn = 200, speed = 0.12, online = true, land = [], last = 0;

  // Longitude and latitude to a point on the screen, or null on the far side.
  const project = (lon, lat, r, cx, cy) => {
    const a = (lon + turn) * RAD, b = lat * RAD, cb = Math.cos(b);
    const x = cb * Math.sin(a), y0 = Math.sin(b), z0 = cb * Math.cos(a);
    const y = y0 * cosT - z0 * sinT, z = y0 * sinT + z0 * cosT;
    return z < 0 ? null : [cx + x * r, cy - y * r];
  };

  function path(ctx, points, r, cx, cy) {
    let open = false;
    for (let i = 0; i < points.length; i += 2) {
      const p = project(points[i], points[i + 1], r, cx, cy);
      if (!p) { open = false; continue; }
      if (open) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]);
      open = true;
    }
  }

  function draw() {
    const ratio = devicePixelRatio || 1, w = canvas.clientWidth, hgt = canvas.clientHeight;
    if (!w || !hgt) return;
    if (canvas.width !== Math.round(w * ratio)) { canvas.width = Math.round(w * ratio); canvas.height = Math.round(hgt * ratio); }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, w, hgt);
    const colour = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
    const r = Math.min(w, hgt) / 2 - 4, cx = w / 2, cy = hgt / 2;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 1;

    ctx.globalAlpha = online ? 0.5 : 0.2;   // the rim
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    ctx.globalAlpha = online ? 0.16 : 0.08;  // the grid: a line every 30 degrees
    ctx.beginPath();
    for (let lon = -180; lon < 180; lon += 30) {
      const meridian = [];
      for (let lat = -90; lat <= 90; lat += 6) meridian.push(lon, lat);
      path(ctx, meridian, r, cx, cy);
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const parallel = [];
      for (let lon = -180; lon <= 180; lon += 6) parallel.push(lon, lat);
      path(ctx, parallel, r, cx, cy);
    }
    ctx.stroke();

    ctx.globalAlpha = online ? 0.95 : 0.3;   // the land
    ctx.beginPath();
    for (const line of land) path(ctx, line, r, cx, cy);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    if (!document.hidden && canvas.offsetParent && now - last > 60) {  // about 16 frames a second is plenty
      turn = (turn + speed * Math.min(100, now - last) / 16) % 360;
      last = now;
      draw();
    }
    requestAnimationFrame(frame);
  }

  coastlines().then((loaded) => { land = loaded; draw(); });
  if (still) new ResizeObserver(draw).observe(canvas); else requestAnimationFrame(frame);

  return (isOnline, activity) => {
    online = isOnline;
    speed = isOnline ? 0.1 + activity * 0.5 : 0.02;
    if (still) draw();
  };
}
