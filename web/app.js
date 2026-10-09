const $ = (id) => document.getElementById(id);

let selected = "frog";
let lastState = null;

const MOVES = [
  ["lurk", "watch"],
  ["post", "chase"],
  ["reply", "hold"],
  ["raid", "fade"],
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
  const leader = (state.ranking || state.creatures || [])[0];

  $("regime").dataset.regime = (Number(leader?.score) || 0) < 0 ? "viral" : "timeline";
  $("regime-name").textContent = leader?.name || "the board";
  $("regime-pays").textContent = live ? fmtInt(leader?.score) : "";
  $("phase-label").textContent = live ? (state.running ? "live" : "paused") : "arming";
  $("moment").textContent = String(state.moment ?? 0);
  drawSource(state);

  easeScore("live", state.totals?.live, $("score-live"), moneyTone(state.totals?.live));
  easeScore("frozen", state.totals?.frozen, $("score-frozen"), moneyTone(state.totals?.frozen));
  easeScore("random", state.totals?.random, $("score-random"), moneyTone(state.totals?.random));
  const count = Number(state.source?.count) || (state.source?.board || []).length;
  const note = $("pool-note");
  if (note) {
    note.textContent = count
      ? `${count.toLocaleString()} coins. The list is the live moves.`
      : "Every USDT pair. Profit is the score.";
  }
  $("event").textContent = live ? "" : nurseryLine(state.progress);

  drawNursery(state);
  drawRanking(state);
  drawBest(state);
  drawTrends(state);
  drawChart(state);
  drawInspector(state);
}

function drawSource(state) {
  const source = state.source || {};
  const box = $("source");
  const link = $("source-link");
  const label = $("source-status");
  const status = source.error ? "down" : (source.status || "reading");
  if (box) box.dataset.status = status;
  if (link) {
    link.textContent = source.name || "Prices";
    if (source.url) link.href = source.url;
  }
  if (label) label.innerHTML = `<i></i>${escapeHtml(status)}`;
}

function growingTrend(state) {
  const board = [...(state.source?.board || [])].sort((a, b) => (b.growth || 0) - (a.growth || 0));
  return board[0] || {};
}

function nurseryLine(progress) {
  if (!progress) return "Reading the pool.";
  if (progress.phase === "reading") return "Reading the pool.";
  const done = progress.moments ? Math.round((100 * progress.moment) / progress.moments) : 0;
  const who = progress.name || "a trader";
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
      <b>Arming</b>
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
          <span class="twin-line"></span>
          <span class="chips"></span>
        </span>
        <span class="score"><b class="total"></b><em class="pnl"></em></span>`;
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
    item.querySelector(".trend-name").textContent = creature.ready
      ? (creature.change || "Held the bag.")
      : "arming";
    const twin = item.querySelector(".twin-line");
    if (twin) {
      const stillBag = 1000 + (Number(creature.twin_pnl) || 0);
      const names = (creature.still || []).join(" ");
      twin.textContent = creature.ready ? `held still ${fmtMoney(stillBag)}` : "";
      twin.title = names
        ? `Same coins, never sold: ${names}`
        : "Same opening coins, never sold";
    }
    const chipHost = item.querySelector(".chips");
    const signature = (creature.list || []).map((trend) => `${trend.hot ? "1" : "0"}${trend.title}`).join("|");
    if (chipHost.dataset.sig !== signature) {
      chipHost.dataset.sig = signature;
      chipHost.innerHTML = (creature.list || []).map((trend) => `
        <span class="${trend.hot ? "hot" : ""}" title="${move(trend.growth)}">${escapeHtml(trend.title)}</span>
      `).join("");
    }
    const tone = (Number(creature.score) || 0) >= 0 ? "var(--gm)" : "var(--panic)";
    const score = item.querySelector(".score");
    if (!score.querySelector(".total")) {
      score.innerHTML = `<b class="total"></b><em class="pnl"></em>`;
    }
    const total = creature.total != null ? Number(creature.total) : 1000 + (Number(creature.score) || 0);
    easeScore(`${creature.id}-bag`, total, score.querySelector(".total"), "var(--ink)", fmtMoney);
    const pnl = score.querySelector(".pnl");
    pnl.textContent = fmtInt(creature.score);
    pnl.style.color = tone;
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

function easeScore(id, value, element, color, format) {
  if (!element) return;
  const target = Number(value) || 0;
  const view = shownScores.get(id) || { shown: target, target };
  view.target = target;
  view.element = element;
  view.format = format || fmtInt;
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
    if (view.element) view.element.textContent = (view.format || fmtInt)(view.shown);
  });
  scoreFrame = moving ? requestAnimationFrame(stepScores) : 0;
}

function priceMeta(trend) {
  const since = `${move(trend.growth)} since open`;
  if (trend.day == null || trend.day === "") {
    return trend.status ? `${move(trend.growth)} · ${escapeHtml(trend.status)}` : move(trend.growth);
  }
  return `${since} · 24h ${move(trend.day)}`;
}

function move(value) {
  const number = Number(value) || 0;
  const abs = Math.abs(number);
  const digits = abs !== 0 && abs < 10 ? 1 : 0;
  const body = abs.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (number > 0) return `+${body}%`;
  if (number < 0) return `-${body}%`;
  return "0%";
}

function moneyTone(value) {
  const number = Number(value) || 0;
  if (number > 0) return "var(--gm)";
  if (number < 0) return "var(--panic)";
  return "var(--muted)";
}

function fmtMoney(value) {
  const number = Number(value) || 0;
  const body = Math.abs(number).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return number < 0 ? `-$${body}` : `$${body}`;
}

function fmtInt(value) {
  const number = Number(value) || 0;
  const body = Math.abs(number).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (number > 0) return `+$${body}`;
  if (number < 0) return `-$${body}`;
  return "$0.00";
}

const SLOT_COLOR = {
  post: "#d6ff4a",
  lurk: "#9fd4ff",
  raid: "#ffcf70",
  reply: "#c8bfb4",
};

function lessonLine(creature) {
  if (!creature.ready) return "Arming.";
  const mood = creature.mode === "aroused" ? "Learning" : "Steady";
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

function drawBest(state) {
  const board = [...(state.source?.board || [])].sort((a, b) => (b.growth || 0) - (a.growth || 0));
  const best = board[0];
  const box = $("best-now");
  const name = $("best-name");
  const move = $("best-move");
  if (!name || !move) return;
  if (!best) {
    name.textContent = "—";
    move.textContent = "";
    return;
  }
  name.textContent = best.title || "—";
  move.textContent = priceMeta(best);
  if (box) box.dataset.side = Number(best.growth) < 0 ? "down" : "up";
}

function drawTrends(state) {
  const host = $("trends");
  const board = [...(state.source?.board || [])].sort((a, b) => (b.growth || 0) - (a.growth || 0));
  const rest = board.slice(1);
  host.innerHTML = rest.map((trend) => `
    <li class="${Number(trend.growth) > 0 ? "paying" : ""}">
      <div class="trend-title">
        <b>${escapeHtml(trend.title)}</b>
      </div>
      <p class="trend-meta">${priceMeta(trend)}</p>
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
    if (who) who.textContent = "Pick a trader";
    return;
  }
  if (who) who.textContent = creature.name;
  if (swatch) swatch.style.background = creature.color;

  const trace = (state.traces || {})[creature.id] || {};
  const rate = smoothSeries(trace.rate || []);
  const twin = smoothSeries(trace.twin || []);
  const span = chartSpan(rate, twin);
  strokeSeries(ctx, twin, "#9a9288", width, height, span);
  strokeSeries(ctx, rate, creature.color || "#d6ff4a", width, height, span);
}

function chartSpan(rate, twin) {
  const values = [...rate, ...twin, 0];
  const low = Math.min(...values);
  const high = Math.max(...values);
  const pad = Math.max(1, (high - low) * 0.08);
  return { low: low - pad, high: high + pad };
}

function smoothSeries(values) {
  return values.map((value, index) => {
    const slice = values.slice(Math.max(0, index - 2), index + 1);
    return slice.reduce((sum, item) => sum + item, 0) / slice.length;
  });
}

function strokeSeries(ctx, values, color, width, height, span) {
  if (values.length < 2) return;
  const heightSpan = span.high - span.low || 1;
  const point = (value, index) => ({
    x: 8 + (index / (values.length - 1)) * (width - 16),
    y: height - 10 - ((value - span.low) / heightSpan) * (height - 20),
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

const STYLES = {
  hottest: "Sells the weakest move and buys the strongest outside, only when the new move is better.",
  second: "Sells the winner and buys the second-best move outside.",
  patient: "Sells the weakest move and buys the strongest only when it is at least 1.75× bigger.",
  crowd: "Sells the busiest coin and buys the quietest volume outside.",
  size: "Sells the quietest volume and buys the busiest coin outside.",
  wander: "Sells the middle move and buys the middle move outside.",
};

function drawInspector(state) {
  const creature = (state.creatures || []).find((row) => row.id === selected) || state.creatures?.[0];
  const host = $("inspector");
  if (!creature) {
    host.innerHTML = `<p class="inspector-empty">Pick a trader.</p>`;
    return;
  }
  const activity = creature.activity || {};
  const motors = activity.motor || [];
  const trading = creature.total != null ? Number(creature.total) : 1000 + (Number(creature.score) || 0);
  const still = 1000 + (Number(creature.twin_pnl) || 0);
  const stillNames = (creature.still || []).join(" · ");
  host.innerHTML = `
    <header>
      <h3 style="color:${creature.color}">${escapeHtml(creature.name)}</h3>
      <p class="meta">${escapeHtml(creature.taste || "")} · seed ${escapeHtml(creature.seed ?? "")}</p>
      <p class="compare" title="${escapeHtml(stillNames ? `Never sold ${stillNames}` : "Same opening coins, never sold")}">
        <span><em>trading</em><b style="color:${moneyTone(creature.score)}">${fmtMoney(trading)}</b></span>
        <span><em>held still</em><b style="color:${moneyTone(creature.twin_pnl)}">${fmtMoney(still)}</b></span>
      </p>
    </header>
    <div class="visuals">${visuals(state, creature)}</div>
    <div class="brain" title="What this trader is firing">${brainCells(activity.association, creature.color)}</div>
    <div class="motors">${motorCells(motors, creature)}</div>`;
}

function visuals(state, creature) {
  const setup = state.setup || {};
  const mix = creature.mix || {};
  const share = (key) => Math.round((Number(mix[key]) || 0) * 100);
  const chase = share("post");
  const hold = share("reply");
  const watch = share("lurk");
  const fade = share("raid");
  const nursery = creature.nursery_reply == null ? 0 : Math.round(Number(creature.nursery_reply) * 100);
  const calm = creature.calm == null ? 0 : Math.round(Number(creature.calm) * 100);
  const learning = creature.mode === "aroused";
  const color = creature.color || "var(--gm)";
  return `
    <div class="meters" title="${escapeHtml(STYLES[creature.style] || "")}">
      ${meter("mod", setup.modules, 32, color)}
      ${meter("learn", setup.learn, 0.4, color)}
      ${meter("mem", setup.memory, 1, color)}
      ${meter("wake", setup.surprise, 1, color)}
    </div>
    <div class="shift" title="Held when it woke up, chases now">
      <span>then <em>${nursery}%</em></span>
      <b><i style="width:${nursery}%"></i></b>
      <span>now <em>${chase}%</em></span>
      <b class="now"><i style="width:${chase}%;background:${color}"></i></b>
    </div>
    <div class="verbmix" title="watch ${watch}% · chase ${chase}% · hold ${hold}% · fade ${fade}%">
      <i style="width:${watch}%;background:#9fd4ff"></i>
      <i style="width:${chase}%;background:${color}"></i>
      <i style="width:${hold}%;background:#c8bfb4"></i>
      <i style="width:${fade}%;background:#ffcf70"></i>
    </div>
    <div class="calm ${learning ? "learning" : ""}" title="${learning ? "Learning" : "Steady"} · ${calm}% calm · ${creature.sweeps || 0} sweeps">
      <b><i style="width:${calm}%;background:${color}"></i></b>
      <em>${learning ? "learning" : "steady"}</em>
    </div>`;
}

function meter(label, value, max, color) {
  const amount = Number(value) || 0;
  const pct = Math.max(6, Math.min(100, (amount / max) * 100));
  return `<span class="meter" title="${label} ${amount}"><b><i style="height:${pct.toFixed(0)}%;background:${color}"></i></b><em>${label}</em></span>`;
}

function setupLine(state) {
  const setup = state.setup || {};
  if (!setup.modules) return "Same Cadence setup for every trader.";
  return `${setup.modules} modules · learns at ${setup.learn} · memory ${setup.memory} · surprise wakes it at ${setup.surprise}`;
}

function knowledgeLine(creature) {
  if (!creature.ready) return "Still arming.";
  const mix = creature.mix || {};
  const chase = Math.round((Number(mix.post) || 0) * 100);
  const hold = Math.round((Number(mix.reply) || 0) * 100);
  const calm = creature.calm == null ? null : Math.round(Number(creature.calm) * 100);
  const nursery = creature.nursery_reply == null ? null : Math.round(Number(creature.nursery_reply) * 100);
  const mode = creature.mode === "aroused" ? "Learning" : "Steady";
  const parts = [];
  if (nursery != null) parts.push(`Left holding ${nursery}%.`);
  parts.push(`This round: chase ${chase}%, hold ${hold}%.`);
  parts.push(mode);
  if (calm != null) parts.push(`${calm}% calm`);
  if (creature.sweeps) parts.push(`${creature.sweeps} sweeps`);
  if (creature.learned) parts.push("a lesson landed");
  const head = parts.splice(0, nursery != null ? 2 : 1);
  return `${head.join(" ")} ${parts.join(" · ")}`.trim();
}

function bagText(creature) {
  const rows = creature.bag || [];
  if (!rows.length) return "No bag yet.";
  return rows.map((row) => `${row.title} ${fmtInt(row.gain)}`).join(" · ");
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

async function watch() {
  await poll();
  window.setTimeout(watch, 200);
}

watch();
