// Reglages : projecteurs, decouverte, reseau, testeur de canal, clavier.
function showPane(p) {
  pane = ["fixtures", "console", "network", "phone", "keys"].includes(p) ? p : "fixtures";
  for (const b of $("subnav").querySelectorAll("button")) b.setAttribute("aria-current", String(b.dataset.pane === pane));
  for (const d of document.querySelectorAll(".pane")) d.hidden = d.dataset.pane !== pane;
  if (pane === "console") { stripsKey = ""; renderConsole(); }
  history.replaceState(null, "", "#reglages/" + pane);
}
for (const b of $("subnav").querySelectorAll("button")) b.onclick = () => showPane(b.dataset.pane);
let settingsLoaded = false;
function loadSettings() {
  if (!config) return;
  settingsLoaded = true;
  $("cfgTarget").value = config.target_ip; $("cfgPort").value = config.port; $("cfgFps").value = config.fps;
  const s = $("cfgBind"); s.innerHTML = ""; s.append(el("option", { value: "" }, "Automatique"));
  for (const ip of new Set([...localIps, config.bind_ip].filter(Boolean))) s.append(el("option", { value: ip }, ip));
  s.value = config.bind_ip || "";
  $("fxRows").innerHTML = ""; config.fixtures.forEach(f => $("fxRows").append(fxRow(f)));
  const inp = config.input || {};
  $("inEnabled").checked = !!inp.enabled; $("inUniverse").value = inp.universe ?? 1;
  $("keysOn").checked = pref("keys", true);
  checkOverlap(); discKey = ""; stripsKey = "";
}
function netValues() { return { target_ip: $("cfgTarget").value.trim() || config.target_ip, bind_ip: $("cfgBind").value, port: +$("cfgPort").value || 6454, fps: +$("cfgFps").value || 30 }; }
async function saveConfig(fixtures) {
  try { await api("/api/config", Object.assign(netValues(), { fixtures })); await poll(); loadSettings(); }
  catch (e) { alert("Enregistrement impossible : " + e.message); }
}
$("saveNet").onclick = () => saveConfig(config.fixtures);
$("saveFx").onclick = () => {
  const old = Object.fromEntries(config.fixtures.map(f => [f.id, f]));   // garde la place des spots sur le plan
  saveConfig(readRows().map(f => old[f.id] && Number.isInteger(old[f.id].x) ? Object.assign(f, { x: old[f.id].x, y: old[f.id].y }) : f));
};
function fxRow(fx) {
  const tr = el("tr", { "data-id": fx.id || "" },
    el("td", {}, el("input", { type: "text", "data-f": "name", "aria-label": "Nom" })),
    el("td", { class: "n" }, el("input", { type: "number", "data-f": "universe", min: 0, "aria-label": "Univers" })),
    el("td", { class: "n" }, el("input", { type: "number", "data-f": "address", min: 1, max: 512, "aria-label": "Adresse" })),
    el("td", {}, el("input", { type: "text", "data-f": "layout", placeholder: "D,R,G,B", "aria-label": "Canaux" })),
    el("td", {}, el("button", { class: "btn quiet", type: "button", "aria-label": "Retirer " + (fx.name || ""), onclick: () => { tr.remove(); checkOverlap(); } }, "Retirer")));
  for (const k of ["name", "universe", "address", "layout"]) tr.querySelector(`[data-f=${k}]`).value = fx[k] ?? "";
  tr.querySelectorAll("input").forEach(i => i.oninput = checkOverlap);
  return tr;
}
function readRows() {
  return [...$("fxRows").children].map((tr, i) => {
    const v = k => tr.querySelector(`[data-f=${k}]`).value;
    return { id: tr.dataset.id || ("f" + Date.now().toString(36) + i), name: v("name"), universe: +v("universe") || 0, address: +v("address") || 1, layout: v("layout") || "D,R,G,B" };
  });
}
function checkOverlap() {
  const fx = readRows(), msgs = [];
  for (let i = 0; i < fx.length; i++) for (let j = i + 1; j < fx.length; j++) {
    const a = fx[i], b = fx[j]; if (a.universe !== b.universe) continue;
    const la = layoutOf(a).length || 1, lb = layoutOf(b).length || 1;
    if (a.address < b.address + lb && b.address < a.address + la) msgs.push(`${a.name} et ${b.name} utilisent les mêmes canaux (univers ${a.universe}).`);
  }
  for (const f of fx) if (f.address + (layoutOf(f).length || 1) - 1 > 512) msgs.push(`${f.name} dépasse le canal 512.`);
  $("overlap").textContent = msgs.join("\n");
}
$("addFx").onclick = () => {
  const rows = readRows(), last = rows[rows.length - 1];
  const fx = last ? { name: "Spot " + (rows.length + 1), universe: last.universe, address: Math.min(512, last.address + (layoutOf(last).length || 1)), layout: last.layout }
                  : { name: "Spot 1", universe: 0, address: 1, layout: "D,R,G,B" };
  $("fxRows").append(fxRow(fx)); checkOverlap();
};
$("keysOn").onchange = e => { setPref("keys", e.target.checked); render(); };

// decouverte
function alreadyPatched(d) { return readRows().some(f => f.universe === d.universe && f.address === d.address); }
function addDevice(d) {
  if (alreadyPatched(d)) return;
  $("fxRows").append(fxRow({ name: d.label || d.model || ("Spot " + d.address), universe: d.universe, address: d.address, layout: d.layout }));
  checkOverlap(); renderDiscovery();
}
let discKey = "";
function renderDiscovery() {
  const d = discovery; if (!d) return;
  $("discover").disabled = d.running;
  $("discover").textContent = d.running ? "Recherche en cours…" : (d.nodes.length ? "Chercher à nouveau" : "Chercher");
  $("discPhase").textContent = d.phase || "";
  $("discError").textContent = d.error || "";
  const key = JSON.stringify([d.nodes, d.devices, readRows().map(f => [f.universe, f.address])]);
  if (key === discKey) return;
  discKey = key;
  const nodes = $("discNodes"); nodes.innerHTML = "";
  if (d.nodes.length) {
    const tb = el("tbody");
    for (const n of d.nodes) tb.append(el("tr", {},
      el("td", { class: "num" }, n.ip),
      el("td", {}, n.short_name || "sans nom", n.style ? el("span", { class: "tag" }, "console") : null),
      el("td", { class: "muted" }, n.universes.length ? "univers " + n.universes.join(", ") : "aucune sortie"),
      el("td", { class: "muted" }, n.rdm ? "RDM" : ""),
      el("td", {}, el("button", { class: "btn", type: "button", onclick: () => { $("cfgTarget").value = n.ip; showPane("network"); } }, "Envoyer ici"))));
    nodes.append(el("span", { class: "legend" }, `Nodes Art-Net (${d.nodes.length})`), el("div", { class: "tablewrap" }, el("table", {}, tb)));
  }
  const devs = $("discDevices"); devs.innerHTML = "";
  if (d.devices.length) {
    const tb = el("tbody");
    for (const x of d.devices) {
      const name = [x.label, [x.manufacturer, x.model].filter(Boolean).join(" ")].filter(Boolean).join(" · ") || x.uid;
      const action = x.error || !x.address ? el("span", { class: "muted" }, x.error || "pas d'adresse DMX")
        : alreadyPatched(x) ? el("span", { class: "muted" }, "déjà dans la liste")
        : el("button", { class: "btn", type: "button", onclick: () => addDevice(x) }, "Ajouter");
      tb.append(el("tr", {},
        el("td", { class: "num" }, `U${x.universe} · ${x.address || "?"}`), el("td", {}, name),
        el("td", { class: "muted" }, x.personality_name || (x.footprint ? x.footprint + " canaux" : "")),
        el("td", {}, x.layout || "", x.layout && !x.layout_sure ? el("span", { class: "tag attn", title: "Le projecteur ne décrit pas ses canaux : ordre deviné" }, "à vérifier") : null),
        el("td", {}, action)));
    }
    const todo = d.devices.filter(x => x.address && x.footprint && !alreadyPatched(x));
    devs.append(el("span", { class: "legend" }, `Projecteurs RDM (${d.devices.length})`), el("div", { class: "tablewrap" }, el("table", {}, tb)),
      todo.length > 1 ? el("button", { class: "btn", type: "button", onclick: () => todo.forEach(addDevice) }, `Tout ajouter (${todo.length})`) : null,
      el("p", { class: "help" }, "Pense à Enregistrer après avoir ajouté."));
  }
}
$("discover").onclick = async () => { try { await api("/api/discover", {}); discKey = ""; await poll(); } catch (e) { $("discError").textContent = "Erreur : " + e.message; } };

// testeur de canal
const sendRaw = () => { $("rawOut").textContent = $("rawVal").value;
  queue({ raw: { universe: +$("rawUni").value || 0, address: Math.max(1, Math.min(512, +$("rawAddr").value || 1)), value: +$("rawVal").value } }); };
["rawUni", "rawAddr", "rawVal"].forEach(id => $(id).oninput = sendRaw);
$("rawStop").onclick = () => { $("rawVal").value = 0; $("rawOut").textContent = "0"; queue({ raw: null }); };
