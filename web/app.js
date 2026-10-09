const $ = (id) => document.getElementById(id);

let selected = "frog";

const play = $("play");
const round = $("round");

play.addEventListener("click", () => send(play.dataset.cmd || "play"));
round.addEventListener("click", () => send("round"));

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
  const live = state.phase === "live";
  play.disabled = !live;
  round.disabled = !live;
  play.textContent = state.running ? "Pause" : "Play";
  play.dataset.cmd = state.running ? "pause" : "play";
  const growing = growingTrend(state);

  $("regime").dataset.regime = "viral";
  $("regime-name").textContent = growing.title || "reading trends";
  $("regime-pays").textContent = live
    ? `${Math.round(growing.growth || 0)} new posts an hour`
    : "reading live trends";
  $("phase-label").textContent = live ? (state.running ? "ranking" : "paused") : "first lesson";
  $("moment").textContent = String(state.moment ?? 0);

  $("score-live").textContent = fmt(state.totals?.live);
  $("score-frozen").textContent = fmt(state.totals?.frozen);
  $("score-random").textContent = fmt(state.totals?.random);
  $("event").textContent = (state.events && state.events[state.events.length - 1]) || nurseryLine(state.progress);

  drawNursery(state);
  drawRanking(state);
  drawTrends(state);
  drawChart(state.history || []);
  drawInspector(state);
}

function growingTrend(state) {
  const board = state.source?.board || [];
  return board.find((item) => item.paying) || board[0] || {};
}

function nurseryLine(progress) {
  if (!progress) return "Reading the live feed.";
  if (progress.phase === "reading") return "Reading which trend is growing fastest.";
  const done = progress.moments ? Math.round((100 * progress.moment) / progress.moments) : 0;
  const who = progress.name || "a brain";
  return `First lesson for ${who}: sit on a quiet trend. Brain ${progress.index + 1} of ${progress.count}, ${done}% through.`;
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
      <p>${nurseryLine(progress)} After this, only the fastest-growing trend adds points. The brains are not told its name.</p>
      <div class="track"><i style="width:${pct}%"></i></div>
      <p>${raised}</p>
    </div>`;
}

function drawRanking(state) {
  const host = $("ranking");
  const rows = state.ranking || state.creatures || [];
  const seen = new Set();
  rows.forEach((creature) => {
    seen.add(creature.id);
    let item = host.querySelector(`[data-id="${creature.id}"]`);
    if (!item) {
      item = document.createElement("li");
      item.dataset.id = creature.id;
      item.addEventListener("click", () => {
        selected = creature.id;
      });
      host.appendChild(item);
    }
    item.className = (creature.rank === 1 ? "leader" : "") + (creature.id === selected ? " selected" : "");
    item.style.order = String(creature.rank || 0);
    const tone = (Number(creature.score) || 0) >= 0 ? "var(--gm)" : "var(--panic)";
    const payTone = (Number(creature.last_pay) || 0) > 0 ? "var(--gm)" : "var(--panic)";
    item.innerHTML = `
      <span class="place">${creature.rank || "–"}</span>
      <span class="mark" style="background:${creature.color};color:${creature.ink}">${escapeHtml(creature.mark)}</span>
      <span class="detail">
        <span class="who">${escapeHtml(creature.name)}</span>
        <span class="trend-name${creature.on_growing ? " on" : ""}">${escapeHtml(creature.ready ? `sitting on ${creature.trend}` : "still in the first lesson")}</span>
        <span class="lesson">${escapeHtml(lessonLine(creature))}</span>
        ${mixBar(state, creature)}
        <span class="twin-line">Copy that stopped learning is still on ${escapeHtml(trendTitle(state, creature.twin))}</span>
      </span>
      <span class="score" style="color:${tone}">${fmt(creature.score)}<span class="pay-chip" style="color:${payTone}">last ${fmt(creature.last_pay)}</span></span>`;
  });
  host.querySelectorAll("li").forEach((item) => {
    if (!seen.has(item.dataset.id)) item.remove();
  });
}

const SLOT_COLOR = {
  post: "#d6ff4a",
  lurk: "#9fd4ff",
  raid: "#ffcf70",
  reply: "#c8bfb4",
};

function lessonLine(creature) {
  if (!creature.ready) return "Still in the first lesson, on a quiet trend.";
  const surprised = creature.mode === "aroused";
  if (surprised && creature.on_growing) return "Surprised. This trend added points, so the next pick leans toward it.";
  if (surprised) return "Surprised. This trend cost points, so the next pick leans away.";
  if (creature.on_growing) return "Calm. Staying on the trend that adds points.";
  return "Calm. Still on a trend that costs points.";
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
  host.innerHTML = board.map((trend) => `
    <li class="${trend.paying ? "paying" : ""}">
      <div class="trend-title">
        <b>${escapeHtml(trend.title)}</b>
        ${trend.paying ? `<span class="badge">adds points</span>` : ""}
      </div>
      <p class="trend-meta">${Math.round(trend.growth || 0)} posts/hour · ${Number(trend.post_count || 0).toLocaleString()} posts${trend.status ? ` · ${escapeHtml(trend.status)}` : ""}</p>
      ${trend.sample ? `<p class="trend-sample">${escapeHtml(trend.sample)}</p>` : ""}
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

function drawChart(history) {
  const canvas = $("chart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#100e0c";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(244,239,230,0.12)";
  ctx.beginPath();
  ctx.moveTo(0, height / 2);
  ctx.lineTo(width, height / 2);
  ctx.stroke();

  if (!history.length) {
    $("chart-note").textContent = "share sitting on the trend that adds points";
    return;
  }
  const smooth = trailing(history, 12);
  stroke(ctx, smooth.map((row) => row.random), "#6d645c", width, height);
  stroke(ctx, smooth.map((row) => row.frozen), "#c8bfb4", width, height);
  stroke(ctx, smooth.map((row) => row.live), "#d6ff4a", width, height, "rgba(214,255,74,0.18)");
  const last = smooth[smooth.length - 1];
  $("chart-note").textContent = `on the trend that adds points · still learning ${pct(last.live)} · stopped ${pct(last.frozen)}`;
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
    host.innerHTML = `<p class="inspector-empty">Pick a brain.</p>`;
    return;
  }
  host.innerHTML = `
    <header>
      <h3 style="color:${creature.color}">${escapeHtml(creature.name)}</h3>
      <p class="meta">${escapeHtml(lessonLine(creature))}</p>
    </header>
    <p class="meta">Last score ${fmt(creature.last_pay)}. Sitting on ${escapeHtml(creature.trend || "the first lesson")}.</p>
    <p class="meta">The copy that stopped learning is still on ${escapeHtml(trendTitle(state, creature.twin))}.</p>`;
}

function fmt(value) {
  const number = Number(value) || 0;
  const text = number.toFixed(1);
  return number > 0 ? `+${text}` : text;
}

function pct(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

poll();
setInterval(poll, 160);
