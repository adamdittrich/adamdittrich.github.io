/* Historical GIS explorer. Native SVG and browser APIs; no remote map tiles. */
(() => {
  "use strict";
  const root = document.querySelector(".gis-page");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const assetRoot = new URL(root.dataset.assetRoot, document.baseURI);
  const PALETTES = {
    blue: ["#e0ecf1", "#afcddd", "#75a7bf", "#407a9a", "#174c6c"],
    green: ["#e2eddd", "#b8d3b1", "#80b49b", "#498b78", "#225b54"],
    teal: ["#e0efea", "#afd4cc", "#79b4af", "#448d91", "#225d6f"],
    rust: ["#f5e6c9", "#e8c28c", "#d79758", "#bd663e", "#8d3d32"],
    purple: ["#eee5f1", "#d2b9db", "#ae8dbd", "#846493", "#554264"],
    diverging: ["#a45a43", "#d5aa84", "#eee9da", "#85b5b5", "#3c7c8c"]
  };
  const state = {
    explorer: null, metrics: [], metric: null, selected: null, year: 1930,
    classification: "quantile", paths: new Map(), focused: false,
    annualMetric: null, comparison: "", dictionary: [], dictionaryFiltered: [],
    dictionaryPage: 0, gallery: [], galleryFiltered: [], galleryGroup: "all",
    galleryVisible: 9, lightboxIndex: 0, lastGalleryButton: null
  };
  const finite = (n) => typeof n === "number" && Number.isFinite(n);
  const text = (v) => v == null ? "" : typeof v === "object"
    ? Array.isArray(v) ? v.map(text).join("; ") : text(v.label || v.name || v.description || v.url || "")
    : String(v);
  const normal = (v) => text(v).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const element = (tag, content, className) => {
    const e = document.createElement(tag);
    if (content != null) e.textContent = text(content);
    if (className) e.className = className;
    return e;
  };
  const svgElement = (tag, attrs, content) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
    if (content != null) e.textContent = String(content);
    return e;
  };
  const assetURL = (path) => {
    if (!path) return "";
    const raw = String(path);
    const base = raw.startsWith("assets/") || raw.startsWith("/") ? document.baseURI : assetRoot;
    const url = new URL(raw, base);
    if (!["https:", "http:"].includes(url.protocol)) throw new Error("Unsupported asset URL");
    return url.href;
  };
  const items = (data, keys) => {
    if (Array.isArray(data)) return data;
    for (const k of keys) if (Array.isArray(data?.[k])) return data[k];
    return [];
  };
  const option = (value, label) => {
    const e = element("option", label); e.value = value; return e;
  };
  const formatNumber = (value, metric = {}) => {
    if (!finite(value)) return "Not available";
    const key = normal(metric.key || metric.label);
    const defaultDigits = /population(?! density)|_count|votes|persons|people/.test(key) ? 0 : 1;
    const decimals = Number.isInteger(metric.digits) ? metric.digits
      : Number.isInteger(metric.decimals) ? metric.decimals : defaultDigits;
    return new Intl.NumberFormat("en-GB", {maximumFractionDigits: decimals}).format(value);
  };
  const fmtShort = (value) => new Intl.NumberFormat("en-GB", {
    notation: Math.abs(value) >= 100000 ? "compact" : "standard", maximumFractionDigits: Math.abs(value) < 10 ? 1 : 0
  }).format(value);
  const metricPeriod = (m) => m?.annual_key ? String(state.year) : text(m?.period);
  const median = (a) => a.length ? quantile(a, .5) : null;
  function quantile(sorted, p) {
    if (!sorted.length) return null;
    const index = (sorted.length - 1) * p;
    const low = Math.floor(index), high = Math.ceil(index);
    return sorted[low] + (sorted[high] - sorted[low]) * (index - low);
  }
  function metricValue(district, metric) {
    if (!district || !metric) return null;
    const value = metric.annual_key
      ? state.explorer.annual?.districts?.[district.id]?.[metric.annual_key]?.[state.explorer.annual.years.indexOf(state.year)]
      : district.values?.[metric.key];
    return finite(value) ? value : null;
  }
  async function loadJSON(file) {
    const response = await fetch(assetURL(file), {credentials: "same-origin"});
    if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
    return response.json();
  }
  async function loadExplorer() {
    // Climate remains a separately licensed data product on the server. The
    // reader joins it by the same stable IDs only when both files have loaded.
    const [core, climate] = await Promise.all([
      loadJSON("explorer.json"), loadJSON("climate_explorer.json")
    ]);
    if (!climate || typeof climate.values !== "object" || !climate.annual) {
      throw new Error("The separately licensed climate explorer is incomplete");
    }
    for (const d of core.districts || []) {
      d.values = {...d.values, ...(climate.values[d.id] || {})};
    }
    core.annual = climate.annual;
    for (const m of core.metrics || []) {
      if (Object.values(climate.values).some(values => Object.hasOwn(values, m.key))) {
        m.license = m.license || climate.license;
      }
    }
    for (const m of core.annual.metrics || []) m.license = m.license || climate.license;
    return core;
  }
  function sourceText(source) {
    return Array.isArray(source) ? source.map(text).join("; ") : text(source);
  }
  function getPalette(metric, count) {
    let colors;
    if (Array.isArray(metric.colors)) colors = metric.colors;
    else if (Array.isArray(metric.palette)) colors = metric.palette;
    else {
      const name = normal(metric.palette || "blue");
      const preset = name.includes("diverg") || /rdbu|brbg|puor/.test(name) ? "diverging"
        : name.includes("green") || name.includes("ylgn") ? "green"
        : name.includes("teal") || name.includes("pubugn") ? "teal"
        : name.includes("purple") || name.includes("purp") ? "purple"
        : /rust|ylor|oranges|reds|brown/.test(name) ? "rust" : "blue";
      colors = PALETTES[preset];
    }
    colors = colors.filter(c => /^#[0-9a-fA-F]{3,8}$/.test(c));
    if (!colors.length) colors = PALETTES.blue;
    if (count === 1) return [colors[Math.floor(colors.length / 2)]];
    return Array.from({length: count}, (_, i) => colors[Math.round(i * (colors.length - 1) / (count - 1))]);
  }
  function makeScale(metric) {
    const values = state.explorer.districts.map(d => metricValue(d, metric)).filter(finite).sort((a, b) => a - b);
    if (!values.length) return {values, thresholds: [], colors: [], min: null, max: null, color: () => "#d1d4d5"};
    let min = values[0], max = values.at(-1), thresholds = [];
    if (min !== max) {
      if (state.classification === "equal") {
        if (finite(metric.center)) {
          const distance = Math.max(Math.abs(min - metric.center), Math.abs(max - metric.center));
          min = metric.center - distance; max = metric.center + distance;
        }
        thresholds = [1, 2, 3, 4].map(i => min + (max - min) * i / 5);
      } else thresholds = [1, 2, 3, 4].map(i => quantile(values, i / 5));
      thresholds = [...new Set(thresholds)].filter(n => n > min && n < max);
    }
    const colors = getPalette(metric, thresholds.length + 1);
    return {values, thresholds, colors, min, max,
      color: value => !finite(value) ? "#d1d4d5" : colors[thresholds.filter(t => value > t).length]};
  }
  function districtNotes(d) {
    const notes = d?.quality_notes || d?.flags || d?.quality || [];
    if (Array.isArray(notes)) return notes.map(text).filter(Boolean);
    if (typeof notes === "string") return notes ? [notes] : [];
    return Object.entries(notes).filter(([, value]) => value).map(([key, value]) => typeof value === "string" ? value : key.replaceAll("_", " "));
  }
  function populateDistrictSelect(search = "") {
    const select = $("gis-district");
    const query = normal(search);
    const districts = state.explorer.districts.filter(d => normal(d.name + " " + d.id).includes(query));
    select.replaceChildren(...districts.map(d => option(d.id, d.name)));
    if (!districts.length) select.append(option("", "No matching district"));
    if (districts.some(d => d.id === state.selected?.id)) select.value = state.selected.id;
    else if (districts.length) {
      const placeholder = option("", "Choose a matching district…");
      placeholder.disabled = true; select.prepend(placeholder); select.value = "";
    } else select.selectedIndex = 0;
    select.disabled = !districts.length;
  }
  function populateMetrics() {
    const select = $("gis-metric"); select.replaceChildren();
    const groups = new Map();
    for (const m of state.metrics) {
      const group = m.group || "District measures";
      if (!groups.has(group)) {
        const node = element("optgroup"); node.label = group; groups.set(group, node); select.append(node);
      }
      groups.get(group).append(option(m.key, m.label || m.key));
    }
    select.value = state.metric.key; select.disabled = false;
  }
  function renderMainSVG() {
    const canvas = $("gis-map-canvas");
    const svg = svgElement("svg", {id: "gis-map-svg-element", viewBox: state.explorer.viewBox.join(" "), role: "group", "aria-label": "Interactive map of the 330 judicial districts in 1930. Use the district selector or arrow keys to select a district."});
    svg.append(svgElement("title", {}, "Judicial districts of the Czech lands, 1930"));
    const g = svgElement("g", {id: "gis-district-paths"});
    for (const d of state.explorer.districts) {
      const path = svgElement("path", {d: d.path, class: "gis-district-shape", "data-district": d.id, role: "button", tabindex: d.id === state.selected.id ? 0 : -1});
      path.append(svgElement("title", {}, d.name));
      path.addEventListener("click", () => selectDistrict(d.id));
      path.addEventListener("pointermove", event => showTooltip(event, d));
      path.addEventListener("pointerleave", hideTooltip);
      path.addEventListener("keydown", event => {
        if (["Enter", " "].includes(event.key)) { event.preventDefault(); selectDistrict(d.id); }
        const direction = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 0;
        if (direction) {
          event.preventDefault();
          const index = state.explorer.districts.findIndex(x => x.id === d.id);
          const next = state.explorer.districts[(index + direction + state.explorer.districts.length) % state.explorer.districts.length];
          selectDistrict(next.id); state.paths.get(next.id)?.focus();
        }
      });
      state.paths.set(d.id, path); g.append(path);
    }
    svg.append(g, svgElement("path", {id: "gis-map-selection", class: "gis-selected-outline", "aria-hidden": true}));
    canvas.querySelector(".gis-map-fallback")?.remove();
    canvas.prepend(svg); canvas.setAttribute("aria-busy", "false");
  }
  function renderHero() {
    const svg = svgElement("svg", {viewBox: state.explorer.viewBox.join(" "), role: "img", "aria-label": "The 330 historical judicial districts of the Czech lands, with Semily highlighted."});
    const palette = ["#3d5966", "#527782", "#6b9299", "#91b1b2", "#bed0c5"];
    const baseMetric = state.metrics.find(m => /population.*density|density.*population/.test(normal(m.key + " " + m.label))) || state.metric;
    const vals = state.explorer.districts.map(d => metricValue(d, baseMetric)).filter(finite).sort((a, b) => a - b);
    const boundaries = [.2, .4, .6, .8].map(p => quantile(vals, p));
    const g = svgElement("g", {});
    for (const d of state.explorer.districts) {
      const value = metricValue(d, baseMetric);
      const semily = normal(d.name) === "semily";
      g.append(svgElement("path", {d: d.path, fill: semily ? "#e7c38b" : finite(value) ? palette[boundaries.filter(t => value > t).length] : "#4b5e66", stroke: semily ? "#f1d8ad" : "#203d49", "stroke-width": semily ? 1.8 : .75, "vector-effect": "non-scaling-stroke"}));
    }
    svg.append(g);
    const semily = state.explorer.districts.find(d => normal(d.name) === "semily");
    if (semily && finite(semily.x) && finite(semily.y)) {
      svg.append(svgElement("circle", {cx: semily.x, cy: semily.y, r: 4.5, fill: "#e7c38b", stroke: "#fff4db", "stroke-width": 1.5}));
      svg.append(svgElement("line", {x1: semily.x, y1: semily.y, x2: semily.x + 24, y2: semily.y - 38, stroke: "#e7c38b", "stroke-width": 1.5}));
      svg.append(svgElement("text", {x: semily.x + 30, y: semily.y - 40, fill: "#f4dcad", "font-size": 19, "font-family": "Segoe UI, Helvetica, Arial, sans-serif"}, "Semily"));
    }
    $("gis-hero-map").replaceChildren(svg);
    $("gis-hero-caption").textContent = `${baseMetric.label || "District structure"} · ${metricPeriod(baseMetric)} · Semily highlighted`;
  }
  function showTooltip(event, district) {
    if (event.pointerType === "touch") return;
    const tip = $("gis-map-tooltip");
    const value = metricValue(district, state.metric);
    tip.replaceChildren(element("strong", district.name), element("span", `${formatNumber(value, state.metric)}${finite(value) && state.metric.unit ? " " + state.metric.unit : ""}`));
    tip.hidden = false;
    const rect = $("gis-map-canvas").getBoundingClientRect();
    tip.style.left = Math.max(3, Math.min(event.clientX - rect.left + 13, rect.width - tip.offsetWidth - 4)) + "px";
    tip.style.top = Math.max(3, Math.min(event.clientY - rect.top + 13, rect.height - tip.offsetHeight - 4)) + "px";
  }
  function hideTooltip() { $("gis-map-tooltip").hidden = true; }
  function renderMap() {
    const m = state.metric, scale = makeScale(m);
    for (const d of state.explorer.districts) {
      const p = state.paths.get(d.id), value = metricValue(d, m);
      p.setAttribute("fill", scale.color(value));
      p.setAttribute("aria-label", `${d.name}: ${formatNumber(value, m)}${finite(value) && m.unit ? " " + m.unit : ""}`);
      p.setAttribute("aria-pressed", String(d.id === state.selected.id));
      p.querySelector("title").textContent = p.getAttribute("aria-label");
      p.setAttribute("tabindex", d.id === state.selected.id ? "0" : "-1");
    }
    $("gis-map-selection").setAttribute("d", state.selected.path);
    $("gis-map-title").textContent = m.label || m.key;
    $("gis-map-period").textContent = `${metricPeriod(m)} · Judicial districts 1930${m.unit ? " · " + m.unit : ""}`;
    $("gis-map-description").textContent = text(m.description || "");
    $("gis-map-source").textContent = m.source ? "Source: " + sourceText(m.source) : "Source definitions are provided in the variable dictionary.";
    $("gis-map-quality").textContent = text(m.quality_note || m.note || "");
    $("gis-map-quality").hidden = !$("gis-map-quality").textContent;
    $("gis-map-year-control").hidden = !m.annual_key;
    $("gis-map-year").value = state.year; $("gis-map-year-label").textContent = state.year;
    const legend = $("gis-map-legend"); legend.replaceChildren();
    const bounds = [scale.min, ...scale.thresholds, scale.max];
    scale.colors.forEach((c, i) => {
      const span = element("span", null, "gis-legend-item"), swatch = element("i");
      swatch.style.background = c;
      const label = scale.colors.length === 1 ? formatNumber(scale.min, m)
        : `${formatNumber(bounds[i], m)}–${formatNumber(bounds[i + 1], m)}`;
      span.append(swatch, document.createTextNode(label)); legend.append(span);
    });
    const missing = state.explorer.districts.length - scale.values.length;
    const unavailable = element("span", null, "gis-legend-item"), grey = element("i");
    grey.style.background = "#d1d4d5"; unavailable.append(grey, document.createTextNode(`Unavailable (${missing})`)); legend.append(unavailable);
    const summary = $("gis-map-summary"); summary.replaceChildren();
    for (const [label, val] of [["Available", `${scale.values.length} / ${state.explorer.districts.length} districts`],
      ["District median", formatNumber(median(scale.values), m)],
      ["Classification", state.classification === "quantile" ? "Quantiles of available districts" : "Equal value intervals"]]) {
      const node = element("span", label + ": "); node.append(element("strong", val)); summary.append(node);
    }
    renderDistrict();
    if (state.focused) focusDistrict();
  }
  function renderDistrict() {
    const d = state.selected, m = state.metric, value = metricValue(d, m);
    $("gis-district-name").textContent = d.name; $("gis-district-id").textContent = d.id;
    $("gis-selected-label").textContent = m.label || m.key;
    $("gis-selected-value").textContent = formatNumber(value, m);
    $("gis-selected-unit").textContent = finite(value) ? text(m.unit) : "Missing or withheld for this measure";
    const sorted = state.explorer.districts.map(x => metricValue(x, m)).filter(finite).sort((a, b) => a - b);
    $("gis-selected-context").textContent = finite(value) && sorted.length ? `${metricPeriod(m)} · ${value > median(sorted) ? "Above" : value < median(sorted) ? "Below" : "At"} the median of available districts.` : `${metricPeriod(m)} · See coverage and quality notes.`;
    const profile = $("gis-district-profile"); profile.replaceChildren();
    let metrics = (state.explorer.profileMetrics || []).map(k => typeof k === "object" ? k : state.metrics.find(x => x.key === k)).filter(Boolean);
    if (!metrics.length) {
      const preferred = ["population", "agriculture_pct_active_atlas", "mean_elevation_m", "clim_normal_1901_1928_precip_mm_year"];
      metrics = preferred.map(key => state.metrics.find(x => x.key === key)).filter(Boolean);
      if (!metrics.length) {
        const patterns = [/^population$|^o_po$|total population/, /agricultur/, /elevat|altitude/, /annual.*precip.*mean|mean annual.*precip/];
        metrics = patterns.map(p => state.metrics.find(x => !x.annual_key && (p.test(normal(x.key)) || p.test(normal(x.label))))).filter(Boolean);
      }
    }
    metrics = [...new Map(metrics.map(x => [x.key, x])).values()].filter(x => x.key !== m.key).slice(0, 5);
    for (const metric of metrics) {
      const row = element("div"), value = metricValue(d, metric);
      const label = element("dt", metric.short_label || metric.label || metric.key);
      label.title = `${metric.period || ""}; ${metric.unit || ""}`;
      label.append(element("small", [metric.period, metric.unit].filter(Boolean).join(" · ")));
      row.append(label, element("dd", finite(value) ? formatNumber(value, metric) : "—")); profile.append(row);
    }
    const flags = $("gis-district-flags"); flags.replaceChildren(...districtNotes(d).map(n => element("p", n)));
  }
  function selectDistrict(id) {
    const district = state.explorer.districts.find(d => d.id === id);
    if (!district) return;
    state.selected = district; hideTooltip();
    if (![...$("gis-district").options].some(o => o.value === id)) {
      $("gis-district-search").value = ""; populateDistrictSelect();
    }
    $("gis-district").value = id;
    if (state.comparison === id) { state.comparison = ""; $("gis-climate-comparison").value = ""; }
    renderMap(); renderClimate();
    $("gis-map-status").textContent = `Selected ${district.name}.`;
  }
  function focusDistrict() {
    const p = state.paths.get(state.selected.id), bbox = p.getBBox(), full = state.explorer.viewBox;
    const aspect = full[2] / full[3];
    let width = Math.max(bbox.width * 4, full[2] / 4.2), height = Math.max(bbox.height * 4, width / aspect);
    width = Math.max(width, height * aspect);
    const x = bbox.x + bbox.width / 2 - width / 2, y = bbox.y + bbox.height / 2 - height / 2;
    $("gis-map-svg-element").setAttribute("viewBox", [x, y, width, height].join(" "));
    state.focused = true; $("gis-reset-map").disabled = false;
  }
  function resetMap() {
    state.focused = false; $("gis-map-svg-element").setAttribute("viewBox", state.explorer.viewBox.join(" ")); $("gis-reset-map").disabled = true;
  }
  function setupAnnual() {
    const a = state.explorer.annual;
    if (!a || !Array.isArray(a.years) || !a.metrics?.length || !a.districts) {
      $("gis-climate-plot").replaceChildren(element("p", "The annual panel is available through the downloads. No browser series was supplied.", "gis-empty"));
      $("gis-climate-plot").setAttribute("aria-busy", "false"); return;
    }
    a.years = a.years.map(Number);
    state.year = a.years.includes(1930) ? 1930 : a.years[0];
    state.annualMetric = a.metrics[0];
    for (const id of ["gis-map-year", "gis-climate-year"]) {
      $(id).min = Math.min(...a.years); $(id).max = Math.max(...a.years); $(id).value = state.year;
    }
    $("gis-climate-metric").replaceChildren(...a.metrics.map(m => option(m.key, m.label || m.key)));
    $("gis-climate-metric").disabled = false;
    $("gis-climate-comparison").replaceChildren(option("", "No comparison"), ...state.explorer.districts.map(d => option(d.id, d.name)));
    const initial = state.explorer.districts.find(d => normal(d.name) === "vrchlabi" && d.id !== state.selected.id);
    state.comparison = initial?.id || ""; $("gis-climate-comparison").value = state.comparison; $("gis-climate-comparison").disabled = false;
    $("gis-climate-csv").disabled = false; $("gis-climate-svg").disabled = false;
  }
  function annualSeries() {
    if (!state.annualMetric || !state.explorer?.annual) return [];
    const districts = [state.selected, state.explorer.districts.find(d => d.id === state.comparison)].filter(Boolean);
    return districts.map((d, i) => ({district: d, color: i ? "#b67534" : "#286785", values: state.explorer.annual.districts[d.id]?.[state.annualMetric.key] || []}));
  }
  function renderClimate() {
    if (!state.annualMetric) return;
    const plot = $("gis-climate-plot"), years = state.explorer.annual.years, series = annualSeries(), m = state.annualMetric;
    const values = series.flatMap(s => s.values.filter(finite));
    $("gis-climate-title").textContent = series.map(s => s.district.name).join(" & ") + " · " + (m.label || m.key);
    $("gis-climate-unit").textContent = text(m.unit);
    $("gis-climate-year-label").textContent = state.year;
    $("gis-climate-year").value = state.year;
    $("gis-map-year").value = state.year; $("gis-map-year-label").textContent = state.year;
    const legend = $("gis-climate-legend"); legend.replaceChildren();
    for (const s of series) {
      const e = element("span"), swatch = element("i"); swatch.style.background = s.color;
      e.append(swatch, document.createTextNode(s.district.name)); legend.append(e);
    }
    if (!values.length) { plot.replaceChildren(element("p", "No annual values are available for this selection.", "gis-empty")); return; }
    const width = Math.max(280, Math.round(plot.getBoundingClientRect().width || 900));
    const height = Math.max(240, Math.min(345, width * .39));
    const margins = {left: width < 430 ? 43 : 58, right: 18, top: 22, bottom: 35};
    const pw = width - margins.left - margins.right, ph = height - margins.top - margins.bottom;
    let ymin = Math.min(...values), ymax = Math.max(...values);
    if (m.zero_base === true) ymin = Math.min(0, ymin);
    const pad = (ymax - ymin || Math.max(Math.abs(ymax), 1)) * .1;
    ymin -= pad; ymax += pad;
    if (m.zero_base === true && Math.min(...values) >= 0) ymin = 0;
    const x = year => margins.left + (year - years[0]) / (years.at(-1) - years[0] || 1) * pw;
    const y = value => margins.top + ph - (value - ymin) / (ymax - ymin) * ph;
    const svg = svgElement("svg", {id: "gis-climate-svg-element", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${m.label}: annual values for ${series.map(s => s.district.name).join(" and ")}, ${years[0]}–${years.at(-1)}`, "font-family": "Segoe UI, Helvetica, Arial, sans-serif", "font-size": 11, fill: "#53636b"});
    svg.append(svgElement("title", {}, $("gis-climate-title").textContent));
    const periodStart = Math.max(years[0], 1918), periodEnd = Math.min(years.at(-1), 1938);
    if (periodEnd >= periodStart) svg.append(svgElement("rect", {x: x(periodStart), y: margins.top, width: x(periodEnd) - x(periodStart), height: ph, fill: "#f4f0e7"}));
    for (let i = 0; i < 5; i++) {
      const value = ymin + (ymax - ymin) * i / 4, yy = y(value);
      svg.append(svgElement("line", {x1: margins.left, x2: width - margins.right, y1: yy, y2: yy, stroke: "#dce1df", "stroke-width": 1}));
      svg.append(svgElement("text", {x: margins.left - 9, y: yy + 4, "text-anchor": "end"}, fmtShort(value)));
    }
    const ticks = [...new Set([years[0], ...years.filter(n => n % 10 === 0), years.at(-1)])];
    for (const year of ticks) svg.append(svgElement("text", {x: x(year), y: height - 11, "text-anchor": year === years[0] ? "start" : year === years.at(-1) ? "end" : "middle"}, year));
    const selectedX = x(state.year);
    svg.append(svgElement("line", {x1: selectedX, x2: selectedX, y1: margins.top, y2: margins.top + ph, stroke: "#977c55", "stroke-width": 1, "stroke-dasharray": "3 4"}));
    for (const s of series) {
      let path = "", previous = false;
      years.forEach((year, i) => {
        const value = s.values[i];
        if (!finite(value)) { previous = false; return; }
        path += `${previous ? "L" : "M"}${x(year).toFixed(2)},${y(value).toFixed(2)} `; previous = true;
      });
      svg.append(svgElement("path", {d: path, stroke: s.color, fill: "none", "stroke-width": 2.2, "stroke-linejoin": "round", "stroke-linecap": "round"}));
      const value = s.values[years.indexOf(state.year)];
      if (finite(value)) svg.append(svgElement("circle", {cx: selectedX, cy: y(value), r: 4.5, fill: s.color, stroke: "white", "stroke-width": 1.5}));
    }
    svg.addEventListener("click", event => {
      const rect = svg.getBoundingClientRect(), logicalX = (event.clientX - rect.left) * width / rect.width;
      const raw = years[0] + (logicalX - margins.left) / pw * (years.at(-1) - years[0]);
      const year = years.reduce((best, candidate) => Math.abs(candidate - raw) < Math.abs(best - raw) ? candidate : best, years[0]);
      setYear(year);
    });
    plot.replaceChildren(svg); plot.setAttribute("aria-busy", "false");
    const readout = $("gis-climate-readout"); readout.replaceChildren();
    for (const s of series) {
      const value = s.values[years.indexOf(state.year)], row = element("span", s.district.name + ": ");
      const strong = element("strong", formatNumber(value, m)); strong.style.color = s.color;
      row.append(strong, document.createTextNode(finite(value) && m.unit ? " " + m.unit : "")); readout.append(row);
    }
    $("gis-climate-caption").textContent = [text(m.description), "CRU-TS v4.10, area-weighted to the fixed 1930 district geography. The shaded period marks 1918–1938. The 330 series use 60 cells at 0.5° resolution; neighbouring districts can share source information.", text(m.quality_note)].filter(Boolean).join(" ");
  }
  function setYear(year) {
    if (!state.explorer?.annual?.years.includes(Number(year))) return;
    state.year = Number(year); renderClimate(); if (state.metric.annual_key) renderMap();
  }
  function setupExplorer(data) {
    if (!Array.isArray(data?.districts) || !data.districts.length || !Array.isArray(data.metrics) || !data.metrics.length) throw new Error("No district geometry or measures supplied");
    if (!Array.isArray(data.viewBox) || data.viewBox.length !== 4 || !data.viewBox.every(finite)) throw new Error("Invalid map extent");
    const ids = new Set();
    for (const d of data.districts) {
      if (!d.id || !d.name || typeof d.path !== "string" || !d.values || ids.has(d.id)) throw new Error("Invalid or duplicated district record");
      ids.add(d.id);
    }
    data.districts.sort((a, b) => a.name.localeCompare(b.name, "cs")); state.explorer = data;
    state.selected = data.districts.find(d => d.id === data.defaultDistrict)
      || data.districts.find(d => normal(d.name) === "semily") || data.districts[0];
    state.metrics = [...data.metrics];
    for (const m of data.annual?.metrics || []) if (!state.metrics.some(x => x.annual_key === m.key)) {
      state.metrics.push({...m, key: "annual:" + m.key, annual_key: m.key, group: "Climate · annual values", source: m.source || "CRU-TS v4.10 · University of East Anglia", period: "1901–1938"});
    }
    state.metric = state.metrics.find(m => m.key === data.defaultMetric)
      || state.metrics.find(m => /population.*density|density.*population/.test(normal(m.key + " " + m.label))) || state.metrics[0];
    populateMetrics(); populateDistrictSelect(); setupAnnual(); renderMainSVG(); renderHero(); renderMap(); renderClimate();
    ["gis-map-csv", "gis-map-svg", "gis-district-csv", "gis-focus-district"].forEach(id => $(id).disabled = false);
    $("gis-metric").addEventListener("change", () => {
      state.metric = state.metrics.find(m => m.key === $("gis-metric").value);
      if (finite(state.metric.center)) { state.classification = "equal"; $("gis-classification").value = "equal"; }
      if (state.metric.annual_key) {
        state.annualMetric = state.explorer.annual.metrics.find(m => m.key === state.metric.annual_key);
        $("gis-climate-metric").value = state.annualMetric.key; renderClimate();
      }
      hideTooltip(); renderMap();
    });
    $("gis-classification").addEventListener("change", () => { state.classification = $("gis-classification").value; renderMap(); });
    $("gis-district-search").addEventListener("input", () => populateDistrictSelect($("gis-district-search").value));
    $("gis-district-search").addEventListener("keydown", e => {
      if (e.key !== "Enter") return;
      const candidate = $("gis-district").value || [...$("gis-district").options].find(o => o.value)?.value;
      if (candidate) { e.preventDefault(); selectDistrict(candidate); }
    });
    $("gis-district").addEventListener("change", () => selectDistrict($("gis-district").value));
    $("gis-focus-district").addEventListener("click", focusDistrict); $("gis-reset-map").addEventListener("click", resetMap);
    $("gis-climate-metric").addEventListener("change", () => { state.annualMetric = state.explorer.annual.metrics.find(m => m.key === $("gis-climate-metric").value); renderClimate(); });
    $("gis-climate-comparison").addEventListener("change", () => { state.comparison = $("gis-climate-comparison").value === state.selected.id ? "" : $("gis-climate-comparison").value; $("gis-climate-comparison").value = state.comparison; renderClimate(); });
    ["gis-map-year", "gis-climate-year"].forEach(id => $(id).addEventListener("input", () => setYear(Number($(id).value))));
    if (window.ResizeObserver) {
      let request = 0, lastWidth = 0;
      new ResizeObserver(entries => {
        const width = entries[0].contentRect.width;
        if (Math.abs(width - lastWidth) < 2) return;
        lastWidth = width; cancelAnimationFrame(request); request = requestAnimationFrame(renderClimate);
      }).observe($("gis-climate-plot"));
    }
  }
  function normalizeDictionary(data) {
    return items(data, ["variables", "items", "fields", "dictionary"]).map(v => ({
      name: text(v.name || v.field || v.field_name || v.variable || v.column),
      label: text(v.label || v.label_en || v.description_short || ""),
      group: text(v.group || v.module || v.category || "Other fields"),
      unit: text(v.unit || v.units), period: text(v.period || v.observation_period || v.temporal_coverage),
      description: text(v.description || v.definition || v.definition_en || v.label),
      coverage: text(v.coverage ?? v.coverage_note ?? v.non_missing),
      source: sourceText(v.source || v.source_name || v.source_id),
      quality_note: text(v.quality_note || v.notes || v.interpretation_note),
      public_file: text(v.public_file)
    })).filter(v => v.name);
  }
  function setupDictionary(data) {
    state.dictionary = normalizeDictionary(data);
    if (!state.dictionary.length) throw new Error("No variable definitions supplied");
    const groups = [...new Set(state.dictionary.map(v => v.group))].sort((a, b) => a.localeCompare(b));
    $("gis-dictionary-group").append(...groups.map(g => option(g, g)));
    ["gis-dictionary-search", "gis-dictionary-group"].forEach(id => $(id).addEventListener(id.endsWith("search") ? "input" : "change", () => { state.dictionaryPage = 0; renderDictionary(); }));
    $("gis-dictionary-prev").addEventListener("click", () => { state.dictionaryPage--; renderDictionary(); });
    $("gis-dictionary-next").addEventListener("click", () => { state.dictionaryPage++; renderDictionary(); });
    $("gis-dictionary-csv").disabled = false; renderDictionary();
  }
  function renderDictionary() {
    const q = normal($("gis-dictionary-search").value), group = $("gis-dictionary-group").value;
    state.dictionaryFiltered = state.dictionary.filter(v => (group === "all" || v.group === group) && normal(Object.values(v).join(" ")).includes(q));
    const count = state.dictionaryFiltered.length, size = 18, pages = Math.max(1, Math.ceil(count / size));
    state.dictionaryPage = Math.min(Math.max(0, state.dictionaryPage), pages - 1);
    const body = $("gis-dictionary-table").querySelector("tbody"); body.replaceChildren();
    for (const v of state.dictionaryFiltered.slice(state.dictionaryPage * size, (state.dictionaryPage + 1) * size)) {
      const row = element("tr"), first = element("td");
      first.append(element("code", v.name));
      if (v.label && v.label !== v.description) first.append(element("strong", v.label + ". "));
      first.append(element("span", v.description || v.label, "gis-definition"));
      if (v.quality_note) first.append(element("span", v.quality_note, "gis-dictionary-source"));
      const source = element("td", v.coverage || "See source metadata");
      source.append(element("span", v.source || v.group, "gis-dictionary-source"));
      if (/^[a-zA-Z0-9_.-]+\.csv$/.test(v.public_file)) {
        const link = element("a", v.public_file.includes("climate") ? "Climate table (CSV)" : "Core table (CSV)", "gis-dictionary-source");
        link.href = assetURL("data/" + v.public_file); link.title = v.public_file; link.setAttribute("download", ""); source.append(link);
      }
      row.append(first, element("td", v.period || "Source-specific"), element("td", v.unit || "—"), source); body.append(row);
    }
    if (!count) { const row = element("tr"), cell = element("td", "No definitions match this search.", "gis-empty"); cell.colSpan = 4; row.append(cell); body.append(row); }
    $("gis-dictionary-count").textContent = `${count.toLocaleString("en-GB")} matching fields of ${state.dictionary.length.toLocaleString("en-GB")} in this dictionary.`;
    $("gis-dictionary-page").textContent = `${state.dictionaryPage + 1} / ${pages}`;
    $("gis-dictionary-prev").disabled = state.dictionaryPage === 0; $("gis-dictionary-next").disabled = state.dictionaryPage >= pages - 1;
    $("gis-dictionary-csv").disabled = count === 0;
    $("gis-dictionary-table").parentElement.scrollTop = 0;
  }
  function setupModules(data) {
    const modules = items(data, ["modules", "items"]);
    if (!modules.length) throw new Error("No module inventory supplied");
    const grid = $("gis-module-grid"); grid.replaceChildren();
    const categories = new Set(["historical", "derived", "context"]);
    root.querySelector(".gis-time-key").hidden = !modules.some(m => categories.has(text(m.kind || m.type || m.temporal_type)));
    for (const m of modules) {
      const category = text(m.kind || m.type || m.temporal_type);
      const card = element("article", null, "gis-module-card " + (categories.has(category) ? category : "unclassified"));
      card.append(element("span", m.period || "Source-specific period", "gis-module-period"), element("h3", m.name || m.title), element("p", m.description));
      if (m.coverage) card.append(element("p", m.coverage, "gis-module-coverage"));
      if (m.status) card.append(element("p", m.status, "gis-module-source"));
      if (m.source) card.append(element("p", "Source: " + sourceText(m.source), "gis-module-source"));
      grid.append(card);
    }
  }
  function setupGallery(data) {
    state.gallery = items(data, ["items", "maps", "figures", "gallery"]);
    if (!state.gallery.length) throw new Error("No atlas catalogue supplied");
    const groups = [...new Set(state.gallery.map(x => x.group || "Other maps"))];
    const filters = $("gis-gallery-filters"); filters.replaceChildren();
    for (const [value, label] of [["all", "All maps"], ...groups.map(g => [g, g])]) {
      const button = element("button", label); button.type = "button"; button.dataset.group = value; button.setAttribute("aria-pressed", String(value === "all"));
      button.addEventListener("click", () => {
        state.galleryGroup = value; state.galleryVisible = 9;
        [...filters.children].forEach(b => b.setAttribute("aria-pressed", String(b.dataset.group === value)));
        renderGallery();
      }); filters.append(button);
    }
    $("gis-gallery-search").addEventListener("input", () => { state.galleryVisible = 9; renderGallery(); });
    $("gis-gallery-more").addEventListener("click", () => { state.galleryVisible += 9; renderGallery(); });
    $("gis-lightbox-close").addEventListener("click", closeLightbox);
    $("gis-lightbox").addEventListener("click", event => { if (event.target === $("gis-lightbox")) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) closeLightbox(); } });
    $("gis-lightbox").addEventListener("close", () => { state.lastGalleryButton?.focus(); });
    $("gis-lightbox").addEventListener("keydown", event => {
      if (event.key === "ArrowRight") { event.preventDefault(); openLightbox((state.lightboxIndex + 1) % state.galleryFiltered.length); }
      if (event.key === "ArrowLeft") { event.preventDefault(); openLightbox((state.lightboxIndex - 1 + state.galleryFiltered.length) % state.galleryFiltered.length); }
    });
    $("gis-lightbox-prev").addEventListener("click", () => openLightbox((state.lightboxIndex - 1 + state.galleryFiltered.length) % state.galleryFiltered.length));
    $("gis-lightbox-next").addEventListener("click", () => openLightbox((state.lightboxIndex + 1) % state.galleryFiltered.length));
    renderGallery();
  }
  function renderGallery() {
    const query = normal($("gis-gallery-search").value);
    state.galleryFiltered = state.gallery.filter(g => (state.galleryGroup === "all" || (g.group || "Other maps") === state.galleryGroup)
      && normal([g.title, g.group, g.period, g.summary, g.warning].map(text).join(" ")).includes(query));
    const grid = $("gis-gallery"); grid.replaceChildren();
    state.galleryFiltered.slice(0, state.galleryVisible).forEach((g, index) => {
      const card = element("article", null, "gis-gallery-card"), button = element("button", null, "gis-gallery-image"); button.type = "button";
      button.setAttribute("aria-label", `Open map: ${g.title}`);
      const img = element("img"); img.src = assetURL(g.thumbnail || g.image); img.alt = g.title || "Historical district map"; img.loading = "lazy"; img.decoding = "async"; img.width = 650; img.height = 400;
      button.append(img); button.addEventListener("click", () => { state.lastGalleryButton = button; openLightbox(index); });
      const copy = element("div", null, "gis-gallery-copy");
      copy.append(element("p", [g.group, g.period].filter(Boolean).join(" · "), "gis-eyebrow"), element("h3", g.title), element("p", g.summary));
      card.append(button, copy); grid.append(card);
    });
    const count = state.galleryFiltered.length, shown = Math.min(state.galleryVisible, count);
    $("gis-gallery-count").textContent = `Showing ${shown} of ${count} matching figures · ${state.gallery.length} figures in the complete gallery.`;
    $("gis-gallery-more").hidden = shown >= count;
    if (!count) grid.append(element("p", "No maps match this topic. Try another search or choose All maps.", "gis-empty"));
  }
  function openLightbox(index) {
    const g = state.galleryFiltered[index]; if (!g) return;
    state.lightboxIndex = index;
    $("gis-lightbox-title").textContent = g.title; $("gis-lightbox-period").textContent = [g.group, g.period].filter(Boolean).join(" · ");
    $("gis-lightbox-image").src = assetURL(g.image); $("gis-lightbox-image").alt = g.title + (g.period ? ", " + g.period : "");
    $("gis-lightbox-description").textContent = text(g.summary);
    $("gis-lightbox-source").textContent = g.source ? "Source: " + sourceText(g.source) : "Source, scale and method are printed in the original atlas figure.";
    $("gis-lightbox-warning").textContent = text(g.warning); $("gis-lightbox-warning").hidden = !g.warning;
    $("gis-lightbox-download").href = assetURL(g.image);
    $("gis-lightbox-prev").disabled = state.galleryFiltered.length < 2; $("gis-lightbox-next").disabled = state.galleryFiltered.length < 2;
    if (!$("gis-lightbox").open) {
      if (typeof $("gis-lightbox").showModal === "function") $("gis-lightbox").showModal();
      else window.open(assetURL(g.image), "_blank", "noopener");
    }
  }
  function closeLightbox() { $("gis-lightbox").close(); }
  function sizeLabel(bytes) {
    return !finite(bytes) ? "" : bytes >= 1000000 ? `${new Intl.NumberFormat("en-GB", {maximumFractionDigits: 1}).format(bytes / 1000000)} MB`
      : `${Math.max(1, Math.round(bytes / 1000))} kB`;
  }
  function setupDownloads(data) {
    const downloads = items(data, ["items", "downloads", "files"]);
    if (!downloads.length) throw new Error("No download catalogue supplied");
    const container = $("gis-downloads"); container.replaceChildren();
    downloads.forEach((d, index) => {
      const row = element("div", null, "gis-download-row"), copy = element("div");
      copy.append(element("h3", d.title || d.name), element("p", d.description));
      const meta = element("div", null, "gis-download-meta");
      for (const value of [d.format, sizeLabel(d.size_bytes), d.license, d.status]) if (value) meta.append(element("span", value));
      copy.append(meta); row.append(copy);
      if (d.url && d.available !== false) {
        const actions = element("div", null, "gis-download-actions"), link = element("a", d.button_label || `Download ${d.format || "file"} ↓`, "gis-button" + (d.primary || index === 0 ? " gis-primary" : ""));
        link.href = assetURL(d.url); link.setAttribute("download", ""); actions.append(link); row.append(actions);
      }
      container.append(row);
    });
    if (data.r_example) $("gis-r-example").querySelector("code").textContent = data.r_example;
    if (data.citation) $("gis-citation-text").textContent = data.citation;
  }
  function setupSources(data) {
    const sources = items(data, ["sources", "items"]);
    if (!sources.length) return;
    const container = $("gis-source-register"); container.replaceChildren();
    for (const s of sources) {
      const article = element("article"), heading = element("h4");
      if (s.url) {
        const link = element("a", s.name); link.href = assetURL(s.url); link.target = "_blank"; link.rel = "noopener"; heading.append(link);
      } else heading.textContent = s.name;
      article.append(heading);
      if (s.description) article.append(element("p", s.description));
      if (s.citation) article.append(element("p", "Citation: " + s.citation));
      if (s.period) article.append(element("p", "Period: " + s.period));
      if (s.terms) article.append(element("p", "Source terms: " + s.terms, "gis-source-terms"));
      if (s.redistribution) article.append(element("p", s.redistribution));
      if (s.license_url) {
        const p = element("p"), link = element("a", "Provider terms and licence ↗"); link.href = assetURL(s.license_url); link.target = "_blank"; link.rel = "noopener"; p.append(link); article.append(p);
      }
      container.append(article);
    }
  }
  function safeName(value) { return normal(value).replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, ""); }
  function csvCell(value) {
    const s = value == null ? "" : String(value);
    return /[",\r\n]/.test(s) ? '"' + s.replaceAll('"', '""') + '"' : s;
  }
  function downloadCSV(name, rows) { downloadBlob(name, "\ufeff" + rows.map(row => row.map(csvCell).join(",")).join("\r\n"), "text/csv;charset=utf-8"); }
  function downloadBlob(name, content, type) {
    const url = URL.createObjectURL(new Blob([content], {type})), a = element("a");
    a.href = url; a.download = name; a.style.display = "none"; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1500);
  }
  function exportMapCSV() {
    const m = state.metric;
    const rows = [["district_year_id", "district_name", "boundary_year", "field", "observation_period", "value", "unit", "source", "source_terms", "quality_note"]];
    state.explorer.districts.forEach(d => rows.push([d.id, d.name, 1930, m.key, metricPeriod(m), metricValue(d, m), m.unit, sourceText(m.source), text(m.license || "Source-specific terms; see publication source register"), [m.quality_note, ...districtNotes(d)].filter(Boolean).join("; ")]));
    downloadCSV(`historical_gis_${safeName(m.key)}_${safeName(metricPeriod(m))}.csv`, rows);
  }
  function exportDistrictCSV() {
    const d = state.selected, rows = [["district_year_id", "district_name", "boundary_year", "field", "label", "observation_period", "value", "unit", "source", "source_terms", "quality_note"]];
    state.metrics.forEach(m => rows.push([d.id, d.name, 1930, m.key, m.label, metricPeriod(m), metricValue(d, m), m.unit, sourceText(m.source), text(m.license || "Source-specific terms; see publication source register"), [m.quality_note, ...districtNotes(d)].filter(Boolean).join("; ")]));
    downloadCSV(`historical_gis_profile_${safeName(d.name)}.csv`, rows);
  }
  function exportClimateCSV() {
    const m = state.annualMetric, rows = [["geography", "district_year_id", "district_name", "boundary_year", "calendar_year", "field", "value", "unit", "source", "source_terms"]];
    for (const series of annualSeries()) state.explorer.annual.years.forEach((year, i) => rows.push(["judicial_1930", series.district.id, series.district.name, 1930, year, m.key, finite(series.values[i]) ? series.values[i] : null, m.unit, sourceText(m.source || "CRU-TS v4.10 · University of East Anglia"), text(m.license || "Open Database License (ODbL) 1.0 and Database Contents License")]));
    downloadCSV(`historical_gis_climate_${safeName(m.key)}.csv`, rows);
  }
  function wrapSVGText(svg, value, x, y, maxLength = 125, color = "#53636b", size = 12) {
    const words = text(value).split(/\s+/), lines = []; let line = "";
    for (const word of words) { if ((line + " " + word).length > maxLength && line) { lines.push(line); line = word; } else line += (line ? " " : "") + word; }
    if (line) lines.push(line);
    lines.forEach((l, i) => svg.append(svgElement("text", {x, y: y + i * (size + 5), fill: color, "font-size": size}, l)));
    return lines.length * (size + 5);
  }
  function exportSVG(type) {
    const isMap = type === "map", original = $(isMap ? "gis-map-svg-element" : "gis-climate-svg-element");
    if (!original) return;
    const width = 1100;
    let height = isMap ? 885 : 675;
    const out = svgElement("svg", {xmlns: NS, width, height, viewBox: `0 0 ${width} ${height}`, "font-family": "Segoe UI, Helvetica, Arial, sans-serif"});
    out.append(svgElement("rect", {width, height, fill: "white"}));
    wrapSVGText(out, "CZECH LANDS HISTORICAL GIS · PUBLIC EDITION 0.6.1", 35, 30, 125, "#7a2e34", 12);
    wrapSVGText(out, isMap ? state.metric.label : $("gis-climate-title").textContent, 35, 65, 100, "#162b36", 22);
    wrapSVGText(out, isMap ? `${metricPeriod(state.metric)} · ${state.metric.unit || ""} · Judicial districts 1930` : `${state.explorer.annual.years[0]}–${state.explorer.annual.years.at(-1)} · ${state.annualMetric.unit || ""} · Fixed district boundaries 1930`, 35, 94, 125, "#53636b", 13);
    const clone = original.cloneNode(true); clone.removeAttribute("id"); clone.setAttribute("x", "25"); clone.setAttribute("y", "115"); clone.setAttribute("width", "1050"); clone.setAttribute("height", isMap ? "600" : "380");
    clone.querySelectorAll("[tabindex], [role]").forEach(e => { e.removeAttribute("tabindex"); e.removeAttribute("role"); });
    clone.querySelectorAll(".gis-district-shape").forEach(p => { p.setAttribute("stroke", "white"); p.setAttribute("stroke-width", ".6"); p.setAttribute("vector-effect", "non-scaling-stroke"); });
    clone.querySelectorAll(".gis-selected-outline").forEach(p => { p.setAttribute("fill", "none"); p.setAttribute("stroke", "#12364c"); p.setAttribute("stroke-width", "2"); p.setAttribute("vector-effect", "non-scaling-stroke"); });
    out.append(clone);
    let footY = isMap ? 745 : 525;
    if (isMap) {
      const scale = makeScale(state.metric), bounds = [scale.min, ...scale.thresholds, scale.max];
      scale.colors.forEach((c, i) => {
        const x = 35 + i * 175; out.append(svgElement("rect", {x, y: footY - 10, width: 22, height: 12, fill: c}));
        out.append(svgElement("text", {x: x + 29, y: footY, "font-size": 12, fill: "#53636b"}, `${formatNumber(bounds[i], state.metric)}–${formatNumber(bounds[i + 1], state.metric)}`));
      });
      out.append(svgElement("rect", {x: 920, y: footY - 10, width: 22, height: 12, fill: "#d1d4d5"}), svgElement("text", {x: 949, y: footY, "font-size": 12, fill: "#53636b"}, "Unavailable"));
      footY += 29;
      footY += wrapSVGText(out, `Classification: ${state.classification === "quantile" ? "quantiles of available districts" : "equal value intervals"}. Selected district: ${state.selected.name}. ${state.metric.quality_note || ""}`, 35, footY, 150);
    } else {
      for (const s of annualSeries()) { out.append(svgElement("line", {x1: 35, x2: 57, y1: footY - 4, y2: footY - 4, stroke: s.color, "stroke-width": 3})); out.append(svgElement("text", {x: 66, y: footY, "font-size": 13, fill: "#162b36"}, s.district.name)); footY += 22; }
    }
    footY += 6 + wrapSVGText(out, "Source: " + (isMap ? sourceText(state.metric.source) : sourceText(state.annualMetric.source || "CRU-TS v4.10 · University of East Anglia")), 35, footY + 6, 150);
    height = Math.max(height, footY + 52);
    out.setAttribute("height", height); out.setAttribute("viewBox", `0 0 ${width} ${height}`); out.firstElementChild.setAttribute("height", height);
    out.append(svgElement("text", {x: 35, y: height - 22, "font-size": 11, fill: "#53636b"}, "Adam Dittrich · https://adamdittrich.github.io/czech-lands-historical-gis.html · Source-specific terms apply"));
    downloadBlob(`historical_gis_${isMap ? safeName(state.metric.key) : "climate_" + safeName(state.annualMetric.key)}.svg`, new XMLSerializer().serializeToString(out), "image/svg+xml;charset=utf-8");
  }
  $("gis-map-csv").addEventListener("click", exportMapCSV);
  $("gis-district-csv").addEventListener("click", exportDistrictCSV);
  $("gis-climate-csv").addEventListener("click", exportClimateCSV);
  $("gis-map-svg").addEventListener("click", () => exportSVG("map"));
  $("gis-climate-svg").addEventListener("click", () => exportSVG("climate"));
  $("gis-dictionary-csv").addEventListener("click", () => {
    const keys = ["name", "label", "group", "period", "unit", "description", "coverage", "source", "quality_note", "public_file"];
    downloadCSV("historical_gis_variable_definitions.csv", [keys, ...state.dictionaryFiltered.map(v => keys.map(k => v[k]))]);
  });
  root.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
    const target = $(button.dataset.copy), content = target.innerText;
    try {
      await navigator.clipboard.writeText(content);
      const previous = button.textContent; button.textContent = "Copied";
      $("gis-copy-status").textContent = "Copied to clipboard."; setTimeout(() => { button.textContent = previous; }, 1800);
    } catch (_) {
      const selection = window.getSelection(), range = document.createRange(); range.selectNodeContents(target); selection.removeAllRanges(); selection.addRange(range);
      $("gis-copy-status").textContent = "Text selected. Press Ctrl+C or Command+C to copy.";
    }
  }));
  const tasks = [
    ["explorer.json", setupExplorer, error => {
      $("gis-map-description").textContent = "The interactive data could not be loaded. The static preview remains available; use the download section for the full files.";
      $("gis-map-canvas").setAttribute("aria-busy", "false"); $("gis-map-status").textContent = "Interactive map unavailable.";
      $("gis-climate-plot").replaceChildren(element("p", "The annual chart could not be loaded. Annual and monthly files are available in the downloads.", "gis-empty")); $("gis-climate-plot").setAttribute("aria-busy", "false"); console.warn("Historical GIS explorer:", error.message);
    }],
    ["dictionary.json", setupDictionary, () => { $("gis-dictionary-count").textContent = "The browser dictionary could not be loaded. Definitions are also included in the downloadable edition."; }],
    ["gallery.json", setupGallery, () => { $("gis-gallery-count").textContent = "The map catalogue could not be loaded. The atlas files are available in the downloads."; }],
    ["downloads.json", setupDownloads, () => {}],
    ["module_inventory.json", setupModules, () => {}],
    ["sources.json", setupSources, () => {}]
  ];
  Promise.allSettled(tasks.map(async ([file, setup, fail]) => {
    try { setup(await (file === "explorer.json" ? loadExplorer() : loadJSON(file))); } catch (error) { fail(error); }
  }));
})();
