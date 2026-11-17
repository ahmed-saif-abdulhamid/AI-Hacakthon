/* ProveIt console. Plain JavaScript, no build step. Uses the browser's speechSynthesis and
   SpeechRecognition, WebAudio (AnalyserNode.getByteFrequencyData) for the voice visual, and the
   local Piper voice through /api/voice/speak when it is installed. */
"use strict";
(() => {
const CFG = window.PROVEIT || {};
const API = CFG.api || "";
const DEMO = !!CFG.demo;
const NAME = CFG.assistant || "J.A.R.V.I.S.";
const WAKE_WORD = CFG.wake || "Jarvis";
const PHASES = ["Discover", "Validate", "Build", "Price and policies", "Sell and deliver", "Learn"];
const OUT = {go: "Go.", stop: "Stop.", repeat: "Look again.", pivot: "Try another angle."};
const OUT_SHORT = {go: "Go", stop: "Stop", repeat: "Look again", pivot: "Another angle"};
const DECEPTION = /fake_social_proof|fake_signups|urgency|income_promise|impersonation|credentials|bypass|arabic_intent|output_/;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const human = s => String(s || "").replace(/_/g, " ");
const plural = (n, one, many) => `${n} ${Number(n) === 1 ? one : (many || one + "s")}`;
const S = {mode: CFG.mode || "tactical", run: null, seq: 0, view: null, voice: true, history: [], tab: "evidence",
           showZero: false, runs: [], showAll: false, keys: {}, fails: 0, pollTimer: null, theme: "system",
           lastAsk: "", asking: false, wake: false, state: "idle"};

/* ---------- small utilities ---------- */
async function api(path, opts = {}, timeoutMs = 20000) {
  const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(API + path, Object.assign({headers: {"Content-Type": "application/json"}, signal: ctrl.signal}, opts));
    const ct = r.headers.get("content-type") || "";
    const body = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok) throw Object.assign(new Error((body && (body.error || body.detail)) || ("HTTP " + r.status)), {status: r.status, body});
    return body;
  } finally { clearTimeout(t); }
}
function announce(text, assertive) { const el = $(assertive ? "sr-alert" : "sr-live"); el.textContent = ""; setTimeout(() => { el.textContent = text; }, 60); }
const RTF = (typeof Intl !== "undefined" && Intl.RelativeTimeFormat) ? new Intl.RelativeTimeFormat("en-GB", {numeric: "auto"}) : null;
function ago(ts) {
  const t = Date.parse(ts); if (!t) return "";
  const s = Math.round((t - Date.now()) / 1000), a = Math.abs(s);
  if (!RTF) return new Date(t).toLocaleString();
  if (a < 60) return RTF.format(Math.round(s), "second");
  if (a < 3600) return RTF.format(Math.round(s / 60), "minute");
  if (a < 86400) return RTF.format(Math.round(s / 3600), "hour");
  return RTF.format(Math.round(s / 86400), "day");
}
function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn._label = btn.innerHTML; btn.setAttribute("aria-busy", "true"); btn.disabled = true; btn.innerHTML = `<span class="spin" aria-hidden="true"></span>${esc(label || "Working…")}`; }
  else { btn.removeAttribute("aria-busy"); btn.disabled = false; if (btn._label) btn.innerHTML = btn._label; }
}
function setOnce(id, key, html) {          // only touch the DOM when that section really changed
  if (S.keys[id] === key) return false;
  S.keys[id] = key; $(id).innerHTML = html; return true;
}

/* ---------- layout: modes, theme, drawer, dialogs ---------- */
function setMode(m) {
  if (!["tactical", "hud", "dual"].includes(m)) m = "tactical";
  S.mode = m;
  const st = $("stage");
  $("workspace").hidden = m === "hud";
  $("voicepanel").hidden = m === "tactical";
  st.classList.toggle("dual", m === "dual");
  st.classList.toggle("voiceonly", m === "hud");
  document.querySelectorAll(".seg [data-mode]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === m)));
  try { localStorage.setItem("proveit_mode", m); } catch (e) {}
  requestAnimationFrame(resizeOrb);
  renderVoiceVerdict();
}
function cycleTheme() {
  const order = ["system", "light", "dark"]; S.theme = order[(order.indexOf(S.theme) + 1) % 3];
  if (S.theme === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = S.theme;
  try { S.theme === "system" ? localStorage.removeItem("proveit_theme") : localStorage.setItem("proveit_theme", S.theme); } catch (e) {}
  $("themebtn").textContent = "Theme: " + S.theme;
}
function toggleVoice() {
  S.voice = !S.voice; const b = $("voiceToggle"); b.setAttribute("aria-pressed", String(S.voice));
  b.querySelector("[aria-hidden]").textContent = S.voice ? "🔊" : "🔇";
  b.title = S.voice ? "Spoken replies are on" : "Spoken replies are off";
  if (!S.voice) { try { speechSynthesis.cancel(); } catch (e) {} stopAudio(); }
  announce(S.voice ? "Spoken replies on" : "Spoken replies off");
}
const SMALL = matchMedia("(max-width: 860px)");
function syncDrawer() { const sb = $("sidebar"); sb.inert = SMALL.matches && !sb.classList.contains("open"); }
SMALL.addEventListener("change", syncDrawer);
function openDrawer(open) {
  const sb = $("sidebar"), btn = document.querySelector("[data-act=menu]");
  const wasOpen = sb.classList.contains("open");
  sb.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); syncDrawer();
  if (!open && wasOpen && SMALL.matches) btn.focus();
  let scrim = document.querySelector(".scrim");
  if (open && !scrim) { scrim = document.createElement("div"); scrim.className = "scrim"; scrim.onclick = () => openDrawer(false); document.body.appendChild(scrim); }
  if (!open && scrim) scrim.remove();
  if (open) sb.querySelector("button, a")?.focus();
}
function openDialog(id) { const d = $(id); if (!d.open) d.showModal(); }
document.addEventListener("click", e => { const c = e.target.closest("[data-close]"); if (c) c.closest("dialog").close(); });

/* ---------- new idea ---------- */
const FIELDS = ["idea", "skills", "budget", "hours_per_week", "target_market", "values"];
const LABELS = {idea: /^(starting )?idea$/, skills: /^(founder'?s? )?skills?$/, budget: /^budget$/,
  hours_per_week: /^(available )?(time|hours?)( ?(\/|per) ?week)?$/, target_market: /^(target( market)?|market|region|audience|who it'?s for)$/, values: /^(core )?values$/};
function parseBrief(text) {
  const out = {};
  for (let line of text.split(/\r?\n/)) {
    line = line.replace(/^[\s>*\-#]+/, "").replace(/\*\*/g, "").trim();
    const m = line.match(/^([A-Za-z' \/]+?)\s*[:\-–]\s+(.+)$/); if (!m) continue;
    const label = m[1].trim().toLowerCase();
    for (const f of FIELDS) if (!out[f] && LABELS[f].test(label)) { out[f] = m[2].trim(); break; }
  }
  return out;
}
function parsePaste() {
  const t = $("paste").value; const p = parseBrief(t);
  for (const f of FIELDS) if (p[f]) $("f-" + f).value = p[f];
  if (!p.idea && t.trim()) $("f-idea").value = t.trim();
  announce("Brief read into the fields");
}
async function loadPreset(name) {
  try { const r = await api("/api/presets/" + name); $("paste").value = r.text; parsePaste(); $("f-idea").focus(); }
  catch (e) { showAnswer("I couldn't load that example: " + e.message, "err"); }
}
function openNew() {
  if (DEMO) { showAnswer("This online demo only shows saved results. To test your own idea, run ProveIt on your own computer: clone the repository, add a free NVIDIA key and run docker compose up.", "plain"); return; }
  openDialog("newdlg"); setTimeout(() => $("f-idea").focus(), 30);
}
async function startRun(ev) {
  ev.preventDefault();
  const idea = $("f-idea"), err = $("idea-err"), btn = $("startbtn");
  if (!idea.value.trim()) { idea.setAttribute("aria-invalid", "true"); err.hidden = false; idea.focus(); return; }
  idea.removeAttribute("aria-invalid"); err.hidden = true;
  const fields = {}; for (const f of FIELDS) fields[f] = $("f-" + f).value.trim();
  busy(btn, true, "Starting…");
  try {
    const r = await api("/api/runs", {method: "POST", body: JSON.stringify({brief_text: "", fields, mode: $("runmode").value})});
    $("newdlg").close(); $("newform").reset();
    await refreshRuns(); followRun(r.run_id); announce("Started. Looking for evidence now.");
  } catch (e) { err.textContent = e.status === 429 ? "Too many starts in a short time. Wait a few seconds." : "That didn't start: " + e.message; err.hidden = false; }
  finally { busy(btn, false); }
}

/* ---------- runs list ---------- */
function runDot(r) {
  if (r.status === "error") return "error";
  if (r.status === "running") return "running";
  return r.outcome || "";
}
async function refreshRuns() {
  let runs; try { runs = await api("/api/runs"); } catch (e) { return; }
  S.runs = runs; $("latestbtn").hidden = !runs.length;
  const groups = []; const seen = new Map();
  const visible = S.showAll ? runs : runs.filter(r => !r.calibration);
  const examples = visible.filter(r => r.example);
  for (const r of visible.filter(r => !r.example)) {                      // newest first; repeats of the same idea collapse into one row
    const key = (r.title || r.id).toLowerCase();
    if (seen.has(key)) { seen.get(key).n++; continue; }
    const g = {r, n: 1}; seen.set(key, g); groups.push(g);
  }
  const rows = S.showAll ? visible.filter(r => !r.example).map(r => ({r, n: 1})) : groups.slice(0, 8);
  $("showall").hidden = groups.length <= 8 && groups.length === visible.length - examples.length && !runs.some(r => r.calibration);
  $("showall").textContent = S.showAll ? "Show fewer" : "Show all";
  const box = $("runlist");
  if (!runs.length) { box.innerHTML = `<p class="empty" style="padding:8px 12px">No ideas tested yet.</p>`; return; }
  const item = ({r, n}) => {
    const title = r.title || "Untitled idea"; const dot = runDot(r);
    const state = r.status === "error" ? "Needs attention" : (r.status === "running" ? "Working…" : (r.outcome ? OUT_SHORT[r.outcome] || r.outcome : "Waiting for you"));
    return `<button class="runitem" type="button" data-run="${esc(r.id)}" aria-current="${r.id === S.run}" title="${esc(title)}">
      <span class="t" dir="auto">${esc(title)}</span>
      <span class="m"><i class="status-dot ${dot}" aria-hidden="true"></i>${esc(state)} · ${esc(ago(r.created_at))}${n > 1 ? `<span class="x" title="${n} attempts of this idea; the newest opens">${n} tries</span>` : ""}</span></button>`;
  };
  const html = (examples.length ? `<p class="group">Examples</p>` + examples.map(r => item({r, n: 1})).join("") + `<p class="group">Your ideas</p>` : "")
    + (rows.length ? rows.map(item).join("") : `<p class="empty" style="padding:4px 12px">None yet.</p>`);
  setOnce("runlist", html, html);
}

/* ---------- following a run ---------- */
function followRun(id, {push = true} = {}) {
  if (!id) return;
  const changed = id !== S.run;
  S.run = id; S.seq = 0; S.keys = {}; S.view = null;
  if (changed) { $("convo").innerHTML = ""; S.history = []; hideAnswer(); }
  $("viewer").innerHTML = "";
  try { localStorage.setItem("proveit_run", id); } catch (e) {}
  if (push) { const u = new URL(location.href); u.searchParams.set("run", id); history.replaceState(null, "", u); }
  $("intro").hidden = true; $("runview").hidden = false;
  setState("idle"); poll(true); refreshRuns();
  if (!DEMO) fetch(API + "/api/ask/warm", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text: "", run_id: id})}).catch(() => {});
  openDrawer(false);
}
function showWelcome() {
  S.run = null; $("intro").hidden = false; $("runview").hidden = true; $("crumb").textContent = "Welcome";
  document.title = "ProveIt: find out if anyone wants it";
  const u = new URL(location.href); u.searchParams.delete("run"); history.replaceState(null, "", u);
}

/* ---------- polling with back-off ---------- */
function schedule(ms) { clearTimeout(S.pollTimer); S.pollTimer = setTimeout(poll, ms); }
async function poll(now) {
  if (document.hidden && !now) { schedule(4000); return; }
  if (!S.run) { schedule(4000); return; }
  try {
    const [v, tel] = await Promise.all([api("/api/runs/" + encodeURIComponent(S.run)), api(`/api/runs/${encodeURIComponent(S.run)}/telemetry?since=${S.seq}`)]);
    if (S.fails >= 2) announce("Reconnected to ProveIt.");
    S.fails = 0; $("conn").hidden = true;
    S.view = v;
    for (const t of tel) { S.seq = Math.max(S.seq, t.seq); onTelemetry(t); }
    render(v);
    schedule(isBusy(v) ? 1500 : 5000);
  } catch (e) {
    if (e.status === 404) { showWelcome(); showAnswer("That idea no longer exists here.", "plain"); return; }
    S.fails++;
    if (S.fails >= 2) $("conn").hidden = false;
    schedule(Math.min(30000, 1500 * 2 ** Math.min(S.fails, 5)));
  }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(true); });
window.addEventListener("online", () => poll(true));
window.addEventListener("offline", () => { $("conn").hidden = false; });
const isBusy = v => v && (v.working || v.status === "running");

async function sysStatus() {
  try {
    const m = await api("/api/model");
    const st = m.state || "unknown"; const dot = $("modelDot");
    const words = {ready: "AI model ready", busy: "AI model busy, retrying", unreachable: "AI model not answering",
      "missing NVIDIA_API_KEY": "Add your NVIDIA key", "not attached in this demo": "Saved results only (demo)"}[st] || ("AI model: " + st);
    $("modelState").textContent = words;
    $("modelState").title = m.model || "";
    dot.className = "status-dot " + (st === "ready" ? "ok" : (st === "busy" || st.startsWith("not attached") ? "warn" : "bad"));
  } catch (e) {}
  try {
    const v = await api("/api/voice/status"); const t = v.tts || {};
    $("voiceState").textContent = t.engine === "piper" ? "Voice: on this computer" : "Voice: browser";
    $("voiceState").title = t.engine === "piper" ? "Piper, " + (t.voice || "en-GB") : "Your browser's built-in voice";
  } catch (e) {}
}

function onTelemetry(t) {
  const fresh = Date.parse(t.ts) > Date.now() - 20000;  // never re-speak an old run's narration
  if (!fresh) return;
  if (t.kind === "narration") { addMsg("sys", t.text); say(t.text); }
  if (t.kind === "gate") {
    setState(t.text === "go" ? "go" : (t.text === "stop" ? "alert" : "hold"), "Verdict: " + (OUT_SHORT[t.text] || t.text));
    announce("Verdict: " + (OUT_SHORT[t.text] || t.text) + ".");
  }
  if (t.kind === "approval") { setState("hold", "Waiting for your approval"); announce("Something is waiting for your approval."); }
  if (t.kind === "error") { addMsg("sys", t.text); setState("alert", "Needs attention"); announce(t.text, true); }
  if (t.kind === "protocol0") setState("alert", "I couldn't help with that one");
}

/* ---------- rendering ---------- */
function verdictGate(v) { return v.gate1 || null; }
function isEligibilityStop(v) { return v.gate1 && v.gate1.gate === "phase1_eligibility"; }

function render(v) {
  const variant = (v.variants || [])[(v.variant_n || 1) - 1];
  const title = variant ? variant.title : (v.title || v.idea || "Your idea");
  $("ideaTitle").textContent = title;
  $("ideaSub").textContent = variant ? `For ${variant.segment}.${v.idea ? " Your idea: " + v.idea : ""}` : (v.idea && v.idea !== title ? v.idea : "");
  const g = v.gate1;
  const stateWord = v.status === "error" ? "Needs attention" : (isBusy(v) ? "Working…" : (g ? OUT_SHORT[g.outcome] || "" : "Waiting"));
  $("crumb").textContent = stateWord + " · started " + ago(v.created_at);
  document.title = `${isBusy(v) ? "Working… " : (g ? OUT[g.outcome] + " " : "")}${title} · ProveIt`;
  renderBanners(v); renderSteps(v); renderVerdict(v); renderDecide(v); renderNext(v); renderLater(v);
  renderEvidence(v); renderDebate(v); renderFiles(v); renderApprovals(v); renderCost(v); renderVoiceVerdict();
}

function renderBanners(v) {
  let h = "";
  if (v.status === "error") h += `<div class="banner stop" role="alert"><div><b>I had to pause.</b> ${esc(v.error_message || "The AI service returned an error. Your run is saved.")}
      ${v.error ? `<details><summary>Technical detail</summary><pre>${esc(v.error)}</pre></details>` : ""}</div>
      ${DEMO ? "" : `<button class="btn primary" type="button" data-act="retry">Try again</button>`}</div>`;
  if (v.override) h += `<div class="banner hold"><div><b>Preview only.</b> You chose to carry on even though the evidence was thin, so treat the later steps as a preview. Your note: “${esc(v.override.reason)}”</div></div>`;
  if (v.goalpost_moved) h += `<div class="banner stop"><div><b>The bar was changed after this run started.</b> Its verdict is marked as unreliable.</div></div>`;
  if (v.clarify && v.stage === "await_clarify") h += `<div class="banner hold"><div><b>Please confirm.</b> ${esc(v.clarify)}</div>${DEMO ? "" : `<button class="btn" type="button" data-decide="clarify_ok">Yes, it's a digital product with no advice</button>`}</div>`;
  if (DEMO) h += `<div class="banner info"><div><b>Online demo.</b> These are saved results from a real run. Buttons that change a run are switched off here.</div></div>`;
  setOnce("banners", h, h);
}

function renderSteps(v) {
  const stopped = v.stage === "stopped" || v.stage === "done" && false;
  const html = PHASES.map((n, i) => {
    const p = i + 1; const cls = p < v.phase ? "done" : (p === v.phase ? (v.stage === "stopped" ? "halt" : "now") : "");
    const sub = p < v.phase ? "Done" : (p === v.phase ? (v.stage === "stopped" ? "Stopped here" : (v.stage === "done" ? "Done" : "Current")) : "Not started");
    return `<li class="${cls}"${p === v.phase ? ' aria-current="step"' : ""}><b>${p}. ${n}</b>${sub}</li>`;
  }).join("");
  setOnce("steps", html, html);
  $("stepsCompact").textContent = `Step ${v.phase} of 6 · ${PHASES[v.phase - 1] || ""}${stopped ? "" : ""}`;
}

function bar(label, val, thr, max, unit, note) {
  const pass = val >= thr; const pct = Math.max(0, Math.min(100, 100 * val / max)), tp = Math.min(100, 100 * thr / max);
  const txt = `${val}${unit || ""} (needs ${thr}${unit || ""})`;
  return `<div class="bar"><div class="lbl"><strong>${label}</strong><span>${txt}</span></div>
    <div class="track ${pass ? "pass" : "fail"}" role="meter" aria-valuenow="${val}" aria-valuemin="0" aria-valuemax="${max}" aria-label="${label}" aria-valuetext="${txt}, ${pass ? "met" : "not met"}"><i style="width:${pct}%"></i><u style="left:calc(${tp}% - 1px)"></u></div>
    ${note ? `<small>${note}</small>` : ""}</div>`;
}
function counts(v) {
  const cl = (v.claims || []).filter(c => c.weight > 0);
  const by = k => cl.filter(c => c.kind === k).length;
  const comments = new Set(cl.filter(c => c.kind === "pain").map(c => c.hit_id || c.url));   // one complaint per comment, as the gate counts
  return {pain: comments.size, wtp: by("wtp"), price: by("price_point"), comp: by("competitor")};
}
function whyLine(g, m, th) {
  if (g.gate === "phase1_eligibility") return g.recommendation || "This is a kind of product ProveIt can't help build.";
  const pain = Math.round(m.sourced_pain || 0), need = th.min_sourced_pain;
  if (g.outcome === "go") return "Enough people describe this problem in their own words, from more than one place. It's worth taking to the next step.";
  if (g.reason === "model_failure" || g.reason === "model_suspect") return "My research didn't come back clean this time, so I won't base a verdict on it. Search again.";
  if (g.outcome === "repeat" && g.reason === "insufficient_evidence")
    return "I couldn't find enough people talking about this online to call it either way. That isn't proof nobody wants it: the next step is five short conversations with people who have this problem.";
  if (g.outcome === "repeat") return "It's close. A broader search could tip it either way.";
  const parts = [];
  if (pain === 0) parts.push("I didn't find anyone clearly describing this problem as a real frustration");
  else if (pain < need) parts.push(`I found ${plural(pain, "real complaint")} about this problem, and I wanted at least ${need} before saying it's worth building`);
  if (m.distinct_sources != null && th.min_distinct_sources != null && m.distinct_sources < th.min_distinct_sources && pain > 0)
    parts.push(m.distinct_sources === 1 ? "they all came from one place online" : "they came from too few places");
  if (g.outcome === "pivot") return "The problem looks real, but this version of the idea doesn't fit it well. Try another angle.";
  return (parts.length ? parts.join(", and ") + ". " : "") + "Better to know now than after months of work.";
}
function renderVerdict(v) {
  const g = v.gate1;
  if (!g || (isBusy(v) && v.stage === "phase1")) {
    const latest = v.latest || "Getting started…";
    const html = `<div class="verdict working" aria-busy="true"><div class="lead"><div class="which">First checkpoint: do people have this problem?</div>
      <p class="word">${isBusy(v) || !g ? "Looking…" : "Waiting"}</p><p class="working-lines" aria-live="polite">${esc(latest)}</p></div>
      <div class="skeleton" aria-hidden="true"><i style="width:80%"></i><i style="width:55%"></i><i style="width:92%"></i><i style="width:40%"></i></div></div>`;
    S.keys.verdict = null; $("verdict").innerHTML = html; return;
  }
  const m = v.metrics || g.metrics || {}, th = v.thresholds || g.thresholds || {};
  const elig = g.gate === "phase1_eligibility";
  const c = counts(v);
  const chips = elig ? "" : `<div class="chips" aria-label="What counted">
      <span class="chip"><b>${c.pain}</b> ${c.pain === 1 ? "complaint" : "complaints"}</span>
      <span class="chip"><b>${c.wtp}</b> said they'd pay</span>
      <span class="chip"><b>${c.comp}</b> existing ${c.comp === 1 ? "tool" : "tools"}</span>
      ${c.price ? `<span class="chip"><b>${c.price}</b> ${c.price === 1 ? "price" : "prices"} seen</span>` : ""}</div>`;
  const bars = elig ? `<p class="why" style="margin:0">ProveIt builds digital products only, and never financial, crypto, health or legal advice products or physical goods.</p>` : [
    m.sourced_pain != null ? bar("Real complaints found", Math.round(m.sourced_pain * 10) / 10, th.min_sourced_pain, Math.max(th.min_sourced_pain * 1.6, m.sourced_pain), "", "Quotes count only if they're about this problem and checked on their source page") : "",
    m.coverage != null ? (() => { const rows = (v.coverage_rows || []).length || 5; const got = Math.round(m.coverage * rows), need = Math.ceil(th.min_coverage * rows);
        return bar("Searches that found people discussing it", got, need, rows, "", `${got} of ${rows} searches`); })() : "",
    m.distinct_sources != null && th.min_distinct_sources != null ? bar("Different places online", m.distinct_sources, th.min_distinct_sources, Math.max(th.min_distinct_sources * 2, m.distinct_sources), "") : "",
  ].join("") + `<p class="lockline" title="Fingerprint ${esc(v.thresholds_sha256 || "")}">${v.goalpost_moved ? '<span class="moved">The bar was changed after the search started.</span>' : "🔒 The bar was set before searching, so it can't be moved to fit the result."}</p>`;
  const html = `<div class="verdict ${g.outcome}"><div class="lead"><div class="which">${elig ? "Before searching: can ProveIt help with this?" : "First checkpoint: do people have this problem?"}</div>
    <p class="word">${elig ? "Not eligible." : (OUT[g.outcome] || esc(g.outcome))}</p><p class="why">${esc(whyLine(g, m, th))}</p>${chips}
    ${g.founder_decision && g.founder_decision !== "pending" ? `<p class="founder">${esc(decisionText(g.founder_decision))}</p>` : ""}</div>
    <div class="bars">${bars}</div></div>`;
  setOnce("verdict", html, html);
}
const DECISIONS = {accepted: "You accepted this advice.", overridden: "You chose to carry on anyway.", stopped: "You stopped here."};
const decisionText = d => DECISIONS[d] || "";

function renderDecide(v) {
  const acts = v.actions || [];
  const key = JSON.stringify([v.stage, acts, v.variant_n, (v.variants || []).length, isBusy(v)]);
  if (S.keys.decide === key) return;                // never rebuild while someone is typing a reason
  S.keys.decide = key;
  if (isBusy(v) || !acts.length || acts.every(a => a === "clarify_ok")) { $("decide").innerHTML = ""; return; }
  const n = (v.variants || []).length, next = (v.variant_n || 1) + 1;
  let title = "What would you like to do?", lead = "It's your call. Every choice is saved with the run.", btns = "";
  if (v.stage === "await_gate4") {
    title = "Approve the price and the policy drafts?"; lead = "Read them in the Files tab first. Nothing is sold without this.";
    btns = `<button class="btn primary" type="button" data-decide="gate4_approve">Approve price and policies</button><button class="btn stop" type="button" data-decide="gate4_reject">Reject and redraft</button>`;
  } else if (v.stage === "await_override") {
    title = "No one has signed up yet"; lead = "The waiting-list page isn't public (that part is switched off), so it can't show demand. You can stop, or carry on as a preview.";
    btns = `<button class="btn stop" type="button" data-decide="stop">Stop here</button>`;
  } else {
    if (acts.includes("repeat")) btns += `<button class="btn" type="button" data-decide="repeat">Search again, wider</button>`;
    if (acts.includes("pivot")) btns += `<button class="btn" type="button" data-decide="pivot">Try another angle (${next} of ${n})</button>`;
    if (acts.includes("stop")) btns += `<button class="btn stop" type="button" data-decide="stop">Stop here</button>`;
  }
  const ovr = acts.includes("override") ? `<div class="override"><label for="ovr">Or carry on anyway, against the advice. Write why; it's saved with the run, and every later step is marked as a preview.</label>
      <div class="row"><input id="ovr" maxlength="1000" dir="auto" placeholder="Why carry on despite the evidence?"><button class="btn hold" type="button" data-decide="override">Carry on as a preview</button></div></div>` : "";
  $("decide").innerHTML = `<section class="decide" aria-labelledby="decide-h"><h2 id="decide-h">${title}</h2><p>${lead}</p><div class="actions">${btns}</div>${ovr}<p class="formerr" id="decide-err" role="alert" hidden></p></section>`;
}

function renderNext(v) {
  const g = v.gate1; let html = "";
  if (g && !isBusy(v) && v.stage !== "done") {
    const kit = (v.files || []).find(f => f.startsWith("phase1_step4"));
    if (g.gate === "phase1_eligibility")
      html = `<div class="next"><div><h2>Try a digital product instead</h2><p>Templates, checklists, guides or a small tool work well here.</p></div><button class="btn primary" type="button" data-act="new">Test a different idea</button></div>`;
    else if (g.outcome === "repeat" && kit)
      html = `<div class="next"><div><h2>Next: five short conversations</h2><p>Your interview kit has the questions, who to ask, and how to decide afterwards.</p></div><button class="btn primary" type="button" data-file="${esc(kit)}">Open the interview kit</button></div>`;
    else if (g.outcome === "stop" && !v.override)
      html = `<div class="next"><div><h2>Stopping here saved you the build.</h2><p>Have another idea? Testing it takes about a minute.</p></div><button class="btn primary" type="button" data-act="new">Test a different idea</button></div>`;
  }
  setOnce("next", html, html);
}

function renderLater(v) {
  const items = [["Did people sign up?", v.gate2], ["Is the product ready?", v.gate3], ["Price and policies", v.gate4]].filter(x => x[1]);
  const R = {insufficient_evidence: "No real sign-ups yet", all_required_pass: "All checks passed", founder_approved_pricing_and_policies: "You approved them",
    founder_rejected: "You asked for a redraft", checks_failed: "Some checks failed"};
  const html = items.map(([k, g]) => { const pv = v.override && g.outcome === "go";
    return `<div><div class="k">${k}</div><div class="v ${pv ? "" : g.outcome}">${pv ? "Preview" : (OUT_SHORT[g.outcome] || esc(g.outcome))}</div><div class="k">${esc(pv ? (R[g.reason] || human(g.reason)) + " (after carrying on anyway)" : (R[g.reason] || human(g.reason)))}</div></div>`; }).join("");
  setOnce("later", html, html);
}

async function decide(d, btn) {
  const errEl = $("decide-err"); let reason = "";
  if (d === "override") { reason = ($("ovr")?.value || "").trim(); if (reason.length < 8) { if (errEl) { errEl.textContent = "Write a short reason first; it's saved with your decision."; errEl.hidden = false; } $("ovr")?.focus(); return; } }
  busy(btn, true);
  try {
    const r = await api(`/api/runs/${encodeURIComponent(S.run)}/decide`, {method: "POST", body: JSON.stringify({decision: d, reason})});
    if (!r.ok) { if (errEl) { errEl.textContent = r.error; errEl.hidden = false; } else showAnswer(r.error, "err"); }
    else { S.keys = {}; announce(d === "stop" ? "Stopped." : "Done. Working on it."); }
  } catch (e) { if (errEl) { errEl.textContent = "That didn't go through: " + e.message; errEl.hidden = false; } }
  finally { busy(btn, false); poll(true); }
}
async function retryRun(btn) {
  busy(btn, true, "Trying again…");
  try { await api(`/api/runs/${encodeURIComponent(S.run)}/continue`, {method: "POST"}); S.keys = {}; announce("Trying again."); }
  catch (e) { showAnswer("That didn't work: " + e.message, "err"); }
  finally { poll(true); }
}

/* ---------- tabs (WAI-ARIA tabs pattern) ---------- */
const TABS = ["evidence", "debate", "approvals", "files", "status"];
function tab(name, focus) {
  S.tab = name;
  for (const t of TABS) {
    const b = $("tab-" + t), p = $("pane-" + t), on = t === name;
    b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; p.hidden = !on;
  }
  if (focus) $("tab-" + name).focus();
}
$("tabs").addEventListener("click", e => { const b = e.target.closest("[role=tab]"); if (b) tab(b.id.slice(4)); });
$("tabs").addEventListener("keydown", e => {
  const i = TABS.indexOf(S.tab); let j = null;
  if (e.key === "ArrowRight") j = (i + 1) % TABS.length; else if (e.key === "ArrowLeft") j = (i - 1 + TABS.length) % TABS.length;
  else if (e.key === "Home") j = 0; else if (e.key === "End") j = TABS.length - 1;
  if (j !== null) { e.preventDefault(); tab(TABS[j], true); }
});

/* evidence */
const KIND = {pain: ["pain", "Complaint"], wtp: ["wtp", "Would pay"], price_point: ["price_point", "Price"], competitor: ["competitor", "Existing tool"],
  trend: ["none", "Context"], market_size: ["none", "Context"]};
const PLACE = {hn: "Hacker News", stackexchange: "Stack Exchange", github: "GitHub", web: "Web", wikipedia: "Wikipedia"};
function renderEvidence(v) {
  const all = (v.claims || []).slice().sort((a, b) => (b.weight - a.weight) || ((a.kind !== "pain") - (b.kind !== "pain")));
  const counted = all.filter(c => c.weight > 0);
  const list = S.showZero ? all : counted;
  const key = JSON.stringify([all.length, counted.length, S.showZero, v.variant_n]);
  if (S.keys.evidence === key) return; S.keys.evidence = key;
  if (!all.length && !isBusy(v) && (v.coverage_rows || []).length) {
    const P = {hn: "Hacker News", stackexchange: "Stack Exchange", github: "GitHub", searxng: "the web"};
    $("pane-evidence").innerHTML = `<p class="empty">No quote counted toward the verdict. Here is what was searched:</p><ul>` +
      v.coverage_rows.map(r => `<li>${esc(P[r.source] || r.source)}: “${esc(String(r.query).replace(/ @ .*/, ""))}”, ${r.on_topic} of ${r.hits} results on topic${r.ok ? "" : " (did not answer)"}</li>`).join("") + `</ul>`;
    return;
  }
  if (!all.length && isBusy(v)) { $("pane-evidence").innerHTML = `<div class="skeleton" aria-hidden="true"><i></i><i style="width:70%"></i><i style="width:85%"></i></div><p class="empty">Quotes appear here as they're checked.</p>`; return; }
  const head = `<div class="filterrow"><span>${counted.length} of ${plural(all.length, "quote")} count toward the verdict.</span>
    ${all.length > counted.length ? `<label><input type="checkbox" id="showzero" ${S.showZero ? "checked" : ""}> Show the ones that didn't count, and why</label>` : ""}</div>`;
  const rows = list.map(c => {
    const [cls, word] = KIND[c.kind] || ["none", human(c.kind)];
    const counts = c.weight > 0;
    const status = c.status === "verified_live" ? "Checked on the page" : (c.status === "archived_match" ? "Page offline: matched a saved copy (counts half)" : "Not checked");
    return `<article class="claim ${counts ? "" : "zero"}" id="ev-${esc(c.id)}"><div class="meta"><b>${esc(c.id)}</b><span class="tag ${counts ? cls : "none"}">${esc(word)}</span><span>${counts ? esc(status) : "Didn't count"}</span></div>
      <div><blockquote dir="auto">“${esc(c.quote || c.claim_text || "")}”</blockquote>
      <div class="src">${/^https?:\/\//i.test(c.url || "") ? `<a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(PLACE[c.source] || c.source)}${c.hit_title ? ": " + esc(String(c.hit_title).slice(0, 90)) : ""}</a>` : "ASSUMPTION"}${c.source === "stackexchange" ? " · CC BY-SA" : ""}${!counts && c.weight_note ? " · " + esc(c.weight_note.replace(/;? ?archived match/, "")) : ""}</div></div></article>`;
  }).join("");
  $("pane-evidence").innerHTML = head + (rows || `<p class="empty">${all.length ? "None of the quotes I found were clearly about this problem. Tick the box to see them and why." : "No quotes yet."}</p>`);
}

/* for and against */
function renderDebate(v) {
  const key = JSON.stringify([!!v.debate, v.variant_n, (v.debate?.advocate || []).length]);
  if (S.keys.debate === key) return; S.keys.debate = key;
  if (!v.debate) { $("pane-debate").innerHTML = `<p class="empty">Two short arguments, one for going ahead and one for stopping, appear once the evidence is in.</p>`; return; }
  const ok = new Set((v.claims || []).filter(c => c.weight > 0).map(c => c.id));
  const st = s => { const ids = (s.claim_ids || []).filter(i => ok.has(i));
    const text = String(s.text || "").replace(/\s*\((C\d+(,\s*C\d+)*)\)/g, "").replace(/\s*\[C\d+\]/g, "");
    return `<p>${ids.length ? "" : `<span class="assume" title="Not backed by a counted quote">ASSUMPTION</span>`}${esc(text)}${ids.map(i => `<a class="cite" href="#ev-${esc(i)}" data-cite="${esc(i)}">${esc(i)}</a>`).join("")}</p>`; };
  $("pane-debate").innerHTML = `<div class="debate"><div><h2>The case for going ahead</h2><p class="sub">The optimist, citing only counted quotes.</p>${v.debate.advocate.map(st).join("")}</div>
    <div><h2>The case for stopping</h2><p class="sub">The sceptic, using the same quotes.</p>${v.debate.skeptic.map(st).join("")}</div></div>`;
}

/* files, with a small safe Markdown renderer (text is escaped first) */
const PHASE_OF = f => { const m = f.match(/^phase(\d)/); return m ? `Step ${m[1]} · ${PHASES[+m[1] - 1]}` : "Practice sale"; };
function prettyName(f) {
  const base = f.replace(/^phase\d_(step\d_|gate_)?/, "").replace(/\.(md|json|html|csv|txt)$/, "").replace(/[_-]/g, " ");
  return base.replace(/^./, c => c.toUpperCase()) + (f.includes("_gate_") ? " (checkpoint)" : "");
}
function renderFiles(v) {
  const files = (v.files || []).filter(f => /^(phase|payment)/.test(f));
  const key = files.join(","); if (S.keys.files === key) return; S.keys.files = key;
  $("files").innerHTML = files.length ? files.map(f => `<button type="button" data-file="${esc(f)}" aria-pressed="false" title="${esc(f)}"><span class="p">${PHASE_OF(f)}</span><span class="n">${esc(prettyName(f))}</span></button>`).join("")
    : `<p class="empty">Files appear as each step finishes.</p>`;
}
function md(src) {
  const lines = esc(src).split(/\r?\n/); let out = "", list = null, table = [];
  const inline = s => s.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|\W)\*([^*\s][^*]*)\*/g, "$1<i>$2</i>")
    .replace(/(https?:\/\/[^\s)<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  const flushList = () => { if (list) { out += `</${list}>`; list = null; } };
  const flushTable = () => { if (table.length) { const rows = table.filter(r => !/^\|?\s*-{2,}/.test(r.replace(/[|:\s-]/g, "") ? "x" : r) || !/^[|:\s-]+$/.test(r));
      out += "<table>" + rows.map((r, i) => "<tr>" + r.replace(/^\||\|$/g, "").split("|").map(c => i === 0 ? `<th>${inline(c.trim())}</th>` : `<td>${inline(c.trim())}</td>`).join("") + "</tr>").join("") + "</table>"; table = []; } };
  for (const raw of lines) {
    const l = raw.trimEnd();
    if (/^\|.*\|$/.test(l)) { flushList(); table.push(l); continue; } else flushTable();
    let m;
    if ((m = l.match(/^(#{1,3})\s+(.*)$/))) { flushList(); const n = m[1].length; out += `<h${n}>${inline(m[2])}</h${n}>`; }
    else if ((m = l.match(/^\s*[-*]\s+(.*)$/))) { if (list !== "ul") { flushList(); out += "<ul>"; list = "ul"; } out += `<li>${inline(m[1])}</li>`; }
    else if ((m = l.match(/^\s*\d+\.\s+(.*)$/))) { if (list !== "ol") { flushList(); out += "<ol>"; list = "ol"; } out += `<li>${inline(m[1])}</li>`; }
    else if ((m = l.match(/^&gt;\s?(.*)$/))) { flushList(); out += `<blockquote>${inline(m[1])}</blockquote>`; }
    else if (!l.trim()) { flushList(); }
    else { flushList(); out += `<p>${inline(l)}</p>`; }
  }
  flushList(); flushTable(); return out;
}
async function viewFile(name, btn) {
  tab("files");
  document.querySelectorAll("#files button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.file === name)));
  const el = $("viewer"); el.innerHTML = `<div class="skeleton" aria-hidden="true"><i></i><i style="width:70%"></i></div>`;
  try {
    const t = await api(`/api/runs/${encodeURIComponent(S.run)}/files/${encodeURIComponent(name)}`);
    const text = typeof t === "string" ? t : JSON.stringify(t, null, 2);
    if (name.endsWith(".html")) { el.innerHTML = `<iframe sandbox="" title="${esc(prettyName(name))}"></iframe>`; el.querySelector("iframe").srcdoc = text; }
    else if (name.endsWith(".md")) el.innerHTML = `<article class="doc" tabindex="-1"><div class="docbar"><span>${esc(PHASE_OF(name))}</span><span>${esc(name)}</span></div>${md(text)}</article>`;
    else el.innerHTML = `<article class="doc"><div class="docbar"><span>${esc(PHASE_OF(name))}</span><span>${esc(name)}</span></div><pre>${esc(text)}</pre></article>`;
    el.scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start"});
  } catch (e) { el.innerHTML = `<p class="empty">That file couldn't be opened (${esc(e.message)}).</p>`; }
}
function renderCost(v) {
  const u = v.usage || {};
  $("costline").textContent = `This run, including questions asked about it: ${plural(u.calls || 0, "AI call")}, ${((u.tokens_in || 0) + (u.tokens_out || 0)).toLocaleString("en-GB")} tokens, about ${Math.round(u.seconds || 0)} seconds of AI time. Cost: $0.00.`;
}

/* approvals */
let shownApprovals = "";
async function renderApprovals() {
  let list = [];
  try { list = await api("/api/approvals?status=pending" + (S.run ? "&run=" + encodeURIComponent(S.run) : "")); } catch (e) { return; }
  const c = $("apCount"); c.hidden = !list.length; c.textContent = list.length;
  const key = list.map(a => a.id).join(","); if (key === shownApprovals) return; shownApprovals = key;
  const box = $("approvals");
  if (!list.length) { box.innerHTML = `<p class="empty">Nothing is waiting for your approval.</p>`; return; }
  box.innerHTML = "";
  const WHAT = {publish_landing_page: "Publish the waiting-list page", open_store: "Open the store page", refund: "Approve the refund",
    publish_post: "Post the launch announcement", send_email: "Send the email"};
  for (const a of list) {
    let payload = ""; try { payload = await api(`/api/approvals/${a.id}/payload`); } catch (e) {}
    const div = document.createElement("article"); div.className = "ap"; div.id = "ap-" + a.id;
    div.innerHTML = `<h3>${esc(WHAT[a.action] || human(a.action))}</h3><p class="note">${esc(a.note || "")}</p>
      <p class="sha">You approve exactly what you see below. If it changes, the approval no longer matches. <span title="SHA-256 ${esc(a.payload_sha256)}">Fingerprint <code>${esc(a.payload_sha256.slice(0, 12))}…</code></span></p><div class="slot"></div>
      <div class="actions"><button class="btn primary" type="button">Approve (hash-locked)</button><button class="btn stop" type="button">Reject and redraft</button></div>`;
    const slot = div.querySelector(".slot");
    if (/^\s*<!doctype html/i.test(payload)) { const f = document.createElement("iframe"); f.sandbox = ""; f.srcdoc = payload; f.title = "Preview of what you are approving"; slot.appendChild(f); }
    else { slot.innerHTML = `<pre>${esc(payload)}</pre>`; }
    const [ok, no] = div.querySelectorAll(".actions button");
    if (DEMO) { ok.disabled = no.disabled = true; }
    ok.onclick = () => approve(a.id, true, a.payload_sha256, ok); no.onclick = () => approve(a.id, false, a.payload_sha256, no);
    box.appendChild(div);
  }
}
async function approve(id, yes, sha, btn) {
  busy(btn, true);
  try { await api(`/api/approvals/${id}`, {method: "POST", body: JSON.stringify({approve: yes, payload_sha256: sha})}); announce(yes ? "Approved." : "Rejected. A new draft is being written."); }
  catch (e) { showAnswer("That didn't go through: " + e.message, "err"); busy(btn, false); }
  shownApprovals = ""; poll(true);
}
function highlightApproval(id) {
  if (S.mode === "hud") setMode("dual");
  tab("approvals");
  setTimeout(() => { const el = $("ap-" + id); if (el) { el.scrollIntoView({block: "center"}); el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); el.querySelector("button")?.focus(); } }, 300);
}

/* ---------- voice-panel summary ---------- */
function renderVoiceVerdict() {
  const el = $("voiceVerdict"), v = S.view;
  if (S.mode === "tactical" || !v || !v.gate1) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<b>${esc(v.title || "This idea")}:</b> ${esc(OUT_SHORT[v.gate1.outcome] || v.gate1.outcome)}. Ask me why, or what to do next.`;
}

/* ---------- Ask the assistant (streams sentences; speaks each as it arrives) ---------- */
function screenLabels() {
  return [...document.querySelectorAll("#decide button, #next button, #banners button, #approvals .actions button")]
    .filter(b => b.offsetParent !== null).map(b => b.textContent.trim()).slice(0, 12);
}
function showAnswer(text, tone, extra) {
  const o = $("askout");
  o.className = "askout" + (tone && tone !== "plain" ? " " + tone : "");
  $("askbody").textContent = text; $("askextra").innerHTML = extra || ""; o.hidden = false;
  o.setAttribute("role", tone === "err" || tone === "deny" ? "alert" : "status");
}
function hideAnswer() { $("askout").hidden = true; }
function addMsg(kind, text) {
  const c = $("convo"); const d = document.createElement("div"); d.className = "msg " + kind; d.dir = "auto"; d.textContent = text;
  c.appendChild(d); c.scrollTop = c.scrollHeight; return d;
}
async function sendAsk(text) {
  const inp = $("askq"); text = (text ?? inp.value).trim(); if (!text) return;
  if (S.asking) { showAnswer("One moment, I'm still answering. Your question is still in the box.", "plain"); return; }
  inp.value = "";
  S.asking = true; S.lastAsk = text; addMsg("you", text); setState("think", "Thinking");
  const bubble = addMsg("him", "…"); let full = "", meta = null, failed = null;
  const inBar = S.mode !== "hud";
  if (inBar) showAnswer("…");
  const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 45000);
  try {
    const r = await fetch(API + "/api/ask/stream", {method: "POST", headers: {"Content-Type": "application/json"}, signal: ctrl.signal,
      body: JSON.stringify({text, run_id: S.run, history: S.history.slice(-6), screen: screenLabels()})});
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw Object.assign(new Error(j.error || ("HTTP " + r.status)), {status: r.status}); }
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
    while (true) {
      const {value, done} = await reader.read(); if (done) break;
      buf += dec.decode(value, {stream: true});
      let i; while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (!line) continue;
        const ev = JSON.parse(line);
        if (ev.type === "meta") meta = ev;
        if (ev.type === "sentence" && ev.text) { full = full ? full + " " + ev.text : ev.text; bubble.textContent = full; say(ev.text); if (inBar) showAnswer(full, tone(meta)); $("convo").scrollTop = 1e9; }
      }
    }
  } catch (e) {
    failed = e.name === "AbortError" ? "That took too long. Try again in a moment." :
      e.status === 429 ? "I'm getting a lot of questions. Give me a few seconds and ask again." :
      e.status ? "That didn't work (" + e.message + ")." : "I can't reach ProveIt. Check that it's still running.";
    full = failed; bubble.textContent = full; say(full);
  } finally { clearTimeout(timer); }
  const t = failed ? "err" : tone(meta);
  bubble.classList.toggle("refuse", t === "refuse"); bubble.classList.toggle("deny", t === "deny");
  const detail = meta && meta.detail;
  let extra = "";
  if (detail) {
    const d = document.createElement("details"); d.innerHTML = `<summary>Show the numbers</summary><div></div>`; d.querySelector("div").textContent = detail; bubble.appendChild(d);
    extra = `<details><summary>Show the numbers</summary><div>${esc(detail)}</div></details>`;
  }
  if (failed) extra += `<button class="btn retry" type="button" data-act="retryask">Ask again</button>`;
  if (inBar) showAnswer(full, t, extra);
  announce(full.slice(0, 300));
  if (!failed) { S.history.push({role: "user", text}, {role: "assistant", text: full}); S.history = S.history.slice(-12); }
  S.asking = false;
  if (t !== "deny") setState("idle");
  if (meta && meta.highlight_approval) highlightApproval(meta.highlight_approval);
  if (meta && meta.start_run) { await refreshRuns(); followRun(meta.start_run); }
  if (meta && meta.listen) queue.then(() => startListening(true));
}
function tone(meta) {
  if (!meta || !meta.refused) return "plain";
  return DECEPTION.test(meta.rule || "") ? "deny" : "refuse";
}

/* ---------- voice out: local Piper first, the browser's en-GB voice as fallback ---------- */
let AC = null, analyser = null, freq = new Uint8Array(128), synthLevel = 0, queue = Promise.resolve(), currentSrc = null, piperOK = null, speaking = 0;
function audioCtx() { if (!AC) { AC = new (window.AudioContext || window.webkitAudioContext)(); analyser = AC.createAnalyser(); analyser.fftSize = 256; analyser.smoothingTimeConstant = .8; analyser.connect(AC.destination); } return AC; }
function pickVoice() {
  const vs = speechSynthesis.getVoices(); const pref = ["Microsoft Sonia Online (Natural) - English (United Kingdom)", "Microsoft Ryan Online (Natural) - English (United Kingdom)", "Google UK English Female", "Google UK English Male", "Daniel", "Serena"];
  for (const n of pref) { const v = vs.find(x => x.name === n); if (v) return v; }
  return vs.find(v => v.lang === "en-GB") || null;
}
function fetchSpeech(text) {
  // The first request must answer within 500 ms or the browser voice takes over. Once local Piper has
  // answered, later sentences are fetched while the previous one plays, so they get more time.
  if (piperOK === false) return Promise.resolve(null);
  const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), piperOK ? 6000 : 500);
  return fetch(API + "/api/voice/speak", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text}), signal: ctrl.signal})
    .then(r => { clearTimeout(t); if (!r.ok) { piperOK = false; return null; } piperOK = true; return r.arrayBuffer(); })
    .catch(() => { clearTimeout(t); return null; });
}
function say(text) {
  if (!S.voice || !text) return;
  const pending = fetchSpeech(text);
  queue = queue.then(() => speakOne(text, pending)).catch(() => {});
}
function stopAudio() { try { if (currentSrc) currentSrc.stop(); } catch (e) {} }
async function speakOne(text, pending) {
  if (!S.voice) return;
  speaking++; if (S.state !== "alert") setState("speak");
  const buf = await pending;
  try {
    if (!buf) throw new Error("browser");
    const ctx = audioCtx(); if (ctx.state === "suspended") await ctx.resume();
    const audio = await ctx.decodeAudioData(buf);
    await new Promise(res => { const src = ctx.createBufferSource(); currentSrc = src; src.buffer = audio; src.connect(analyser); src.onended = res; src.start(); });
    $("voiceInfo").textContent = "Speaking with a voice that runs on this computer (Piper).";
  } catch (e) {
    if (!("speechSynthesis" in window)) { speaking--; return; }
    await new Promise(res => {
      const u = new SpeechSynthesisUtterance(text); const v = pickVoice(); if (v) u.voice = v; u.lang = "en-GB"; u.rate = 1.02;
      let done = false; const finish = () => { if (!done) { done = true; synthLevel = 0; res(); } };
      u.onstart = () => synthLevel = 1; u.onend = u.onerror = finish;
      setTimeout(finish, 2000 + text.length * 90);           // safety net for browsers that never fire "end"
      u.onboundary = () => synthLevel = 1.5;
      speechSynthesis.speak(u);
      $("voiceInfo").textContent = "Speaking with your browser's voice" + (v ? " (" + v.name + ")" : "") + ".";
    });
  }
  speaking--;
  if (!speaking && S.state === "speak") setState("idle");
}

/* ---------- voice in: push-to-talk and wake word (browser SpeechRecognition), local transcription fallback ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null, wakeRec = null, micSrc = null, micAn = null, micFreq = new Uint8Array(128), mediaRec = null;
const WAKE = new RegExp("(?:^|\\b)(?:hey\\s+|ok\\s+|okay\\s+)?(?:" + (CFG.wakeRe || "jarvis") + ")(?![a-z])[\\s,.:!?-]*(.*)$", "i");
// Speech recognition language: English by default (the browser's own language may not be what you speak).
let SR_LANG = "en-GB";
try { SR_LANG = localStorage.getItem("proveit_speech_lang") || "en-GB"; } catch (e) {}
function micError(e) {
  const name = e && (e.error || e.name);
  const msg = name === "not-allowed" || name === "NotAllowedError" || name === "service-not-allowed"
    ? "The microphone is blocked. Allow it from the icon in the address bar, or type your question instead."
    : name === "audio-capture" || name === "NotFoundError" ? "No microphone found. Type your question below instead."
    : name === "network" ? "Speech recognition needs an internet connection in this browser. Type your question instead." : "";
  if (msg) { showAnswer(msg, "refuse"); $("voiceInfo").textContent = msg; announce(msg, true); setState("idle"); }
  return !!msg;
}
async function micToAnalyser(on) {
  try {
    if (on && !micSrc) { const ctx = audioCtx(); if (ctx.state === "suspended") await ctx.resume(); const stream = await navigator.mediaDevices.getUserMedia({audio: true}); micSrc = ctx.createMediaStreamSource(stream); micSrc._stream = stream; micAn = ctx.createAnalyser(); micAn.fftSize = 256; micSrc.connect(micAn); }
    if (!on && micSrc) { micSrc.disconnect(); micSrc._stream.getTracks().forEach(t => t.stop()); micSrc = null; micAn = null; micFreq.fill(0); }
    return true;
  } catch (e) { return false; }          // the visual is optional; recognition reports its own errors
}
function pauseWake() { if (wakeRec) { wakeRec._paused = true; try { wakeRec.stop(); } catch (e) {} } }
function resumeWake() { if (S.wake && wakeRec) { wakeRec._paused = false; try { wakeRec.start(); } catch (e) {} } }
function micPressed(on) { $("ptt").classList.toggle("live", on); $("askmic").setAttribute("aria-pressed", String(on)); }
function startListening(auto) {
  if (rec || mediaRec) return;
  stopAudio(); try { speechSynthesis.cancel(); } catch (e) {}
  pauseWake();
  setState("listen", "Listening"); micPressed(true);
  if (!SR) { micToAnalyser(true); recordFallback(); return; }
  // Start recognition straight away, inside the press itself; the voice visual starts alongside and never
  // holds recognition up (waiting for it first meant a quick press-and-release recorded nothing).
  rec = new SR(); rec.lang = SR_LANG; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 3;
  let finalText = "";
  rec.onresult = e => { let t = ""; for (const r of e.results) { t += r[0].transcript; if (r.isFinal) finalText = t; } $("caption").textContent = t; };
  rec.onerror = e => { if (e.error !== "no-speech" && e.error !== "aborted") micError(e); };
  rec.onend = () => { rec = null; micToAnalyser(false); micPressed(false);
    const t = (finalText || $("caption").textContent).trim(); $("caption").textContent = "";
    if (t) sendAsk(t); else if (S.state === "listen") setState("idle");
    setTimeout(resumeWake, 400); };
  try { rec.start(); } catch (e) { rec = null; micPressed(false); setState("idle"); return; }
  micToAnalyser(true);                       // visual only: errors here never stop listening
  if (auto) setTimeout(() => { if (rec) rec.stop(); }, 8000);
}
function stopListening() { if (rec) { try { rec.stop(); } catch (e) {} } else if (mediaRec) mediaRec.stop(); }
async function recordFallback() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true}); const chunks = [];
    mediaRec = new MediaRecorder(stream); mediaRec.ondataavailable = e => chunks.push(e.data);
    mediaRec.onstop = async () => { stream.getTracks().forEach(t => t.stop()); mediaRec = null; micToAnalyser(false); micPressed(false);
      const fd = new FormData(); fd.append("audio", new Blob(chunks, {type: "audio/webm"}), "speech.webm");
      try { const r = await fetch(API + "/api/voice/transcribe", {method: "POST", body: fd}); const j = await r.json();
        if (j.text) sendAsk(j.text); else throw new Error("none"); }
      catch (e) { setState("idle"); showAnswer("This browser can't turn speech into text, and local transcription isn't installed. Use Chrome or Edge, or type your question.", "refuse"); } };
    mediaRec.start();
  } catch (e) { micError(e) || showAnswer("The microphone isn't available. Type your question instead.", "refuse"); micPressed(false); setState("idle"); }
}
function toggleWake() {
  const b = $("wake");
  if (!SR) { showAnswer(`Saying “${WAKE_WORD}” to start needs speech recognition, which works in Chrome and Edge. Typing always works.`, "refuse"); return; }
  if (!S.wake) {
    wakeRec = new SR(); wakeRec.lang = SR_LANG; wakeRec.continuous = true; wakeRec.interimResults = false; wakeRec.maxAlternatives = 3;
    wakeRec.onstart = () => { S.wake = true; b.setAttribute("aria-pressed", "true"); b.textContent = `Say “${WAKE_WORD}” to start: on`; addMsg("sys", `Listening for “${WAKE_WORD}”. Say it, then your question.`); };
    wakeRec.onerror = e => { if (micError(e)) { S.wake = false; wakeRec = null; b.setAttribute("aria-pressed", "false"); b.textContent = `Say “${WAKE_WORD}” to start: off`; } };
    wakeRec.onresult = e => {
      if (speaking || S.asking || rec) return;                     // never react to our own voice
      const res = e.results[e.results.length - 1]; let m = null;
      for (let k = 0; k < res.length && !m; k++) m = res[k].transcript.trim().match(WAKE);
      if (!m) return;
      if (m[1].trim().length > 2) sendAsk(m[1].trim());
      else { pauseWake(); say("Yes?"); queue.then(() => startListening(true)); }
      addMsg("sys", "Heard: “" + res[0].transcript.trim() + "”");
    };
    wakeRec.onend = () => { if (S.wake && wakeRec && !wakeRec._paused) { try { wakeRec.start(); } catch (e) {} } };
    try { wakeRec.start(); } catch (e) { micError(e); }
  } else {
    S.wake = false; b.setAttribute("aria-pressed", "false"); b.textContent = `Say “${WAKE_WORD}” to start: off`;
    if (wakeRec) { wakeRec.onend = null; try { wakeRec.stop(); } catch (e) {} wakeRec = null; }
  }
}

/* ---------- the voice visual ---------- */
const STATE_TEXT = {idle: "is ready", listen: "is listening", think: "is thinking", speak: "is speaking"};
const STATE_COL = {idle: [143, 139, 255], listen: [60, 198, 180], think: [143, 139, 255], speak: [230, 235, 245], alert: [240, 113, 103], go: [91, 196, 140], hold: [224, 169, 59]};
function setState(s, text) { S.state = s; $("vstate").innerHTML = text ? esc(text) : `<b>${esc(NAME)}</b> ${STATE_TEXT[s] || ""}`; }
const cv = $("orb"), g2 = cv.getContext("2d");
function resizeOrb() { const r = cv.getBoundingClientRect(); const d = window.devicePixelRatio || 1; if (r.width) { cv.width = r.width * d; cv.height = r.width * d; } }
window.addEventListener("resize", resizeOrb);
let tick = 0, col = [143, 139, 255], level = 0;
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
function draw() {
  requestAnimationFrame(draw);
  const W = cv.width, H = cv.height; if (!W || $("voicepanel").hidden || document.hidden) return;   // no work while unseen
  tick++;
  const cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2;
  const tgt = STATE_COL[S.state] || STATE_COL.idle; col = col.map((c, i) => c + (tgt[i] - c) * 0.08);
  const rgb = a => `rgba(${col[0] | 0},${col[1] | 0},${col[2] | 0},${a})`;
  if (analyser) analyser.getByteFrequencyData(freq);
  if (micAn) micAn.getByteFrequencyData(micFreq);
  let e = 0; for (let i = 2; i < 48; i++) e = Math.max(e, freq[i] / 255, micAn ? micFreq[i] / 255 : 0);
  if (synthLevel) { e = Math.max(e, .35 + .3 * Math.abs(Math.sin(tick / 4.5)) * (synthLevel > 1 ? 1.2 : 1)); if (synthLevel > 1) synthLevel = 1; }
  if (S.state === "think") e = Math.max(e, .12 + .08 * Math.sin(tick / 9));
  level += (e - level) * 0.25;
  g2.clearRect(0, 0, W, H);
  const phase = (S.view && S.view.phase) || 0;
  for (let i = 0; i < 6; i++) {
    const a0 = -Math.PI / 2 + i * Math.PI / 3 + 0.05, a1 = a0 + Math.PI / 3 - 0.1;
    g2.beginPath(); g2.arc(cx, cy, R * .95, a0, a1); g2.lineWidth = R * .012; g2.lineCap = "round";
    g2.strokeStyle = i + 1 < phase ? "rgba(230,235,245,.55)" : (i + 1 === phase ? rgb(.95) : "rgba(147,160,188,.18)"); g2.stroke();
  }
  const N = 96, base = R * .46;
  for (let i = 0; i < N; i++) {
    const bin = 2 + Math.floor((i < N / 2 ? i : N - 1 - i) * 0.9);
    let v = Math.max(freq[bin] / 255, micAn ? micFreq[bin] / 255 : 0);
    if (synthLevel) v = Math.max(v, level * (0.45 + 0.55 * Math.abs(Math.sin(i * 0.55 + tick / 5))));
    if (!reduce) v = Math.max(v, 0.04 + 0.03 * Math.sin(i * 0.35 + tick / 28));
    const a = i / N * Math.PI * 2 - Math.PI / 2, len = R * (.03 + v * .32);
    g2.beginPath(); g2.moveTo(cx + Math.cos(a) * base, cy + Math.sin(a) * base); g2.lineTo(cx + Math.cos(a) * (base + len), cy + Math.sin(a) * (base + len));
    g2.strokeStyle = rgb(.25 + v * .75); g2.lineWidth = Math.max(1.5, R * .012); g2.lineCap = "round"; g2.stroke();
  }
  const pr = R * (.36 + level * .05 + (reduce ? 0 : .008 * Math.sin(tick / 30)));
  const grad = g2.createRadialGradient(cx - pr * .25, cy - pr * .3, pr * .05, cx, cy, pr);
  grad.addColorStop(0, rgb(.95)); grad.addColorStop(.55, rgb(.35)); grad.addColorStop(1, rgb(.06));
  g2.fillStyle = grad; g2.beginPath(); g2.arc(cx, cy, pr, 0, Math.PI * 2); g2.fill();
  if (S.state === "think" && !reduce) { g2.beginPath(); g2.arc(cx, cy, pr * 1.08, tick / 12, tick / 12 + 1.2); g2.strokeStyle = rgb(.9); g2.lineWidth = R * .012; g2.stroke(); }
}

/* ---------- events ---------- */
document.addEventListener("click", e => {
  const t = e.target.closest("[data-act],[data-decide],[data-file],[data-run],[data-preset],[data-mode],[data-cite]");
  if (!t) return;
  if (t.dataset.mode) return setMode(t.dataset.mode);
  if (t.dataset.run) return followRun(t.dataset.run);
  if (t.dataset.decide) return decide(t.dataset.decide, t);
  if (t.dataset.file) return viewFile(t.dataset.file, t);
  if (t.dataset.preset) return loadPreset(t.dataset.preset);
  if (t.dataset.cite) { e.preventDefault(); tab("evidence"); S.showZero = true; S.keys.evidence = null; renderEvidence(S.view); setTimeout(() => { const el = $("ev-" + t.dataset.cite); if (el) { el.scrollIntoView({block: "center"}); el.classList.add("flash"); } }, 50); return; }
  const a = t.dataset.act;
  if (a === "new") openNew(); else if (a === "latest") { if (S.runs.length) followRun(S.runs[0].id); }
  else if (a === "voice") toggleVoice(); else if (a === "theme") cycleTheme();
  else if (a === "privacy") openDialog("privacydlg"); else if (a === "keys") openDialog("keysdlg");
  else if (a === "menu") openDrawer(!$("sidebar").classList.contains("open"));
  else if (a === "parse") parsePaste(); else if (a === "closeask") hideAnswer();
  else if (a === "retry") retryRun(t); else if (a === "retryask") { hideAnswer(); sendAsk(S.lastAsk); }
  else if (a === "print") window.print();
});
document.addEventListener("change", e => { if (e.target.id === "showzero") { S.showZero = e.target.checked; S.keys.evidence = null; renderEvidence(S.view); } });
$("showall").addEventListener("click", () => { S.showAll = !S.showAll; S.keys.runlist = null; refreshRuns(); });
$("newform").addEventListener("submit", startRun);
$("askform").addEventListener("submit", e => { e.preventDefault(); sendAsk(); });
$("askmic").addEventListener("click", () => { if (rec || mediaRec) stopListening(); else startListening(true); });
$("wake").addEventListener("click", toggleWake);
const ptt = $("ptt");
ptt.addEventListener("pointerdown", e => { e.preventDefault(); startListening(); });
ptt.addEventListener("pointerup", stopListening); ptt.addEventListener("pointerleave", () => { if (rec || mediaRec) stopListening(); });
ptt.addEventListener("keydown", e => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); startListening(); } });
ptt.addEventListener("keyup", e => { if (e.key === " " || e.key === "Enter") stopListening(); });
document.addEventListener("keydown", e => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("askq").focus(); return; }
  if (e.key === "Escape" && !document.querySelector("dialog[open]")) { hideAnswer(); openDrawer(false); return; }
  if (typing || e.ctrlKey || e.metaKey || e.altKey || document.querySelector("dialog[open]") || !S.singleKeys) return;
  if (e.key === "/") { e.preventDefault(); $("askq").focus(); }
  else if (e.key === "?") { e.preventDefault(); openDialog("keysdlg"); }
  else if (e.key === "n" || e.key === "N") { e.preventDefault(); openNew(); }
  else if (e.key === "1") setMode("tactical"); else if (e.key === "2") setMode("hud"); else if (e.key === "3") setMode("dual");
});
document.addEventListener("click", () => { if (AC && AC.state === "suspended") AC.resume(); });

/* ---------- start ---------- */
S.singleKeys = true;
try { S.singleKeys = localStorage.getItem("proveit_singlekeys") !== "off"; } catch (e) {}
$("singlekeys").checked = S.singleKeys;
$("singlekeys").addEventListener("change", e => { S.singleKeys = e.target.checked; try { localStorage.setItem("proveit_singlekeys", S.singleKeys ? "on" : "off"); } catch (x) {} });
syncDrawer();
try { const m = localStorage.getItem("proveit_mode"); if (m && !CFG.embed && !new URL(location.href).searchParams.get("mode")) S.mode = m; } catch (e) {}
try { const t = localStorage.getItem("proveit_theme"); if (t === "light" || t === "dark") S.theme = t; } catch (e) {}
$("themebtn").textContent = "Theme: " + S.theme;
setMode(S.mode); setState("idle"); sysStatus(); setInterval(sysStatus, 30000); setInterval(refreshRuns, 8000);
if (!SR) $("voiceInfo").textContent = "Speaking to me needs Chrome or Edge. Typing always works.";
if ("speechSynthesis" in window) { speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged = () => {}; }
refreshRuns().then(() => {
  const want = new URL(location.href).searchParams.get("run");
  if (want) followRun(want, {push: false});
  else showWelcome();
});
requestAnimationFrame(draw);
})();
