// Plan de scene : les spots places comme dans la salle.
let arrange = false, moving = null, placeMsg = "";
const grid = () => config.grid || { cols: 12, rows: 7 };
function positions() {
  // case de chaque spot ; ceux jamais places (ou sur une case deja prise) vont sur la premiere case libre
  const { cols, rows } = grid(), n = config.fixtures.length, out = {}, taken = new Set();
  for (const f of config.fixtures) if (Number.isInteger(f.x) && Number.isInteger(f.y)) {
    const p = [Math.min(f.x, cols - 1), Math.min(f.y, rows - 1)];
    if (taken.has(p.join())) continue;
    out[f.id] = p; taken.add(p.join());
  }
  let i = 0;
  for (const f of config.fixtures) {
    if (out[f.id]) continue;
    let x = Math.min(cols - 1, Math.floor((i + 0.5) * cols / n)), y = Math.max(0, rows - 2), tries = 0;
    while (taken.has(x + "," + y) && tries++ < cols * rows) { x = (x + 1) % cols; if (x === 0) y = (y + rows - 1) % rows; }
    out[f.id] = [x, y]; taken.add(x + "," + y); i++;
  }
  return out;
}
function buildPlan() {
  const g = $("grid"), { cols, rows } = grid();
  g.style.backgroundSize = `calc(100% / ${cols}) calc(100% / ${rows})`;
  for (const s of g.querySelectorAll(".spot")) s.remove();
  config.fixtures.forEach((fx, i) => {
    const b = el("button", { class: "spot", type: "button", "data-id": fx.id, "aria-pressed": "false" },
      el("span", { class: "disc" }, el("span", { class: "n" }, String(i + 1)), el("span", { class: "ck", html: CHECK })), el("span", { class: "lb" }, fx.name));
    b.onclick = () => {
      if (arrange) { moving = moving === fx.id ? null : fx.id; placeMsg = ""; render(); return; }
      toggleSel(fx.id);
    };
    b.onkeydown = e => {   // en mode Disposer : fleches pour deplacer le spot case par case
      if (!arrange || moving !== fx.id) return;
      if (e.key === "Escape" || e.key === "Enter") { moving = null; render(); e.preventDefault(); return; }
      const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
      if (!d) return;
      e.preventDefault();
      const [x, y] = positions()[fx.id], nx = x + d[0], ny = y + d[1];
      if (nx >= 0 && ny >= 0 && nx < cols && ny < rows) place(fx.id, nx, ny, true);
    };
    g.append(b);
  });
  const cells = $("cells"); cells.innerHTML = "";
  cells.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`; cells.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++)
    cells.append(el("button", { type: "button", tabindex: -1, "aria-label": `Case ${x + 1} depuis jardin, rang ${y + 1} depuis le lointain`, onclick: () => moving && place(moving, x, y) }));
  $("colOut").textContent = cols; $("rowOut").textContent = rows;
  $("gridSize").textContent = `grille ${cols} × ${rows}`;
  for (const id of [...selected]) if (!fxById(id)) selected.delete(id);
}
function place(id, x, y, keep) {   // keep : deplacement aux fleches, le spot reste a deplacer
  const pos = positions(), other = config.fixtures.find(f => f.id !== id && pos[f.id][0] === x && pos[f.id][1] === y);
  if (other) { placeMsg = `Case occupée par ${other.name}.`; render(); return; }
  const fx = fxById(id); fx.x = x; fx.y = y; placeMsg = "";
  if (!keep) moving = null;
  render();
  api("/api/layout", { positions: { [id]: [x, y] } }).then(poll);
}
function resizeGrid(dc, dr) {
  const g = grid(), cols = Math.max(4, Math.min(24, g.cols + dc)), rows = Math.max(3, Math.min(14, g.rows + dr));
  if (cols === g.cols && rows === g.rows) return;
  const pos = positions();   // on fige toutes les positions en meme temps que la nouvelle taille
  api("/api/layout", { grid: { cols, rows }, positions: Object.fromEntries(Object.entries(pos).map(([id, [x, y]]) => [id, [Math.min(x, cols - 1), Math.min(y, rows - 1)]])) }).then(poll);
}
$("colMinus").onclick = () => resizeGrid(-1, 0); $("colPlus").onclick = () => resizeGrid(1, 0);
$("rowMinus").onclick = () => resizeGrid(0, -1); $("rowPlus").onclick = () => resizeGrid(0, 1);
$("arrangeBtn").onclick = () => { arrange = !arrange; moving = null; placeMsg = ""; render(); };
function renderPlan() {
  const { cols, rows } = grid(), pos = positions();
  config.fixtures.forEach((fx, i) => {
    const b = $("grid").querySelector(`.spot[data-id="${fx.id}"]`); if (!b) return;
    const [x, y] = pos[fx.id], st = shown(fx, i), k = level(st), on = selected.has(fx.id);
    b.style.left = ((x + 0.5) / cols * 100) + "%"; b.style.top = ((y + 0.5) / rows * 100) + "%";
    const disc = b.querySelector(".disc");
    disc.classList.toggle("off", k <= 0.004);
    disc.style.background = k > 0.004 ? swatchBg(st, k) : "";
    b.setAttribute("aria-pressed", String(arrange ? moving === fx.id : on));
    b.classList.toggle("moving", arrange && moving === fx.id);
    b.setAttribute("aria-label", `${fx.name} : ${k > 0.004 ? colorName(st) + ", " + Math.round(k * 100) + " %" : "éteint"}${arrange ? "" : on ? ". Coché" : ". Pas coché"}`);
  });
  $("arrangeBtn").setAttribute("aria-pressed", String(arrange));
  $("arrangeBar").hidden = !arrange; $("cells").hidden = !arrange;
  const mv = fxById(moving);
  $("arrangeHint").textContent = placeMsg || (mv ? `${mv.name} : touche sa nouvelle case (ou flèches, puis Entrée).` : "Touche un spot, puis la case où il est accroché dans la salle.");
  $("colMinus").disabled = cols <= 4; $("colPlus").disabled = cols >= 24; $("rowMinus").disabled = rows <= 3; $("rowPlus").disabled = rows >= 14;
}
