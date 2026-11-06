// Spots : actions, selection, cartes, panneau des spots coches.
function patchAll(ids, fn) {
  if (!ids.length) return;
  const patch = {};
  for (const id of ids) { const st = fxState(id), vals = fn(st, id); Object.assign(st, vals); patch[id] = vals; }
  queue({ fixtures: patch }); render();
}
const setDim = (ids, dim) => patchAll(ids, () => ({ dim }));
const setChannel = (ids, k, v) => patchAll(ids, () => ({ [k]: v, k: 0 }));   // un canal touche a la main : ce n'est plus un blanc calcule
function applyColor(ids, r, g, b) {   // couleur pure : blanc, lime et ambre coupes
  const [h, s] = rgbToHs(r, g, b);
  patchAll(ids, st => Object.assign({ r, g, b, w: 0, l: 0, a: 0, u: 0, h, s, k: 0 }, st.dim ? {} : { dim: 255 }));
}
function applyWhite(ids, k, tint) {
  patchAll(ids, (st, id) => Object.assign(whiteVals(layoutOf(fxById(id) || {}), k, tint ?? st.tint ?? 0), st.dim ? {} : { dim: 255 }));
}
const toggleBlackout = () => { state.blackout = !state.blackout; queue({ blackout: state.blackout }); render(); };
function toggleSel(id) { selected.has(id) ? selected.delete(id) : selected.add(id); render(); }

/* ---------- en-tete et selection ---------- */
$("master").oninput = e => { state.master = +e.target.value; queue({ master: state.master }); render(); };
$("blackout").onclick = toggleBlackout;
// un seul bouton : tout cocher, ou tout decocher des qu'un spot est coche
$("selAll").onclick = () => { if (selected.size) selected.clear(); else allIds().forEach(id => selected.add(id)); render(); };
$("gotoTools").onclick = () => { $("tools").scrollIntoView({ behavior: calm ? "auto" : "smooth" }); $("selDim").focus({ preventScroll: true }); };
function renderHeader() {
  if (document.activeElement !== $("master")) $("master").value = state.master;
  $("masterOut").textContent = Math.round(state.master / 2.55) + " %";
  $("blackout").setAttribute("aria-pressed", String(!!state.blackout));
  $("blackout").textContent = state.blackout ? "Rallumer" : "Blackout";
  const n = selected.size, names = config.fixtures.filter(f => selected.has(f.id)).map(f => f.name);
  $("selCount").textContent = n === 0 ? "Aucun spot coché" : n === config.fixtures.length ? `Tous les spots cochés (${n})`
    : `${n} spot${n > 1 ? "s" : ""} coché${n > 1 ? "s" : ""} : ${names.join(", ")}`;
  $("selCount").classList.toggle("has", n > 0);
  $("secTitle").textContent = view === "plan" ? "Plan de scène" : "Spots";
  $("selAll").textContent = n ? "Tout décocher" : "Tout cocher";
  $("gotoTools").hidden = n === 0 || !narrow.matches;   // sur telephone, le panneau est sous les cartes
}

/* ---------- cartes des spots ---------- */
let cardFaders = {};
function presentChannels(ids) {
  const lay = new Set(ids.flatMap(id => layoutOf(fxById(id) || {})));
  return CHANNELS.filter(c => !c[3] || lay.has(c[3]));
}
function buildCards() {
  const box = $("cards"); box.innerHTML = ""; cardFaders = {};
  if (!config.fixtures.length) { box.append(el("p", { class: "empty" }, "Aucun projecteur. Va dans Réglages > Projecteurs pour les ajouter ou les chercher.")); return; }
  config.fixtures.forEach(fx => {
    const faders = {};
    faders.dim = makeFader({ label: `Luminosité de ${fx.name}`, short: "Lum.", cls: "mini lum", fill: "#d9d2c5", onInput: v => setDim([fx.id], v) });
    for (const [k, name, color] of presentChannels([fx.id])) faders[k] = makeFader({ label: `${name} de ${fx.name}`, short: SHORT[k], cls: "mini", fill: color, onInput: v => setChannel([fx.id], k, v) });
    cardFaders[fx.id] = faders;
    const { dim, ...chans } = faders;
    const card = el("article", { class: "card", "data-id": fx.id, "aria-label": fx.name },
      el("button", { class: "toggle", type: "button", "aria-pressed": "false", onclick: () => toggleSel(fx.id) },
        el("span", { class: "swatch" }, el("span", { class: "box", html: CHECK })),
        el("span", { class: "who" }, el("span", { class: "nm" }, fx.name), el("span", { class: "st" }))),
      el("div", { class: "minis" }, dim.el, el("div", { class: "chans" }, ...Object.values(chans).map(f => f.el))));
    box.append(card);
  });
}
function renderCards() {
  config.fixtures.forEach((fx, i) => {
    const card = $("cards").querySelector(`.card[data-id="${fx.id}"]`); if (!card) return;
    const base = state.fixtures[fx.id] || {}, st = shown(fx, i), k = level(st), on = selected.has(fx.id);
    card.classList.toggle("sel", on);
    const tg = card.querySelector(".toggle");
    tg.setAttribute("aria-pressed", String(on));
    const txt = k > 0.004 ? `${colorName(st)}, ${Math.round(k * 100)} %` : "éteint";
    tg.setAttribute("aria-label", `${fx.name} : ${txt}. ${on ? "Coché" : "Pas coché"}`);
    card.querySelector(".st").textContent = state.effect ? "effet en cours" : txt.charAt(0).toUpperCase() + txt.slice(1);
    const sw = card.querySelector(".swatch");
    sw.classList.toggle("off", k <= 0.004);
    sw.style.background = k > 0.004 ? swatchBg(st, k) : "";
    const f = cardFaders[fx.id];
    if (f) for (const [c, fd] of Object.entries(f)) fd.set(base[c] ?? 0);
  });
}

/* ---------- panneau « pour les spots coches » ---------- */
const sel = () => config.fixtures.filter(f => selected.has(f.id)).map(f => f.id);   // dans l'ordre des spots
let selRawFaders = {};
function buildSelRaw() {
  $("selRaw").innerHTML = ""; selRawFaders = {};
  for (const [k, name, color] of presentChannels(allIds())) {
    selRawFaders[k] = makeFader({ label: `${name} des spots cochés`, short: name, fill: color, onInput: v => setChannel(sel(), k, v) });
    $("selRaw").append(selRawFaders[k].el);
  }
}
for (const [name, r, g, b] of PRESETS) {
  const [dr, dg, db] = displayRgb({ r, g, b });
  const sw = el("button", { class: "sw", type: "button", "aria-label": name }, el("i"), name);
  sw.querySelector("i").style.background = `rgb(${dr},${dg},${db})`;
  sw.onclick = () => applyColor(sel(), r, g, b);
  $("swatches").append(sw);
}
for (const [k, label] of QUICK_WHITES) {
  const [r, g, b] = displayRgb(whiteVals(PREVIEW_LAYOUT, k));
  const q = el("button", { type: "button", "aria-label": `Blanc ${label.toLowerCase()} (${k} K)` }, label, el("br"), el("small", {}, k + " K"));
  q.style.background = `rgb(${r},${g},${b})`;
  q.onclick = () => applyWhite(sel(), k, 0);
  $("quickWhites").append(q);
}
const temp = $("temp");
temp.style.background = `linear-gradient(to right, ${[2700, 3200, 4000, 5000, 5600, 6500].map(k => { const [r, g, b] = displayRgb(whiteVals(PREVIEW_LAYOUT, k)); return `rgb(${r},${g},${b}) ${(k - KMIN) / (KMAX - KMIN) * 100}%`; }).join(", ")})`;
function tempPick(e) {
  const r = temp.getBoundingClientRect(), x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  applyWhite(sel(), KMIN + x * (KMAX - KMIN));
}
temp.addEventListener("pointerdown", e => { temp.setPointerCapture(e.pointerId); temp.dataset.drag = "1"; tempPick(e); });
temp.addEventListener("pointermove", e => { if (temp.dataset.drag) tempPick(e); });
temp.addEventListener("pointerup", () => delete temp.dataset.drag);
temp.addEventListener("keydown", e => {
  const k = (state.fixtures[sel()[0]] || {}).k || 3200, d = { ArrowLeft: -100, ArrowDown: -100, ArrowRight: 100, ArrowUp: 100 }[e.key];
  if (d) { e.preventDefault(); applyWhite(sel(), k + d); }
});
$("tint").oninput = e => { const st = state.fixtures[sel()[0]] || {}; applyWhite(sel(), st.k || 3200, +e.target.value); };
$("selDim").oninput = e => setDim(sel(), +e.target.value);
$("identify").onclick = () => queue({ identify: sel() });
function renderTools() {
  const ids = sel(), n = ids.length, names = ids.map(id => fxById(id).name);
  $("tools").classList.toggle("off", n === 0);
  $("toolsWhy").hidden = n > 0;
  for (const c of $("tools").querySelectorAll(".body button, .body input, .body [tabindex]")) c.toggleAttribute("disabled", n === 0);
  $("temp").tabIndex = n ? 0 : -1;
  const all = n === config.fixtures.length;
  $("toolsTitle").textContent = n === 0 ? "Aucun spot coché" : all ? "Tout le plateau" : n === 1 ? names[0] : `${n} spots`;
  $("toolsWho").textContent = n > 1 && !all ? names.join(", ") : "";
  if (!n) return;
  const st = state.fixtures[ids[0]] || {};
  if (document.activeElement !== $("selDim")) $("selDim").value = st.dim ?? 0;
  $("selDimOut").textContent = Math.round((st.dim ?? 0) / 2.55) + " %";
  for (const [k, f] of Object.entries(selRawFaders)) f.set(st[k] ?? 0);
  const k = st.k || 0, tint = st.tint || 0;
  $("tempMark").hidden = !k;
  if (k) { $("tempMark").style.left = ((k - KMIN) / (KMAX - KMIN) * 100) + "%"; temp.setAttribute("aria-valuenow", k); temp.setAttribute("aria-valuetext", k + " K, " + colorName(st)); }
  $("kOut").textContent = k ? `${colorName(st)} · ${k} K` : "";
  if (tint) $("tintBox").open = true;   // une correction deja reglee reste visible
  if (document.activeElement !== $("tint")) $("tint").value = tint;
  const tt = tint === 0 ? "neutre" : tint < 0 ? `plus vert (${-tint})` : `plus rose (${tint})`;
  $("tintOut").textContent = tt; $("tint").setAttribute("aria-valuetext", tt);
}
