// InterPore Abstracts Explorer: plain JS, no build step.
// Data: data/papers.json + data/topics.json first, then data/abstracts.json in the
// background; data/history.json + data/charts/*.json when the History view opens.
// All abstract text is untrusted: it only ever goes into the DOM via textContent
// (inline $...$ math goes through KaTeX with trust off).
"use strict";

const WORLD = 1000; // map coordinates are [0, 1] -> [0, WORLD]
const $ = (id) => document.getElementById(id);

const state = {
  papers: [],
  byId: new Map(),
  topics: new Map(),
  hiddenTopics: new Set(),
  abstracts: null, // Map id -> abstract once loaded
  byPerson: new Map(), // name key -> [ids]
  format: "", // presentation format to show, or "" for all
  session: null, // {year, name} or null
  yearMin: 0,
  yearMax: 0,
  matches: null, // Set of ids matching the search, or null
  selected: null,
  view: "list", // "list" | "map" | "history"
  sort: "newest",
  hitRank: null, // Map id -> search rank, or null
};
let deck;
let search;

const FORMAT_LABEL = { Other: "Not recorded" };
const fmtLabel = (f) => FORMAT_LABEL[f] || f;

function topicColor(index) {
  // Evenly spaced hues, alternating lightness so neighbours stay distinguishable.
  const h = (index * 360 * 0.618033) % 360;
  const l = index % 2 ? 58 : 46;
  return hslToRgb(h, 62, l);
}

function hslToRgb(h, s, l) {
  s /= 100; l /= 100;
  const k = (n) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
}

const css = (rgb) => `rgb(${rgb.join(",")})`;

// Same normalisation as text.name_key in the pipeline.
function nameKey(name) {
  return (name || "")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .match(/[a-z]+/g)
    ?.join(" ") || "";
}

// All filters, or all but one (`skip`: "topic" | "format"), which is what that
// filter's counts use: each option shows what it would give with the others applied.
function passes(p, skip) {
  return (
    (skip === "topic" || !state.hiddenTopics.has(p.topic)) &&
    (skip === "format" || !state.format || p.format === state.format) &&
    (!state.session || (p.year === state.session.year && p.session === state.session.name)) &&
    p.year >= state.yearMin &&
    p.year <= state.yearMax &&
    (!state.matches || state.matches.has(p.id))
  );
}

const visible = (p) => passes(p);

function radius(p) {
  return p.format === "Invited" ? 5 : 3;
}

function render() {
  const shown = state.papers.filter(visible);
  document.body.classList.toggle("has-detail", !!state.selected);
  $("count").textContent = `${state.papers.length.toLocaleString()} abstracts · ${state.yearSpan}`;
  renderList(shown);
  renderMap(shown);
  renderResults();
  updateFormatCounts();
  updateTopicCounts();
}

// ---- Map ---------------------------------------------------------------------

function renderMap(shown) {
  if (!deck) return;
  const { ScatterplotLayer } = window.deck;
  const sel = state.selected && state.byId.get(state.selected);
  const layers = [
    new ScatterplotLayer({
      id: "faded",
      data: state.papers.filter((p) => !visible(p)),
      getPosition: (p) => [p.x * WORLD, (1 - p.y) * WORLD],
      getRadius: 1.6,
      radiusUnits: "pixels",
      getFillColor: [128, 128, 128, 36],
    }),
    new ScatterplotLayer({
      id: "papers",
      data: shown,
      pickable: true,
      getPosition: (p) => [p.x * WORLD, (1 - p.y) * WORLD],
      getRadius: radius,
      radiusUnits: "pixels",
      getFillColor: (p) => [...state.topics.get(p.topic).rgb, p.outlier ? 140 : 210],
      stroked: true,
      lineWidthUnits: "pixels",
      getLineWidth: 0.3,
      getLineColor: [255, 255, 255, 110],
      onHover: ({ object, x, y }) => tooltip(object, x, y),
      onClick: ({ object }) => object && select(object.id),
    }),
    // Selection marker: an accent ring with a halo so it shows on light and dark maps.
    new ScatterplotLayer({
      id: "selected",
      data: sel ? [sel, sel] : [],
      getPosition: (p) => [p.x * WORLD, (1 - p.y) * WORLD],
      getRadius: (p) => radius(p) + 6,
      radiusUnits: "pixels",
      filled: false,
      stroked: true,
      lineWidthUnits: "pixels",
      getLineWidth: (_, { index }) => (index ? 2.5 : 6),
      getLineColor: (_, { index }) => (index ? labelTheme().accent : [...labelTheme().pill.slice(0, 3), 200]),
      updateTriggers: { getLineColor: labelTheme().key },
    }),
  ];
  state.baseLayers = layers;
  state.labelKey = null;
  updateLabels(true);
}

const LABEL_FONT = "600 14px system-ui, -apple-system, Segoe UI, sans-serif";
const LABEL_GAP = 4; // px between label pills

function labelBox(t) {
  if (!t.box) {
    const ctx = (labelBox.ctx ||= document.createElement("canvas").getContext("2d"));
    ctx.font = LABEL_FONT;
    t.box = [ctx.measureText(t.short).width + 15, 23];
  }
  return t.box;
}

// Greedy placement: biggest topics first, skip any label that would overlap
// one already placed at this zoom. Zooming in spreads them out and reveals more.
function placeLabels(zoom) {
  const scale = 2 ** zoom;
  const placed = [];
  const topics = [...state.topics.values()]
    .filter((t) => !state.hiddenTopics.has(t.id))
    .sort((a, b) => b.size - a.size);
  for (const t of topics) {
    const [w, h] = labelBox(t);
    const cx = t.x * WORLD * scale, cy = (1 - t.y) * WORLD * scale;
    const r = [cx - w / 2 - LABEL_GAP, cy - h / 2 - LABEL_GAP, cx + w / 2 + LABEL_GAP, cy + h / 2 + LABEL_GAP];
    if (placed.some(({ r: q }) => r[0] < q[2] && q[0] < r[2] && r[1] < q[3] && q[1] < r[3])) continue;
    placed.push({ t, r });
  }
  return placed.map(({ t }) => t);
}

function updateLabels(force = false) {
  if (!state.baseLayers) return;
  const data = placeLabels(state.mapView?.zoom ?? state.zoom);
  const key = data.map((t) => t.id).join(",");
  if (!force && key === state.labelKey) return;
  state.labelKey = key;
  const theme = labelTheme();
  const labels = new window.deck.TextLayer({
    id: "labels",
    data,
    getPosition: (t) => [t.x * WORLD, (1 - t.y) * WORLD],
    getText: (t) => t.short,
    getSize: 14,
    getColor: theme.text,
    fontWeight: 600,
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
    characterSet: "auto",
    getTextAnchor: "middle",
    getAlignmentBaseline: "center",
    background: true,
    getBackgroundColor: theme.pill,
    getBorderColor: (t) => [...t.rgb, 255],
    getBorderWidth: 1.5,
    backgroundPadding: [6, 3],
    backgroundBorderRadius: 4,
    updateTriggers: { getColor: theme.key, getBackgroundColor: theme.key },
  });
  deck.setProps({ layers: [...state.baseLayers, labels] });
}

function isDark() {
  return document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
}

function labelTheme() {
  return isDark()
    ? { key: "dark", text: [235, 235, 238, 255], pill: [24, 25, 30, 225], accent: [122, 167, 255, 255] }
    : { key: "light", text: [29, 29, 31, 255], pill: [255, 255, 255, 230], accent: [36, 99, 199, 255] };
}

function setupTheme() {
  const btn = $("theme");
  const sync = () => {
    btn.setAttribute("aria-checked", isDark());
    btn.title = isDark() ? "Switch to light theme" : "Switch to dark theme";
  };
  btn.addEventListener("click", () => {
    const t = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    try {
      localStorage.setItem("theme", t);
    } catch {}
    sync();
    render();
    renderCharts();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    sync();
    render();
    renderCharts();
  });
  sync();
}

function tooltip(p, x, y) {
  const el = $("tooltip");
  if (!p) {
    el.hidden = true;
    return;
  }
  el.replaceChildren();
  const b = document.createElement("b");
  b.textContent = plainTex(p.title);
  const s = document.createElement("div");
  s.className = "muted";
  s.textContent = `${p.year} · ${shortAuthors(p)}`;
  el.append(b, s);
  const box = $("map").getBoundingClientRect();
  el.style.left = `${box.left + x + 14}px`;
  el.style.top = `${box.top + y + 14}px`;
  el.hidden = false;
}

const shortAuthors = (p) => {
  const a = p.authors || [];
  return a.length ? a.slice(0, 3).join(", ") + (a.length > 3 ? " et al." : "") : p.id;
};

function paperItem(p, onClick) {
  const li = document.createElement("li");
  li.textContent = plainTex(p.title);
  const small = document.createElement("small");
  small.textContent = ` ${p.year} · ${(p.authors || [])[0] || p.id}`;
  li.append(small);
  li.addEventListener("click", onClick);
  return li;
}

// ---- Text ----------------------------------------------------------------------

// Inline LaTeX ($...$, $$...$$; \$ is a literal dollar). Must match
// text.MATH_SPAN_RE. Math goes through KaTeX (trust off); everything else is text.
const MATH_SPLIT = /(\$\$[\s\S]+?\$\$|(?<!\\)\$[^$\n]+?(?<!\\)\$)/;

function setTex(el, text) {
  el.replaceChildren();
  const parts = (text || "").split(MATH_SPLIT);
  parts.forEach((part, i) => {
    if (i % 2 === 0) {
      if (part) el.append(part.replaceAll("\\$", "$"));
      return;
    }
    const display = part.startsWith("$$");
    const tex = part.slice(display ? 2 : 1, display ? -2 : -1);
    const span = document.createElement("span");
    if (window.katex) {
      try {
        katex.render(tex, span, { throwOnError: false, trust: false, displayMode: false });
      } catch {
        span.textContent = tex;
      }
    } else {
      span.textContent = tex;
    }
    el.append(span);
  });
}

// Paragraphs (blank-line separated) as <p>, each through setTex.
function setParagraphs(el, text) {
  el.replaceChildren(
    ...(text || "").split(/\n\s*\n/).filter(Boolean).map((para) => {
      const p = document.createElement("p");
      setTex(p, para);
      return p;
    }),
  );
}

function plainTex(text) {
  return (text || "")
    .split(MATH_SPLIT)
    .map((part, i) =>
      i % 2 === 0
        ? part.replaceAll("\\$", "$")
        : part.replace(/^\$+|\$+$/g, "").replace(/\\(text|mathrm|mathbf|rm)\{([^}]*)\}/g, "$2").replace(/[{}\\_^]/g, ""),
    )
    .join("");
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {}
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.append(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}

// ---- Reading pane --------------------------------------------------------------

function sessionText(p) {
  if (!p.session && !p.session_code) return "";
  if (p.session_code && p.session && !p.session.includes(p.session_code)) return `${p.session_code} · ${p.session}`;
  return p.session || p.session_code;
}

function select(id) {
  const p = state.byId.get(id);
  state.selected = p ? id : null;
  if (location.hash.slice(1) !== (p ? id : "")) history.replaceState(null, "", p ? `#${id}` : location.pathname);
  const panel = $("detail");
  if (!p) {
    panel.hidden = true;
    refreshSelection();
    return;
  }
  const topic = state.topics.get(p.topic);
  $("d-id").textContent = p.id;
  $("d-meeting").textContent = `InterPore${p.year}`;
  $("d-format").textContent = fmtLabel(p.format);
  $("d-topic").textContent = topic.label;
  $("d-topic").style.background = css(topic.rgb);
  setTex($("d-title"), p.title);
  renderAuthors(p);
  const sess = sessionText(p);
  $("d-session").parentElement.hidden = !sess;
  $("d-session").textContent = sess;
  const src = $("d-source");
  src.href = p.url;
  src.textContent = p.source === "book" ? "Book of abstracts, this page ↗" : "Open on Indico ↗";
  src.title = p.source === "book" ? "The abstract's page in the meeting's book of abstracts (PDF)" : "The abstract's page on events.interpore.org";
  const files = p.attachments || [];
  $("d-files-wrap").hidden = !files.length;
  $("d-files").replaceChildren(
    ...files.map((f) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = f.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = f.title || "file";
      a.title = "Uploaded by the authors to events.interpore.org";
      li.append(a);
      return li;
    }),
  );
  showAbstract(p);
  const people = sameAuthors(p);
  state.people = people;
  $("n-similar").textContent = p.similar.length;
  $("n-people").textContent = people.length;
  showRelated();
  panel.hidden = false;
  panel.querySelector(".d-body").scrollTop = 0;
  refreshSelection();
}

function renderAuthors(p) {
  const ul = $("d-authors");
  const presenters = new Set((p.presenters || []).map(nameKey));
  const authors = p.authors || [];
  const affs = p.affs || [];
  const withAff = $("detail").classList.contains("wide") || authors.length <= 6;
  ul.classList.toggle("wide", withAff);
  ul.replaceChildren(
    ...authors.map((name, i) => {
      const li = document.createElement("li");
      li.append(name);
      if (presenters.has(nameKey(name))) {
        const s = document.createElement("span");
        s.className = "pres";
        s.textContent = "presenter";
        li.append(s);
      }
      if (withAff && affs[i]) {
        const a = document.createElement("span");
        a.className = "aff";
        a.textContent = ` · ${affs[i]}`;
        li.append(a);
      }
      return li;
    }),
  );
  if (!authors.length) ul.textContent = "Authors not recorded";
}

function showAbstract(p) {
  const el = $("d-abstract");
  if (!state.abstracts) {
    el.textContent = "Loading…";
    return;
  }
  const text = state.abstracts.get(p.id);
  $("d-abstract-wrap").hidden = !text;
  setParagraphs(el, text);
}

// Other abstracts by any of this abstract's authors (same name as written).
function sameAuthors(p) {
  const ids = new Set();
  for (const a of p.authors || []) for (const id of state.byPerson.get(nameKey(a)) || []) if (id !== p.id) ids.add(id);
  return [...ids].map((i) => state.byId.get(i)).sort((a, b) => b.year - a.year || a.id.localeCompare(b.id));
}

function refreshSelection() {
  document.body.classList.toggle("has-detail", !!state.selected);
  markSelectedCard();
  renderMap(state.papers.filter(visible));
}

const RELATED_EMPTY = {
  similar: "No similar abstracts.",
  people: "No other abstracts by these authors (names matched as written).",
};

function showRelated(tab = state.tab || "similar") {
  state.tab = tab;
  for (const b of document.querySelectorAll(".tabs button")) b.setAttribute("aria-selected", b.dataset.tab === tab);
  const p = state.byId.get(state.selected);
  if (!p) return;
  const items = tab === "similar" ? p.similar.map((i) => state.byId.get(i)).filter(Boolean) : state.people;
  $("d-related").replaceChildren(...items.slice(0, 200).map((q) => relatedCard(q, tab === "people" ? p : null)));
  $("d-related-empty").hidden = items.length > 0;
  $("d-related-empty").textContent = RELATED_EMPTY[tab];
}

function relatedCard(q, shared) {
  const li = document.createElement("li");
  li.tabIndex = 0;
  const t = document.createElement("span");
  t.className = "t";
  t.textContent = plainTex(q.title);
  const m = document.createElement("span");
  m.className = "m";
  const dot = document.createElement("span");
  dot.className = "dot";
  dot.style.background = css(state.topics.get(q.topic).rgb);
  let who = q.authors?.length ? q.authors[0].split(" ").at(-1) + (q.authors.length > 1 ? " et al." : "") : q.id;
  if (shared) {
    const mine = new Set(shared.authors.map(nameKey));
    const common = q.authors.filter((a) => mine.has(nameKey(a)));
    who = common.slice(0, 2).join(", ") + (common.length > 2 ? " …" : "");
  }
  m.append(dot, `${q.year} · ${who}`);
  li.append(t, m);
  li.addEventListener("click", () => focus(q.id));
  li.addEventListener("keydown", (e) => e.key === "Enter" && focus(q.id));
  return li;
}

function showOnMap(id) {
  const p = state.byId.get(id);
  if (!p) return;
  setWide(false);
  setView("map");
  focus(id, 3);
  if (!visible(p)) {
    $("d-map").textContent = "Hidden by filters";
    setTimeout(() => ($("d-map").textContent = "Show on map"), 1800);
  }
}

function setWide(on) {
  $("detail").classList.toggle("wide", on);
  $("wide").setAttribute("aria-pressed", on);
  const p = state.byId.get(state.selected);
  if (p) renderAuthors(p);
  try {
    localStorage.setItem("wide", on ? "1" : "");
  } catch {}
}

function focus(id, minZoom = 1.2) {
  const p = state.byId.get(id);
  if (!p) return;
  if (state.view === "history") setView("list");
  select(id);
  scrollListTo(id);
  const zoom = Math.max(state.mapView?.zoom ?? 0, minZoom);
  const covered = innerWidth > 760 ? state.widths.right + 24 : 0;
  deck.setProps({
    initialViewState: {
      target: [p.x * WORLD + covered / 2 / 2 ** zoom, (1 - p.y) * WORLD, 0],
      zoom,
      transitionDuration: 500,
    },
  });
}

// ---- List view -------------------------------------------------------------

const PAGE = 60;

const SORTS = {
  relevance: (a, b) => state.hitRank.get(a.id) - state.hitRank.get(b.id),
  newest: (a, b) => b.year - a.year || a.order - b.order,
  oldest: (a, b) => a.year - b.year || a.order - b.order,
  title: (a, b) => a.sortTitle.localeCompare(b.sortTitle),
};

function renderList(shown) {
  const sort = state.sort === "relevance" && !state.hitRank ? "newest" : state.sort;
  state.listItems = [...shown].sort(SORTS[sort]);
  state.listShown = 0;
  state.listSort = sort;
  $("list").replaceChildren();
  $("list-count").textContent = state.matches
    ? `${shown.length.toLocaleString()} matching abstract${shown.length === 1 ? "" : "s"}`
    : `${shown.length.toLocaleString()} abstracts`;
  appendCards();
}

function appendCards(upTo = state.listShown + PAGE) {
  const items = state.listItems, list = $("list");
  const byYear = state.listSort === "newest" || state.listSort === "oldest";
  const frag = document.createDocumentFragment();
  for (let i = state.listShown; i < Math.min(upTo, items.length); i++) {
    const p = items[i];
    if (byYear && (i === 0 || items[i - 1].year !== p.year)) {
      const h = document.createElement("li");
      h.className = "year-head";
      const m = state.meetingByYear?.get(p.year);
      h.textContent = m ? `${p.year} · ${m.city}${m.country ? ", " + m.country : ""}` : p.year;
      frag.append(h);
    }
    frag.append(card(p));
  }
  state.listShown = Math.min(upTo, items.length);
  list.append(frag);
  const left = items.length - state.listShown;
  $("list-more").textContent = left > 0 ? `Scroll for ${left.toLocaleString()} more…` : items.length ? "" : "No abstracts match the filters.";
}

function card(p) {
  const li = document.createElement("li");
  li.className = "card" + (p.id === state.selected ? " on" : "");
  li.dataset.id = p.id;
  li.tabIndex = 0;
  const body = document.createElement("div");
  const meta = document.createElement("div");
  meta.className = "c-meta";
  const topic = state.topics.get(p.topic);
  const dot = document.createElement("span");
  dot.className = "dot";
  dot.style.background = css(topic.rgb);
  const metaText = document.createElement("span");
  metaText.textContent = `${topic.short} · ${p.year} · ${fmtLabel(p.format)} · ${p.id}`;
  meta.append(dot, metaText);
  const h = document.createElement("h3");
  setTex(h, p.title);
  const au = document.createElement("p");
  au.className = "c-authors";
  au.textContent = (p.authors || []).join(", ") || "Authors not recorded";
  body.append(meta, h, au);
  const abs = state.abstracts?.get(p.id);
  if (abs) {
    const ab = document.createElement("p");
    ab.className = "c-abs";
    setTex(ab, abs.replace(/\n+/g, " "));
    body.append(ab);
  }
  const sess = sessionText(p);
  if (sess) {
    const foot = document.createElement("div");
    foot.className = "c-foot";
    foot.textContent = sess;
    body.append(foot);
  }
  li.append(body);
  return li;
}

function scrollListTo(id) {
  if (state.view !== "list") return;
  let el = $("list").querySelector(`[data-id="${CSS.escape(id)}"]`);
  if (!el) {
    const i = state.listItems.findIndex((p) => p.id === id);
    if (i < 0) return;
    appendCards(i + PAGE);
    el = $("list").querySelector(`[data-id="${CSS.escape(id)}"]`);
  }
  el?.scrollIntoView({ block: "nearest" });
}

function markSelectedCard() {
  for (const el of $("list").querySelectorAll(".card.on")) el.classList.remove("on");
  if (state.selected) $("list").querySelector(`[data-id="${CSS.escape(state.selected)}"]`)?.classList.add("on");
}

function setupList() {
  const list = $("list");
  const open = (e) => {
    const el = e.target.closest(".card");
    if (el) select(el.dataset.id);
  };
  list.addEventListener("click", open);
  list.addEventListener("keydown", (e) => e.key === "Enter" && open(e));
  $("list-view").addEventListener("scroll", (e) => {
    const v = e.target;
    if (v.scrollTop + v.clientHeight > v.scrollHeight - 800 && state.listShown < state.listItems.length) appendCards();
  });
  $("sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    $("list-view").scrollTop = 0;
    render();
  });
}

function setView(view) {
  state.view = view;
  document.body.classList.toggle("map", view === "map");
  document.body.classList.toggle("history", view === "history");
  $("list-view").hidden = view !== "list";
  $("map-view").hidden = view !== "map";
  $("history-view").hidden = view !== "history";
  for (const b of document.querySelectorAll(".views button")) b.setAttribute("aria-selected", b.dataset.view === view);
  if (view === "list" && state.selected) scrollListTo(state.selected);
  if (view === "history") showHistory();
  try {
    localStorage.setItem("view", view);
  } catch {}
}

// ---- Resizable sidebars -------------------------------------------------------

const WIDTHS = { left: [310, 220, 480], right: [560, 360, 1100] };

function setWidth(side, px) {
  const [, min, max] = WIDTHS[side];
  const room = innerWidth - (side === "left" ? state.widths.right : state.widths.left) - 320;
  state.widths[side] = Math.round(Math.max(min, Math.min(px, max, room)));
  document.documentElement.style.setProperty(`--${side}-w`, `${state.widths[side]}px`);
}

function setupResizers() {
  state.widths = { left: WIDTHS.left[0], right: WIDTHS.right[0] };
  try {
    const saved = JSON.parse(localStorage.getItem("widths") || "{}");
    for (const side of ["left", "right"]) if (saved[side]) state.widths[side] = saved[side];
  } catch {}
  for (const side of ["left", "right"]) setWidth(side, state.widths[side]);
  const save = () => {
    try {
      localStorage.setItem("widths", JSON.stringify(state.widths));
    } catch {}
  };
  for (const el of document.querySelectorAll(".resizer")) {
    const side = el.dataset.side;
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      document.body.classList.add("resizing");
      const move = (ev) => setWidth(side, side === "left" ? ev.clientX - 12 : innerWidth - 12 - ev.clientX);
      const up = () => {
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        document.body.classList.remove("resizing");
        save();
      };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
    });
    el.addEventListener("dblclick", () => {
      setWidth(side, WIDTHS[side][0]);
      save();
    });
  }
  addEventListener("resize", () => ["left", "right"].forEach((side) => setWidth(side, state.widths[side])));
}

// ---- Filters -------------------------------------------------------------------

// A toggle list of topics. Click toggles one; double-click (or alt/cmd-click)
// shows only that one, and double-clicking the only visible one shows all again.
function buildFilterList(ul, countEl, items, hidden) {
  const sync = () => {
    for (const t of items.values()) t.li.classList.toggle("off", hidden.has(t.id));
    const all = items.size;
    const on = [...items.keys()].filter((k) => !hidden.has(k)).length;
    countEl.textContent = on < all ? `· ${on} of ${all}` : `· ${all}`;
  };
  const sorted = [...items.values()].sort((a, b) => b.size - a.size);
  ul.replaceChildren(
    ...sorted.map((t) => {
      const li = document.createElement("li");
      li.title = `${t.tip}\n\nClick to toggle, double-click to show only this one`;
      const sw = document.createElement("span");
      sw.className = "swatch";
      sw.style.background = css(t.rgb);
      const name = document.createElement("span");
      name.textContent = t.label;
      const n = document.createElement("span");
      n.className = "n";
      n.textContent = t.size;
      t.n = n;
      li.append(sw, name, n);
      li.addEventListener("click", (e) => {
        if (e.altKey || e.metaKey) return showOnly(items, hidden, t.id);
        if (hidden.has(t.id)) hidden.delete(t.id);
        else hidden.add(t.id);
        sync();
        render();
      });
      li.addEventListener("dblclick", () => {
        const solo = !hidden.has(t.id) && [...items.keys()].every((k) => k === t.id || hidden.has(k));
        if (solo) hidden.clear();
        showOnly(items, hidden, solo ? null : t.id);
      });
      t.li = li;
      return li;
    }),
  );
  sync();
  items.sync = sync;
  return sync;
}

function showOnly(items, hidden, id) {
  hidden.clear();
  if (id !== null) for (const k of items.keys()) if (k !== id) hidden.add(k);
  items.sync?.();
  render();
}

function setupFilters() {
  for (const t of state.topics.values()) t.tip = `Keywords: ${t.keywords.join(", ")}`;
  buildFilterList($("topics"), $("topics-n"), state.topics, state.hiddenTopics);
  $("topics-all").addEventListener("click", () => showOnly(state.topics, state.hiddenTopics, null));
  $("topics-none").addEventListener("click", () => {
    for (const k of state.topics.keys()) state.hiddenTopics.add(k);
    state.topics.sync();
    render();
  });
  const order = ["Invited", "Oral", "Poster", "Online", "Other"];
  const present = new Set(state.papers.map((p) => p.format));
  const el = $("format");
  el.append(...order.filter((f) => present.has(f)).map((f) => new Option(fmtLabel(f), f)));
  el.addEventListener("change", () => {
    state.format = el.value;
    render();
  });
  $("session-clear").addEventListener("click", () => setSession(null));
}

function updateFormatCounts() {
  const counts = new Map();
  let all = 0;
  for (const p of state.papers) {
    if (!passes(p, "format")) continue;
    all++;
    counts.set(p.format, (counts.get(p.format) || 0) + 1);
  }
  for (const o of $("format").options) {
    const label = o.value ? fmtLabel(o.value) : "All formats";
    o.textContent = `${label} (${(o.value ? counts.get(o.value) || 0 : all).toLocaleString()})`;
  }
}

function updateTopicCounts() {
  const counts = new Map();
  for (const p of state.papers) if (passes(p, "topic")) counts.set(p.topic, (counts.get(p.topic) || 0) + 1);
  const n = (t) => counts.get(t.id) || 0;
  const sorted = [...state.topics.values()].filter((t) => t.li).sort((a, b) => n(b) - n(a) || b.size - a.size);
  for (const t of sorted) t.n.textContent = n(t);
  const ul = $("topics");
  if (sorted.some((t, i) => ul.children[i] !== t.li)) ul.append(...sorted.map((t) => t.li));
}

// A session (mini-symposium) is specific to one meeting.
function setSession(s) {
  state.session = s;
  $("session-field").hidden = !s;
  $("session-name").textContent = s ? `InterPore${s.year} · ${s.name}` : "";
  $("list-view").scrollTop = 0;
  render();
}

function setYears(lo, hi) {
  $("year-min").value = lo;
  $("year-max").value = hi;
  $("year-max").dispatchEvent(new Event("change"));
}

function setupYears() {
  const years = state.papers.map((p) => p.year);
  const lo = Math.min(...years);
  const hi = Math.max(...years);
  state.yearSpan = `${lo}–${hi}`;
  const minEl = $("year-min"), maxEl = $("year-max");
  for (const el of [minEl, maxEl]) Object.assign(el, { min: lo, max: hi, step: 1 });
  minEl.placeholder = lo;
  maxEl.placeholder = hi;
  minEl.value = state.yearMin = lo;
  maxEl.value = state.yearMax = hi;
  const read = (el, fallback) => {
    const v = el.value.trim();
    if (!v) return fallback;
    const n = Number(v);
    return Number.isInteger(n) && n >= lo && n <= hi ? n : null;
  };
  const apply = () => {
    const a = read(minEl, lo), b = read(maxEl, hi);
    minEl.classList.toggle("bad", a === null);
    maxEl.classList.toggle("bad", b === null);
    if (a === null || b === null) return;
    [state.yearMin, state.yearMax] = a <= b ? [a, b] : [b, a];
    $("years-reset").hidden = state.yearMin === lo && state.yearMax === hi;
    render();
  };
  const settle = () => {
    apply();
    minEl.value = state.yearMin;
    maxEl.value = state.yearMax;
    minEl.classList.remove("bad");
    maxEl.classList.remove("bad");
  };
  for (const el of [minEl, maxEl]) {
    el.addEventListener("input", apply);
    el.addEventListener("change", settle);
    el.addEventListener("keydown", (e) => e.key === "Enter" && settle());
    el.addEventListener("focus", () => el.select());
  }
  $("years-reset").addEventListener("click", () => setYears(lo, hi));
}

// ---- Search --------------------------------------------------------------------

const SEARCH_FIELDS = ["title", "authorText", "affText", "sessionText", "id"];

function newIndex(withAbstracts) {
  const idx = new MiniSearch({
    fields: withAbstracts ? [...SEARCH_FIELDS, "abstract"] : SEARCH_FIELDS,
    storeFields: [],
    searchOptions: {
      boost: { title: 3, authorText: 2.5, id: 3, sessionText: 1.5 },
      prefix: true,
      fuzzy: 0.15,
      combineWith: "AND",
    },
  });
  idx.addAll(
    state.papers.map((p) => ({
      id: p.id,
      title: p.title,
      authorText: (p.authors || []).join(" "),
      affText: (p.affs || []).filter(Boolean).join(" "),
      sessionText: sessionText(p),
      abstract: withAbstracts ? state.abstracts.get(p.id) || "" : "",
    })),
  );
  return idx;
}

function setupSearch() {
  search = newIndex(false);
  let timer;
  $("search").addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(runSearch, 150);
  });
}

function runSearch() {
  const q = $("search").value.trim();
  const sortEl = $("sort");
  if (!q) {
    state.matches = state.hitRank = state.hits = null;
    sortEl.querySelector('[value="relevance"]').disabled = true;
    if (state.sort === "relevance") sortEl.value = state.sort = state.sortBeforeSearch || "newest";
    render();
    return;
  }
  const hits = search.search(q);
  state.hits = hits.map((h) => h.id);
  state.matches = new Set(state.hits);
  state.hitRank = new Map(hits.map((h, i) => [h.id, i]));
  sortEl.querySelector('[value="relevance"]').disabled = false;
  if (state.sort !== "relevance") {
    state.sortBeforeSearch = state.sort;
    sortEl.value = state.sort = "relevance";
  }
  $("list-view").scrollTop = 0;
  render();
}

function setSearch(q) {
  $("search").value = q;
  runSearch();
}

function renderResults() {
  const list = $("results");
  if (!state.hits) return list.replaceChildren();
  const ids = state.hits.filter((id) => visible(state.byId.get(id)));
  list.replaceChildren(...ids.slice(0, 40).map((id) => paperItem(state.byId.get(id), () => focus(id))));
  const note = (text) => {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = text;
    list.append(li);
  };
  if (ids.length > 40) note(`… ${ids.length - 40} more on the map`);
  const hidden = state.hits.length - ids.length;
  if (hidden) note(`${hidden} more hidden by the filters`);
}

// ---- History view ----------------------------------------------------------------

async function loadHistory() {
  if (!state.historyData) state.historyData = fetch("data/history.json").then((r) => r.json());
  return state.historyData;
}

async function showHistory() {
  const data = await loadHistory();
  if (!state.historyBuilt) {
    buildHistory(data);
    state.historyBuilt = true;
  }
  renderCharts();
}

function ORDINAL(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function link(href, text, cls) {
  const a = el("a", cls, text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function fmtDates(m) {
  const s = new Date(m.start + "T00:00:00Z"), e = new Date(m.end + "T00:00:00Z");
  const mon = (d) => d.toLocaleString("en", { month: "long", timeZone: "UTC" });
  const sameMonth = s.getUTCMonth() === e.getUTCMonth();
  return sameMonth
    ? `${s.getUTCDate()}–${e.getUTCDate()} ${mon(s)} ${s.getUTCFullYear()}`
    : `${s.getUTCDate()} ${mon(s)} – ${e.getUTCDate()} ${mon(e)} ${e.getUTCFullYear()}`;
}

function buildHistory(data) {
  $("h-about").textContent = data.society.about.replace(/\s+/g, " ");
  const t = data.totals;
  const tiles = [
    ["Annual meetings", `${t.meetings}`, `since ${data.society.founded + 1}`],
    ["Abstracts online", t.abstracts.toLocaleString(), `from ${t.first_year_with_abstracts}`],
    ["Distinct authors", t.authors.toLocaleString(), "since 2016"],
    ["Host countries", `${t.countries}`, "plus two online years"],
  ];
  $("h-totals").replaceChildren(
    ...tiles.map(([label, value, sub]) => {
      const d = el("div");
      const dt = el("dt", null, label);
      const dd = el("dd", null, value);
      const small = el("dd", "sub", sub);
      d.append(dt, dd, small);
      return d;
    }),
  );
  const items = [...data.meetings].reverse().map((m) => meetingItem(m));
  $("h-timeline").replaceChildren(...items);
}

function meetingItem(m) {
  const li = el("li", "m-item");
  if (!m.stats) li.classList.add("no-abstracts");
  if (m.upcoming) li.classList.add("upcoming");
  li.id = `m-${m.year}`;
  li.append(el("div", "m-year", m.year), el("div", "m-dot"));
  const c = el("div", "m-card");
  const head = el("div", "m-head");
  head.append(el("h4", null, `${ORDINAL(m.number)} meeting · ${m.title}`), el("span", "when", fmtDates(m)));
  if (m.format && m.format !== "in-person") head.append(el("span", "badge", m.format));
  if (m.upcoming) head.append(el("span", "badge", "upcoming"));
  c.append(head);
  const place = [m.venue, m.city === "Online" ? null : m.city, m.country].filter(Boolean).join(", ");
  c.append(el("p", "m-place", m.city === "Online" ? "Online" : place));
  if (m.notes) c.append(el("p", "m-notes", m.notes.replace(/\s+/g, " ")));
  const s = m.stats;
  if (s) {
    const p = el("p", "m-stats");
    const parts = [
      [s.abstracts.toLocaleString(), " abstracts"],
      [s.sessions, " sessions"],
      [s.authors.toLocaleString(), " authors"],
    ];
    if (s.new_authors !== null) parts.push([`${Math.round((100 * s.new_authors) / s.authors)}%`, " first seen"]);
    parts.push([s.mean_authors.toFixed(1), " authors per abstract"]);
    parts.forEach(([b, rest], i) => {
      if (i) p.append(" · ");
      p.append(el("b", null, b), rest);
    });
    c.append(p);
    const terms = el("div", "m-terms");
    terms.title = "Words most distinctive of this meeting's abstracts (c-TF-IDF). Click to search them in this year.";
    for (const w of s.terms) {
      const b = el("button", null, w);
      b.type = "button";
      b.addEventListener("click", () => {
        setYears(m.year, m.year);
        setView("list");
        setSearch(w);
      });
      terms.append(b);
    }
    c.append(terms);
    if (s.top_sessions.length) {
      const det = el("details", "m-more");
      det.append(el("summary", null, "Largest sessions and stand-out topics"));
      const ol = el("ol");
      for (const ss of s.top_sessions) {
        const item = el("li");
        const b = el("button", "link", ss.name);
        b.type = "button";
        b.addEventListener("click", () => {
          setYears(m.year, m.year);
          setView("list");
          setSession({ year: m.year, name: ss.name });
        });
        item.append(b, ` (${ss.n})`);
        ol.append(item);
      }
      det.append(ol);
      if (s.top_topics.length) {
        det.append(
          el("p", "muted small", "Topics most over-represented compared with all meetings: " +
            s.top_topics.map((x) => `${x.name} (${x.lift}×)`).join(", ")),
        );
      }
      c.append(det);
    }
  }
  const links = el("div", "m-links");
  if (s) {
    const b = el("button", "btn", "Browse these abstracts");
    b.type = "button";
    b.addEventListener("click", () => {
      setSession(null);
      setYears(m.year, m.year);
      setView("list");
    });
    links.append(b);
  }
  if (m.indico_url) links.append(link(m.indico_url, "Indico event ↗"));
  if (m.book) links.append(link(m.book, "Book of abstracts (PDF) ↗"));
  if (m.program) links.append(link(m.program, "Programme (PDF) ↗"));
  if (m.report) links.append(link(m.report, "Conference report ↗"));
  if (m.page) links.append(link(m.page, "interpore.org ↗"));
  if (links.childElementCount) c.append(links);
  li.append(c);
  return li;
}

// Chart colours: the validated default palette (dataviz skill), stepped for each mode.
const VIZ = {
  light: {
    surface: "#fcfcfb", ink: "#0b0b0b", ink2: "#52514e", muted: "#898781", grid: "#e1e0d9", axis: "#c3c2b7",
    series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    ramp: ["#f0f5fc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
  },
  dark: {
    surface: "#1a1a19", ink: "#f0efec", ink2: "#c3c2b7", muted: "#898781", grid: "#2c2c2a", axis: "#383835",
    series: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"],
    ramp: ["#1d2633", "#104281", "#184f95", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"],
  },
};

function vegaConfig(v) {
  const font = "system-ui, -apple-system, Segoe UI, sans-serif";
  return {
    background: v.surface,
    font,
    padding: 8,
    view: { stroke: null },
    axis: {
      labelColor: v.ink2, titleColor: v.ink2, gridColor: v.grid, domainColor: v.axis, tickColor: v.axis,
      labelFontSize: 12, titleFontSize: 12, titleFontWeight: 500,
    },
    axisX: { grid: false },
    legend: { labelColor: v.ink2, titleColor: v.ink2, labelFontSize: 12, titleFontSize: 12, titleFontWeight: 500, orient: "top" },
    header: { labelColor: v.ink, labelFontSize: 13, labelFontWeight: 600 },
    range: { category: v.series, heatmap: v.ramp, ramp: v.ramp },
    bar: { stroke: v.surface, strokeWidth: 1 },
    rect: { stroke: v.surface, strokeWidth: 2 },
    line: { color: v.series[0], strokeWidth: 2 },
    point: { color: v.series[0], stroke: v.surface, strokeWidth: 1.5 },
    tooltipFormat: {},
  };
}

// "Not recorded" is not a category of its own: draw it in the neutral ink.
function patchColors(spec, v) {
  const walk = (o) => {
    if (!o || typeof o !== "object") return;
    const color = o.encoding?.color;
    const domain = color?.scale?.domain;
    if (Array.isArray(domain) && color.type === "nominal") {
      let i = 0;
      color.scale.range = domain.map((d) => (d === "Not recorded" ? v.muted : v.series[i++]));
    }
    for (const k of ["layer", "spec"]) {
      if (Array.isArray(o[k])) o[k].forEach(walk);
      else if (o[k]) walk(o[k]);
    }
  };
  walk(spec);
  return spec;
}

async function renderCharts() {
  if (state.view !== "history" || !window.vegaEmbed) return;
  const v = isDark() ? VIZ.dark : VIZ.light;
  for (const box of document.querySelectorAll(".chart[data-chart]")) {
    const name = box.dataset.chart;
    state.specs ||= {};
    state.specs[name] ||= fetch(`data/charts/${name}.json`).then((r) => r.json());
    const spec = patchColors(structuredClone(await state.specs[name]), v);
    const holder = box.querySelector(".plot") || box.appendChild(el("div", "plot"));
    try {
      await vegaEmbed(holder, spec, {
        actions: false,
        renderer: "svg",
        config: vegaConfig(v),
        tooltip: { theme: isDark() ? "dark" : "light" },
      });
    } catch (err) {
      holder.textContent = `Chart failed to load: ${err.message}`;
    }
    if (!box.querySelector(".chart-table")) box.append(chartTable(await state.specs[name]));
  }
}

// The data behind a chart as a table (accessibility; one row per data value).
function chartTable(spec) {
  const values = spec.data?.values || spec.datasets?.[Object.keys(spec.datasets)[0]] || [];
  const det = el("details", "chart-table");
  det.append(el("summary", null, "Data table"));
  if (!values.length) return det;
  const cols = Object.keys(values[0]).filter((k) => k !== "o");
  const table = el("table");
  const thead = el("tr");
  for (const c of cols) thead.append(el("th", null, c));
  table.append(thead);
  for (const row of values) {
    const tr = el("tr");
    for (const c of cols) tr.append(el("td", null, row[c]));
    table.append(tr);
  }
  const wrap = el("div", "scroll");
  wrap.append(table);
  det.append(wrap);
  return det;
}

// ---- Start -----------------------------------------------------------------------

async function main() {
  setupTheme();
  setupResizers();
  const [papers, topics] = await Promise.all([
    fetch("data/papers.json").then((r) => r.json()),
    fetch("data/topics.json").then((r) => r.json()),
  ]);
  state.papers = papers;
  papers.forEach((p, i) => {
    p.order = i;
    p.authors ||= [];
    p.similar ||= [];
    p.sortTitle = plainTex(p.title).replace(/^[^\p{L}\p{N}]+/u, "").toLowerCase();
    state.byId.set(p.id, p);
    for (const a of p.authors) {
      const k = nameKey(a);
      if (!k) continue;
      if (!state.byPerson.has(k)) state.byPerson.set(k, []);
      state.byPerson.get(k).push(p.id);
    }
  });
  const bySize = [...topics].sort((a, b) => b.size - a.size);
  bySize.forEach((t, i) => {
    t.rgb = topicColor(i);
    t.short ||= t.label.split(" / ").slice(0, 2).join(" / ");
    state.topics.set(t.id, t);
  });

  const box = $("map").getBoundingClientRect();
  const zoom = Math.log2(Math.min(box.width || 800, box.height || 600) / (WORLD * 1.08));
  state.zoom = zoom;
  deck = new window.deck.Deck({
    parent: $("map"),
    views: new window.deck.OrthographicView({ flipY: false }),
    initialViewState: { target: [WORLD / 2, WORLD / 2, 0], zoom, minZoom: zoom - 1, maxZoom: 7 },
    controller: { doubleClickZoom: true },
    onViewStateChange: ({ viewState }) => {
      state.mapView = viewState;
      updateLabels();
      return viewState;
    },
    getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
    layers: [],
  });

  setupFilters();
  setupList();
  setupYears();
  setupSearch();
  for (const b of document.querySelectorAll(".views button")) b.addEventListener("click", () => setView(b.dataset.view));
  let view = "list";
  try {
    view = localStorage.getItem("view") || "list";
  } catch {}
  if (location.hash === "#history") view = "history";
  setView(["list", "map", "history"].includes(view) ? view : "list");
  $("close").addEventListener("click", () => select(null));
  $("wide").addEventListener("click", () => setWide(!$("detail").classList.contains("wide")));
  try {
    setWide(localStorage.getItem("wide") === "1");
  } catch {}
  for (const b of document.querySelectorAll(".tabs button")) b.addEventListener("click", () => showRelated(b.dataset.tab));
  $("d-topic").addEventListener("click", () => {
    const t = state.byId.get(state.selected)?.topic;
    if (t !== undefined) showOnly(state.topics, state.hiddenTopics, t);
  });
  $("d-session").addEventListener("click", () => {
    const p = state.byId.get(state.selected);
    if (p?.session) setSession({ year: p.year, name: p.session });
  });
  $("d-map").addEventListener("click", () => showOnMap(state.selected));
  $("d-copy").addEventListener("click", async () => {
    $("d-copy").textContent = (await copyText(location.href)) ? "Copied" : "Copy failed";
    setTimeout(() => ($("d-copy").textContent = "Copy link"), 1500);
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, select, textarea")) return;
    if (e.key === "Escape") select(null);
    else if (e.key === "r" && state.selected) setWide(!$("detail").classList.contains("wide"));
    else if (e.key === "m" && state.selected) showOnMap(state.selected);
  });
  window.addEventListener("hashchange", () => {
    const h = decodeURIComponent(location.hash.slice(1));
    if (h === "history") setView("history");
    else focus(h);
  });
  render();
  const h = decodeURIComponent(location.hash.slice(1));
  if (h && h !== "history") focus(h);

  // Meeting places for the list's year headings.
  loadHistory()
    .then((data) => {
      state.meetingByYear = new Map(data.meetings.map((m) => [m.year, m]));
      if (state.view === "list") render();
    })
    .catch(() => {});

  // Abstracts in the background: then the cards show snippets and search covers them.
  const abstracts = await fetch("data/abstracts.json").then((r) => r.json());
  state.abstracts = new Map(Object.entries(abstracts));
  search = newIndex(true);
  if ($("search").value.trim()) runSearch();
  else render();
  if (state.selected) showAbstract(state.byId.get(state.selected));
}

main().catch((err) => {
  $("count").textContent = `Failed to load data: ${err.message}`;
});
