// Bande regie : ambiances, GO, transition, effets.
function nextScene() {
  const sc = state.scenes || [], cur = state.active_scene || lastScene, i = sc.findIndex(s => s.id === cur);
  return sc.length ? sc[i >= 0 ? (i + 1) % sc.length : 0] : null;
}
let scenesKey = "";
function renderScenes() {
  const scenes = state.scenes || [], next = nextScene(), live = state.active_scene;
  const sc = scenes.find(s => s.id === (live || lastScene));
  $("liveName").textContent = state.blackout ? "Blackout" : sc ? sc.name : "réglage à la main";
  $("liveModified").hidden = state.blackout || !sc || !!live;
  $("liveEffect").hidden = state.blackout || !state.effect;
  if (state.effect) $("liveEffect").textContent = "effet : " + (FX.find(f => f[0] === state.effect.name) || [, ""])[1];
  $("goBtn").disabled = !next;
  $("goLabel").textContent = next ? `suivante : ${next.name}` : "enregistre d'abord une ambiance";
  $("goKey").hidden = !pref("keys", true);
  if (document.activeElement !== $("fades")) $("fades").value = String(state.fade);
  const key = JSON.stringify([scenes.map(s => [s.id, s.name, s.fixtures]), live, next && next.id, config.fixtures.map(f => f.id)]);
  if (key === scenesKey) return;
  scenesKey = key;
  const list = $("sceneList"); list.innerHTML = "";
  scenes.forEach((s, i) => {
    const isLive = s.id === live, isNext = next && s.id === next.id && !isLive;
    const mini = el("span", { class: "mini", "aria-hidden": "true" });
    for (const fx of config.fixtures) {
      const v = (s.fixtures || {})[fx.id]; if (!v) continue;
      const d = el("i"); d.style.background = (v.dim ?? 0) > 2 ? swatchBg(v, (v.dim ?? 0) / 255) : "#1d1b18"; mini.append(d);
    }
    list.append(el("div", { class: "tile" + (isLive ? " on" : "") },
      el("button", { class: "pick", type: "button", "aria-pressed": String(isLive), "aria-label": s.name + (isLive ? ", en scène" : isNext ? ", suivante" : ""), onclick: () => recallScene(s.id) },
        el("span", { class: "top" }, el("span", {}, i < 9 ? String(i + 1) : ""),
          isLive ? el("span", { class: "live" }, "en scène") : isNext ? el("span", {}, "· suivante") : null),
        el("span", { class: "nm" }, s.name), mini),
      el("button", { class: "edit", type: "button", "aria-label": "Modifier " + s.name, title: "Renommer, remplacer ou supprimer", onclick: () => openSceneDlg(s) }, "⋯")));
  });
  // garder l'ambiance en scene visible dans la bande, sans faire defiler la page
  const on = list.querySelector(".tile.on");
  if (on && (on.offsetLeft < list.scrollLeft || on.offsetLeft + on.offsetWidth > list.scrollLeft + list.clientWidth))
    list.scrollLeft = on.offsetLeft - list.clientWidth / 2 + on.offsetWidth / 2;
  stripFade();
}
// bande des ambiances : fondu a droite tant qu'il en reste a voir
function stripFade() {
  const s = $("sceneList");
  s.classList.toggle("more-right", s.scrollLeft + s.clientWidth < s.scrollWidth - 2);
}
$("sceneList").addEventListener("scroll", stripFade, { passive: true });
window.addEventListener("resize", stripFade);
function sceneApi(body) { return api("/api/scene", body).then(poll).catch(e => alert("Erreur : " + e.message)); }
function recallScene(id) { sceneApi({ action: "recall", id, fade: state.fade }); }
const go = () => { if (nextScene()) sceneApi({ action: "go", after: lastScene }); };
$("goBtn").onclick = go;
for (const [v, label] of FADES) $("fades").append(el("option", { value: v }, label));
$("fades").onchange = e => sceneApi({ action: "fade", fade: +e.target.value });
function openSceneDlg(sc) {
  const dlg = $("sceneDlg"), btns = $("sceneDlgBtns");
  $("sceneDlgTitle").textContent = sc ? sc.name : "Nouvelle ambiance";
  $("sceneName").value = sc ? sc.name : "Ambiance " + ((state.scenes || []).length + 1);
  btns.innerHTML = "";
  const done = body => { dlg.close(); sceneApi(body); }, name = () => $("sceneName").value.trim();
  if (sc) btns.append(
    el("button", { class: "btn primary", type: "button", onclick: () => done({ action: "rename", id: sc.id, name: name() }) }, "Renommer"),
    el("button", { class: "btn", type: "button", onclick: () => done({ action: "save", id: sc.id, name: name() }) }, "Remplacer par la lumière actuelle"),
    el("button", { class: "btn", type: "button", onclick: () => { if (confirm(`Supprimer « ${sc.name} » ?`)) done({ action: "delete", id: sc.id }); } }, "Supprimer"));
  else btns.append(el("button", { class: "btn primary", type: "button", onclick: () => done({ action: "save", name: name() }) }, "Enregistrer"));
  btns.append(el("span", { class: "spacer" }), el("button", { class: "btn quiet", type: "button", onclick: () => dlg.close() }, "Annuler"));
  $("sceneName").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); btns.querySelector("button").click(); } };
  dlg.showModal(); $("sceneName").select();
}
$("sceneNew").onclick = () => openSceneDlg(null);

/* ---------- effets ---------- */
$("fxSel").append(el("option", { value: "" }, "Aucun"), ...FX.map(([id, label]) => el("option", { value: id }, label)));
$("fxSel").onchange = e => {
  const id = e.target.value;
  state.effect = id ? { name: id, speed: +$("fxSpeed").value } : null;
  if (state.effect) fxPhase = 0;
  queue({ effect: state.effect }); render();
};
$("fxSpeed").oninput = e => { if (state.effect) { state.effect.speed = +e.target.value; queue({ effect: state.effect }); } renderFx(); };
function renderFx() {
  if (document.activeElement !== $("fxSel")) $("fxSel").value = state.effect ? state.effect.name : "";
  $("fxSpeedRow").hidden = !state.effect;   // la vitesse n'apparait que quand un effet tourne
  const sp = $("fxSpeed");
  if (state.effect && document.activeElement !== sp) sp.value = state.effect.speed;
  $("fxSpeedOut").textContent = (+sp.value).toFixed(1).replace(".", ",") + "×";
}
