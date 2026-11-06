// Ecrans, rendu, animation des effets, clavier, demarrage.
let view = "spots", pane = "fixtures";
function route() {
  // sur telephone, les ambiances ont leur page (c'est elle qui sert pendant le spectacle) ;
  // sur ordinateur, elles sont dans la bande regie, au-dessus des spots
  const [v, p] = (location.hash.slice(1) || (narrow.matches ? "ambiances" : "spots")).split("/");
  const prev = view;
  view = ["ambiances", "spots", "plan", "reglages"].includes(v) ? v : "spots";
  if (view === "ambiances" && !narrow.matches) view = "spots";
  document.body.dataset.view = view;
  $("work").hidden = view === "reglages"; $("view-reglages").hidden = view !== "reglages";
  $("view-spots").hidden = view !== "spots"; $("view-plan").hidden = view !== "plan";
  for (const a of document.querySelectorAll("nav.views a")) {
    if (a.dataset.view === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  $("settingsLink").hidden = view === "reglages";
  if (view === "reglages") { if (prev !== "reglages") { settingsLoaded = false; loadSettings(); } showPane(p || pane); }
  else if (prev === "reglages") queue({ raw: null });   // le testeur de canal s'arrete en quittant les reglages
  if (config) render();
}
window.addEventListener("hashchange", route);
narrow.addEventListener("change", route);

/* ---------- rendu ---------- */
function renderChips() {
  const on = config.input && config.input.enabled, seen = input && input.seen;
  let kind = "", txt = "Console : non utilisée";
  if (on && input && input.conflict) { kind = "warn"; txt = "Console : univers à changer"; }
  else if (on && seen !== null && seen < 3) { kind = "ok"; txt = "Console connectée"; }
  else if (on) txt = "Console : pas de signal";
  if (midi.name) { kind = kind || "ok"; txt += " · MIDI"; }
  $("consoleDot").className = "dot " + kind; $("consoleText").textContent = txt;
}
function render() {
  if (!config || !state) return;
  renderChips(); renderHeader();
  renderScenes(); renderFx();   // la bande regie reste juste, meme dans les reglages
  if (view !== "reglages") { renderTools(); if (view === "spots") renderCards(); else if (view === "plan") renderPlan(); }
  else { renderDiscovery(); if (pane === "console") renderConsole(); }
}
// animation des apercus pendant un effet : au plus 3 images par seconde (pas de flash a l'ecran),
// et rien si le systeme demande moins d'animations
let fxClock = performance.now(), lastPaint = 0;
(function tick(now) {
  if (state && config && state.effect) {
    fxPhase += (now - fxClock) / 1000 * (state.effect.speed || 1);
    if (!calm && now - lastPaint > 340) { lastPaint = now; if (view === "spots") renderCards(); if (view === "plan") renderPlan(); }
  }
  fxClock = now;
  requestAnimationFrame(tick);
})(performance.now());

/* ---------- clavier ---------- */
document.addEventListener("keydown", e => {
  if (!pref("keys", true) || e.ctrlKey || e.metaKey || e.altKey || view === "reglages") return;
  if (e.target.closest("input,select,textarea,[role=slider],button,a,dialog,summary") && e.key !== "Escape") return;
  if (e.key === " ") { e.preventDefault(); go(); }
  else if (/^[1-9]$/.test(e.key)) { const s = (state.scenes || [])[+e.key - 1]; if (s) recallScene(s.id); }
  else if (e.key === "b" || e.key === "B") toggleBlackout();
  else if (e.key === "Escape" && !$("sceneDlg").open) { selected.clear(); arrange = false; moving = null; render(); }
});

route();
poll();
