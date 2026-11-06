// Echanges avec le serveur (ou, sur la telecommande, avec le PC par le canal P2P).
// sur la telecommande, chaque appel passe par le canal P2P ouvert par la page qui nous heberge
const REMOTE = (() => { try { return (window.parent !== window && window.parent.damoRemote) || null; } catch (e) { return null; } })();
async function api(path, body) {
  const r = await (REMOTE ? REMOTE.fetch : fetch)(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}
function queue(patch) {
  lastEdit = Date.now();
  for (const [k, v] of Object.entries(patch)) {
    if (k === "fixtures") {
      pending.fixtures = pending.fixtures || {};
      for (const [id, vals] of Object.entries(v)) pending.fixtures[id] = Object.assign(pending.fixtures[id] || {}, vals);
    } else pending[k] = v;
  }
  if (!sendTimer) sendTimer = setTimeout(flush, 30);
}
async function flush() {
  sendTimer = null;
  const body = pending; pending = {};
  try { await api("/api/state", body); } catch (e) { setStatus("err", "Erreur : " + e.message); }
}
let pollTimer = null, fxPhase = 0;
async function poll() {
  clearTimeout(pollTimer);
  let fast = false;
  try {
    const snap = await api("/api/state");
    const cfgChanged = JSON.stringify([snap.config.fixtures, snap.config.grid]) !== JSON.stringify(config && [config.fixtures, config.grid]);
    if (!state || Date.now() - lastEdit > 1500) state = snap.state;
    for (const k of ["scenes", "active_scene", "fade", "effect"]) state[k] = snap.state[k];   // toujours a jour, meme pendant une edition
    if (state.active_scene) lastScene = state.active_scene;
    if (snap.state.effect) fxPhase = snap.effect_phase;
    config = snap.config; input = snap.input;
    localIps = snap.local_ips; discovery = snap.discovery;
    if (cfgChanged) { buildCards(); buildPlan(); buildSelRaw(); }
    if (view === "reglages" && !settingsLoaded) loadSettings();   // page ouverte directement sur les reglages
    render();
    fast = snap.fading || (view === "reglages" && pane === "console");
    if (snap.error) setStatus("err", snap.error);
    else setStatus(snap.packets !== lastPackets ? "ok" : "err", `Art-Net vers ${config.target_ip}`);
    lastPackets = snap.packets;
    rcSync();
  } catch (e) { setStatus("err", REMOTE ? "La régie ne répond pas (connexion perdue ?)" : "Damogran ne répond pas : la fenêtre noire est-elle ouverte ?"); }
  pollTimer = setTimeout(poll, fast ? 150 : 1000);   // plus rapide pendant un fondu ou en reglage console
}
function setStatus(kind, txt) { $("dot").className = "dot " + kind; $("statusText").textContent = txt; }
