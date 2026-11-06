// Telecommande telephone (P2P).
/*
   Le PC de regie (cette page, ouverte en local) s'inscrit sur le relais PeerJS et attend les telephones.
   Le telephone ouvre la page statique (remote/index.html), s'y connecte en WebRTC, envoie la cle du QR code,
   recoit cette interface et la fait tourner : chaque appel /api passe ensuite par le canal de donnees.
   Le relais ne sert qu'a la mise en relation ; la lumiere passe en direct (ou par un TURN si le reseau bloque). */
const CDN = {
  peer: ["https://cdn.jsdelivr.net/npm/peerjs@1.5.5/dist/peerjs.min.js", "sha384-x0YgkOr/3UOZP2CRDxGW9e0Q+2Qjyr3uJrm4xU32Y7ZCNAo7Cc7bjhrZMi/dwczu"],
  qr: ["https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.js", "sha384-8FWZA6BGMXhsfO+BLtrJK0We6gg5o1JyO8xQm6peWDEUs17ACA5ziE/NIAkl9z2k"],
};
const scripts = {};
function loadScript([src, integrity]) {
  return scripts[src] = scripts[src] || new Promise((ok, ko) => {
    const s = el("script", { src, integrity, crossorigin: "anonymous" });
    s.onload = ok; s.onerror = () => { delete scripts[src]; s.remove(); ko(new Error("pas d'Internet")); };
    document.head.append(s);
  });
}
const RC_API = new Set(["/api/state", "/api/config", "/api/input", "/api/layout", "/api/midi", "/api/scene", "/api/discover"]);
const rcHost = !REMOTE && ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
const rc = { id: "", peer: null, conns: new Set(), status: "", err: false, retry: null, qrUrl: null };
const rcCfg = () => (config && config.remote) || {};
const rnd = n => Array.from(crypto.getRandomValues(new Uint8Array(n)), b => "abcdefghijkmnpqrstuvwxyz23456789"[b % 32]).join("");
const rcSet = (txt, err = false) => { rc.status = txt; rc.err = err; renderPhone(); };
function rcSync() {
  const r = rcCfg(), want = rcHost && r.on && r.id && r.key ? r.id : "";
  if (want !== rc.id) { rcStop(); if (want) rcStart(want); }
  renderPhone();
}
function rcStop() {
  clearTimeout(rc.retry);
  for (const c of rc.conns) try { c.close(); } catch (e) { }
  rc.conns.clear();
  if (rc.peer) try { rc.peer.destroy(); } catch (e) { }
  rc.peer = null; rc.id = ""; rc.status = ""; rc.err = false;
}
function rcRetry() {
  const id = rc.id; clearTimeout(rc.retry);
  rc.retry = setTimeout(() => { if (rc.id === id) { rcStop(); rcStart(id); } }, 15000);
}
async function rcStart(id) {
  rc.id = id; rcSet("Connexion au relais…");
  try { await loadScript(CDN.peer); }
  catch (e) { if (rc.id === id) { rcSet("Ce PC n'a pas Internet : la télécommande ne peut pas démarrer. Nouvel essai dans 15 s.", true); rcRetry(); } return; }
  if (rc.id !== id) return;
  const peer = rc.peer = new Peer(id, window.DAMO_PEER || {});
  peer.on("open", () => { if (rc.peer === peer) rcSet("Prête : scanne le code avec le téléphone."); });
  peer.on("connection", c => rcAccept(c));
  peer.on("disconnected", () => {
    if (rc.peer !== peer || peer.destroyed) return;
    rcSet("Relais perdu, reconnexion…", true);
    setTimeout(() => { if (rc.peer === peer && !peer.destroyed && peer.disconnected) peer.reconnect(); }, 3000);
  });
  peer.on("error", e => {
    if (rc.peer !== peer || e.type === "peer-unavailable") return;
    rcSet(e.type === "unavailable-id" ? "Déjà active dans un autre onglet (ou sur un autre PC). Nouvel essai dans 15 s." : `Relais injoignable (${e.type}). Nouvel essai dans 15 s.`, true);
    rcRetry();
  });
}
function rcAccept(c) {
  let ok = false;
  const kick = setTimeout(() => { if (!ok) c.close(); }, 10000);
  const drop = () => { rc.conns.delete(c); renderPhone(); };
  c.on("close", drop); c.on("error", drop);
  c.on("data", async m => {
    if (!m || typeof m !== "object") return;
    if (!ok) {
      if (m.t !== "hello" || !rcCfg().key || m.k !== rcCfg().key) { c.send({ t: "denied" }); setTimeout(() => c.close(), 500); return; }
      ok = true; clearTimeout(kick); rc.conns.add(c); renderPhone();
      c.send({ t: "welcome", html: await (await fetch("/")).text() });   // le telephone fait tourner cette meme interface
      return;
    }
    if (m.t !== "req") return;
    let res;
    try {
      if (!RC_API.has(m.url)) throw new Error("adresse refusée");
      const r = await fetch(m.url, m.body == null ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: String(m.body) });
      res = { t: "res", id: m.id, status: r.status, body: await r.text() };
    } catch (e) { res = { t: "res", id: m.id, status: 502, body: JSON.stringify({ error: e.message }) }; }
    if (c.open) c.send(res);
  });
}
// enregistrements a la file : chacun part de la config deja a jour (sinon « adresse » puis « Activer » se marchent dessus)
let rcQueue = Promise.resolve();
function rcSave(patch) {
  return rcQueue = rcQueue.then(async () => {
    const r = Object.assign({ on: false, id: "", key: "", page: "" }, rcCfg(), patch);
    try { await api("/api/config", Object.assign({}, config, { remote: r })); await poll(); }
    catch (e) { rcSet("Erreur : " + e.message, true); }
  });
}
const rcPageUrl = () => $("rcPage").value.trim();
$("rcPage").onchange = () => { if (rcPageUrl() !== (rcCfg().page || "")) rcSave({ page: rcPageUrl() }); };
$("rcToggle").onclick = () => {
  const r = rcCfg();
  if (r.on) return rcSave({ on: false });
  if (!/^https?:\/\/\S+$/.test(rcPageUrl())) { $("rcPage").focus(); return rcSet("Indique d'abord l'adresse de la page télécommande (voir le README).", true); }
  rcSave({ on: true, page: rcPageUrl(), id: r.id || "damogran-" + rnd(20), key: r.key || rnd(24) });
};
$("rcNew").onclick = () => {
  if (confirm("Les téléphones connectés seront déconnectés et l'ancien code ne marchera plus. Continuer ?"))
    rcSave({ id: "damogran-" + rnd(20), key: rnd(24) });
};
function renderPhone() {
  const r = rcCfg(), n = rc.conns.size;
  $("rcOnPhone").hidden = !REMOTE; $("rcNotHere").hidden = !!REMOTE || rcHost; $("rcBox").hidden = !rcHost;
  $("rcChip").hidden = !n;
  $("rcChipText").textContent = n > 1 ? `${n} téléphones` : "Téléphone";
  if (!rcHost) return;
  if (document.activeElement !== $("rcPage")) $("rcPage").value = r.page || "";
  $("rcToggle").textContent = r.on ? "Désactiver" : "Activer";
  $("rcNew").hidden = !r.on;
  const url = r.on && r.page && r.id ? r.page.replace(/#.*$/, "") + "#p=" + r.id + "&k=" + r.key : "";
  $("rcStatus").textContent = !r.on ? (rc.err ? rc.status : "Désactivée.") : rc.status + (n ? ` · ${n} téléphone${n > 1 ? "s" : ""} connecté${n > 1 ? "s" : ""}` : "");
  $("rcStatus").style.color = rc.err ? "var(--red)" : "var(--ink)";
  $("rcLinkRow").hidden = $("rcQr").hidden = !url;
  $("rcLink").href = url; $("rcLink").textContent = url;
  if (url !== rc.qrUrl) {
    rc.qrUrl = url; $("rcQr").innerHTML = "";
    if (url) loadScript(CDN.qr).then(() => {
      if (rc.qrUrl !== url) return;
      const q = qrcode(0, "M"); q.addData(url); q.make();
      $("rcQr").innerHTML = q.createSvgTag({ cellSize: 6, margin: 2, alt: "QR code de la télécommande" });
    }).catch(() => { rc.qrUrl = null; });
  }
}
