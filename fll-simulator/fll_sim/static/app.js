"use strict";

// ------------------------------------------------------------------ state
const state = {
  board: null,        // source-of-truth board (width_cm/height_cm/regions/...)
  result: null,       // last run result from the server
  frameIndex: 0,
  playing: false,
  speed: 1,
  playhead: 0,        // simulated seconds
  bgImage: null,      // cached Image for the background
  bgUrl: null,
};

const $ = (id) => document.getElementById(id);
const canvas = $("board");
const ctx = canvas.getContext("2d");

// ------------------------------------------------------------------ helpers
function normBoard(b) {
  if (!b) return null;
  return {
    width: b.width != null ? b.width : b.width_cm,
    height: b.height != null ? b.height : b.height_cm,
    base_color: b.base_color || "white",
    regions: b.regions || [],
    obstacles: b.obstacles || [],
    zones: b.zones || [],
    grid_cm: b.grid_cm || b.grid || 20,
    grid_labels: b.grid_labels || false,
    image_grid: b.image_grid || false,
    background_image: b.background_image || null,
    margins: b.margins || {left:0, right:0, top:0, bottom:0},
    table_color: b.table_color || [34, 38, 48],
  };
}

const COLOR_RGB = {
  black:"#000000", white:"#ffffff", red:"#dc2828", green:"#28aa5a",
  blue:"#286edc", yellow:"#f5d228", magenta:"#d23caa", cyan:"#3cc8d2",
  violet:"#965adc", orange:"#f08c28", brown:"#8c5a32", gray:"#8c8c8c", grey:"#8c8c8c",
};
function colorCss(c) {
  if (Array.isArray(c)) return `rgb(${c[0]},${c[1]},${c[2]})`;
  return COLOR_RGB[String(c).toLowerCase()] || "#808080";
}

// world(cm) -> canvas(px) transform (world = mat + staging margins), each draw
let T = { scale: 1, ox: 0, oy: 0, minX: 0, maxY: 0 };
function worldBox(b) {
  const m = b.margins || {left:0,right:0,top:0,bottom:0};
  return {
    minX: -m.left, maxX: b.width + m.right,
    minY: -m.bottom, maxY: b.height + m.top,
    w: m.left + b.width + m.right, h: m.bottom + b.height + m.top,
  };
}
function setTransform(b) {
  const pad = 14;   // room for the table bezel/frame
  const W = worldBox(b);
  const cw = canvas.width - pad * 2, ch = canvas.height - pad * 2;
  const scale = Math.min(cw / W.w, ch / W.h);
  T.scale = scale; T.minX = W.minX; T.maxY = W.maxY;
  T.ox = pad + (cw - W.w * scale) / 2;
  T.oy = pad + (ch - W.h * scale) / 2;
}
const PX = (x) => T.ox + (x - T.minX) * T.scale;
const PY = (y) => T.oy + (T.maxY - y) * T.scale;   // flip Y so up = up

// ------------------------------------------------------------------ drawing
function drawBoard(frame) {
  const b = normBoard(state.result ? state.result.board : state.board);
  if (!b) return;
  const W = worldBox(b);
  // keep canvas at the full table's aspect ratio
  const targetH = Math.round(canvas.clientWidth * (W.h / W.w));
  if (canvas.width !== canvas.clientWidth || canvas.height !== targetH) {
    canvas.width = canvas.clientWidth;
    canvas.height = targetH;
  }
  setTransform(b);
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // ---- table bezel (dark frame around everything) ----
  ctx.fillStyle = "#0c0d11";
  roundRect(PX(W.minX) - 10, PY(W.maxY) - 10,
            W.w * T.scale + 20, W.h * T.scale + 20, 12);
  ctx.fill();

  // ---- staging surface (whole table interior) ----
  ctx.fillStyle = colorCss(b.table_color);
  ctx.fillRect(PX(W.minX), PY(W.maxY), W.w * T.scale, W.h * T.scale);
  drawStaging(b, W);

  // ---- the mat (playing field) ----
  ctx.fillStyle = colorCss(b.base_color);
  ctx.fillRect(PX(0), PY(b.height), b.width * T.scale, b.height * T.scale);
  if (b.background_image && state.bgImage && state.bgUrl === b.background_image) {
    ctx.drawImage(state.bgImage, PX(0), PY(b.height), b.width * T.scale, b.height * T.scale);
  } else if (b.background_image && state.bgUrl !== b.background_image) {
    const img = new Image();
    img.onload = () => { state.bgImage = img; state.bgUrl = b.background_image; redraw(); };
    img.src = b.background_image;
  }

  // decorative zones (home / launch areas), clipped to the mat rectangle
  drawZones(b);
  // regions
  for (const r of b.regions) drawShape(r, colorCss(r.color));
  // grid lines: skip when the background image already draws them
  if ($("showGrid").checked && !(b.image_grid && b.background_image)) drawGridLines(b);
  if (b.grid_labels) drawGridLabels(b);
  // obstacles
  for (const o of b.obstacles) {
    drawShape(o, colorCss(o.color || "gray"));
    ctx.save();
    ctx.strokeStyle = "rgba(0,0,0,.55)"; ctx.lineWidth = 2; strokeShape(o); ctx.restore();
  }
  // mat edge
  ctx.strokeStyle = "rgba(0,0,0,.5)"; ctx.lineWidth = 2;
  ctx.strokeRect(PX(0), PY(b.height), b.width * T.scale, b.height * T.scale);

  // path trace
  if (state.result && $("showTrace").checked) drawTrace();
  // robot
  if (frame) drawRobot(frame);
  else drawStartPreview();
}

function drawStaging(b, W) {
  const m = b.margins || {left:0,right:0,top:0,bottom:0};
  ctx.save();
  ctx.font = "bold " + Math.max(10, 0.9 * T.scale) + "px sans-serif";
  const drawArea = (x0, y0, x1, y1, label) => {
    const px = PX(x0), py = PY(y1), w = (x1-x0)*T.scale, h = (y1-y0)*T.scale;
    if (w < 6 || h < 6) return;
    // yellow dashed "attachment staging" border, like the real table margins
    ctx.strokeStyle = "#f2c200"; ctx.lineWidth = 2; ctx.setLineDash([9, 7]);
    ctx.strokeRect(px + 4, py + 4, w - 8, h - 8);
    ctx.setLineDash([]);
    if (label && h > 60) {
      ctx.save();
      ctx.translate(px + w/2, py + h/2); ctx.rotate(-Math.PI/2);
      ctx.fillStyle = "rgba(242,194,0,.75)"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(label, 0, 0);
      ctx.restore();
    }
  };
  if (m.left)  drawArea(W.minX, W.minY, 0, W.maxY, "ATTACHMENT STAGING");
  if (m.right) drawArea(b.width, W.minY, W.maxX, W.maxY, "ATTACHMENT STAGING");
  if (m.top)    drawArea(0, b.height, b.width, W.maxY, "");
  if (m.bottom) drawArea(0, W.minY, b.width, 0, "");
  ctx.restore();
}

function drawShape(s, fill) {
  ctx.fillStyle = fill;
  if ((s.shape || "rect") === "rect") {
    ctx.fillRect(PX(s.x), PY(s.y + s.h), s.w * T.scale, s.h * T.scale);
  } else if (s.shape === "circle") {
    ctx.beginPath();
    ctx.arc(PX(s.x), PY(s.y), s.r * T.scale, 0, Math.PI * 2);
    ctx.fill();
  }
}
function strokeShape(s) {
  if ((s.shape || "rect") === "rect") {
    ctx.strokeRect(PX(s.x), PY(s.y + s.h), s.w * T.scale, s.h * T.scale);
  } else if (s.shape === "circle") {
    ctx.beginPath();
    ctx.arc(PX(s.x), PY(s.y), s.r * T.scale, 0, Math.PI * 2);
    ctx.stroke();
  }
}

function drawZones(b) {
  if (!b.zones || !b.zones.length) return;
  ctx.save();
  // clip to the board so corner arcs render as quarter-circles
  ctx.beginPath();
  ctx.rect(PX(0), PY(b.height), b.width * T.scale, b.height * T.scale);
  ctx.clip();
  for (const z of b.zones) {
    ctx.fillStyle = withAlpha(colorCss(z.color), 0.22);
    ctx.strokeStyle = withAlpha(colorCss(z.color), 0.85);
    ctx.lineWidth = 2;
    drawShape(z, ctx.fillStyle);
    strokeShape(z);
    if (z.label) {
      ctx.fillStyle = withAlpha(colorCss(z.color), 0.95);
      ctx.font = `bold ${Math.max(11, 0.06 * (z.r || 20) * T.scale)}px sans-serif`;
      const lx = z.shape === "circle" ? z.x : z.x + (z.w || 0) / 2;
      const ly = z.shape === "circle" ? z.y : z.y + (z.h || 0) / 2;
      // nudge corner labels inward
      const dx = lx < b.width / 2 ? 14 : -14;
      const dy = ly < b.height / 2 ? 14 : -14;
      ctx.textAlign = "center";
      ctx.fillText(z.label, PX(lx + dx), PY(ly + dy));
    }
  }
  ctx.restore();
}

function withAlpha(hex, a) {
  // hex like #rrggbb -> rgba()
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`;
}

function drawGridLines(b) {
  const step = b.grid_cm || 20;
  ctx.save();
  ctx.strokeStyle = "rgba(220,40,40,.32)"; ctx.lineWidth = 1;
  for (let x = 0; x <= b.width + 0.01; x += step) {
    ctx.beginPath(); ctx.moveTo(PX(x), PY(0)); ctx.lineTo(PX(x), PY(b.height)); ctx.stroke();
  }
  for (let y = 0; y <= b.height + 0.01; y += step) {
    ctx.beginPath(); ctx.moveTo(PX(0), PY(y)); ctx.lineTo(PX(b.width), PY(y)); ctx.stroke();
  }
  ctx.restore();
}

function drawGridLabels(b) {
  const step = b.grid_cm || 20;
  ctx.save();
  // columns A,B,C... along the bottom; rows 1,2,3... up the left (official layout)
  const cols = Math.round(b.width / step);
  const rows = Math.round(b.height / step);
  ctx.fillStyle = "#c81e1e"; ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "bottom";
  for (let c = 0; c < cols; c++) {
    ctx.fillText(String.fromCharCode(65 + c), PX((c + 0.5) * step), PY(0) - 2);
  }
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  for (let r = 0; r < rows; r++) {
    ctx.fillText(String(r + 1), PX(0) + 3, PY((r + 0.5) * step));
  }
  ctx.restore();
}

function drawTrace() {
  const p = state.result.path;
  if (!p || p.length < 2) return;
  ctx.save();
  ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.setLineDash([]);
  const path = new Path2D();
  path.moveTo(PX(p[0][0]), PY(p[0][1]));
  for (let i = 1; i < p.length; i++) path.lineTo(PX(p[i][0]), PY(p[i][1]));
  // dark halo for contrast over the busy mat art, then bright core
  ctx.strokeStyle = "rgba(10,20,20,.55)"; ctx.lineWidth = 5.5; ctx.stroke(path);
  ctx.strokeStyle = "#2affc0"; ctx.lineWidth = 2.5; ctx.stroke(path);
  ctx.restore();
}

function robotDims() {
  const r = state.result ? state.result.robot : {
    body_length: +$("body_length_cm").value, body_width: +$("body_width_cm").value };
  return { L: r.body_length, W: r.body_width };
}

function drawRobot(f) {
  const { L, W } = robotDims();
  const cx = PX(f.x), cy = PY(f.y);
  const h = f.heading * Math.PI / 180;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(h);               // heading 0 = up, clockwise positive
  const lpx = L * T.scale, wpx = W * T.scale;
  // body
  ctx.fillStyle = "rgba(74,163,255,.85)";
  ctx.strokeStyle = "#0b2a4a"; ctx.lineWidth = 2;
  roundRect(-wpx/2, -lpx/2, wpx, lpx, 4*T.scale/2 + 2);
  ctx.fill(); ctx.stroke();
  // nose (front)
  ctx.fillStyle = "#ffd54a";
  ctx.beginPath();
  ctx.moveTo(0, -lpx/2 - 6);
  ctx.lineTo(-wpx*0.28, -lpx/2 + 2);
  ctx.lineTo(wpx*0.28, -lpx/2 + 2);
  ctx.closePath(); ctx.fill();
  ctx.restore();

  // sensor dots + distance ray (drawn in world space)
  drawSensors(f);
}

function drawSensors(f) {
  const offs = getSensorOffsets();
  const h = f.heading * Math.PI / 180;
  const fwd = [Math.sin(h), Math.cos(h)];
  const right = [Math.cos(h), -Math.sin(h)];
  for (const port in offs) {
    const o = offs[port];
    const wx = f.x + o.forward*fwd[0] + o.side*right[0];
    const wy = f.y + o.forward*fwd[1] + o.side*right[1];
    ctx.beginPath();
    ctx.fillStyle = port === "D" ? "#ff6b6b" : "#35d0a5";
    ctx.arc(PX(wx), PY(wy), Math.max(3, 2.5*T.scale/2+1), 0, Math.PI*2);
    ctx.fill();
    // distance ray
    if (port === "D" && f.distance != null) {
      const ex = wx + fwd[0]*f.distance, ey = wy + fwd[1]*f.distance;
      ctx.save();
      ctx.strokeStyle = "rgba(255,107,107,.6)"; ctx.setLineDash([4,4]); ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(PX(wx), PY(wy)); ctx.lineTo(PX(ex), PY(ey)); ctx.stroke();
      ctx.restore();
    }
  }
}

function drawStartPreview() {
  const f = { x: +$("start_x").value, y: +$("start_y").value, heading: +$("start_heading").value, distance: null };
  drawRobot(f);
}

function roundRect(x, y, w, h, r) {
  r = Math.min(r, w/2, h/2);
  ctx.beginPath();
  ctx.moveTo(x+r, y);
  ctx.arcTo(x+w, y, x+w, y+h, r);
  ctx.arcTo(x+w, y+h, x, y+h, r);
  ctx.arcTo(x, y+h, x, y, r);
  ctx.arcTo(x, y, x+w, y, r);
  ctx.closePath();
}

function redraw() {
  const f = currentFrame();
  drawBoard(f);
  updateReadouts(f);
}

// ------------------------------------------------------------------ playback
function currentFrame() {
  if (!state.result || !state.result.frames.length) return null;
  return state.result.frames[state.frameIndex] || state.result.frames[0];
}

function frameIndexForTime(t) {
  const fr = state.result.frames;
  let lo = 0, hi = fr.length - 1;
  if (t <= fr[0].t) return 0;
  if (t >= fr[hi].t) return hi;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (fr[mid].t <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

let lastTs = null;
function animate(ts) {
  if (!state.playing) { lastTs = null; return; }
  if (lastTs == null) lastTs = ts;
  const dt = (ts - lastTs) / 1000;
  lastTs = ts;
  state.playhead += dt * state.speed;
  const fr = state.result.frames;
  const endT = fr[fr.length - 1].t;
  if (state.playhead >= endT) {
    state.playhead = endT;
    setFrameByTime();
    stopPlay();
    return;
  }
  setFrameByTime();
  requestAnimationFrame(animate);
}

function setFrameByTime() {
  state.frameIndex = frameIndexForTime(state.playhead);
  $("scrub").value = state.frameIndex;
  redraw();
}

function startPlay() {
  if (!state.result || !state.result.frames.length) return;
  const fr = state.result.frames;
  if (state.playhead >= fr[fr.length - 1].t) state.playhead = 0;
  state.playing = true;
  $("playBtn").textContent = "⏸";
  lastTs = null;
  requestAnimationFrame(animate);
}
function stopPlay() {
  state.playing = false;
  $("playBtn").textContent = "▶";
}

// ------------------------------------------------------------------ readouts
function updateReadouts(f) {
  const chip = $("statusChip");
  if (!f) { $("timeLabel").textContent = "0.00s"; return; }
  $("timeLabel").textContent = f.t.toFixed(2) + "s";
  $("rdPos").textContent = `x ${f.x.toFixed(1)}  y ${f.y.toFixed(1)} cm`;
  $("rdHead").textContent = `${f.heading.toFixed(1)}°`;
  $("rdColor").textContent = f.color;
  $("rdRefl").textContent = f.reflected + " %";
  $("rdDist").textContent = f.distance == null ? "—" : f.distance.toFixed(1) + " cm";
  const m = f.motors || {};
  const keys = Object.keys(m);
  $("rdMotors").textContent = keys.length ? keys.map(k => `${k}:${m[k].toFixed(0)}°`).join("  ") : "—";
}

function renderConsole() {
  const el = $("console");
  el.innerHTML = "";
  const r = state.result;
  const status = $("outStatus");
  if (!r) {
    el.innerHTML = '<div class="empty">Press ▶ Run to see your program\'s output, robot actions, and any errors here.</div>';
    status.textContent = ""; status.className = "out-status";
    return;
  }
  // error banner FIRST so it's impossible to miss
  if (r.error) {
    const box = document.createElement("div");
    box.className = "errbanner";
    const kind = r.error.type === "timeout" ? "⏱ Timed out" : "✖ Error";
    box.innerHTML = `<b>${kind}</b>\n` + escapeHtml(r.error.message);
    el.appendChild(box);
  }
  const showEvents = $("showEvents").checked;
  let printed = 0;
  for (const ev of r.events) {
    if (ev.type !== "print" && !showEvents) continue;
    const line = document.createElement("div");
    line.className = ev.type;
    line.innerHTML = `<span class="t">${ev.t.toFixed(2)}s </span>` +
      (ev.type === "print" ? "" : `<span class="t">[${ev.type}]</span> `) + escapeHtml(ev.text);
    el.appendChild(line);
    printed++;
  }
  if (!printed && !r.error) {
    el.appendChild(Object.assign(document.createElement("div"),
      {className: "empty", textContent: "Program finished with no printed output."}));
  }
  // status summary in the header
  if (r.error) {
    status.textContent = r.error.type === "timeout" ? "⏱ timed out — see below" : "✖ error — see below";
    status.className = "out-status err";
    showOutput(true);   // make sure the panel is open when something breaks
  } else {
    status.textContent = `✓ finished at ${r.final ? r.final.sim_time : "?"}s`;
    status.className = "out-status ok";
  }
  el.scrollTop = 0;   // keep the error/topmost line in view
}

function showOutput(open) {
  const out = $("output");
  out.classList.toggle("collapsed", !open);
  $("toggleOut").textContent = open ? "Hide ▾" : "Show ▴";
}
function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;" }[c]));
}

// ------------------------------------------------------------------ config gather
function getSensorOffsets() {
  const offs = {};
  document.querySelectorAll("#sensorRows tr").forEach(tr => {
    const port = tr.querySelector(".port-in").value.trim();
    if (!port) return;
    offs[port] = {
      forward: parseFloat(tr.querySelector(".fwd-in").value) || 0,
      side: parseFloat(tr.querySelector(".side-in").value) || 0,
    };
  });
  return offs;
}

function getRobotConfig() {
  return {
    wheel_diameter_cm: +$("wheel_diameter_cm").value,
    axle_track_cm: +$("axle_track_cm").value,
    full_speed_cmps: +$("full_speed_cmps").value,
    body_length_cm: +$("body_length_cm").value,
    body_width_cm: +$("body_width_cm").value,
    left_port: $("left_port").value.trim() || "A",
    right_port: $("right_port").value.trim() || "B",
    start_x: +$("start_x").value,
    start_y: +$("start_y").value,
    start_heading: +$("start_heading").value,
    sensor_offsets: getSensorOffsets(),
  };
}

function getBoardConfig() {
  const b = Object.assign({}, state.board);
  b.width_cm = +$("board_w").value;
  b.height_cm = +$("board_h").value;
  state.board = b;
  return b;
}

// ------------------------------------------------------------------ run
async function run() {
  const chip = $("statusChip");
  chip.textContent = "running…"; chip.className = "chip run";
  $("runBtn").disabled = true;
  try {
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: $("code").value,
        robot: getRobotConfig(),
        board: getBoardConfig(),
      }),
    });
    const result = await resp.json();
    state.result = result;
    state.frameIndex = 0;
    state.playhead = 0;
    $("scrub").max = Math.max(0, result.frames.length - 1);
    $("scrub").value = 0;
    renderConsole();
    redraw();
    if (result.error) {
      chip.textContent = result.error.type === "timeout" ? "timed out" : "error";
      chip.className = "chip err";
    } else {
      chip.textContent = `done · ${result.final.sim_time}s`;
      chip.className = "chip run";
      startPlay();
    }
  } catch (e) {
    chip.textContent = "server error"; chip.className = "chip err";
    console.error(e);
  } finally {
    $("runBtn").disabled = false;
  }
}

function reset() {
  stopPlay();
  state.result = null;
  state.frameIndex = 0;
  state.playhead = 0;
  $("scrub").value = 0; $("scrub").max = 0;
  $("statusChip").textContent = "ready"; $("statusChip").className = "chip";
  renderConsole();
  redraw();
}

// ------------------------------------------------------------------ boards & examples
async function loadBoardList() {
  const names = await (await fetch("/api/boards")).json();
  const sel = $("boardSelect");
  sel.innerHTML = "";
  names.forEach(n => { const o = document.createElement("option"); o.value = n; o.textContent = n; sel.appendChild(o); });
  if (names.length) await loadBoard(names[0]);
}
async function loadBoard(name) {
  const b = await (await fetch("/api/board/" + name)).json();
  state.board = b;
  $("board_w").value = b.width_cm;
  $("board_h").value = b.height_cm;
  if (b.start) {
    $("start_x").value = b.start.x;
    $("start_y").value = b.start.y;
    $("start_heading").value = b.start.heading || 0;
  }
  $("boardJson").value = JSON.stringify(
    { zones: b.zones || [], regions: b.regions || [], obstacles: b.obstacles || [], base_color: b.base_color },
    null, 2);
  state.bgImage = null; state.bgUrl = null;
  redraw();
}

async function loadExampleList() {
  const names = await (await fetch("/api/examples")).json();
  const sel = $("exampleSelect");
  names.forEach(n => { const o = document.createElement("option"); o.value = n; o.textContent = n; sel.appendChild(o); });
}
async function loadExample(name) {
  if (!name) return;
  const data = await (await fetch("/api/example/" + name)).json();
  $("code").value = data.code;
}

// ------------------------------------------------------------------ sensor rows
function addSensorRow(port = "", fwd = 9, side = 0) {
  const tr = document.createElement("tr");
  tr.innerHTML =
    `<td><input class="port-in" type="text" value="${port}"></td>` +
    `<td><input class="fwd-in" type="number" step="0.5" value="${fwd}"></td>` +
    `<td><input class="side-in" type="number" step="0.5" value="${side}"></td>`;
  tr.querySelectorAll("input").forEach(i => i.addEventListener("input", redraw));
  $("sensorRows").appendChild(tr);
}

// ------------------------------------------------------------------ wire up
function init() {
  // default sensor mounts: color 'C' and distance 'D', both at the front
  addSensorRow("C", 9, 0);
  addSensorRow("D", 9, 0);

  $("runBtn").addEventListener("click", run);
  $("resetBtn").addEventListener("click", reset);
  $("playBtn").addEventListener("click", () => state.playing ? stopPlay() : startPlay());
  $("scrub").addEventListener("input", (e) => {
    stopPlay();
    state.frameIndex = +e.target.value;
    const f = currentFrame();
    if (f) state.playhead = f.t;
    redraw();
  });
  $("speedSel").addEventListener("change", (e) => state.speed = +e.target.value);
  $("showTrace").addEventListener("change", redraw);
  $("showGrid").addEventListener("change", redraw);
  $("addSensorRow").addEventListener("click", () => addSensorRow());
  $("clearOut").addEventListener("click", () => {
    $("console").innerHTML = '<div class="empty">(cleared)</div>';
    $("outStatus").textContent = ""; $("outStatus").className = "out-status";
  });
  $("toggleOut").addEventListener("click", () =>
    showOutput($("output").classList.contains("collapsed")));
  $("showEvents").addEventListener("change", renderConsole);
  $("exampleSelect").addEventListener("change", (e) => loadExample(e.target.value));
  $("boardSelect").addEventListener("change", (e) => loadBoard(e.target.value));
  $("applyBoard").addEventListener("click", () => {
    try {
      const parsed = JSON.parse($("boardJson").value);
      state.board = Object.assign({}, state.board, parsed);
      redraw();
    } catch (err) { alert("Board JSON error: " + err.message); }
  });
  $("bgFile").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { state.board.background_image = reader.result; state.bgUrl = null; redraw(); };
    reader.readAsDataURL(file);
  });

  // start-pose inputs live-update the preview
  ["start_x","start_y","start_heading","body_length_cm","body_width_cm","board_w","board_h"]
    .forEach(id => $(id).addEventListener("input", () => { if (!state.result) redraw(); else redraw(); }));

  // click the mat to set the start position
  canvas.addEventListener("click", (e) => {
    const b = normBoard(state.result ? state.result.board : state.board);
    if (!b) return;
    const rect = canvas.getBoundingClientRect();
    const px = (e.clientX - rect.left) * (canvas.width / rect.width);
    const py = (e.clientY - rect.top) * (canvas.height / rect.height);
    const x = T.minX + (px - T.ox) / T.scale;
    const y = T.maxY - (py - T.oy) / T.scale;
    const W = worldBox(b);
    if (x < W.minX || x > W.maxX || y < W.minY || y > W.maxY) return;
    $("start_x").value = x.toFixed(1);
    $("start_y").value = y.toFixed(1);
    if (!state.result) redraw();
  });

  // tabs
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    document.querySelectorAll(".tab-body").forEach(b => b.classList.toggle("hidden", b.dataset.body !== t.dataset.tab));
  }));

  // keyboard: Ctrl/Cmd+Enter to run
  $("code").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); }
    if (e.key === "Tab") {
      e.preventDefault();
      const s = e.target.selectionStart, en = e.target.selectionEnd;
      e.target.value = e.target.value.slice(0, s) + "    " + e.target.value.slice(en);
      e.target.selectionStart = e.target.selectionEnd = s + 4;
    }
  });

  window.addEventListener("resize", redraw);

  renderConsole();   // show the "press Run" prompt in the output panel
  loadBoardList();
  loadExampleList().then(() => loadExample("01_drive_square"));
}

document.addEventListener("DOMContentLoaded", init);
