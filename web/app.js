const $ = (id) => document.getElementById(id);

let selected = "frog";
let lastState = null;

const MOVES = [
  ["lurk", "look"],
  ["post", "faster"],
  ["reply", "hold"],
  ["raid", "colder"],
];

const shownScores = new Map();
let scoreFrame = 0;

const play = $("play");
const round = $("round");

play.addEventListener("click", () => send(play.dataset.cmd || "play"));
round.addEventListener("click", () => send("round"));

$("ranking").addEventListener("click", (event) => {
  const item = event.target.closest("li");
  if (!item?.dataset.id) return;
  selected = item.dataset.id;
  if (lastState) {
    drawRanking(lastState);
    drawChart(lastState);
    drawInspector(lastState);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
  if (event.code === "Space") {
    event.preventDefault();
    send("toggle");
  }
});

async function send(cmd) {
  const response = await fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd }),
  });
  render(await response.json());
}

async function poll() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    render(await response.json());
  } catch (error) {
    $("event").textContent = "The page lost the server. Start it again with python server.py.";
  }
}

function render(state) {
  if (!state || state.error && state.phase !== "live" && !state.creatures) {
    $("event").textContent = state?.error || "No state yet.";
    return;
  }
  lastState = state;
  const live = state.phase === "live";
  play.disabled = !live;
  round.disabled = !live;
  play.textContent = state.running ? "Pause" : "Play";
  play.dataset.cmd = state.running ? "pause" : "play";
  const growing = growingTrend(state);

  $("regime").dataset.regime = "viral";
  $("regime-name").textContent = growing.title || "reading trends";
  $("regime-pays").textContent = live
    ? `${Math.round(growing.growth || 0)}/h`
    : "";
  $("phase-label").textContent = live ? (state.running ? "ranking" : "paused") : "first lesson";
  $("moment").textContent = String(state.moment ?? 0);

  easeScore("live", state.totals?.live, $("score-live"));
  easeScore("frozen", state.totals?.frozen, $("score-frozen"));
  easeScore("random", state.totals?.random, $("score-random"));
  $("event").textContent = live ? "" : nurseryLine(state.progress);

  drawNursery(state);
  drawRanking(state);
  drawTrends(state);
  drawChart(state);
  drawInspector(state);
}

function growingTrend(state) {
  const board = [...(state.source?.board || [])].sort((a, b) => (b.growth || 0) - (a.growth || 0));
  return board[0] || {};
}

function nurseryLine(progress) {
  if (!progress) return "Reading trends.";
  if (progress.phase === "reading") return "Reading trends.";
  const done = progress.moments ? Math.round((100 * progress.moment) / progress.moments) : 0;
  const who = progress.name || "a brain";
  return `${who} · ${done}%`;
}

function drawNursery(state) {
  let veil = document.querySelector(".nursery");
  if (state.phase === "live") {
    veil?.remove();
    return;
  }
  if (!veil) {
    veil = document.createElement("div");
    veil.className = "nursery";
    $("board-wrap").appendChild(veil);
  }
  const progress = state.progress || {};
  const pct = progress.moments ? Math.round((100 * progress.moment) / progress.moments) : 0;
  const raised = (progress.raised || []).map((row) => row.name).join(" · ");
  veil.innerHTML = `
    <div>
      <b>First lesson</b>
      <p>${nurseryLine(progress)}</p>
      <div class="track"><i style="width:${pct}%"></i></div>
      <p>${raised}</p>
    </div>`;
}

function drawRanking(state) {
  const host = $("ranking");
  const rows = state.ranking || state.creatures || [];
  const orderKey = rows.map((creature) => creature.id).join();
  const reorder = orderKey !== host.dataset.order && host.dataset.order;
  const before = new Map();
  if (reorder) {
    host.querySelectorAll("li").forEach((item) => {
      before.set(item.dataset.id, item.getBoundingClientRect().top);
    });
  }
  const seen = new Set();
  rows.forEach((creature) => {
    seen.add(creature.id);
    let item = host.querySelector(`[data-id="${creature.id}"]`);
    if (!item) {
      item = document.createElement("li");
      item.dataset.id = creature.id;
      item.innerHTML = `
        <span class="place"></span>
        <span class="mark"></span>
        <span class="detail">
          <span class="who"></span>
          <span class="trend-name"></span>
          <span class="chips"></span>
        </span>
        <span class="score"></span>`;
      host.appendChild(item);
    }
    item.className = (creature.rank === 1 ? "leader" : "") + (creature.id === selected ? " selected" : "");
    item.style.order = String(creature.rank || 0);
    item.querySelector(".place").textContent = creature.rank || "–";
    const mark = item.querySelector(".mark");
    mark.textContent = creature.mark;
    mark.style.background = creature.color;
    mark.style.color = creature.ink;
    item.querySelector(".who").innerHTML = `${escapeHtml(creature.name)} <em>${escapeHtml(creature.taste || "")}</em>`;
    item.querySelector(".trend-name").innerHTML = creature.ready
      ? `${Math.round(creature.list_rate || 0)}/h <em>stopped ${Math.round(creature.twin_rate || 0)}/h</em>`
      : "first lesson";
    const chipHost = item.querySelector(".chips");
    const signature = (creature.list || []).map((trend) => `${trend.hot ? "1" : "0"}${trend.title}`).join("|");
    if (chipHost.dataset.sig !== signature) {
      chipHost.dataset.sig = signature;
      chipHost.innerHTML = (creature.list || []).map((trend) => `
        <span class="${trend.hot ? "hot" : ""}" title="${Math.round(trend.growth || 0)}/h">${escapeHtml(trend.title)}</span>
      `).join("");
    }
    const tone = (Number(creature.score) || 0) >= 0 ? "var(--gm)" : "var(--panic)";
    easeScore(creature.id, creature.score, item.querySelector(".score"), tone);
  });
  host.querySelectorAll("li").forEach((item) => {
    if (!seen.has(item.dataset.id)) item.remove();
  });
  if (reorder) {
    host.querySelectorAll("li").forEach((item) => {
      const previous = before.get(item.dataset.id);
      if (previous == null) return;
      item.style.transition = "none";
      item.style.transform = "";
      const dy = previous - item.getBoundingClientRect().top;
      if (Math.abs(dy) < 2) return;
      item.style.transform = `translateY(${dy}px)`;
      requestAnimationFrame(() => {
        item.style.transition = "transform 0.45s ease";
        item.style.transform = "";
      });
    });
  }
  host.dataset.order = orderKey;
}

function easeScore(id, value, element, color) {
  if (!element) return;
  const target = Number(value) || 0;
  const view = shownScores.get(id) || { shown: target, target };
  view.target = target;
  view.element = element;
  if (color) view.color = color;
  shownScores.set(id, view);
  if (view.color) element.style.color = view.color;
  if (!scoreFrame) scoreFrame = requestAnimationFrame(stepScores);
}

function stepScores() {
  let moving = false;
  shownScores.forEach((view) => {
    const gap = view.target - view.shown;
    view.shown = Math.abs(gap) < 0.6 ? view.target : view.shown + gap * 0.22;
    if (view.shown !== view.target) moving = true;
    if (view.element) view.element.textContent = fmtInt(view.shown);
  });
  scoreFrame = moving ? requestAnimationFrame(stepScores) : 0;
}

function fmtInt(value) {
  const number = Math.round(Number(value) || 0);
  return number > 0 ? `+${number.toLocaleString()}` : number.toLocaleString();
}

const SLOT_COLOR = {
  post: "#d6ff4a",
  lurk: "#9fd4ff",
  raid: "#ffcf70",
  reply: "#c8bfb4",
};

function lessonLine(creature) {
  if (!creature.ready) return "First lesson.";
  const mood = creature.mode === "aroused" ? "Surprised" : "Calm";
  return `${mood} · ${shortChange(creature.change)}`;
}

function shortChange(text) {
  if (!text || text === "Kept this list of five." || text === "Held.") return "Held.";
  if (text.startsWith("No hotter") || text === "Already on the fastest.") return "Already on the fastest.";
  const swapped = text.match(/^Swapped (.+) for (.+)\.?$/);
  if (swapped) return `${swapped[1]} → ${swapped[2]}`;
  return text;
}

function chips(creature) {
  const items = (creature.list || []).map((trend) => `
    <span class="${trend.hot ? "hot" : ""}" title="${Math.round(trend.growth || 0)} posts/hour">${escapeHtml(trend.title)}</span>
  `).join("");
  return `<span class="chips">${items}</span>`;
}

function mixBar(state, creature) {
  const mix = creature.mix || {};
  const board = state.source?.board || [];
  const parts = ["post", "lurk", "raid", "reply"].map((slot) => {
    const share = Number(mix[slot]) || 0;
    if (share < 0.02) return "";
    const trend = board.find((item) => item.slot === slot);
    const title = trend?.title || slot;
    return `<i style="width:${Math.round(share * 100)}%;background:${SLOT_COLOR[slot]}" title="${escapeHtml(title)}"></i>`;
  }).join("");
  return `<span class="mixbar" title="Where this brain has been sitting">${parts}</span>`;
}

function drawTrends(state) {
  const host = $("trends");
  const board = [...(state.source?.board || [])].sort((a, b) => (b.growth || 0) - (a.growth || 0));
  board.forEach((trend, index) => {
    trend.hot = index < 5;
  });
  host.innerHTML = board.map((trend) => `
    <li class="${trend.paying ? "paying" : ""}">
      <div class="trend-title">
        <b>${escapeHtml(trend.title)}</b>
        ${trend.hot ? `<span class="badge">hot</span>` : ""}
      </div>
      <p class="trend-meta">${Math.round(trend.growth || 0)}/h${trend.status ? ` · ${escapeHtml(trend.status)}` : ""}</p>
    </li>`).join("");
}

function drawActors(state) {
  const pit = $("pit");
  const host = $("actors");
  const rect = pit.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  const maxR = Math.max(80, Math.min(cx, cy) - 78);
  const voidR = maxR * (0.18 + 0.58 * (state.close || 0));
  placeDisc($("void-disc"), cx, cy, voidR * 2);
  placeDisc($("halo-disc"), cx, cy, maxR * 2);

  const seen = new Set();
  (state.creatures || []).forEach((creature, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / state.creatures.length;
    const heat = Math.tanh((creature.score || 0) / 8);
    const orbit = 0.34 + 0.62 * (heat * 0.5 + 0.5);
    const radius = maxR * orbit;
    const fading = state.phase === "live" && radius < voidR;
    let button = host.querySelector(`[data-id="${creature.id}"]`);
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.dataset.id = creature.id;
      button.addEventListener("click", () => {
        selected = creature.id;
      });
      host.appendChild(button);
    }
    seen.add(creature.id);
    button.className = "actor"
      + (creature.id === selected ? " selected" : "")
      + (creature.mode === "aroused" ? " aroused" : "")
      + (fading ? " fading" : "");
    button.style.left = `${cx + Math.cos(angle) * radius}px`;
    button.style.top = `${cy + Math.sin(angle) * radius}px`;
    button.innerHTML = `
      <span class="disc" style="background:${creature.color};color:${creature.ink}">${creature.mark}</span>
      <span class="who">${creature.handle}</span>
      <span class="verbs">${creature.ready ? `<em>${creature.verb}</em>` : "raising"}</span>`;
  });
  host.querySelectorAll(".actor").forEach((button) => {
    if (!seen.has(button.dataset.id)) button.remove();
  });
}

function placeDisc(node, cx, cy, size) {
  node.style.left = `${cx}px`;
  node.style.top = `${cy}px`;
  node.style.width = `${size}px`;
  node.style.height = `${size}px`;
}

function drawFeed(feed) {
  const list = $("feed");
  list.innerHTML = "";
  [...feed].reverse().forEach((line) => {
    const item = document.createElement("li");
    item.style.setProperty("--accent", line.color);
    const payClass = line.pay > 0.05 ? "up" : line.pay < -0.05 ? "down" : "";
    const credit = line.live_handle
      ? `<span class="verb">${escapeHtml(line.live_handle)}${line.likes == null ? "" : ` · ${Number(line.likes)} likes`}</span>`
      : "";
    item.innerHTML = `
      <span><span class="handle" style="color:${escapeHtml(line.color)}">${escapeHtml(line.handle)}</span><span class="verb">${escapeHtml(line.verb)}</span></span>
      <span class="text">${escapeHtml(line.text)}${credit}</span>
      <span class="pay ${payClass}">${fmt(line.pay)}</span>`;
    list.appendChild(item);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function drawChart(state) {
  const creature = (state.creatures || []).find((row) => row.id === selected) || state.creatures?.[0];
  const canvas = $("chart");
  const ctx = canvas.getContext("2d");
  const { width, height } = fitCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#100e0c";
  ctx.fillRect(0, 0, width, height);

  const who = $("chart-who");
  const swatch = $("chart-live");
  if (!creature) {
    if (who) who.textContent = "Click a brain";
    return;
  }
  if (who) who.textContent = creature.name;
  if (swatch) swatch.style.background = creature.color;

  const trace = (state.traces || {})[creature.id] || {};
  const rate = smoothSeries(trace.rate || []);
  const twin = smoothSeries(trace.twin || []);
  const ceiling = chartCeiling(state, rate, twin);
  strokeSeries(ctx, twin, "#9a9288", width, height, ceiling);
  strokeSeries(ctx, rate, creature.color || "#d6ff4a", width, height, ceiling);
}

function chartCeiling(state, rate, twin) {
  const board = [...(state.source?.board || [])].sort((a, b) => (b.growth || 0) - (a.growth || 0));
  const hottest = board.slice(0, 5).reduce((sum, trend) => sum + (Number(trend.growth) || 0), 0);
  const seen = Math.max(hottest, ...rate, ...twin, 1);
  return seen * 1.08;
}

function smoothSeries(values) {
  return values.map((value, index) => {
    const slice = values.slice(Math.max(0, index - 2), index + 1);
    return slice.reduce((sum, item) => sum + item, 0) / slice.length;
  });
}

function strokeSeries(ctx, values, color, width, height, ceiling) {
  if (values.length < 2) return;
  const point = (value, index) => ({
    x: 8 + (index / (values.length - 1)) * (width - 16),
    y: height - 10 - (Math.max(0, value) / ceiling) * (height - 20),
  });
  ctx.beginPath();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  values.forEach((value, index) => {
    const { x, y } = point(value, index);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(2, height / 55);
  ctx.stroke();
}

function fitCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round((rect.height || 108) * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { width, height };
}

function trailing(history, window) {
  return history.map((_, index) => {
    const slice = history.slice(Math.max(0, index - window + 1), index + 1);
    const avg = (key) => slice.reduce((sum, row) => sum + row[key], 0) / slice.length;
    return { live: avg("live"), frozen: avg("frozen"), random: avg("random") };
  });
}

function stroke(ctx, values, color, width, height, fill) {
  const point = (value, index) => ({
    x: (index / Math.max(1, values.length - 1)) * (width - 8) + 4,
    y: height - 8 - value * (height - 16),
  });
  ctx.beginPath();
  values.forEach((value, index) => {
    const { x, y } = point(value, index);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
  if (!fill || !values.length) return;
  const last = point(values[values.length - 1], values.length - 1);
  const first = point(values[0], 0);
  ctx.lineTo(last.x, height - 4);
  ctx.lineTo(first.x, height - 4);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
}

function trendTitle(state, slot) {
  const board = state.source?.board || [];
  const match = board.find((item) => item.slot === slot);
  return match?.title || slot || "";
}

function drawInspector(state) {
  const creature = (state.creatures || []).find((row) => row.id === selected) || state.creatures?.[0];
  const host = $("inspector");
  if (!creature) {
    host.innerHTML = `<p class="inspector-empty">Click a brain.</p>`;
    return;
  }
  const activity = creature.activity || {};
  const motors = activity.motor || [];
  host.innerHTML = `
    <header>
      <h3 style="color:${creature.color}">${escapeHtml(creature.name)}</h3>
      <p class="meta">${escapeHtml(creature.taste || "")}</p>
      <p class="meta">${escapeHtml(lessonLine(creature))}</p>
    </header>
    <div class="brain" title="What this brain is firing">${brainCells(activity.association, creature.color)}</div>
    <div class="motors">${motorCells(motors, creature)}</div>`;
}

function brainCells(values, color) {
  const nums = (values || []).map(Number);
  if (!nums.length) return `<span class="inspector-empty">Still quiet.</span>`;
  const min = Math.min(...nums);
  const span = Math.max(...nums) - min || 1;
  return nums.map((value) => {
    const tone = 0.16 + ((value - min) / span) * 0.84;
    return `<i style="opacity:${tone.toFixed(2)};background:${color}"></i>`;
  }).join("");
}

function motorCells(values, creature) {
  const nums = values.map(Number);
  const min = nums.length ? Math.min(...nums) : 0;
  const span = (nums.length ? Math.max(...nums) : 1) - min || 1;
  return MOVES.map(([verb, label], index) => {
    const tone = nums.length ? 0.2 + ((nums[index] - min) / span) * 0.8 : 0.25;
    const on = creature.verb === verb ? " on" : "";
    return `<span class="${on.trim()}"><i style="opacity:${tone.toFixed(2)};background:${creature.color}"></i>${label}</span>`;
  }).join("");
}

function fmt(value) {
  const number = Number(value) || 0;
  const text = number.toFixed(1);
  return number > 0 ? `+${text}` : text;
}

poll();
setInterval(poll, 160);
