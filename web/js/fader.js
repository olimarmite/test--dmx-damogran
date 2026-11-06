// Fader vertical (souris, doigt, clavier).
function makeFader({ label, short, cls = "", fill, onInput }) {
  const root = el("div", { class: "fader " + cls, role: "slider", tabindex: 0, "aria-label": label, "aria-valuemin": 0, "aria-valuemax": 100 });
  const track = el("div", { class: "track" }), fillEl = el("div", { class: "fill" }), cap = el("div", { class: "cap" });
  const val = el("div", { class: "val" }), lab = el("div", { class: "lab", "aria-hidden": "true" }, el("i"), short || label);
  if (fill) root.style.setProperty("--fill", fill);
  track.append(fillEl, cap); root.append(val, track, lab);
  let value = 0;
  const show = v => {
    value = v; const p = v / 255;
    fillEl.style.height = `calc(${p * 100}% - ${p * 6}px)`;
    cap.style.bottom = `calc(${p * 100}% - ${p * 2}px + 1px)`;
    const pct = Math.round(p * 100); val.textContent = pct;
    root.setAttribute("aria-valuenow", pct); root.setAttribute("aria-valuetext", pct + " %");
  };
  const emit = v => { v = Math.max(0, Math.min(255, Math.round(v))); show(v); onInput(v); };
  const fromY = e => { const r = track.getBoundingClientRect(); return (1 - (e.clientY - r.top) / r.height) * 255; };
  track.addEventListener("pointerdown", e => { track.setPointerCapture(e.pointerId); root.dataset.drag = "1"; emit(fromY(e)); e.stopPropagation(); });
  track.addEventListener("pointermove", e => { if (root.dataset.drag) emit(fromY(e)); });
  const end = () => { delete root.dataset.drag; };
  track.addEventListener("pointerup", end); track.addEventListener("pointercancel", end);
  root.addEventListener("keydown", e => {
    const step = { ArrowUp: 2.55, ArrowRight: 2.55, ArrowDown: -2.55, ArrowLeft: -2.55, PageUp: 25.5, PageDown: -25.5 }[e.key];
    if (step) { emit(value + step); e.preventDefault(); }
    if (e.key === "Home") { emit(0); e.preventDefault(); }
    if (e.key === "End") { emit(255); e.preventDefault(); }
  });
  return { el: root, set: v => { if (!root.dataset.drag) show(v); } };
}
