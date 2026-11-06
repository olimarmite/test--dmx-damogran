// Constantes, etat partage et petits utilitaires.
const PRESETS = [
  ["Rouge", 255, 0, 0], ["Orange", 255, 110, 0], ["Jaune", 255, 220, 0], ["Vert", 0, 255, 0], ["Turquoise", 0, 255, 200],
  ["Bleu", 0, 60, 255], ["Violet", 140, 0, 255], ["Magenta", 255, 0, 190],
];
const QUICK_WHITES = [[2700, "Chaud"], [4000, "Neutre"], [6500, "Froid"]];
const KMIN = 2700, KMAX = 6500;
const PREVIEW_LAYOUT = ["R", "G", "B", "L"];   // pour dessiner les blancs des boutons et de la bande
// canaux reglables a la main : cle d'etat, nom, couleur du repere, lettre dans « Canaux » (aucune = toujours)
const CHANNELS = [["r", "Rouge", "#ff3b30"], ["g", "Vert", "#34d058"], ["b", "Bleu", "#3b6bff"], ["l", "Lime", "#c6dd3c", "L"], ["w", "Blanc", "#e8e2d6", "W"], ["a", "Ambre", "#ffa31a", "A"], ["u", "UV", "#9b6bff", "U"]];
const SHORT = { r: "R", g: "V", b: "B", l: "L", w: "W", a: "A", u: "UV" };
const FX = [["chase", "Chase"], ["party", "C'est la fête"], ["applause", "Applaudissements"]];
const FADES = [[0, "aucune"], [2, "2 s"], [5, "5 s"], [10, "10 s"]];
const CHECK = '<svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M2.5 7.5l3 3 6-7"/></svg>';

let config = null, state = null, input = null, selected = new Set(), localIps = [], discovery = null;
let pending = {}, sendTimer = null, lastEdit = 0, lastPackets = -1, lastScene = null;
const $ = id => document.getElementById(id);
const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
const narrow = matchMedia("(max-width: 760px)");   // telephone
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k.startsWith("on")) e[k] = v; else if (k === "html") e.innerHTML = v; else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids) if (k != null && k !== false) e.append(k);
  return e;
}
const pref = (k, d) => { try { const v = localStorage.getItem("damogran." + k); return v === null ? d : v === "1"; } catch (e) { return d; } };
const setPref = (k, v) => { try { localStorage.setItem("damogran." + k, v ? "1" : "0"); } catch (e) { } };
