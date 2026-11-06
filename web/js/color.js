// Couleurs des LED et effets : memes formules que app/colors.py et app/effects.py.
// chromaticite CIE 1931 (x, y) et flux relatif de chaque LED. Valeurs typiques de LED de theatre,
// pas des mesures des ColorSource : la correction vert / rose sert a ajuster a l'oeil.
const EMITTERS = { r: [0.700, 0.299, 0.28], g: [0.170, 0.700, 0.60], b: [0.145, 0.045, 0.07], l: [0.410, 0.550, 1.00], w: [0.330, 0.340, 1.00], a: [0.570, 0.425, 0.45], u: [0.170, 0.010, 0.01] };
const xyzOf = (x, y, Y) => [x / y * Y, Y, (1 - x - y) / y * Y];
function planckXy(T) {   // Kim et al., 2002
  const x = T <= 4000 ? -0.2661239e9 / T ** 3 - 0.2343589e6 / T ** 2 + 0.8776956e3 / T + 0.179910
                      : -3.0258469e9 / T ** 3 + 2.1070379e6 / T ** 2 + 0.2226347e3 / T + 0.240390;
  const y = T <= 2222 ? -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
          : T <= 4000 ? -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
                      : 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - 0.37001483;
  return [x, y];
}
function whiteXy(T, duv) {   // blanc vise, decale de duv perpendiculairement au corps noir (+ vert, - rose)
  const uv = (x, y) => { const d = -2 * x + 12 * y + 3; return [4 * x / d, 6 * y / d]; };
  const [u0, v0] = uv(...planckXy(T)), [u1, v1] = uv(...planckXy(T + 10));
  const n = Math.hypot(u1 - u0, v1 - v0);
  let nu = -(v1 - v0) / n, nv = (u1 - u0) / n;
  if (nv < 0) { nu = -nu; nv = -nv; }
  const u = u0 + duv * nu, v = v0 + duv * nv, d = 2 * u - 8 * v + 4;
  return [3 * u / d, 2 * v / d];
}
const det3 = m => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
function solve3(m, b) {
  const d = det3(m);
  return [0, 1, 2].map(i => det3(m.map((row, r) => row.map((v, c) => c === i ? b[r] : v))) / d);
}
const mixCache = new Map();
function whiteMix(chans, T, duv) {   // melange (0..1) qui donne ce blanc avec le plus de lumiere possible
  const key = chans + T + "/" + duv;
  if (mixCache.has(key)) return mixCache.get(key);
  const base = ["r", "g", "b"].filter(c => chans.includes(c)), extra = ["l", "w", "a"].find(c => chans.includes(c));
  if (base.length < 3) return {};
  const [x, y] = whiteXy(T, duv), t = xyzOf(x, y, 1), em = {};
  for (const c of base.concat(extra ? [extra] : [])) em[c] = xyzOf(...EMITTERS[c]);
  const m = [0, 1, 2].map(k => base.map(c => em[c][k]));
  const u = solve3(m, t), w = extra ? solve3(m, em[extra]) : [0, 0, 0];
  let best = null;
  const steps = extra ? 200 : 0;
  for (let i = 0; i <= steps; i++) {
    const d = steps ? i / steps : 0;
    let lo = 0, hi = Infinity, ok = true;
    for (let j = 0; j < 3; j++) {   // chaque LED de base : 0 <= s*u - d*w <= 1
      const ui = u[j], wi = w[j];
      if (Math.abs(ui) < 1e-12) { ok = ok && -d * wi >= 0 && -d * wi <= 1; continue; }
      const a = d * wi / ui, b = (1 + d * wi) / ui;
      if (ui > 0) { lo = Math.max(lo, a); hi = Math.min(hi, b); } else { lo = Math.max(lo, b); hi = Math.min(hi, a); }
    }
    if (ok && lo <= hi && (!best || hi > best[0])) best = [hi, d, u.map((ui, j) => hi * ui - d * w[j])];
  }
  const out = {};
  if (best) {
    base.forEach((c, j) => out[c] = best[2][j]);
    if (extra) out[extra] = best[1];
    const top = Math.max(...Object.values(out)) || 1;
    for (const c in out) out[c] = Math.max(0, out[c] / top);
  }
  mixCache.set(key, out);
  return out;
}
// couleur a montrer pour des valeurs de LED (0..255) : somme des LED en XYZ, puis sRGB (le plus fort a 255)
function displayRgb(st) {
  let X = 0, Y = 0, Z = 0;
  for (const [c, e] of Object.entries(EMITTERS)) {
    const v = (st[c] || 0) / 255;
    if (v > 0) { const p = xyzOf(...e); X += v * p[0]; Y += v * p[1]; Z += v * p[2]; }
  }
  if (Y <= 0) return [0, 0, 0];
  const lin = [3.2406 * X - 1.5372 * Y - 0.4986 * Z, -0.9689 * X + 1.8758 * Y + 0.0415 * Z, 0.0557 * X - 0.2040 * Y + 1.0570 * Z].map(v => Math.max(0, v));
  const top = Math.max(...lin) || 1, gam = v => v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
  return lin.map(v => Math.round(255 * gam(v / top)));
}
function whiteVals(lay, k, tint = 0) {   // valeurs des LED pour un blanc a k kelvins sur ce projecteur
  k = Math.round(Math.max(KMIN, Math.min(KMAX, k)) / 50) * 50; tint = Math.max(-100, Math.min(100, Math.round(tint)));
  const chans = ["R", "G", "B", "L", "W", "A"].filter(c => lay.includes(c)).join("").toLowerCase();
  const mix = whiteMix(chans, k, -tint * 0.00012), out = {};
  for (const c of ["r", "g", "b", "w", "l", "a"]) out[c] = Math.round((mix[c] || 0) * 255);
  [out.h, out.s] = rgbToHs(...displayRgb(out));
  out.k = k; out.tint = tint;
  return out;
}
function hsToRgb(h, s) {
  s /= 255; const f = n => { const k = (n + h / 60) % 6; return 255 * (1 - s * Math.max(0, Math.min(k, 4 - k, 1))); };
  return [f(5), f(3), f(1)].map(Math.round);
}
function rgbToHs(r, g, b) {
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) h = max === r ? 60 * (((g - b) / d) % 6) : max === g ? 60 * ((b - r) / d + 2) : 60 * ((r - g) / d + 4);
  if (h < 0) h += 360;
  return [Math.round(h), max ? Math.round(255 * d / max) : 0];
}
const NAMED = [["rouge", 0], ["orange", 25], ["ambre", 40], ["jaune", 55], ["vert", 120], ["turquoise", 170], ["bleu", 225], ["violet", 270], ["magenta", 310], ["rose", 340], ["rouge", 360]];
function colorName(st) {
  if (st.k && st.k >= KMIN) return st.k <= 3400 ? "blanc chaud" : st.k >= 5200 ? "blanc froid" : "blanc neutre";
  const [r, g, b] = displayRgb(st), [h, s] = rgbToHs(r, g, b);
  if (!r && !g && !b) return "aucune couleur";
  if (s < 45) return "blanc";
  return NAMED.reduce((a, x) => Math.abs(x[1] - h) < Math.abs(a[1] - h) ? x : a)[0] + (s < 140 ? " pâle" : "");
}
// fond d'un apercu : la couleur reste lisible a faible luminosite (assombrie, jamais noire)
function swatchBg(st, k) {
  const [r, g, b] = displayRgb(st), f = 0.3 + 0.7 * Math.min(1, k);
  return `rgb(${r * f | 0},${g * f | 0},${b * f | 0})`;
}
// effets : memes formules que app/effects.py, pour animer les apercus
function noise(i, seg) { const x = Math.sin(i * 12.9898 + seg * 78.233) * 43758.5453; return x - Math.floor(x); }
function effectValues(name, i, n, ph, base, lay) {
  if (name === "chase") {
    const p = (ph * 2) % n, d0 = Math.abs(i - p), d = Math.min(d0, n - d0);
    const out = Object.assign({}, base);
    if (!["r", "g", "b", "l", "w"].some(k => base[k])) Object.assign(out, whiteVals(lay, 3200));
    out.dim = 255 * Math.max(0, 1 - d / 1.2);
    return out;
  }
  if (name === "party") {
    const [r, g, b] = hsToRgb((ph * 36 + i * 360 / Math.max(n, 1)) % 360, 255);
    return { dim: 255 * (0.8 + 0.2 * Math.sin(ph * 4 + i)), r, g, b, l: 0, w: 0 };
  }
  return Object.assign(whiteVals(lay, 3200), { dim: 255 * (0.55 + 0.45 * noise(i, Math.floor(ph * 8))) });
}
function layoutOf(fx) { return String(fx.layout || "").toUpperCase().split(/[,; ]+/).filter(Boolean); }
function fxState(id) { return state.fixtures[id] || (state.fixtures[id] = { dim: 0, r: 0, g: 0, b: 0 }); }
function level(st) { return state.blackout ? 0 : (st.dim ?? 0) / 255 * (state.master / 255); }
const allIds = () => config.fixtures.map(f => f.id);
const fxById = id => config.fixtures.find(f => f.id === id);
const shown = (fx, i) => {   // valeurs a montrer : l'effet en cours s'il y en a un
  const base = state.fixtures[fx.id] || {};
  return state.effect ? effectValues(state.effect.name, i, config.fixtures.length, fxPhase, base, layoutOf(fx)) : base;
};
