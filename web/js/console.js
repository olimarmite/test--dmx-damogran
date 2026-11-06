// Console MagicQ / Mini Connect et controleurs MIDI.
let source = "mq", strip = null, learn = false, stripsKey = "", lastVals = {}, liveUntil = {};
const midi = { access: null, name: "", vals: {}, order: [], error: "" };
function targetGroups() {
  const fx = config.fixtures, sc = state.scenes || [];
  return [
    ["Luminosité", [["dim:all", "Tous"]].concat(fx.map(f => ["dim:" + f.id, f.name]))],
    ["Couleur", [["white:all", "Blanc chaud → froid"], ["hue:all", "Teinte"]]],
    ["Transition vers une ambiance", sc.map(s => ["xfade:" + s.id, "→ " + s.name])],
    ["Lancer une ambiance (GO à mi-course)", sc.map(s => ["scene:" + s.id, "GO " + s.name])],
    ["Effets", FX.map(([id, label]) => ["fx:" + id, label]).concat([["fxspeed", "Vitesse"]])],
    ["Général", [["master", "Lumière générale"], ["blackout", "Blackout"], ["", "Rien"]]],
  ].filter(g => g[1].length);
}
function targetLabel(t) {
  if (!t) return "rien";
  for (const [, items] of targetGroups()) for (const [v, label] of items) if (v === t) return label;
  return "?";
}
const curMap = () => (source === "mq" ? (config.input || {}).map : (config.input || {}).midi_map) || {};
function stripKeys() {
  if (source === "mq") return Array.from({ length: 10 }, (_, i) => String(i + 1));
  const num = k => +k.replace(/\D/g, "");
  return [...new Set(Object.keys(curMap()).concat(midi.order))].sort((a, b) => a[0] === b[0] ? num(a) - num(b) : a < b ? -1 : 1);
}
const stripValue = k => source === "mq" ? ((input && input.values) || [])[+k - 1] ?? 0 : Math.round((midi.vals[k] ?? 0) * 255 / 127);
const stripLabel = k => source === "mq" ? k : k.startsWith("cc") ? "CC " + k.slice(2) : "Note " + k.slice(1);
async function setTarget(key, target) {
  const m = Object.assign({}, curMap());
  if (target) m[key] = target; else delete m[key];
  try { await api("/api/input", source === "mq" ? { map: m } : { midi_map: m }); stripsKey = ""; await poll(); } catch (e) { alert("Erreur : " + e.message); }
}
function renderConsole() {
  if (!config || !input) return;
  const now = Date.now();
  // une colonne s'allume quand son fader bouge ; en mode Apprendre, elle se selectionne
  for (const k of stripKeys()) {
    const v = stripValue(k), id = source + k;
    if (lastVals[id] !== undefined && lastVals[id] !== v) { liveUntil[id] = now + 1500; if (learn) { strip = k; learn = false; stripsKey = ""; } }
    lastVals[id] = v;
  }
  const seen = input.seen, mqOk = (config.input || {}).enabled && seen !== null && seen < 3;
  const srcs = [
    ["mq", "MagicQ · Mini Connect", mqOk ? "ok" : "", mqOk ? `connectée, reçue de ${input.source}` : (config.input || {}).enabled ? "pas de signal pour l'instant" : "écoute coupée", "passe par MagicQ, en Art-Net"],
    ["midi", "Contrôleur MIDI", midi.name ? "ok" : "", midi.name ? midi.name + " branché" : midi.error || "aucun contrôleur branché", "lu directement par le navigateur de ce PC"],
  ];
  const keys = stripKeys();
  if (strip === null || !keys.includes(strip)) strip = keys[0] ?? null;
  const key = JSON.stringify([source, keys, curMap(), strip, srcs.map(s => s[3]), (state.scenes || []).map(s => s.name), config.fixtures.map(f => f.name)]);
  if (key !== stripsKey) {
    stripsKey = key;
    $("sources").innerHTML = "";
    for (const [id, name, dot, status, how] of srcs) $("sources").append(el("button", { class: "source", type: "button", "aria-pressed": String(source === id), onclick: () => { source = id; strip = null; stripsKey = ""; renderConsole(); } },
      el("b", {}, name), el("span", {}, el("i", { class: "dot " + dot, "aria-hidden": "true" }), status), el("span", { style: "color:var(--ink-3)" }, how)));
    $("mqConn").hidden = source !== "mq";
    $("deskName").textContent = source === "mq" ? "Mini Connect : faders 1 à 10" : (midi.name || "Contrôleur MIDI");
    const box = $("strips"); box.innerHTML = "";
    if (!keys.length) box.append(el("p", { class: "help" }, "Bouge un fader ou appuie sur un bouton du contrôleur : il apparaît ici."));
    for (const k of keys) {
      const t = curMap()[k] || "";
      box.append(el("button", { class: "strip", type: "button", "data-k": k, "aria-pressed": String(k === strip), "aria-label": `Fader ${stripLabel(k)} : ${targetLabel(t)}`, onclick: () => { strip = k; stripsKey = ""; renderConsole(); } },
        el("span", { class: "no" }, stripLabel(k)), el("span", { class: "rail", "aria-hidden": "true" }, el("i"), el("b")), el("span", { class: "v" }), el("span", { class: "as" }, targetLabel(t))));
    }
    $("assignTitle").textContent = strip === null ? "Aucun fader" : "Fader " + stripLabel(strip);
    $("assignNow").textContent = strip === null ? "" : "commande : " + targetLabel(curMap()[strip] || "");
    const groups = $("assignGroups"); groups.innerHTML = "";
    if (strip !== null) for (const [title, items] of targetGroups()) {
      const opts = el("div", { class: "opts" });
      for (const [v, label] of items) opts.append(el("button", { class: "btn", type: "button", "aria-pressed": String((curMap()[strip] || "") === v), onclick: () => setTarget(strip, v) }, label));
      groups.append(el("div", { class: "grp" }, el("span", {}, title), opts));
    }
  }
  for (const b of $("strips").querySelectorAll(".strip")) {
    const k = b.dataset.k, p = stripValue(k) / 255 * 100;
    b.querySelector(".rail i").style.height = `calc(${p}% - ${p * 0.02}px)`;
    b.querySelector(".rail b").style.bottom = `calc(${p}%)`;
    b.querySelector(".v").textContent = Math.round(p) + " %";
    b.classList.toggle("live", (liveUntil[source + k] || 0) > now);
  }
  $("learnBtn").setAttribute("aria-pressed", String(learn));
  $("learnBtn").textContent = learn ? "J'écoute la console…" : "Apprendre un fader";
  $("learnHint").textContent = learn ? "Bouge un fader sur la console : il se sélectionne ici tout seul." : "";
  $("inStatus").textContent = !(config.input || {}).enabled ? "" : seen === null ? "Aucun signal reçu pour l'instant." : seen < 3 ? `Signal reçu de ${input.source}.` : `Plus de signal depuis ${Math.round(seen)} s.`;
  $("inConflict").hidden = !config.fixtures.some(f => f.universe === (+$("inUniverse").value || 0));
}
$("learnBtn").onclick = () => { learn = !learn; renderConsole(); };
$("inEnabled").onchange = e => api("/api/input", { enabled: e.target.checked }).then(poll);
$("inUniverse").onchange = e => api("/api/input", { universe: +e.target.value || 0 }).then(poll);
// MIDI : le navigateur lit le controleur (Chrome, Edge) et transmet chaque mouvement au serveur
function onMidi(data) {
  const [st, d1, d2] = data, kind = st & 0xf0;
  let key, v;
  if (kind === 0xb0) { key = "cc" + d1; v = d2; }
  else if (kind === 0x90) { key = "n" + d1; v = d2 ? 127 : 0; }
  else if (kind === 0x80) { key = "n" + d1; v = 0; }
  else return;
  midi.vals[key] = v;
  if (!midi.order.includes(key)) { midi.order.push(key); stripsKey = ""; }
  api("/api/midi", { key, value: v }).catch(() => { });
  if (view === "reglages" && pane === "console" && source === "midi") renderConsole();
}
window.damogranMidi = onMidi;   // pour les tests
function midiInputs() {
  const ins = [...midi.access.inputs.values()];
  midi.name = ins.map(i => i.name).join(", ");
  for (const i of ins) i.onmidimessage = e => onMidi(e.data);
  stripsKey = "";
}
if (navigator.requestMIDIAccess) {
  navigator.requestMIDIAccess().then(a => { midi.access = a; midiInputs(); a.onstatechange = midiInputs; })
    .catch(() => { midi.error = "accès MIDI refusé par le navigateur"; });
} else midi.error = "ce navigateur ne lit pas le MIDI (utilise Chrome ou Edge sur le PC)";
