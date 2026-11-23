/* Hologram brain and dial nodes (Phase 19, slice b). Ported from mockups/brain/index.html look 6
   (shape, MODEL, drawHolo, DialNode, BrainStage) with the agreed review fixes: fewer sparks and motes,
   a white-gold core whose colour and pulse follow the mood, larger node text, Play clear of the projector.
   Plain canvas + SVG; no old engine code. HB is used by holo.js. */

/* Sector places, as offsets from the brain centre in brain-size units (same five places as the old skin). */
var HB_PLACES = {
  school: { dx: -2.55, dy: -0.74 },
  security: { dx: -2.05, dy: 0.44 },
  intern: { dx: 2.55, dy: -0.74 },
  personal: { dx: 2.05, dy: 0.4 },
  play: { dx: 0, dy: 1.42 },
};
var HB_MOOD = {
  calm: {
    c0: [255, 250, 236],
    c1: [255, 226, 168],
    c2: [190, 176, 255],
    speed: 1.6,
    glow: 0.85,
  },
  busy: {
    c0: [255, 246, 222],
    c1: [255, 206, 128],
    c2: [255, 176, 130],
    speed: 2.3,
    glow: 0.95,
  },
  missed: {
    c0: [255, 240, 226],
    c1: [255, 178, 140],
    c2: [255, 128, 176],
    speed: 3.0,
    glow: 1,
  },
};

/* unit direction -> point on the brain surface. x: left/right, y: up, z: front */
function hbShape(x, y, z) {
  var r = 1;
  r *= 1 - 0.2 * Math.exp(-(x * x) / 0.016) * (y > -0.1 ? 1 : 0.3); // the groove between the halves
  r *=
    1 +
    0.05 * Math.sin(10 * x + 4 * z) * Math.cos(9 * y + 3 * z) +
    0.03 * Math.sin(17 * z + 5 * y); // folds
  var px = x * r * 0.95,
    py = y * r * 0.78,
    pz = z * r * 1.22;
  px *= 1 - 0.1 * Math.max(0, pz); // narrower at the front
  if (py < -0.32) py = -0.32 + (py + 0.32) * 0.4; // flat underside
  return [px, py, pz];
}
function hbModel() {
  var P = [],
    N = 1500,
    gold = Math.PI * (3 - Math.sqrt(5)),
    i,
    y,
    r,
    a;
  for (i = 0; i < N; i++) {
    y = 1 - (2 * (i + 0.5)) / N;
    r = Math.sqrt(1 - y * y);
    a = i * gold;
    P.push(hbShape(Math.cos(a) * r, y, Math.sin(a) * r));
  }
  for (i = 0; i < 230; i++) {
    // cerebellum
    y = 1 - (2 * (i + 0.5)) / 230;
    r = Math.sqrt(1 - y * y);
    a = i * gold;
    var k = 1 + 0.05 * Math.sin(38 * y);
    P.push([
      Math.cos(a) * r * 0.5 * k,
      -0.5 + y * 0.27,
      -0.8 + Math.sin(a) * r * 0.36 * k,
    ]);
  }
  for (i = 0; i < 70; i++) {
    var u = i / 69,
      aa = i * 2.4,
      rad = 0.1 - 0.035 * u;
    P.push([
      Math.cos(aa) * rad,
      -0.42 - 0.6 * u,
      -0.42 - 0.14 * u + Math.sin(aa) * rad,
    ]);
  } // stem
  var n = P.length,
    px = new Float32Array(n),
    py = new Float32Array(n),
    pz = new Float32Array(n),
    hb = new Uint8Array(n);
  P.forEach(function (p, j) {
    px[j] = p[0];
    py[j] = p[1];
    pz[j] = p[2];
    hb[j] = Math.max(0, Math.min(3, Math.floor(((1.22 - p[2]) / 2.44) * 4)));
  });
  var edges = [],
    adj = [],
    seen = {};
  for (i = 0; i < n; i++) adj.push([]);
  for (i = 0; i < n; i++) {
    // join each point to its 3 nearest
    var best = [
      [9, -1],
      [9, -1],
      [9, -1],
    ];
    for (var j = 0; j < n; j++) {
      if (j === i) continue;
      var dx = px[i] - px[j],
        dy = py[i] - py[j],
        dz = pz[i] - pz[j],
        d = dx * dx + dy * dy + dz * dz;
      if (d < best[2][0]) {
        best[2] = [d, j];
        best.sort(function (p, q) {
          return p[0] - q[0];
        });
      }
    }
    best.forEach(function (b) {
      var jj = b[1];
      if (jj < 0 || b[0] > 0.05) return;
      var key = i < jj ? i * 4096 + jj : jj * 4096 + i;
      if (!seen[key]) {
        seen[key] = 1;
        edges.push(i, jj);
      }
      adj[i].push(jj);
      adj[jj].push(i);
    });
  }
  var sparks = [];
  for (i = 0; i < 8; i++) {
    var s0 = Math.floor(Math.random() * N);
    sparks.push({
      a: s0,
      b: adj[s0][0] || s0,
      u: Math.random(),
      v: 1.4 + Math.random() * 1.2,
    });
  }
  return {
    n: n,
    px: px,
    py: py,
    pz: pz,
    hb: hb,
    edges: edges,
    adj: adj,
    sparks: sparks,
    sx: new Float32Array(n),
    sy: new Float32Array(n),
    sd: new Float32Array(n),
    last: 0,
  };
}
var HB_HUES = [186, 204, 232, 262];
function hbRgba(c, a) {
  return (
    "rgba(" +
    c[0] +
    "," +
    c[1] +
    "," +
    c[2] +
    "," +
    Math.max(0, Math.min(1, a)).toFixed(3) +
    ")"
  );
}

/* One frame. full = haze, motes, sparks and scan line (off in low power). */
function hbDraw(M, ctx, w, h, cx, cy, S, t, mood, full) {
  var yaw = 1.98 + 0.42 * Math.sin(t * 0.22) + HB.dragYaw, // the user can drag to orbit it
    pitch = 0.16 + HB.dragPitch,
    i;
  var cyw = Math.cos(yaw),
    syw = Math.sin(yaw),
    cp = Math.cos(pitch),
    sp = Math.sin(pitch);
  for (i = 0; i < M.n; i++) {
    var x = M.px[i] * cyw - M.pz[i] * syw,
      z = M.px[i] * syw + M.pz[i] * cyw,
      y = M.py[i] * cp - z * sp,
      z2 = M.py[i] * sp + z * cp,
      k = 3.6 / (3.6 - z2);
    M.sx[i] = cx + x * S * k;
    M.sy[i] = cy - y * S * k;
    M.sd[i] = Math.max(0, Math.min(0.999, (z2 + 1.3) / 2.6));
  }
  ctx.clearRect(0, 0, w, h);
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  var by = cy + S * 0.96,
    breath = 0.86 + 0.14 * Math.sin(t * 1.3);
  var cone = ctx.createLinearGradient(0, by, 0, cy - S * 0.3);
  cone.addColorStop(0, "rgba(46,230,255,.11)");
  cone.addColorStop(1, "rgba(46,230,255,0)");
  ctx.fillStyle = cone;
  ctx.beginPath();
  ctx.moveTo(cx - S * 0.36, by);
  ctx.lineTo(cx - S * 1.3, cy - S * 0.3);
  ctx.lineTo(cx + S * 1.3, cy - S * 0.3);
  ctx.lineTo(cx + S * 0.36, by);
  ctx.fill();
  for (var r0 = 0; r0 < 2; r0++) {
    ctx.strokeStyle = "rgba(46,230,255," + (0.36 - r0 * 0.18) + ")";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.ellipse(
      cx,
      by,
      S * (0.36 + r0 * 0.16),
      S * (0.05 + r0 * 0.025),
      0,
      0,
      7,
    );
    ctx.stroke();
  }
  if (full) {
    var hz = ctx.createRadialGradient(
      cx,
      cy - S * 0.05,
      S * 0.1,
      cx,
      cy - S * 0.05,
      S * 1.35,
    );
    hz.addColorStop(0, "rgba(70,120,255,.16)");
    hz.addColorStop(0.6, "rgba(90,80,255,.07)");
    hz.addColorStop(1, "rgba(90,80,255,0)");
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(1, 0.68);
    ctx.translate(-cx, -cy);
    ctx.fillStyle = hz;
    ctx.beginPath();
    ctx.arc(cx, cy - S * 0.05, S * 1.35, 0, 7);
    ctx.fill();
    ctx.restore();
    for (i = 0; i < 36; i++) {
      // slow drifting motes
      var r1 = Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1,
        r2 = Math.abs(Math.sin(i * 78.233) * 12543.123) % 1,
        r3 = Math.abs(Math.sin(i * 39.425) * 9631.77) % 1;
      var mx = r1 * w + Math.sin(t * 0.2 + i) * 8,
        my = (((r2 * h - t * (3 + r3 * 7)) % h) + h) % h,
        ma = (0.1 + 0.25 * r3) * (0.6 + 0.4 * Math.sin(t * (0.6 + r1) + i));
      ctx.fillStyle = "rgba(170,200,255," + ma + ")";
      var sz = 0.8 + r3 * 1.3;
      ctx.fillRect(mx, my, sz, sz);
    }
  }
  /* the thalamus: a white-gold core; colour and pulse follow the mood */
  var mo = HB_MOOD[mood] || HB_MOOD.calm;
  var Z = 0.05,
    Y = -0.04,
    kx0 = -Z * syw,
    kz = Z * cyw,
    ky0 = Y * cp - kz * sp,
    kz2 = Y * sp + kz * cp,
    kk = 3.6 / (3.6 - kz2);
  var kx = cx + kx0 * S * kk,
    ky = cy - ky0 * S * kk,
    pulse = 0.8 + 0.2 * Math.sin(t * mo.speed);
  var g = ctx.createRadialGradient(kx, ky, 0, kx, ky, S * 0.6);
  g.addColorStop(0, hbRgba(mo.c0, 0.9 * pulse * mo.glow));
  g.addColorStop(0.12, hbRgba(mo.c1, 0.45 * pulse * mo.glow));
  g.addColorStop(0.42, hbRgba(mo.c2, 0.1 * pulse));
  g.addColorStop(1, hbRgba(mo.c2, 0));
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(kx, ky, S * 0.6, 0, 7);
  ctx.fill();
  var E = M.edges,
    buckets = [],
    q;
  for (q = 0; q < 20; q++) buckets.push([]);
  for (var e = 0; e < E.length; e += 2) {
    var a1 = E[e],
      b1 = E[e + 1];
    buckets[M.hb[a1] * 5 + Math.floor(Math.min(M.sd[a1], M.sd[b1]) * 5)].push(
      a1,
      b1,
    );
  }
  ctx.lineWidth = 0.7;
  buckets.forEach(function (b, qq) {
    if (!b.length) return;
    ctx.strokeStyle =
      "hsla(" +
      HB_HUES[Math.floor(qq / 5)] +
      ",100%,66%," +
      (0.05 + (qq % 5) * 0.085) * breath +
      ")";
    ctx.beginPath();
    for (var kq = 0; kq < b.length; kq += 2) {
      ctx.moveTo(M.sx[b[kq]], M.sy[b[kq]]);
      ctx.lineTo(M.sx[b[kq + 1]], M.sy[b[kq + 1]]);
    }
    ctx.stroke();
  });
  for (q = 0; q < 20; q++) {
    var aq = q % 5,
      sz2 = 1.1 + aq * 0.38;
    ctx.fillStyle =
      "hsla(" +
      HB_HUES[Math.floor(q / 5)] +
      ",100%,74%," +
      (0.2 + aq * 0.18) +
      ")";
    for (i = 0; i < M.n; i++)
      if (M.hb[i] * 5 + Math.floor(M.sd[i] * 5) === q)
        ctx.fillRect(M.sx[i] - sz2 / 2, M.sy[i] - sz2 / 2, sz2, sz2);
  }
  if (full) {
    var band = cy - S * 1.05 + ((t * 0.12) % 1) * S * 2.1; // slow, faint scan line
    ctx.fillStyle = "rgba(220,250,255,.5)";
    for (i = 0; i < M.n; i++)
      if (Math.abs(M.sy[i] - band) < S * 0.016)
        ctx.fillRect(M.sx[i] - 1, M.sy[i] - 1, 2, 2);
    var dt = Math.min(0.05, Math.max(0, t - M.last));
    M.last = t;
    M.sparks.forEach(function (s) {
      s.u += dt * s.v * 3;
      if (s.u >= 1) {
        var nb = M.adj[s.b];
        var nx = nb.length ? nb[Math.floor(Math.random() * nb.length)] : s.a;
        s.a = s.b;
        s.b = nx;
        s.u = 0;
      }
      var sx = M.sx[s.a] + (M.sx[s.b] - M.sx[s.a]) * s.u,
        sy = M.sy[s.a] + (M.sy[s.b] - M.sy[s.a]) * s.u,
        d = 0.4 + 0.6 * M.sd[s.a];
      ctx.fillStyle = "rgba(46,230,255," + 0.24 * d + ")";
      ctx.beginPath();
      ctx.arc(sx, sy, 5, 0, 7);
      ctx.fill();
      ctx.fillStyle = "rgba(255,255,255," + 0.85 * d + ")";
      ctx.beginPath();
      ctx.arc(sx, sy, 1.6, 0, 7);
      ctx.fill();
    });
  }
  ctx.strokeStyle = hbRgba(mo.c1, 0.75);
  ctx.lineWidth = 1;
  for (var o = 0; o < 2; o++) {
    ctx.beginPath();
    ctx.ellipse(
      kx,
      ky,
      S * 0.2,
      S * 0.07,
      t * (o ? -0.7 : 0.9) + o * 1.3,
      0,
      7,
    );
    ctx.stroke();
  }
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.arc(kx, ky, S * 0.035, 0, 7);
  ctx.fill();
  ctx.restore();
  return { x: kx, y: ky, r: S * 0.22 };
}

/* A dial: bright arc = due this week, dim arc = everything, white dots = due in the next two days. */
function hbDialSvg(s) {
  var C = 2 * Math.PI * 36,
    all = Math.min(1, s.count / 40),
    wk = Math.min(all, s.week / 40),
    empty = !s.count,
    out = [],
    i;
  out.push(
    '<svg width="104" height="104" viewBox="-62 -62 124 124" aria-hidden="true" style="filter:drop-shadow(0 0 ' +
      (s.now ? 22 : 14) +
      "px " +
      s.color +
      (s.now ? "88" : "44") +
      ");opacity:" +
      (empty ? 0.6 : 1) +
      '">',
  );
  out.push(
    '<defs><radialGradient id="g-' +
      s.id +
      '"><stop offset="0" stop-color="' +
      s.color +
      '" stop-opacity="' +
      (s.now ? 0.32 : 0.22) +
      '"/><stop offset="1" stop-color="' +
      s.color +
      '" stop-opacity="0.03"/></radialGradient></defs>',
  );
  for (i = 0; i < 36; i++) {
    var a = (i * Math.PI) / 18,
      r0 = i % 3 ? 45.5 : 44,
      c = Math.cos(a),
      q = Math.sin(a);
    out.push(
      '<line x1="' +
        (c * r0).toFixed(1) +
        '" y1="' +
        (q * r0).toFixed(1) +
        '" x2="' +
        (c * 48).toFixed(1) +
        '" y2="' +
        (q * 48).toFixed(1) +
        '" stroke="#fff" stroke-opacity="' +
        (i % 3 ? 0.12 : 0.28) +
        '" stroke-width="1"/>',
    );
  }
  out.push(
    '<circle class="spin" r="55" fill="none" stroke="' +
      s.color +
      '" stroke-opacity=".3" stroke-width="1" stroke-dasharray="1.5 8"/>',
  );
  if (s.soon > 0) {
    out.push('<g class="spin-rev">');
    for (i = 0; i < Math.min(s.soon, 8); i++)
      out.push(
        '<circle cx="' +
          (Math.cos(i * 0.5) * 55).toFixed(1) +
          '" cy="' +
          (Math.sin(i * 0.5) * 55).toFixed(1) +
          '" r="2.6" fill="#fff" style="filter:drop-shadow(0 0 4px ' +
          s.color +
          ')"/>',
      );
    out.push("</g>");
  }
  out.push('<circle r="30" fill="url(#g-' + s.id + ')"/>');
  out.push(
    '<circle r="36" fill="none" stroke="#fff" stroke-opacity=".1" stroke-width="3"/>',
  );
  if (all > 0)
    out.push(
      '<circle r="36" fill="none" stroke="' +
        s.color +
        '" stroke-opacity=".38" stroke-width="3" stroke-linecap="round" stroke-dasharray="' +
        (all * C).toFixed(1) +
        " " +
        C.toFixed(1) +
        '" transform="rotate(-90)"/>',
    );
  if (wk > 0)
    out.push(
      '<circle r="36" fill="none" stroke="' +
        s.color +
        '" stroke-width="' +
        (s.now ? 4.5 : 3.5) +
        '" stroke-linecap="round" stroke-dasharray="' +
        (Math.max(0.02, wk) * C).toFixed(1) +
        " " +
        C.toFixed(1) +
        '" transform="rotate(-90)" style="filter:drop-shadow(0 0 5px ' +
        s.color +
        ')"/>',
    );
  out.push(
    '<text y="9" text-anchor="middle" fill="#fff" fill-opacity="' +
      (empty ? 0.6 : 1) +
      '" font-family="Inter, system-ui, sans-serif" font-weight="600" font-size="26">' +
      s.count +
      "</text></svg>",
  );
  return out.join("");
}

var HB = {
  M: null,
  host: null,
  cv: null,
  ctx: null,
  svg: null,
  nodes: null,
  w: 0,
  h: 0,
  dpr: 1,
  sectors: [],
  mood: "calm",
  low: false,
  still: false,
  raf: 0,
  t0: 0,
  core: null,
  key: "",
  onCoreTap: null,
  init: function (host) {
    HB.host = host;
    HB.cv = host.querySelector("#brainCv");
    HB.svg = host.querySelector("#fibres");
    HB.nodes = host.querySelector("#dials");
    HB.ctx = HB.cv.getContext("2d");
    HB.M = hbModel();
    HB.t0 = performance.now();
    if (window.ResizeObserver)
      new ResizeObserver(function () {
        HB.resize();
      }).observe(host);
    window.addEventListener("resize", HB.resize);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) HB.kick();
    });
    /* Drag the brain to orbit it (not while a sector is open); it drifts a little when let go and
       double-click puts it back. A tap without moving counts toward the five-tap hello on the core. */
    var taps = [], said = false, drag = null, cv = HB.cv;
    function onBrain(e) {
      if (!HB.w || HB.openId) return false;
      var r = host.getBoundingClientRect(), k = r.width / HB.w || 1, G = HB.geom(), dx = ((e.clientX - r.left) / k - G.cx) / (1.25 * G.S), dy = ((e.clientY - r.top) / k - G.cy) / (0.95 * G.S);
      return dx * dx + dy * dy <= 1;
    }
    function tap(e) {
      if (!HB.core) return;
      var r = host.getBoundingClientRect(), k = r.width / HB.w || 1, dx = (e.clientX - r.left) / k - HB.core.x, dy = (e.clientY - r.top) / k - HB.core.y;
      if (dx * dx + dy * dy > HB.core.r * HB.core.r * 4) return;
      var t = performance.now();
      taps = taps.filter(function (x) { return t - x < 2500; }).concat(t);
      if (taps.length >= 5 && !said && HB.onCoreTap) { said = true; taps = []; HB.onCoreTap(); }
    }
    cv.addEventListener("pointerdown", function (e) {
      if (e.button !== 0 || !onBrain(e)) return;
      drag = { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, t: performance.now() };
      HB.vYaw = HB.vPitch = 0;
      try { cv.setPointerCapture(e.pointerId); } catch (x) {}
      cv.style.cursor = "grabbing";
      e.preventDefault();
    });
    cv.addEventListener("pointermove", function (e) {
      if (!drag) { cv.style.cursor = onBrain(e) ? "grab" : ""; return; }
      var now = performance.now(), dt = Math.max(0.008, (now - drag.t) / 1000), dyaw = (e.clientX - drag.x) * 0.008, dpit = (e.clientY - drag.y) * 0.006;
      HB.dragYaw = Math.max(-1.4, Math.min(1.4, HB.dragYaw + dyaw));
      HB.dragPitch = Math.max(-0.7, Math.min(0.7, HB.dragPitch + dpit));
      HB.vYaw = Math.max(-3, Math.min(3, dyaw / dt));
      HB.vPitch = Math.max(-2, Math.min(2, dpit / dt));
      drag.x = e.clientX; drag.y = e.clientY; drag.t = now;
      HB.kick();
    });
    function end(e) {
      if (!drag) return;
      if (e.type === "pointerup" && Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) < 5) { HB.vYaw = HB.vPitch = 0; tap(e); }
      drag = null;
      cv.style.cursor = "";
      HB.last = performance.now();
      HB.kick();
    }
    cv.addEventListener("pointerup", end);
    cv.addEventListener("pointercancel", end);
    cv.addEventListener("dblclick", function (e) {
      if (!onBrain(e)) return;
      HB.dragYaw = HB.dragPitch = HB.vYaw = HB.vPitch = 0;
      HB.kick();
    });
    HB.resize();
  },
  /* Brain size S: as big as the stage allows while the top dials clear the question line and the Play
     dial's labels clear the dock (which overlaps the stage by about 28 px). */
  geom: function () {
    var h = HB.h, cy = h * 0.45, P = HB_PLACES;
    var S = Math.min(h * 0.255, HB.w * 0.14, (h - 150 - cy) / P.play.dy, (cy - 150) / -P.school.dy);
    return { S: Math.max(55, S), cx: HB.w / 2, cy: cy };
  },
  resize: function () {
    if (!HB.host) return;
    /* layout size, not the on-screen rect: the chat drawer scales the stage with a transform */
    var w = Math.round(HB.host.offsetWidth),
      h = Math.round(HB.host.offsetHeight);
    if (!w || !h || (w === HB.w && h === HB.h)) return;
    HB.w = w;
    HB.h = h;
    HB.dpr = Math.min(2, window.devicePixelRatio || 1);
    HB.cv.width = w * HB.dpr;
    HB.cv.height = h * HB.dpr;
    HB.ctx.setTransform(HB.dpr, 0, 0, HB.dpr, 0, 0);
    HB.layout();
    HB.kick();
    if (HB.onResize) HB.onResize();
  },
  set: function (sectors, mood, low, still) {
    HB.resize(); // measure again: the stage may have been hidden (zero size) when the brain started
    var key = JSON.stringify([sectors, mood, low, still]);
    var moved = still !== HB.still || low !== HB.low;
    HB.sectors = sectors;
    HB.mood = mood;
    HB.low = low;
    HB.still = still;
    HB.fx();
    if (key !== HB.key) {
      HB.key = key;
      HB.layout();
    }
    if (moved || HB.still) HB.kick();
  },
  dragYaw: 0, dragPitch: 0, vYaw: 0, vPitch: 0, last: 0,
  frame: function (now) {
    HB.raf = 0;
    if (!HB.w) return;
    var dt = Math.min(0.05, Math.max(0, (now - (HB.last || now)) / 1000));
    HB.last = now;
    if (HB.vYaw || HB.vPitch) { // let-go drift, fading out
      HB.dragYaw = Math.max(-1.4, Math.min(1.4, HB.dragYaw + HB.vYaw * dt));
      HB.dragPitch = Math.max(-0.7, Math.min(0.7, HB.dragPitch + HB.vPitch * dt));
      var k = Math.pow(0.06, dt);
      HB.vYaw *= k; HB.vPitch *= k;
      if (Math.abs(HB.vYaw) < 0.01 && Math.abs(HB.vPitch) < 0.01) HB.vYaw = HB.vPitch = 0;
    }
    var G = HB.geom(),
      t = HB.still ? 2 : ((now - HB.t0) / 1000) * (HB.low ? 0.5 : 1);
    HB.core = hbDraw(
      HB.M,
      HB.ctx,
      HB.w,
      HB.h,
      G.cx,
      G.cy,
      G.S,
      t,
      HB.mood,
      !HB.still,
    );
    if ((!HB.still || HB.vYaw || HB.vPitch) && !document.hidden) HB.raf = requestAnimationFrame(HB.frame);
  },
  kick: function () {
    if (!HB.raf) HB.raf = requestAnimationFrame(HB.frame);
  },
  /* fibres (SVG) and dial buttons, placed from the brain centre */
  layout: function () {
    if (!HB.w || !HB.nodes) return;
    var G = HB.geom(),
      S = G.S,
      cx = G.cx,
      cy = G.cy,
      ns = "http://www.w3.org/2000/svg",
      svg = HB.svg,
      still = HB.still;
    /* Compact: a short brain area (small window). Dials shrink, lose the "next" line and spread by width. */
    /* The full layout spaces dials by brain size. The top and lower dials on each side are 1.18 S apart and need
       about 150 px (dial plus one label line), so a brain smaller than that switches to the compact rows. */
    var P0 = HB_PLACES, gapNeed = 150;
    var compact = HB.h < 520 || (P0.security.dy - P0.school.dy) * S < gapNeed, hw = Math.min(HB.w * 0.34, 560);
    /* roomy compact: the rows are far enough apart for full-size dials with their "next" line */
    var topY = Math.max(138, HB.h * 0.3), lowY = HB.h - 152, roomy = compact && lowY - topY >= 190;
    if (compact && !roomy) { topY = Math.max(96, HB.h * 0.3); lowY = HB.h - 108; }
    var small = compact && !roomy, half = small ? 43 : 52;
    HB.host.classList.toggle("compact", compact);
    HB.host.classList.toggle("roomy", roomy);
    svg.setAttribute("viewBox", "0 0 " + HB.w + " " + HB.h);
    svg.innerHTML = "";
    HB.nodes.innerHTML = "";
    HB.sectors.forEach(function (s, i) {
      var P = HB_PLACES[s.id],
        x = compact ? cx + (P.dx / 2.55) * hw : cx + P.dx * S,
        y = compact ? (P.dy < 0 ? topY : lowY) : cy + P.dy * S,
        ang = compact ? Math.atan2(y - cy, x - cx) : Math.atan2(P.dy, P.dx);
      var ax = cx + Math.cos(ang) * S * 1.28,
        ay = P.dx ? cy + Math.sin(ang) * S * 0.8 : cy + S * 1.0;
      var L = Math.hypot(ax - x, ay - y) || 1,
        /* side dials send their fibre out sideways at the dial's middle, so it never crosses their own caption */
        ex = P.dx ? x + (ax > x ? 1 : -1) * (small ? 42 : 50) : x + ((ax - x) / L) * (small ? 42 : 50),
        ey = P.dx ? y : y + ((ay - y) / L) * (small ? 42 : 50),
        mx = (ex + ax) / 2,
        my = (ey + ay) / 2,
        bend = P.dx ? 0.16 : 0;
      var d =
        "M" +
        ex.toFixed(1) +
        " " +
        ey.toFixed(1) +
        " Q" +
        (mx - (ay - ey) * bend).toFixed(1) +
        " " +
        (my + (ax - ex) * bend * (P.dx > 0 ? -1 : 1)).toFixed(1) +
        " " +
        ax.toFixed(1) +
        " " +
        ay.toFixed(1);
      var inner =
        " Q" +
        ((ax + cx) / 2).toFixed(1) +
        " " +
        ay.toFixed(1) +
        " " +
        cx.toFixed(1) +
        " " +
        (cy + S * 0.04).toFixed(1);
      var g = document.createElementNS(ns, "g"),
        dim = s.count ? 1 : 0.45,
        dur = 3.4 + i * 0.5;
      var html =
        '<path d="' +
        d +
        '" fill="none" stroke="' +
        s.color +
        '" stroke-opacity="' +
        (s.now ? 0.8 : 0.45) * dim +
        '" stroke-width="' +
        (s.now ? 1.5 : 1.1) +
        '"/>' +
        '<path d="M' +
        ax.toFixed(1) +
        " " +
        ay.toFixed(1) +
        inner +
        '" fill="none" stroke="' +
        s.color +
        '" stroke-opacity="' +
        0.28 * dim +
        '" stroke-width="1" stroke-dasharray="2 5"/>' +
        '<circle cx="' +
        ax.toFixed(1) +
        '" cy="' +
        ay.toFixed(1) +
        '" r="3" fill="none" stroke="' +
        s.color +
        '" stroke-width="1.2"/>';
      if (!still && s.count) {
        for (var k = 0; k < 2; k++) {
          var begin = (k * 1.7 + i * 0.4).toFixed(2) + "s",
            path = d + inner;
          html +=
            '<circle cx="' +
            cx.toFixed(1) +
            '" cy="' +
            (cy + S * 0.04).toFixed(1) +
            '" r="' +
            (S * 0.17).toFixed(1) +
            '" fill="' +
            s.color +
            '" opacity="0" style="filter:blur(7px);mix-blend-mode:screen"><animate attributeName="opacity" values="0;0;.6;0" keyTimes="0;.9;.96;1" dur="' +
            dur +
            's" begin="' +
            begin +
            '" repeatCount="indefinite"/></circle>' +
            '<circle r="6" fill="' +
            s.color +
            '" fill-opacity=".22"><animateMotion dur="' +
            dur +
            's" begin="' +
            begin +
            '" repeatCount="indefinite" path="' +
            path +
            '"/></circle>' +
            '<circle r="2" fill="#fff"><animateMotion dur="' +
            dur +
            's" begin="' +
            begin +
            '" repeatCount="indefinite" path="' +
            path +
            '"/></circle>';
        }
      }
      g.innerHTML = html;
      svg.appendChild(g);
      var cap = !s.count
        ? s.repeating ? s.repeating + " repeating" : "clear"
        : s.id === "play"
          ? "playground"
          : s.focus
            ? "one at a time" + (s.later ? " · " + s.later + " later" : "")
            : s.week
              ? s.week +
                " this week" +
                (s.count > s.week ? " · " + (s.count - s.week) + " later" : "")
              : s.count + " later";
      /* a dial opens its sector when the skin says that view is built (HB.canOpen); otherwise it is a picture */
      var openable = !!(HB.canOpen && HB.canOpen(s.id));
      var b = document.createElement(openable ? "button" : "div");
      b.className = "dialn" + (s.count ? "" : " empty") + (s.now ? " now" : "");
      b.dataset.id = s.id;
      b.style.setProperty("--c", s.color);
      b.dataset.hx = x;
      b.dataset.hy = y - half;
      b.style.left = x + "px";
      b.style.top = y - half + "px";
      if (openable) {
        b.type = "button";
        b.setAttribute("aria-expanded", "false");
        b.addEventListener("click", function () { if (HB.onOpen) HB.onOpen(s.id); });
      } else b.setAttribute("role", "img");
      b.setAttribute(
        "aria-label",
        "Sector " +
          s.no +
          ", " +
          s.label +
          ": " +
          s.count +
          (s.id === "play" ? " in the playground" : " open") +
          (s.week ? ", " + s.week + " due this week" : "") +
          (s.next ? ". Next: " + s.next : "") +
          (s.now ? ". Holds what to do now." : ""),
      );
      b.innerHTML =
        (s.now
          ? '<span class="nowtag" style="background:' + s.color + '">now</span>'
          : "") + hbDialSvg(s);
      /* one caption line: the sector's name in its colour, then the counts. "Next" lives on the dock's strip */
      var c1 = document.createElement("span");
      c1.className = "sec";
      var nm = document.createElement("b");
      nm.style.color = s.count ? s.color : "#4ade80";
      nm.textContent = s.label;
      c1.append(nm, document.createTextNode(" · " + cap));
      b.append(c1);
      HB.nodes.appendChild(b);
    });
    HB.place();
  },
  /* open sector: that dial glides left and grows, the others fade; null puts every dial home */
  openId: null,
  canOpen: null,
  onOpen: null,
  openAt: function () { return { x: Math.max(180, HB.w * 0.17), y: HB.h * 0.46 }; },
  setOpen: function (id) { HB.openId = id; HB.place(); },
  fx: function () {
    HB.cv.style.filter = (HB.openId ? "blur(3px) " : "") + (HB.low ? "hue-rotate(28deg) saturate(.65) brightness(.85)" : "");
  },
  place: function () {
    if (!HB.nodes) return;
    var at = HB.openAt();
    HB.host.classList.toggle("xopen", !!HB.openId);
    HB.fx();
    Array.prototype.forEach.call(HB.nodes.children, function (b) {
      var me = b.dataset.id === HB.openId;
      b.classList.toggle("sel", me);
      if (b.tagName === "BUTTON") {
        b.setAttribute("aria-expanded", String(me));
        b.tabIndex = HB.openId && !me ? -1 : 0;
      }
      b.style.left = (me ? at.x : +b.dataset.hx) + "px";
      b.style.top = (me ? at.y - 52 : +b.dataset.hy) + "px";
    });
  },
};
