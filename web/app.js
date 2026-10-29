"use strict";

/* ------------------------------------------------------------------ *
 *  Helpers
 * ------------------------------------------------------------------ */
const $ = (sel, root = document) => root.querySelector(sel);
const cloneOpts = (o) => {
  if (Array.isArray(o)) return o.map(cloneOpts);
  if (o && typeof o === "object") return Object.fromEntries(Object.entries(o).map(([k, v]) => [k, cloneOpts(v)]));
  return o;
};
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 1) => (v === null || v === undefined || Number.isNaN(Number(v)) ? "–" : Number(v).toLocaleString("de-DE", { minimumFractionDigits: 0, maximumFractionDigits: d }));
const pct = (v, d = 1) => (v === null || v === undefined ? "–" : `${num(v * 100, d)} %`);
const PALETTE = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#06b6d4", "#a855f7", "#ec4899", "#84cc16", "#f97316", "#14b8a6", "#8b5cf6", "#eab308"];

function toast(message, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "err" ? 8000 : 4000);
}

async function request(path, { params, method = "GET", body, headers = {}, raw } = {}) {
  const url = new URL(path, location.origin);
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined) url.searchParams.set(k, v);
  });
  const init = { method, headers: { ...headers } };
  if (method === "POST") init.headers["X-Requested-With"] = "pubquizstats";
  if (body !== undefined) {
    if (raw) init.body = body;
    else {
      init.body = JSON.stringify(body);
      init.headers["Content-Type"] = "application/json";
    }
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    let message = res.statusText;
    let detail = {};
    try { detail = await res.json(); message = detail.error || message; } catch { /* not json */ }
    throw Object.assign(new Error(message), { detail });
  }
  return res;
}
const api = async (path, opts) => (await request(path, opts)).json();

async function download(path, params, button) {
  const label = button ? button.innerHTML : null;
  if (button) { button.disabled = true; button.innerHTML = "⏳ Wird erstellt …"; }
  try {
    const res = await request(path, { params });
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
    const name = match ? decodeURIComponent(match[1]) : "export";
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast(`Gespeichert: ${name}`, "ok");
  } catch (err) {
    toast(err.message, "err");
  } finally {
    if (button) { button.disabled = false; button.innerHTML = label; }
  }
}

/* ------------------------------------------------------------------ *
 *  Report definitions
 * ------------------------------------------------------------------ */
// needs: which filter controls are relevant for the report
const REPORTS = {
  standings: { group: "Meisterschaft", label: "Tabelle", desc: "Aktueller Meisterschaftsstand aller Teams", needs: ["year"] },
  "standing-progress": { group: "Meisterschaft", label: "Saisonverlauf", desc: "Entwicklung der Meisterschaftspunkte von Event zu Event", needs: ["year", "top"], exports: [{ label: "PDF-Diagramm", kind: "standing-progress-pdf" }] },
  leaders: { group: "Meisterschaft", label: "Kategorien", desc: "Die besten Teams je Kategorie sowie bei Punkten, Schnitt und Bonus", needs: ["year", "min_events"] },
  consistency: { group: "Meisterschaft", label: "Konstanz", desc: "Wie konstant die Teams über die Events hinweg spielen", needs: ["year", "min_events"] },

  list: { group: "Events", label: "Eventliste", desc: "Alle importierten Quiz-Events im Überblick", needs: [] },
  result: { group: "Events", label: "Event-Ergebnis", desc: "Komplette Rangliste eines einzelnen Events", needs: ["event"] },
  "Event Result Team": { group: "Events", label: "Team-Ergebnis", desc: "Ergebnis des gewählten Teams in einem Event, nach Kategorien", needs: ["event", "team"] },
  "event-difficulty": { group: "Events", label: "Schwierigkeit", desc: "Wie schwer war das Event im Vergleich zu allen anderen, je Kategorie?", needs: ["event"] },

  "event-progress": { group: "Events", label: "Eventverlauf", desc: "Entwicklung der Punkte aller Teams über die Runden eines Events", needs: ["event", "event_top"] },

  team: { group: "Team", label: "Überblick", desc: "Saisonverlauf und alle Events des gewählten Teams", needs: ["year", "team"], teamExports: true },
  averages: { group: "Team", label: "Stärken/Schwächen", desc: "In welchen Kategorien das Team über oder unter dem Feld liegt", needs: ["year", "team"], teamExports: true },
  radar: { group: "Team", label: "Radar-Plots", desc: "Punkte und Platzierung des Teams je Kategorie als Radar-Plots", needs: ["year", "team", "min_events"], teamExports: true, exports: [{ label: "Radar SVG", kind: "radar-svg" }] },
  "bonus-efficiency": { group: "Team", label: "Bonus-Effizienz", desc: "Wie gut wurde die Bonusrunde genutzt? Die Bonus-Effizienz setzt die Punkte, die mit der gewählten Bonusrunde erzielt wurden, ins Verhältnis zu den Punkten, die maximal möglich gewesen wären. Als Maßstab dient die beste Ausbeute, die das Team in einer der anderen Kategorien erreicht hat, denn dort hätte der Bonus am meisten gebracht. Bei der Kategorie „Interessantes“ ist nicht bekannt, ob das Anagramm richtig gelöst wurde. Deshalb wird dort per Wahrscheinlichkeitsschätzung abgeleitet, ob das Anagramm richtig war, und die möglichen Bonuspunkte werden entsprechend geschätzt. 100 % bedeuten: Die Bonusrunde war die bestmögliche Wahl.", needs: ["year", "team"], teamExports: true },
  "Bonus Details": { group: "Team", label: "Bonus-Details", desc: "Welche Bonuspunkte in welcher Kategorie möglich gewesen wären. Für jede Kategorie wird berechnet, wie viele Punkte das Team erreicht hätte, wenn es sie als Bonusrunde gewählt hätte. Puzzle- und Bilderrunde sind als Bonusrunde nicht möglich und bleiben unberücksichtigt. Bei der Kategorie „Interessantes“ ist nicht bekannt, ob das Anagramm richtig gelöst wurde. Deshalb wird dort per Wahrscheinlichkeitsschätzung abgeleitet, wie wahrscheinlich das Anagramm richtig war, und daraus ein erwarteter Bonuswert ermittelt.", needs: ["year", "team"], teamExports: true },
  "team-category-detail": { group: "Team", label: "Themenrunden-Details", desc: "Puzzle-, Bild- und Überraschungsrunde des Teams pro Event", needs: ["year", "team"], teamExports: true, exports: [{ label: "Kategorie-PDF", kind: "team-category-pdf" }] },
  "team-puzzle-details": { group: "Team", label: "Puzzle-Details", desc: "Punkteschnitt des Teams je Puzzle-Kategorie im Vergleich zum Feld", needs: ["year", "team"] },

  difficulty: { group: "Kategorien", label: "Kategorieschwierigkeit", desc: "Durchschnittspunkte je Kategorie über alle Teams", needs: ["year"] },
  "round-strength": { group: "Kategorien", label: "Kategorierangliste", desc: "Rangliste der besten Teams je Kategorie", needs: ["year", "round", "min_events", "top", "team"] },
  "puzzle-categories": { group: "Kategorien", label: "Puzzle", desc: "Punkteschnitt aller Teams je Puzzle-Kategorie", needs: ["year"] },
  "Theme Difficulties": { group: "Kategorien", label: "Themenrunden", desc: "Puzzle-, Bilder- und Überraschungsrunden der Events im Vergleich", needs: ["year"], exports: [{ label: "Themen-PDF", kind: "theme-pdf" }] },
};
const GROUPS = ["Meisterschaft", "Events", "Team", "Kategorien"];

/* ------------------------------------------------------------------ *
 *  State
 * ------------------------------------------------------------------ */
const state = {
  meta: null,
  view: "standings",
  params: { year: "", team: "", event_id: "", round_name: "", min_events: 2, top: 10 },
  data: null,
  token: 0,
  charts: [],
};

function saveParams() {
  localStorage.setItem("pqs.params", JSON.stringify(state.params));
}
function loadParams() {
  try { Object.assign(state.params, JSON.parse(localStorage.getItem("pqs.params") || "{}")); } catch { /* ignore */ }
}

/* ------------------------------------------------------------------ *
 *  Theme + Chart defaults
 * ------------------------------------------------------------------ */
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("pqs.theme", theme);
}
function initTheme() {
  const saved = localStorage.getItem("pqs.theme");
  applyTheme(saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  $("#theme-toggle").addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    if (state.data) renderReport();
  });
}

function destroyCharts() {
  state.charts.forEach((c) => c.destroy());
  state.charts = [];
}

function baseOptions(type, custom = {}) {
  const text = cssVar("--text");
  const muted = cssVar("--muted");
  const grid = cssVar("--grid");
  const opts = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 500 },
    interaction: { mode: "nearest", intersect: false },
    plugins: { legend: { labels: { color: text, usePointStyle: true, boxWidth: 8 } }, tooltip: { padding: 10, cornerRadius: 8 } },
  };
  if (type === "radar") {
    opts.scales = { r: { angleLines: { color: grid }, grid: { color: grid }, pointLabels: { color: text, font: { size: 12 } }, ticks: { color: muted, backdropColor: "transparent" }, suggestedMin: 0, suggestedMax: 1 } };
  } else {
    opts.scales = {
      x: { ticks: { color: muted }, grid: { color: grid, display: custom.indexAxis !== "y" } },
      y: { ticks: { color: muted }, grid: { color: grid }, beginAtZero: true },
    };
  }
  return deepMerge(opts, custom);
}

// Tooltip-Zusatzzeilen (Thema, Puzzle-Kategorie/Lösung) je Datensatz-Index
const themeLines = (e, keys) => (i) => {
  const k = keys[i];
  if (!k) return [];
  const out = [];
  if (k.topic && e[k.topic]) out.push(`Thema: ${e[k.topic]}`);
  if (k.category && e[k.category]) out.push(`Kategorie: ${e[k.category]}`);
  if (k.solution && e[k.solution]) out.push(`Lösung: ${e[k.solution]}`);
  return out;
};

function deepMerge(a, b) {
  for (const [k, v] of Object.entries(b)) {
    a[k] = v && typeof v === "object" && !Array.isArray(v) && a[k] && typeof a[k] === "object" ? deepMerge(a[k], v) : v;
  }
  return a;
}

/* ------------------------------------------------------------------ *
 *  Building blocks (blocks are rendered by mountBlocks)
 * ------------------------------------------------------------------ */
const kpis = (items) => ({ kind: "kpis", items });
const chart = (title, type, data, options = {}, { height = 340, half = false } = {}) => ({ kind: "chart", title, type, data, options, height, half });
const table = (title, columns, rows, { highlight, onRow, sort } = {}) => ({ kind: "table", title, columns, rows, highlight, onRow, sort });

const col = (key, label, fmt, align) => ({ key, label, fmt: fmt || ((v) => esc(v ?? "–")), align: align || (fmt ? "num" : "") });
const colText = (key, label, fmt) => col(key, label, fmt, "");
const colNum = (key, label, d = 1) => col(key, label, (v) => num(v, d), "num");

function dataset(label, data, i, extra = {}) {
  const color = PALETTE[i % PALETTE.length];
  return { label, data, backgroundColor: color + "cc", borderColor: color, borderWidth: 2, borderRadius: 6, ...extra };
}
const lineSet = (label, data, i, extra = {}) => dataset(label, data, i, { tension: 0.3, pointRadius: 3, backgroundColor: PALETTE[i % PALETTE.length] + "33", ...extra });

function mountBlocks(blocks) {
  const root = $("#content");
  root.innerHTML = "";
  destroyCharts();
  const hl = (state.params.team || "").toLowerCase();

  blocks.forEach((block, bi) => {
    if (block.kind === "kpis") {
      const el = document.createElement("div");
      el.className = "kpis";
      el.innerHTML = block.items.map((k) => `<div class="kpi"><div class="label">${esc(k.label)}</div><div class="value">${esc(k.value)}</div>${k.sub ? `<div class="sub">${esc(k.sub)}</div>` : ""}</div>`).join("");
      root.appendChild(el);
    } else if (block.kind === "chart") {
      const el = document.createElement("div");
      el.className = `card${block.half ? " half" : ""}`;
      el.innerHTML = `<h2>${esc(block.title)}</h2><div class="chart-wrap" style="height:${block.height}px"><canvas></canvas></div>`;
      root.appendChild(el);
      state.charts.push(new Chart($("canvas", el), { type: block.type, data: block.data, options: baseOptions(block.type, cloneOpts(block.options)) }));
    } else if (block.kind === "table") {
      const el = document.createElement("div");
      el.className = "card";
      el.innerHTML = `<div class="card-head"><h2>${esc(block.title)}</h2><input type="search" placeholder="Filtern …" class="tbl-filter" style="min-width:160px"></div><div class="table-wrap"></div>`;
      root.appendChild(el);
      mountTable($(".table-wrap", el), $(".tbl-filter", el), block, hl);
    }
  });
}

function mountTable(wrap, filterInput, block, hl) {
  let sortKey = block.sort?.key ?? null;
  let desc = block.sort?.desc ?? false;
  let filter = "";

  const draw = () => {
    let rows = block.rows.map((r, i) => ({ r, i }));
    if (filter) rows = rows.filter(({ r }) => block.columns.some((c) => String(r[c.key] ?? "").toLowerCase().includes(filter)));
    if (sortKey) {
      rows.sort((a, b) => {
        const x = a.r[sortKey], y = b.r[sortKey];
        const cmp = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "de", { numeric: true });
        return desc ? -cmp : cmp;
      });
    }
    wrap.innerHTML = `<table><thead><tr>${block.columns.map((c) => `<th class="${c.align === "num" ? "num " : ""}${c.key === sortKey ? "sorted" + (desc ? " desc" : "") : ""}" data-key="${esc(c.key)}">${esc(c.label)}</th>`).join("")}</tr></thead><tbody>${rows.map(({ r, i }) => {
      const isHl = hl && String(r.team_name ?? "").toLowerCase() === hl;
      return `<tr class="${isHl ? "hl " : ""}${block.onRow ? "clickable" : ""}" data-i="${i}">${block.columns.map((c) => `<td class="${c.align === "num" ? "num" : ""}">${c.fmt(r[c.key], r)}</td>`).join("")}</tr>`;
    }).join("")}</tbody></table>`;
    wrap.querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
      const key = th.dataset.key;
      desc = sortKey === key ? !desc : false;
      sortKey = key;
      draw();
    }));
    if (block.onRow) wrap.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => block.onRow(block.rows[Number(tr.dataset.i)])));
  };
  filterInput.addEventListener("input", () => { filter = filterInput.value.trim().toLowerCase(); draw(); });
  draw();
}

/* ------------------------------------------------------------------ *
 *  Report renderers: data -> blocks
 * ------------------------------------------------------------------ */
const labelOf = (e) => `${e.event_date} ${e.location}`;
const barColors = (names, i = 0) => names.map((n) => (state.params.team && n.toLowerCase() === state.params.team.toLowerCase() ? PALETTE[1] : PALETTE[i] + "cc"));
const openEvent = (id, view) => { state.params.event_id = String(id); state.params.event_top = ""; saveParams(); navigate(view); };

function teamLineSets(teams, values) {
  const sel = (state.params.team || "").toLowerCase();
  const others = PALETTE.filter((_, k) => ![1, 8, 11].includes(k));
  return teams.map((t, i) => {
    const isSel = sel && t.team_name.toLowerCase() === sel;
    const c = isSel ? "#facc15" : others[i % others.length];
    return lineSet(t.team_name, values(t), i, { borderColor: c, backgroundColor: c + "33", pointBackgroundColor: c, ...(isSel ? { borderWidth: 6, pointRadius: 4, order: -1 } : { borderWidth: 2, pointRadius: 2, order: 1 }) });
  });
}

const RENDERERS = {
  list(events) {
    return [
      kpis([{ label: "Events", value: events.length }, { label: "Teams (Ø)", value: num(events.reduce((s, e) => s + e.team_count, 0) / (events.length || 1), 0) }]),
      chart("Teilnehmende Teams je Event", "bar", { labels: events.map(labelOf), datasets: [dataset("Teams", events.map((e) => e.team_count), 0)] }, { plugins: { legend: { display: false } } }),
      table("Events", [colText("id", "#"), colText("event_date", "Datum"), colText("location", "Ort"), colNum("team_count", "Teams", 0), colText("winner", "Siegerteam"), colText("winner_bonus", "Bonusrunde des Siegerteams")], events, { onRow: (r) => openEvent(r.id, "result"), sort: { key: "event_date", desc: true } }),
    ];
  },

  result(d) {
    const teams = d.teams;
    const top = teams.slice(0, 15);
    return [
      kpis([
        { label: "Event", value: d.event.event_date, sub: d.event.location },
        { label: "Teams", value: teams.length },
        { label: "Siegerteam", value: teams[0]?.team_name ?? "–", sub: teams[0] ? `${teams[0].total} Punkte` : "" },
        { label: "Ø Punkte", value: num(teams.reduce((s, t) => s + t.total, 0) / (teams.length || 1)) },
      ]),
      table("Rundenthemen", [colText("puzzle_category", "Puzzle-Kategorie"), colText("puzzle_solution", "Puzzle-Lösung"), colText("image_round_topic", "Bilderrunde-Thema"), colText("surprise_round_topic", "Überraschungsrunden-Thema")], [d.event]),
      chart("Top 15 – Gesamtpunkte", "bar", { labels: top.map((t) => t.team_name), datasets: [dataset("Gesamt", top.map((t) => t.total), 0, { backgroundColor: barColors(top.map((t) => t.team_name)) }), dataset("davon Puzzle", top.map((t) => t.puzzle_points), 2)] }, { indexAxis: "y" }, { height: Math.max(340, top.length * 30) }),
      table("Ergebnis", [colNum("team_rank", "Rang", 0), colText("team_name", "Team"), colNum("total", "Punkte", 0), colNum("puzzle_points", "Puzzle", 0), colText("bonus_round", "Bonusrunde")], teams),
    ];
  },

  "Event Result Team"(d) {
    const t = d.team;
    const rounds = d.rounds;
    return [
      kpis([
        { label: "Platzierung", value: `${t.position} / ${t.total_teams}`, sub: `${t.team_name} · ${d.event.event_date}` },
        { label: "Punkte", value: t.total, sub: `Rundenpunkte ${num(t.round_points_sum)}` },
        { label: "Meisterschaftspunkte", value: t.championship_points },
        { label: "Bonus-Effizienz", value: pct(t.bonus_efficiency), sub: `${t.bonus_round} · ${num(t.achieved_bonus_points)}/${num(t.possible_bonus_points)}` },
        { label: "Puzzle", value: t.puzzle_points, sub: `Platz ${t.puzzle_position}/${t.puzzle_total_teams} · Ø ${num(t.puzzle_average)}` },
      ]),
      table("Rundenthemen", [colText("puzzle_category", "Puzzle-Kategorie"), colText("puzzle_solution", "Puzzle-Lösung"), colText("image_round_topic", "Bilderrunde-Thema"), colText("surprise_round_topic", "Überraschungsrunden-Thema")], [d.event]),
      chart("Rundenpunkte vs. Feld", "bar", { labels: rounds.map((r) => r.round_name), datasets: [dataset("Team", rounds.map((r) => r.points), 0), dataset("Ø aller Teams", rounds.map((r) => r.category_average_points), 1)] }),
      table("Runden", [colText("round_name", "Runde"), colNum("raw_points", "Punkte"), colNum("points", "Punkte ohne Bonus"), col("is_bonus_round", "Bonus", (v) => (v ? '<span class="pill">Bonus</span>' : ""), ""), colNum("category_position", "Platz", 0), colNum("category_average_points", "Ø Feld", 2)], rounds),
    ];
  },

  standings(d) {
    const rows = d.standings.map((r, i) => ({ ...r, rank: i + 1, avg: r.events_count ? r.points / r.events_count : null }));
    const top = rows.slice(0, 15);
    return [
      kpis([
        { label: "Events", value: d.events_count },
        { label: "Teams", value: d.teams_count },
        { label: "Spitzenreiter", value: rows[0]?.team_name ?? "–", sub: rows[0] ? `${rows[0].points} Punkte · ${rows[0].wins} Siege` : "" },
      ]),
      table("Gesamtwertung", [colNum("rank", "Rang", 0), colText("team_name", "Team"), colNum("points", "Punkte", 0), colNum("events_count", "Events", 0), colNum("wins", "Siege", 0), colNum("avg", "Meisterschaftspunkte pro Event"), colNum("avg_total_points", "Durchschnittspunkte")], rows),
      chart("Top 15 – Meisterschaftspunkte", "bar", { labels: top.map((r) => r.team_name), datasets: [dataset("Punkte", top.map((r) => r.points), 0, { backgroundColor: barColors(top.map((r) => r.team_name)) })] }, { indexAxis: "y", plugins: { legend: { display: false } } }, { height: Math.max(340, top.length * 30), half: true }),
      chart("Siege der Top 15", "bar", { labels: top.map((r) => r.team_name), datasets: [dataset("Siege", top.map((r) => r.wins), 2)] }, { indexAxis: "y", plugins: { legend: { display: false } } }, { height: Math.max(340, top.length * 30), half: true }),
    ];
  },

  "standing-progress"(d) {
    return [
      kpis([{ label: "Events", value: d.events.length }, { label: "Spitzenreiter", value: d.teams[0]?.team_name ?? "–", sub: d.teams[0] ? `${d.teams[0].final_points} Punkte` : "" }]),
      chart("Verlauf der Meisterschaftspunkte", "line", { labels: d.events.map((e) => e.label), datasets: teamLineSets(d.teams, (t) => t.values) }, {}, { height: 960 }),
      table("Aktuelle Top-Teams", [colNum("pos", "Pos", 0), colText("team_name", "Team"), colNum("final_points", "Punkte", 0)], d.teams.map((t, i) => ({ ...t, pos: i + 1 }))),
    ];
  },

  leaders(d) {
    const cats = d.category_leaders;
    return [
      kpis([
        { label: "Meisterschaft", value: d.championship_leader?.team_name ?? "–", sub: d.championship_leader ? `${d.championship_leader.points} Punkte · ${d.championship_leader.wins} Siege` : "" },
        { label: "Punkteschnitt", value: d.points_average_leader?.team_name ?? "–", sub: d.points_average_leader ? `Ø ${num(d.points_average_leader.avg_points, 2)} (${d.points_average_leader.events} Events)` : "" },
        { label: "Bonus-Effizienz", value: d.bonus_efficiency_leader?.team_name ?? "–", sub: d.bonus_efficiency_leader ? `${pct(d.bonus_efficiency_leader.avg_efficiency)} (${d.bonus_efficiency_leader.events} Events)` : "" },
      ]),
      chart("Bester Schnitt je Kategorie", "bar", { labels: cats.map((c) => `${c.category_name} – ${c.team_name}`), datasets: [dataset("Ø Punkte", cats.map((c) => c.avg_points), 0)] }, { indexAxis: "y", plugins: { legend: { display: false } } }, { height: Math.max(300, cats.length * 34) }),
      table("Kategorie-Leader", [colText("category_name", "Kategorie"), colText("team_name", "Team"), colNum("avg_points", "Ø Punkte", 2), colNum("events", "Events", 0)], cats),
    ];
  },

  team(d) {
    const ev = d.events;
    const best = ev.reduce((b, e) => (b === null || e.position < b.position ? e : b), null);
    const avg = ev.reduce((s, e) => s + e.total_points, 0) / (ev.length || 1);
    return [
      kpis([
        { label: "Teilnahmen", value: ev.length },
        { label: "Beste Platzierung", value: best ? best.position : "–", sub: best ? labelOf(best) : "" },
        { label: "Ø Punkte", value: num(avg, 2) },
        { label: "Ø Prozent", value: `${num(ev.reduce((s, e) => s + e.percentage, 0) / (ev.length || 1))} %` },
      ]),
      chart("Platzierung je Event (niedriger = besser)", "line", { labels: ev.map(labelOf), datasets: [lineSet("Platz", ev.map((e) => e.position), 0, { fill: true })] }, { scales: { y: { reverse: true, beginAtZero: false, min: 1, max: Math.max(30, ...ev.map((e) => e.position || 0)) } }, plugins: { legend: { display: false } } }, { half: true }),
      chart("Punkte je Event", "bar", { labels: ev.map(labelOf), datasets: [dataset("Punkte", ev.map((e) => e.total_points), 2)] }, { scales: { y: { beginAtZero: false, min: Math.min(30, Math.floor(Math.min(...ev.map((e) => e.total_points).filter((v) => v != null)) / 10) * 10), max: 71, ticks: { stepSize: 10, includeBounds: false } } }, plugins: { legend: { display: false } } }, { half: true }),
      table("Events", [colText("event_date", "Datum"), colText("location", "Ort"), colNum("position", "Platz", 0), colNum("total_points", "Punkte", 0), col("percentage", "Punkte (% des Siegerteams)", (v) => `${num(v)} %`), colText("bonus_round", "Bonusrunde")], ev, { onRow: (r) => openEvent(r.event_id, "Event Result Team") }),
    ];
  },

  averages(d) {
    const rounds = d.team.round_averages;
    const overall = d.overall.round_averages;
    const rows = rounds.map((r) => {
      const overallAverage = r.round_name === "Puzzle" ? d.overall.puzzle_average : (overall[r.round_name] ?? null);
      return {
        ...r,
        overall: overallAverage,
        diff: r.avg_points != null && overallAverage != null ? r.avg_points - overallAverage : null,
      };
    });
    return [
      chart("Rundenschnitt: Team vs. Feld", "bar", { labels: rounds.map((r) => r.round_name), datasets: [dataset(d.team.team_name, rounds.map((r) => r.avg_points), 0), dataset("Ø aller Teams", rows.map((r) => r.overall), 1)] }),
      chart("Differenz zum Feld", "bar", { labels: rows.map((r) => r.round_name), datasets: [{ label: "Differenz", data: rows.map((r) => r.diff), backgroundColor: rows.map((r) => (r.diff >= 0 ? "#10b981cc" : "#ef4444cc")), borderRadius: 6 }] }, { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } }, { height: 280 }),
      table("Rundenschnitte", [colText("round_name", "Runde"), colNum("avg_points", "Team Ø", 2), colNum("overall", "Feld Ø", 2), col("diff", "Differenz", (v) => (v == null ? "–" : `<span class="pill ${v >= 0 ? "ok" : "err"}">${v >= 0 ? "+" : ""}${num(v, 2)}</span>`), "num"), colNum("appearances", "Events", 0)], rows),
    ];
  },

  "team-puzzle-details"(d) {
    const categories = d.categories;
    return [
      kpis([{ label: "Puzzle-Kategorien", value: categories.length }, { label: "Team", value: d.team_name }]),
      chart("Ø Punkte je Puzzle-Kategorie: Team vs. Feld", "bar", {
        labels: categories.map((category) => category.category),
        datasets: [
          dataset(d.team_name, categories.map((category) => category.team_avg_points), 1),
          dataset("Ø aller Teams", categories.map((category) => category.field_avg_points), 0),
        ],
      }, { scales: { y: { beginAtZero: true, max: 10 } } }, { height: Math.max(320, categories.length * 38) }),
      chart("Differenz zum Feld", "bar", {
        labels: categories.map((category) => category.category),
        datasets: [{
          label: "Differenz",
          data: categories.map((category) => category.difference),
          backgroundColor: categories.map((category) => (category.difference >= 0 ? "#10b981cc" : "#ef4444cc")),
          borderRadius: 6,
        }],
      }, { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } }, { height: Math.max(280, categories.length * 34) }),
      table("Puzzle-Kategorien", [
        colText("category", "Kategorie"),
        colNum("team_avg_points", "Team Ø", 2),
        colNum("field_avg_points", "Feld Ø", 2),
        col("difference", "Differenz", (value) => (value == null ? "–" : `<span class="pill ${value >= 0 ? "ok" : "err"}">${value >= 0 ? "+" : ""}${num(value, 2)}</span>`), "num"),
        colNum("team_events", "Team-Events", 0),
      ], categories),
    ];
  },

  radar(d) {
    const rounds = d.rounds;
    const labels = rounds.map((r) => r.round_name);
    const radarSet = (label, data, i) => ({ label, data, borderColor: PALETTE[i], backgroundColor: PALETTE[i] + "33", pointBackgroundColor: PALETTE[i] });
    const radarOptions = (valueText) => ({
      scales: { r: { ticks: { display: false } } },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${valueText(rounds[c.dataIndex], c.datasetIndex)}` } } },
    });
    const val = (v, d = 2) => (v == null ? "–" : num(v, d));
    return [
      chart("Radar – Punkteschnitt", "radar", { labels, datasets: [
        radarSet(d.team_name, rounds.map((r) => r.avg_score), 1),
        radarSet("Ø aller Teams", rounds.map((r) => r.field_avg_score), 0),
      ] }, radarOptions((r, i) => (i === 0 ? `Ø ${val(r.avg_points)} Punkte` : `Ø ${val(r.field_avg_points)} Punkte`)), { height: 480, half: true }),
      chart("Radar – Platzierung", "radar", { labels, datasets: [
        radarSet(d.team_name, rounds.map((r) => r.placement_score), 1),
      ] }, radarOptions((r) => (r.position == null ? "–" : `Platz ${r.position} / ${r.total_teams}`)), { height: 480, half: true }),
      table("Kategorierangliste", [colText("round_name", "Runde"), colNum("avg_points", "Ø Punkte", 2), colNum("position", "Platz", 0), colNum("events", "Events", 0)], rounds),
    ];
  },

  "bonus-efficiency"(d) {
    const ev = d.events;
    return [
      kpis([{ label: "Ø Bonus-Effizienz", value: pct(d.average_bonus_efficiency) }, { label: "Events", value: ev.length }]),
      chart("Bonus-Effizienz je Event", "bar", { labels: ev.map(labelOf), datasets: [dataset("Effizienz (%)", ev.map((e) => (e.bonus_efficiency ?? 0) * 100), 2)] }, { plugins: { legend: { display: false } }, scales: { y: { max: 100 } } }),
      table("Events", [colText("event_date", "Datum"), colText("location", "Ort"), colText("bonus_round", "Bonusrunde"), colNum("achieved_bonus_points", "Erreicht"), colNum("possible_bonus_points", "Möglich"), col("bonus_efficiency", "Effizienz", (v) => pct(v), "num"), colNum("position", "Platz", 0)], ev),
    ];
  },

  "Bonus Details"(d) {
    const r = d.rounds;
    return [
      kpis([{ label: "Events", value: d.events_count }]),
      chart("Ø Punkte: normal vs. hypothetischer Bonus", "bar", { labels: r.map((x) => x.round_name), datasets: [dataset("Normal", r.map((x) => x.normal_points_avg), 0), dataset("Mit Bonus", r.map((x) => x.hypothetical_bonus_points_avg), 1)] }),
      table("Bonus-Details", [colText("round_name", "Runde"), colNum("events", "Events", 0), colNum("normal_points_total", "Normal gesamt"), colNum("hypothetical_bonus_points_total", "Bonus gesamt"), colNum("normal_points_avg", "Normal Ø", 2), colNum("hypothetical_bonus_points_avg", "Bonus Ø", 2)], r),
    ];
  },

  consistency(d) {
    const rows = d.standings;
    const hl = (state.params.team || "").toLowerCase();
    return [
      kpis([{ label: "Teams", value: d.teams_count }, { label: "Konstantestes Team", value: rows.slice().sort((a, b) => a.cv_percent - b.cv_percent)[0]?.team_name ?? "–", sub: "niedrigster Variationskoeffizient" }]),
      chart("Ø Punkte vs. Streuung (links unten = schwach & konstant, rechts unten = stark & konstant)", "scatter", { datasets: [{ label: "Teams", data: rows.map((r) => ({ x: r.avg_points, y: r.stddev, name: r.team_name })), backgroundColor: rows.map((r) => (r.team_name.toLowerCase() === hl ? PALETTE[1] : PALETTE[0] + "aa")), pointRadius: rows.map((r) => (r.team_name.toLowerCase() === hl ? 8 : 5)) }] }, {
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.raw.name}: Ø ${num(c.raw.x, 1)}, Standardabweichung ${num(c.raw.y, 2)}` } } },
        scales: { x: { title: { display: true, text: "Ø Punkte", color: cssVar("--muted") }, beginAtZero: false }, y: { title: { display: true, text: "Standardabweichung", color: cssVar("--muted") } } },
      }, { height: 420 }),
      table("Konstanz", [colText("team_name", "Team"), colNum("events", "Events", 0), colNum("avg_points", "Ø Punkte", 2), colNum("stddev", "Standardabweichung", 2), colNum("cv_percent", "CV %", 1), colNum("max_points", "Max", 0), colNum("min_points", "Min", 0)], rows),
    ];
  },

  "Theme Difficulties"(d) {
    const ev = d.events;
    return [
      kpis([{ label: "Events", value: d.events_count }]),
      chart("Durchschnittspunkte der Themenrunden", "line", { labels: ev.map(labelOf), datasets: [lineSet("Puzzle", ev.map((e) => e.puzzle_average_points), 0), lineSet("Bilderrunde", ev.map((e) => e.image_average_points), 1), lineSet("Überraschung", ev.map((e) => e.surprise_average_points), 2)] }, { scales: { y: { beginAtZero: true } }, plugins: { tooltip: { callbacks: { afterLabel: (c) => themeLines(ev[c.dataIndex], [{ category: "puzzle_category", solution: "puzzle_solution" }, { topic: "image_round_topic" }, { topic: "surprise_round_topic" }])(c.datasetIndex) } } } }, { height: 380 }),
      table("Themen", [colText("event_date", "Datum"), colText("location", "Ort"), colText("puzzle_category", "Puzzle-Kategorie"), colText("puzzle_solution", "Puzzle-Lösung"), colNum("puzzle_average_points", "Puzzle Ø", 1), colText("image_round_topic", "Bilderrunde"), colNum("image_average_points", "Bilder Ø", 1), colText("surprise_round_topic", "Überraschung"), colNum("surprise_average_points", "Überr. Ø", 1)], ev),
    ];
  },

  difficulty(d) {
    const r = d.rounds.slice().sort((a, b) => a.reachable_percent - b.reachable_percent);
    return [
      kpis([{ label: "Events", value: d.events_count }, { label: "Schwerste Kategorie", value: r[0]?.round_name ?? "–", sub: r[0] ? `${num(r[0].reachable_percent, 1)} %` : "" }, { label: "Leichteste Kategorie", value: r.at(-1)?.round_name ?? "–", sub: r.length ? `${num(r.at(-1).reachable_percent, 1)} %` : "" }]),
      chart("Anteil der erreichbaren Punkte je Runde", "bar", { labels: r.map((x) => x.round_name), datasets: [dataset("Erreichbare Punkte (%)", r.map((x) => x.reachable_percent), 0)] }, { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${num(c.raw, 1)} % der erreichbaren Punkte`, afterLabel: (c) => `Ø ${num(r[c.dataIndex].avg_points, 2)} Punkte` } } }, scales: { y: { ticks: { callback: (value) => `${value} %` } } } }),
      table("Kategorieschwierigkeit", [colText("round_name", "Runde"), colNum("avg_points", "Ø Punkte", 2), col("reachable_percent", "Prozent der erreichbaren Punkte", (v) => `${num(v, 1)} %`), colNum("stddev", "Standardabweichung", 2)], d.rounds, { sort: { key: "reachable_percent" } }),
    ];
  },

  "event-difficulty"(d) {
    const r = d.rounds;
    return [
      kpis([{ label: "Event", value: d.event.event_date, sub: d.event.location }, { label: "Jahr", value: d.year }]),
      chart("Ø Punkte: dieses Event vs. andere", "bar", { labels: r.map((x) => x.round_name), datasets: [dataset("Dieses Event", r.map((x) => x.event_avg), 0), dataset("Andere Events", r.map((x) => x.other_avg), 1)] }, {}, { half: true }),
      chart("Differenz (positiv = leichter als sonst)", "bar", { labels: r.map((x) => x.round_name), datasets: [{ label: "Differenz", data: r.map((x) => x.diff), backgroundColor: r.map((x) => (x.diff >= 0 ? "#10b981cc" : "#ef4444cc")), borderRadius: 6 }] }, { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } }, { half: true }),
      table("Runden", [colText("round_name", "Runde"), colNum("event_avg", "Event Ø", 2), colNum("other_avg", "Andere Ø", 2), colNum("diff", "Differenz", 2)], r),
    ];
  },

  "event-progress"(d) {
    const teams = d.teams;
    const shown = teams.slice(0, Math.max(1, Number(state.params.event_top) || teams.length));
    const last = (t) => t.cumulative.at(-1) ?? 0;
    return [
      kpis([{ label: "Event", value: d.event.event_date, sub: d.event.location }, { label: "Teams", value: teams.length }, { label: "Sieger", value: teams[0]?.team_name ?? "–", sub: teams[0] ? `${last(teams[0])} Punkte` : "" }]),
      chart(`Punkteentwicklung über die Runden (Top ${shown.length})`, "line", { labels: d.rounds, datasets: teamLineSets(shown, (t) => t.cumulative) }, {}, { height: 1040 }),
      table("Punkte je Runde", [colNum("pos", "Platz", 0), colText("team_name", "Team"), ...d.rounds.map((r, k) => colNum(`r${k}`, r, 0)), colNum("total", "Gesamt", 0)], teams.map((t, i) => ({ ...t, pos: t.team_rank ?? i + 1, ...Object.fromEntries(t.round_points.map((v, k) => [`r${k}`, v])) }))),
    ];
  },

  "round-strength"(d) {
    const top = Number(state.params.top) || 10;
    const blocks = [];
    const team = (state.params.team || "").toLowerCase();
    d.rankings.forEach((rk, i) => {
      const teams = rk.teams.map((t, idx) => ({ ...t, pos: idx + 1 }));
      const shown = teams.slice(0, top);
      if (team) {
        const mine = teams.find((t) => t.team_name.toLowerCase() === team);
        if (mine && !shown.includes(mine)) shown.push(mine);
      }
      if (d.rankings.length === 1) {
        blocks.push(chart(`${rk.round_name} – Top ${top}`, "bar", { labels: shown.map((t) => `${t.pos}. ${t.team_name}`), datasets: [dataset("Ø Punkte", shown.map((t) => t.avg_points), i, { backgroundColor: barColors(shown.map((t) => t.team_name), i) })] }, { indexAxis: "y", plugins: { legend: { display: false } } }, { height: Math.max(320, shown.length * 30) }));
      }
      blocks.push(table(`${rk.round_name} (${teams.length} Teams)`, [colNum("pos", "Platz", 0), colText("team_name", "Team"), colNum("avg_points", "Ø Punkte", 2), colNum("events", "Events", 0), colNum("best", "Max", 1), colNum("worst", "Min", 1)], shown));
    });
    return blocks;
  },

  "puzzle-categories"(d) {
    const c = d.categories;
    return [
      kpis([{ label: "Puzzle-Kategorien", value: c.length }]),
      chart("Ø Punkte je Puzzle-Kategorie", "bar", { labels: c.map((x) => x.category), datasets: [dataset("Ø Punkte", c.map((x) => x.avg_points), 0)] }, { plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: (t) => [`${c[t.dataIndex].events} Event(s)`, ...c[t.dataIndex].solutions.map((x) => `Lösung: ${x}`)] } } }, scales: { y: { beginAtZero: true, max: 10 } } }, { height: 380 }),
      table("Puzzle-Kategorien", [colText("category", "Kategorie"), colNum("events", "Events", 0), colNum("avg_points", "Ø Punkte", 2), colNum("max_points", "Max", 0), colNum("min_points", "Min", 0)], c),
    ];
  },

  "team-category-detail"(d) {
    const ev = d.events;
    return [
      chart("Punkte der Themenrunden", "line", { labels: ev.map(labelOf), datasets: [lineSet("Puzzle", ev.map((e) => e.puzzle_points), 0), lineSet("Bilderrunde", ev.map((e) => e.image_round_points), 1), lineSet("Überraschung (ohne Bonus)", ev.map((e) => e.surprise_round_points_no_bonus), 2)] }, { plugins: { tooltip: { callbacks: { afterLabel: (c) => themeLines(ev[c.dataIndex], [{ category: "puzzle_category", solution: "puzzle_solution" }, { topic: "image_round_category" }, { topic: "surprise_round_category" }])(c.datasetIndex) } } } }, { height: 360 }),
      table("Kategorien je Event", [colText("event_date", "Datum"), colText("location", "Ort"), colText("puzzle_category", "Puzzle-Kategorie"), colText("puzzle_solution", "Puzzle-Lösung"), colNum("puzzle_points", "Puzzle", 1), colText("image_round_category", "Bilderrunde"), colNum("image_round_points", "Bild", 1), colText("surprise_round_category", "Überraschung"), colNum("surprise_round_points_no_bonus", "Überr.", 1)], ev),
    ];
  },
};

/* ------------------------------------------------------------------ *
 *  Navigation / views
 * ------------------------------------------------------------------ */
function buildNav() {
  const nav = $("#nav");
  let html = "";
  GROUPS.forEach((g) => {
    html += `<div class="nav-group">${g}</div>`;
    Object.entries(REPORTS).filter(([, r]) => r.group === g).forEach(([key, r]) => {
      html += `<button class="nav-item" data-view="${esc(key)}">${esc(r.label)}</button>`;
    });
  });
  if (isAdmin()) html += `<div class="nav-group">Verwaltung</div>
    <button class="nav-item" data-view="__import">Import</button>
    <button class="nav-item" data-view="__export">Team-Reports</button>
    <button class="nav-item" data-view="__config">Einstellungen</button>`;
  nav.innerHTML = html;
  nav.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => { navigate(b.dataset.view); $("#sidebar").classList.remove("open"); }));
}

function navigate(view) {
  if (ADMIN_VIEWS.includes(view) && !isAdmin()) view = "standings";
  state.view = view;
  location.hash = encodeURIComponent(view);
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  renderView();
}

function renderView() {
  const view = state.view;
  $("#global-filters").hidden = true;
  if (view === "__import") return renderImport();
  if (view === "__export") return renderBatch();
  if (view === "__config") return renderConfig();
  const def = REPORTS[view] || REPORTS.standings;
  $("#page-title").textContent = def.label;
  $("#page-desc").textContent = def.desc;
  renderGlobalFilters(def);
  renderFilters(def);
  renderActions(def);
  loadReport();
}

function renderGlobalFilters(def) {
  const box = $("#global-filters");
  const p = state.params;
  const m = state.meta;
  const teamNames = [...new Set(state.teams || [])].sort((a, b) => a.localeCompare(b, "de"));
  if (p.team && !teamNames.includes(p.team)) teamNames.unshift(p.team);
  box.hidden = false;
  box.innerHTML =
    field("f-year", "Jahr", `<select id="f-year">${m.years.map((y) => `<option ${String(y) === String(p.year) ? "selected" : ""}>${y}</option>`).join("")}</select>`) +
    field("f-team", "Team", `<select id="f-team"><option value="">Kein Team</option>${teamNames.map((team) => `<option value="${esc(team)}" ${team === p.team ? "selected" : ""}>${esc(team)}</option>`).join("")}</select>`);
  $("#f-year").addEventListener("change", async (e) => {
    p.year = e.target.value;
    saveParams();
    await loadTeams();
    renderGlobalFilters(def);
    loadReport();
  });
  $("#f-team").addEventListener("change", (e) => {
    p.team = e.target.value;
    saveParams();
    loadReport();
  });
}

function field(id, label, control) {
  const hint = id === "f-min" ? ` title="Nur Teams mit mindestens so viel Eventteilnahmen werden berücksichtigt."` : "";
  return `<div class="field"><label for="${id}"${hint}>${esc(label)}</label>${control}</div>`;
}

const eventTeamCount = () => Number(state.meta.events.find((e) => String(e.id) === String(state.params.event_id))?.team_count) || 100;

function renderFilters(def) {
  const p = state.params;
  const m = state.meta;
  const needs = new Set(def.needs);
  let html = "";
  if (needs.has("event")) html += field("f-event", "Event", `<select id="f-event" class="wide">${m.events.slice().sort((a, b) => b.event_date.localeCompare(a.event_date)).map((e) => `<option value="${e.id}" ${String(e.id) === String(p.event_id) ? "selected" : ""}>${esc(e.event_date)} · ${esc(e.location)} · ${esc(e.winner || "–")}</option>`).join("")}</select>`);
  if (needs.has("round")) html += field("f-round", "Runde", `<select id="f-round"><option value="">Alle Runden</option>${m.rounds.map((r) => `<option ${r === p.round_name ? "selected" : ""}>${esc(r)}</option>`).join("")}</select>`);
  if (needs.has("min_events")) html += field("f-min", "Min. Eventteilnahmen", `<input id="f-min" type="number" title="Nur Teams mit mindestens so viel Eventteilnahmen werden berücksichtigt." min="1" max="100" value="${esc(p.min_events)}">`);
  if (needs.has("event_top")) {
    const total = eventTeamCount();
    const val = Math.min(Number(p.event_top) || total, total);
    html += field("f-event-top", "Top", `<input id="f-event-top" type="number" min="1" max="${total}" value="${val}">`);
  }
  if (needs.has("top")) html += field("f-top", "Top", `<input id="f-top" type="number" min="1" max="100" value="${esc(p.top)}">`);
  $("#filters").innerHTML = html;

  const bind = (id, key, reload = true) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("change", async () => {
      p[key] = el.value;
      if (key === "event_id") p.event_top = "";
      saveParams();
      if (key === "year" || (key === "event_id" && def.needs.includes("event_top"))) {
        if (key === "year") await loadTeams();
        renderFilters(def);
      }
      if (reload) loadReport();
    });
  };
  bind("#f-event", "event_id");
  bind("#f-round", "round_name");
  bind("#f-min", "min_events");
  bind("#f-top", "top");
  bind("#f-event-top", "event_top", false);
  $("#f-event-top")?.addEventListener("change", () => loadReport());
}

const isAdmin = () => state.meta?.role === "admin";
const ADMIN_VIEWS = ["__import", "__export", "__config"];

function renderActions(def) {
  const box = $("#actions");
  if (!isAdmin()) { box.innerHTML = ""; return; }
  let html = "";
  const teamNeeded = def.needs.includes("team") && !def.needs.includes("round");
  if (def.teamExports) html += `<button class="btn" data-export="team-pdf">Team-Report (PDF)</button>`;
  (def.exports || []).forEach((e) => { html += `<button class="btn" data-export="${e.kind}">${e.label}</button>`; });
  box.innerHTML = html;
  box.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", () => {
    const p = state.params;
    if (teamNeeded && !p.team && ["team-pdf", "team-category-pdf", "radar-svg"].includes(b.dataset.export)) return toast("Bitte zuerst ein Team wählen.", "err");
    download(`/api/export/${b.dataset.export}`, { ...reportParams(), report: state.view }, b);
  }));
}

function reportParams() {
  const p = state.params;
  return { type: state.view, year: p.year, team: p.team, event_id: p.event_id, round_name: p.round_name, min_events: p.min_events, top: p.top };
}

async function loadReport() {
  const token = ++state.token;
  const def = REPORTS[state.view];
  const needsTeam = def.needs.includes("team") && !def.needs.includes("round");
  const needsEvent = def.needs.includes("event");
  destroyCharts();
  if (needsTeam && !state.params.team) return emptyState("", "Bitte ein Team wählen.");
  if (needsEvent && !state.params.event_id) return emptyState("", "Bitte ein Event wählen.");
  $("#content").innerHTML = `<div class="loading"><div class="spinner"></div>Lade Daten …</div>`;
  try {
    const res = await api("/api/report", { params: reportParams() });
    if (token !== state.token) return;
    state.data = res;
    renderReport();
  } catch (err) {
    if (token !== state.token) return;
    if (err.detail?.code === "team_not_in_event") return notParticipatedState(err.detail);
    emptyState("", err.message);
    toast(err.message, "err");
  }
}

function notParticipatedState({ team, event_date, location }) {
  state.data = null;
  $("#content").innerHTML = `<div class="notice">
    <div class="notice-icon">🚫</div>
    <h3>Keine Teilnahme</h3>
    <p><strong>${esc(team)}</strong> hat am Event vom <strong>${esc(event_date)}</strong> (${esc(location)}) nicht teilgenommen.</p>
    <p class="muted">Bitte ein anderes Event oder Team wählen.</p>
  </div>`;
}

function emptyState(icon, message) {
  state.data = null;
  $("#content").innerHTML = `<div class="empty"><p>${esc(message)}</p></div>`;
}

function renderReport() {
  mountBlocks(RENDERERS[state.view](state.data.data));
}

/* ------------------------------------------------------------------ *
 *  Import view
 * ------------------------------------------------------------------ */
function setHeader(title, desc) {
  $("#page-title").textContent = title;
  $("#page-desc").textContent = desc;
  $("#filters").innerHTML = "";
  $("#actions").innerHTML = "";
  destroyCharts();
}

function logLine(box, text, cls = "") {
  const div = document.createElement("div");
  if (cls) div.className = cls;
  div.textContent = text;
  box.appendChild(div);
}

function describeImport(box, r) {
  logLine(box, `${r.teams_imported} Teams importiert – ${r.event_date} @ ${r.location}`, "ok");
  if (r.is_new_event && r.first_time_teams?.length) logLine(box, `Neue Teams: ${r.first_time_teams.join(", ")}`);
}

async function refreshMeta() {
  state.meta = await api("/api/meta");
  $("#db-label").textContent = state.meta.db_path;
  await loadTeams();
}

function renderImport() {
  setHeader("Import", "Quiz-Ergebnisse und Event-Themen aus Excel-Dateien importieren");
  $("#content").innerHTML = `
    <div class="card half">
      <h2>Quiz-Datei importieren</h2>
      <div class="dropzone" id="dz-file"><p>Excel-Datei hierher ziehen<br><span class="muted">Dateiname: <code>YYYYMMDD_Ort.xlsx</code></span></p>
        <input type="file" id="file-in" accept=".xlsx,.xlsm,.xltx,.xltm" multiple></div>
    </div>
    <div class="card half">
      <h2>Event-Themen importieren</h2>
      <div class="dropzone" id="dz-themes"><p>Themen-Excel hierher ziehen<br><span class="muted">Spalten: Datum, Puzzle Kategorie, Puzzle Lösung, Bilderrunde, Überraschungsrunde</span></p>
        <input type="file" id="theme-in" accept=".xlsx,.xlsm,.xltx,.xltm"></div>
    </div>
    <div class="card">
      <h2>Ordner importieren</h2>
      <div class="row"><div class="field"><label for="folder">Ordner auf dem Server</label><input id="folder" class="wide" value="data/quizzes"></div>
      <button class="btn primary" id="folder-btn">Ordner importieren</button></div>
    </div>
    <div class="card"><h2>Protokoll</h2><div class="log" id="log"><div class="muted">Noch keine Importe.</div></div></div>`;
  const log = $("#log");
  const clear = () => { if (log.firstElementChild?.classList.contains("muted")) log.innerHTML = ""; };

  const upload = async (file, endpoint, onOk) => {
    clear();
    try {
      const r = await api(endpoint, { method: "POST", raw: true, body: file, headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": "application/octet-stream" } });
      onOk(r);
      await refreshMeta();
    } catch (err) {
      logLine(log, `${file.name}: ${err.message}`, "err");
      toast(err.message, "err");
    }
  };
  const importQuiz = (file) => upload(file, "/api/import/file", (r) => describeImport(log, r));
  const importThemes = (file) => upload(file, "/api/import/themes", (r) => {
    logLine(log, `Themen: ${r.rows_imported}/${r.rows_found} Zeilen importiert`, r.rows_failed ? "err" : "ok");
    (r.errors || []).forEach((e) => logLine(log, `Zeile ${e.row}: ${e.message}`, "err"));
  });

  const wireDrop = (zoneId, inputId, handler) => {
    const zone = $(zoneId), input = $(inputId);
    ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
    zone.addEventListener("drop", async (e) => { for (const f of e.dataTransfer.files) await handler(f); });
    input.addEventListener("change", async () => { for (const f of input.files) await handler(f); input.value = ""; });
  };
  wireDrop("#dz-file", "#file-in", importQuiz);
  wireDrop("#dz-themes", "#theme-in", importThemes);

  $("#folder-btn").addEventListener("click", async (e) => {
    clear();
    e.target.disabled = true;
    try {
      const s = await api("/api/import/folder", { method: "POST", body: { path: $("#folder").value.trim() } });
      s.imports.forEach((r) => describeImport(log, r));
      (s.errors || []).forEach((er) => logLine(log, `${er.file}: ${er.message}`, "err"));
      logLine(log, `Fertig: ${s.files_imported} Dateien importiert, ${s.files_failed || 0} fehlgeschlagen.`, s.files_failed ? "err" : "ok");
      await refreshMeta();
    } catch (err) {
      logLine(log, `${err.message}`, "err");
      toast(err.message, "err");
    } finally {
      e.target.disabled = false;
    }
  });
}

/* ------------------------------------------------------------------ *
 *  Batch team reports
 * ------------------------------------------------------------------ */
function renderBatch() {
  setHeader("Team-Reports", "PDF-Reports für alle Teams einer Saison erzeugen");
  const m = state.meta;
  $("#content").innerHTML = `
    <div class="card">
      <h2>Alle Team-Reports erzeugen</h2>
      <p class="muted">${m.converter ? `DOCX→PDF-Konverter gefunden: <code>${esc(m.converter)}</code>` : "Kein LibreOffice (<code>soffice</code>) gefunden – ohne Konverter können keine Team-PDFs erzeugt werden."}</p>
      <div class="row">
        <div class="field"><label for="b-year">Jahr</label><select id="b-year">${m.years.map((y) => `<option ${String(y) === String(state.params.year) ? "selected" : ""}>${y}</option>`).join("")}</select></div>
        <div class="field"><label for="b-min" title="Nur Teams mit mindestens so viel Eventteilnahmen werden berücksichtigt.">Min. Eventteilnahmen</label><input id="b-min" type="number" title="Nur Teams mit mindestens so viel Eventteilnahmen werden berücksichtigt." min="1" value="${esc(state.params.min_events)}"></div>
        <button class="btn primary" id="b-start">Reports erzeugen</button>
      </div>
      <div id="b-status"></div>
    </div>`;
  $("#b-start").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const { job_id } = await api("/api/jobs/all-team-reports", { method: "POST", body: { year: Number($("#b-year").value), min_events: Number($("#b-min").value) } });
      pollJob(job_id, e.target);
    } catch (err) {
      toast(err.message, "err");
      e.target.disabled = false;
    }
  });
}

async function pollJob(id, button) {
  const box = $("#b-status");
  if (!box) return;
  try {
    const j = await api(`/api/jobs/${id}`);
    const percent = j.total ? Math.round((j.done / j.total) * 100) : 0;
    box.innerHTML = `<div class="progress"><div style="width:${percent}%"></div></div>
      <p>${j.status === "running" ? `Erzeuge ${esc(j.current || "")} (${j.done}/${j.total}) …` : `Fertig: <span class="pill ok">${j.successes} erfolgreich</span> <span class="pill ${j.failures ? "err" : ""}">${j.failures} Fehler</span>`}</p>
      ${j.status !== "running" ? `<p class="muted">Gespeichert in <code>${esc(j.folder)}</code></p>${j.has_zip ? `<button class="btn" id="zip-btn">⬇ZIP herunterladen</button>` : ""}` : ""}
      <div class="log">${j.log.map((l) => `<div class="${l.includes("FAIL") ? "err" : ""}">${esc(l)}</div>`).join("")}</div>`;
    if (j.status === "running") return setTimeout(() => pollJob(id, button), 1000);
    button.disabled = false;
    $("#zip-btn")?.addEventListener("click", (e) => download(`/api/jobs/${id}/zip`, {}, e.currentTarget));
  } catch (err) {
    toast(err.message, "err");
    button.disabled = false;
  }
}

/* ------------------------------------------------------------------ *
 *  Config
 * ------------------------------------------------------------------ */
function renderConfig() {
  setHeader("Einstellungen", "Standard-Team und Datenbank");
  const m = state.meta;
  $("#content").innerHTML = `
    <div class="card">
      <h2>Einstellungen</h2>
      <div class="row">
        <div class="field"><label for="c-team">Standard-Team</label><input id="c-team" class="wide" list="team-list" value="${esc(m.default_team)}"><datalist id="team-list">${(state.teams || []).map((t) => `<option value="${esc(t)}">`).join("")}</datalist></div>
        <div class="field"><label for="c-db">Datenbank</label><input id="c-db" class="wide" value="${esc(m.db_path)}"></div>
        <button class="btn primary" id="c-save">Speichern</button>
      </div>
      ${m.db_error ? `<p class="pill err">Datenbankfehler: ${esc(m.db_error)}</p>` : ""}
    </div>`;
  $("#c-save").addEventListener("click", async () => {
    try {
      await api("/api/settings", { method: "POST", body: { default_team: $("#c-team").value, db_path: $("#c-db").value } });
      const previousDefault = state.meta.default_team;
      await refreshMeta();
      if (!state.params.team || state.params.team === previousDefault) state.params.team = state.meta.default_team;
      saveParams();
      toast("Einstellungen gespeichert.", "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  });
}

/* ------------------------------------------------------------------ *
 *  Boot
 * ------------------------------------------------------------------ */
async function loadTeams() {
  if (!state.params.year) return;
  try { state.teams = (await api("/api/teams", { params: { year: state.params.year } })).teams; } catch { state.teams = []; }
}

function setupAuth() {
  const box = $("#auth-box");
  if (!state.meta.auth_required) { box.innerHTML = ""; return; }
  if (isAdmin()) {
    box.innerHTML = `<button class="btn ghost" id="logout-btn">Abmelden</button>`;
    $("#logout-btn").addEventListener("click", async () => { await api("/api/logout", { method: "POST", body: {} }); location.hash = ""; location.reload(); });
  } else {
    box.innerHTML = `<button class="btn ghost" id="login-btn">Admin-Login</button>`;
    $("#login-btn").addEventListener("click", async () => {
      const dlg = document.createElement("dialog");
      dlg.className = "login-dialog";
      dlg.innerHTML = `<form method="dialog"><h2>Admin-Login</h2><input type="password" id="login-pw" placeholder="Passwort" autocomplete="current-password" required><div class="login-err" id="login-err"></div><div class="login-actions"><button class="btn" value="cancel" formnovalidate>Abbrechen</button><button class="btn primary" id="login-ok" value="ok">Anmelden</button></div></form>`;
      document.body.appendChild(dlg);
      dlg.showModal();
      $("#login-ok", dlg).addEventListener("click", async (ev) => {
        ev.preventDefault();
        try {
          await api("/api/login", { method: "POST", body: { password: $("#login-pw", dlg).value } });
          location.reload();
        } catch (err) { $("#login-err", dlg).textContent = err.message; }
      });
      dlg.addEventListener("close", () => dlg.remove());
    });
  }
}

async function boot() {
  initTheme();
  loadParams();
  $("#menu-btn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  try {
    state.meta = await api("/api/meta");
  } catch (err) {
    $("#content").innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    return;
  }
  const m = state.meta;
  $("#db-label").textContent = m.db_path;
  setupAuth();
  state.params.year = String(m.years[0]);
  const latestEvent = m.events.slice().sort(
    (a, b) => b.event_date.localeCompare(a.event_date) || Number(b.id) - Number(a.id),
  )[0];
  state.params.event_id = String(latestEvent?.id ?? "");
  saveParams();
  await loadTeams();
  buildNav();
  const hash = decodeURIComponent(location.hash.slice(1));
  navigate(REPORTS[hash] || (ADMIN_VIEWS.includes(hash) && isAdmin()) ? hash : "standings");
}

window.addEventListener("hashchange", () => {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash && hash !== state.view && state.meta && (REPORTS[hash] || ADMIN_VIEWS.includes(hash))) navigate(hash);
});

boot();
