"use strict";
// All page text is built with textContent / createElement. Job data comes from other websites,
// so it is never inserted as HTML.

const state = { jobs: [], health: [], meta: {}, tab: "Match", marks: {} };
const $ = (id) => document.getElementById(id);

function loadMarks() {
  try { state.marks = JSON.parse(localStorage.getItem("imjobs.marks") || "{}"); } catch (e) { state.marks = {}; }
}
function saveMarks() {
  try { localStorage.setItem("imjobs.marks", JSON.stringify(state.marks)); } catch (e) { /* storage unavailable */ }
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}

function safeUrl(u) {
  try {
    const x = new URL(u);
    return x.protocol === "https:" || x.protocol === "http:" ? x.href : "#";
  } catch (e) { return "#"; }
}

function daysBetween(a, b) {
  return Math.round((new Date(b + "T00:00:00Z") - new Date(a + "T00:00:00Z")) / 86400000);
}

function schoolLabel(rank, name) {
  return Number(rank) <= 50 ? `#${rank} ${name}` : `${name} (added)`;
}

function divisionOf(j) {
  return (j.ai && j.ai.im_division) ? prettyDiv(j.ai.im_division) : (j.rules ? j.rules.division : "");
}
function prettyDiv(d) {
  if (d === "not_internal_medicine") return "Not Internal Medicine";
  if (d === "unclear") return "Unclear";
  return d;
}

async function getJson(path) {
  const r = await fetch(path + "?v=" + Date.now(), { cache: "no-store" });
  if (!r.ok) throw new Error(path + " HTTP " + r.status);
  return r.json();
}

async function init() {
  loadMarks();
  try {
    const [jobs, health] = await Promise.all([getJson("data/jobs.json"), getJson("data/health.json")]);
    state.meta = jobs.meta || {};
    state.jobs = Object.values(jobs.jobs || {});
    state.health = health.sources || [];
  } catch (e) {
    $("meta").textContent = "No data yet. The first daily run has not finished, or the data files are missing.";
    return;
  }
  const m = state.meta;
  $("meta").textContent = `Updated ${m.generated_utc || "?"} · ${state.jobs.length} postings tracked · AI classifier ${m.ai_enabled ? "on" : "off (keyword rules only)"}`;

  const schools = [...new Set(state.jobs.map((j) => `${String(j.rank).padStart(2, "0")}|${j.school}`))].sort();
  for (const s of schools) {
    const [, name] = s.split("|");
    const o = el("option", null, name); o.value = name; $("school").append(o);
  }
  const divs = [...new Set(state.jobs.map(divisionOf).filter(Boolean))].sort();
  for (const d of divs) { const o = el("option", null, d); o.value = d; $("division").append(o); }

  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    state.tab = b.dataset.tab;
    document.querySelectorAll(".tabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    render();
  }));
  ["q", "school", "division", "since", "showHidden", "activeOnly"].forEach((id) =>
    $(id).addEventListener("input", render));
  render();
}

function filtered() {
  const q = $("q").value.trim().toLowerCase();
  const school = $("school").value, div = $("division").value, since = $("since").value;
  const showHidden = $("showHidden").checked, activeOnly = $("activeOnly").checked;
  const today = state.meta.today;
  return state.jobs.filter((j) => {
    if (!showHidden && state.marks[j.key] === "hidden") return false;
    if (activeOnly && !j.active) return false;
    if (school && j.school !== school) return false;
    if (div && divisionOf(j) !== div) return false;
    if (since && today && daysBetween(j.first_seen, today) >= Number(since)) return false;
    if (q) {
      const hay = [j.title, j.department, j.school, j.snippet, j.reason].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function render() {
  const all = filtered();
  document.querySelectorAll("[data-count]").forEach((c) => {
    c.textContent = all.filter((j) => j.verdict === c.dataset.count).length;
  });
  const list = $("list"), sources = $("sources");
  list.replaceChildren(); sources.replaceChildren();
  if (state.tab === "Sources") {
    $("filters").hidden = true; list.hidden = true; sources.hidden = false; $("hint").textContent = "";
    renderSources(sources);
    return;
  }
  $("filters").hidden = false; list.hidden = false; sources.hidden = true;
  const conf = (j) => ({ high: 0, medium: 1, low: 2 }[(j.ai || {}).confidence] ?? 3);
  const due = (j) => ((j.ai || {}).deadline && (j.ai || {}).deadline >= (state.meta.today || "")) ? j.ai.deadline : "9999";
  const rows = all.filter((j) => j.verdict === state.tab)
    .sort((a, b) => conf(a) - conf(b) || due(a).localeCompare(due(b))
      || (b.posted || b.first_seen || "").localeCompare(a.posted || a.first_seen || "") || (a.rank - b.rank));
  const hints = {
    "Match": "Clinical or dry research in Internal Medicine that the profile appears eligible for. Most certain first.",
    "Stretch": "Dry research in Internal Medicine, but a required skill is not in the profile (for example omics or machine learning).",
    "Title only": "Only the title could be read, and no readable copy of the posting was found on the web. Open the posting to read it.",
    "Below level": "Research assistant, coordinator or outreach jobs below research fellow level.",
    "Check": "The AI could not decide even on a second look and, where a PI or lab is named, a web lookup of the lab (usually because the posting says almost nothing). Open the posting to decide.",
    "Other dept": "Clinical or dry research outside Internal Medicine (for example epidemiology or pediatrics).",
    "Excluded": "Wet-lab work, citizenship requirement, no visa sponsorship, or a PhD-only requirement.",
  };
  $("hint").textContent = `${rows.length} shown. ${hints[state.tab] || ""}`;
  for (const j of rows) {
    try { list.append(card(j)); } catch (e) {
      const li = el("li", "card"); li.append(el("p", "warn", "This posting could not be displayed: " + String(j.title || j.key)));
      list.append(li);
    }
  }
}

function card(j) {
  const li = el("li", "card" + (state.marks[j.key] === "applied" ? " applied" : ""));
  const head = el("div", "head");
  const a = el("a", "title", j.title); a.href = safeUrl(j.url); a.target = "_blank"; a.rel = "noopener noreferrer";
  head.append(a);
  if (j.first_seen === state.meta.today) head.append(el("span", "badge new", "New today"));
  const dl = (j.ai || {}).deadline;
  if (dl && state.meta.today && dl >= state.meta.today) {
    const left = daysBetween(state.meta.today, dl);
    head.append(el("span", "badge " + (left <= 7 ? "warnb" : "ok"), `closes ${dl} (${left} day${left === 1 ? "" : "s"})`));
  }
  if (state.marks[j.key] === "applied") head.append(el("span", "badge done", "Applied"));
  li.append(head);

  const facts = el("p", "facts");
  facts.textContent = [
    schoolLabel(j.rank, j.school), j.source_label !== j.school ? j.source_label : null,
    j.department || null, divisionOf(j), j.location || null,
    j.posted ? `posted ${j.posted}` : null, `first seen ${j.first_seen}`,
  ].filter(Boolean).join(" · ");
  li.append(facts);

  li.append(el("p", "reason", j.reason || ""));
  const aiv = j.ai || {};
  if (aiv.verify) li.append(el("p", "verify", "Verify: " + String(aiv.verify)));
  if (aiv.missing) li.append(el("p", "verify", "Not in profile: " + String(aiv.missing)));
  const cp = j.copy || null;
  if (cp && cp.url) {
    const p = el("p", "lab", `Read from a ${cp.kind === "primary" ? "primary copy (employer's own page)" : "secondary copy (job board)"}, matched by ${cp.match === "job_id" ? "job ID" : "title and department"}: `);
    const u = safeUrl(cp.url);
    if (u !== "#") {
      const la = el("a", "src", String(cp.title || u).slice(0, 80)); la.href = u; la.target = "_blank"; la.rel = "noopener noreferrer";
      p.append(la);
    }
    li.append(p);
  }
  const lab = j.lookup || {};
  if (lab.lab_summary || (lab.lab_sources || []).length) {
    const p = el("p", "lab", `Lab check${lab.pi ? " (" + String(lab.pi) + ")" : ""}: ${String(lab.lab_summary || "no lab details found")}`);
    for (const src of (lab.lab_sources || []).slice(0, 3)) {
      const u = safeUrl(src.url);
      if (!u || u === "#") continue;
      p.append(" ");
      const la = el("a", "src", "[" + (String(src.title || "").slice(0, 60) || "source") + "]");
      la.href = u; la.target = "_blank"; la.rel = "noopener noreferrer";
      p.append(la);
    }
    li.append(p);
  }

  const tags = el("p", "tags");
  const ai = j.ai || {};
  const add = (t, cls) => tags.append(el("span", "tag " + (cls || ""), t));
  const s = (x) => String(x == null ? "" : x);
  if (ai.confidence) add(s(ai.confidence) + " confidence", ai.confidence === "low" ? "warn" : "");
  if (ai.skills_fit) add("skills fit: " + s(ai.skills_fit), ai.skills_fit === "weak" ? "warn" : "");
  if (j.reviewed_by) add("re-checked by " + s(j.reviewed_by));
  if (j.lookup && j.lookup.by) add("lab looked up by " + s(j.lookup.by));
  if (ai.role_type) add(s(ai.role_type).replace(/_/g, " "));
  if (ai.mbbs_without_phd_eligible) add("MBBS eligible: " + s(ai.mbbs_without_phd_eligible), ai.mbbs_without_phd_eligible === "no" ? "warn" : "");
  if (ai.visa) add("visa: " + s(ai.visa).replace(/_/g, " "), /no_|citizen/.test(s(ai.visa)) ? "warn" : "");
  for (const n of (j.rules && j.rules.notes) || []) add(n, /sponsorship mentioned/i.test(n) ? "" : "warn");
  if (tags.childNodes.length) li.append(tags);

  const det = el("details");
  det.append(el("summary", null, "Excerpt and rule signals"));
  det.append(el("p", "snippet", j.snippet || "(no text captured)"));
  if (cp && cp.excerpt) det.append(el("p", "snippet", "Copy: " + String(cp.excerpt)));
  if (j.ai_before_find && j.ai_before_find.verdict) {
    det.append(el("p", "signals", `Before reading the copy: ${s(j.ai_before_find.verdict).replace(/_/g, " ")}. ${s(j.ai_before_find.reason)}`));
  }
  if (j.ai_before_lookup && j.ai_before_lookup.verdict) {
    det.append(el("p", "signals", `Before lab lookup: ${s(j.ai_before_lookup.verdict).replace(/_/g, " ")}. ${s(j.ai_before_lookup.reason)}`));
  }
  if (j.ai_first && j.ai_first.verdict) {
    det.append(el("p", "signals", `First pass: ${s(j.ai_first.verdict).replace(/_/g, " ")}. ${s(j.ai_first.reason)}`));
  }
  const r = j.rules || {};
  det.append(el("p", "signals", `Rules: ${r.research_type || "?"}; wet-lab terms: ${(r.wet_terms || []).join(", ") || "none"}; clinical terms: ${(r.dry_terms || []).join(", ") || "none"}`));
  li.append(det);

  const actions = el("div", "actions");
  const mk = (label, val) => {
    const b = el("button", null, state.marks[j.key] === val ? `Undo ${label.toLowerCase()}` : label);
    b.type = "button";
    b.addEventListener("click", () => {
      if (state.marks[j.key] === val) delete state.marks[j.key]; else state.marks[j.key] = val;
      saveMarks(); render();
    });
    return b;
  };
  actions.append(mk("Applied", "applied"), mk("Hide", "hidden"));
  li.append(actions);
  return li;
}

function renderSources(root) {
  root.append(el("p", "hint", "Status of each careers site in the latest run. Manual sources cannot be read automatically: check them by hand."));
  const ol = el("ol", "list");
  for (const h of state.health) {
    const li = el("li", "card src " + (h.status || ""));
    const head = el("div", "head");
    head.append(el("strong", null, schoolLabel(h.rank, h.school)), el("span", "badge " + (h.status === "ok" ? "ok" : "warnb"), h.status));
    li.append(head);
    li.append(el("p", "facts", `${h.label} · ${h.type}`));
    if (h.status === "ok") li.append(el("p", null, `Postings returned: ${h.found} · matching titles in the last 21 days: ${h.candidates} · older, skipped: ${h.too_old || 0} · newly read today: ${h.new_details}` + (h.detail_errors ? ` · pages that failed to load: ${h.detail_errors}` : "")));
    if (h.error) li.append(el("p", "warn", h.error));
    if (h.note) li.append(el("p", null, h.note));
    if (h.url) { const a = el("a", null, "Open the job board"); a.href = safeUrl(h.url); a.target = "_blank"; a.rel = "noopener noreferrer"; li.append(a); }
    ol.append(li);
  }
  root.append(ol);
  if ((state.meta.log || []).length) {
    root.append(el("h2", null, "Run notes"));
    const ul = el("ul");
    for (const l of state.meta.log) ul.append(el("li", null, l));
    root.append(ul);
  }
}

init();
