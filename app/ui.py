"""Streamlit UI (port 8501): Mode 1 Tactical Writing / Command mode (native), Mode 2 the
holographic voice HUD (embedded), and Dual-Sync (both side by side).

The pipeline runs in a background worker thread; the page polls SQLite every second.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from agents.intake import parse_brief  # noqa: E402
from app import hud_component  # noqa: E402
from proveit import approval, ask, gates, llm, orchestrator, voice  # noqa: E402
from proveit.log import telemetry  # noqa: E402

st.set_page_config(page_title="ProveIt · developer view", page_icon="✅", layout="wide")
st.markdown("""<style>
.stApp{background:#06090F;color:#D8F6FF} code,.mono{font-family:"JetBrains Mono","Fira Code",monospace}
.b{display:inline-block;border:1px solid #00F0FF55;padding:1px 6px;margin:1px;font:12px monospace}
.live{color:#3CFFA0}.arch{color:#FFB800}.asm{color:#7E98AC}.red{color:#FF2A54;border-color:#FF2A54}
.mock{color:#FFB800}.stub{color:#C38BFF}
.verdict{font:700 26px monospace;letter-spacing:.15em}.go{color:#00F0FF}.stop{color:#FF2A54}.repeat,.pivot{color:#FFB800}
</style>""", unsafe_allow_html=True)

FIELDS = ["idea", "skills", "budget", "hours_per_week", "target_market", "values"]
WORKERS: dict[str, threading.Thread] = st.session_state.setdefault("workers", {})


def advance_bg(run_id: str) -> None:
    t = WORKERS.get(run_id)
    if t and t.is_alive():
        return
    t = threading.Thread(target=orchestrator.advance, args=(run_id,), daemon=True)
    WORKERS[run_id] = t
    t.start()


def badge(c) -> str:
    if c.weight > 0 and c.status == "verified_live":
        return f"<span class='b live'>[VERIFIED_LIVE: {c.weight}]</span>"
    if c.weight > 0 and c.status == "archived_match":
        return f"<span class='b arch'>[ARCHIVED_MATCH: {c.weight}]</span>"
    return "<span class='b asm'>[ASSUMPTION: 0.0]</span>"


# ---- sidebar ---------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ProveIt · developer view\nThe main console is at [localhost:8000](http://localhost:8000/hud). This view shows the same runs with their raw details.")
    mode = st.radio("Interface", ["⌨️ Tactical Writing Mode", "🎙️ Holographic Voice HUD", "⇄ Dual-Sync"], index=0)
    ms = llm.status()
    (st.success if ms["state"] == "ready" else st.warning)(f"Model `{ms['model']}`: {ms['state']}")
    st.caption(f"TTS: {voice.tts_status()['engine']} · STT: {voice.stt_status()['engine']}")
    runs = orchestrator.list_runs()
    ids = [r["id"] for r in runs]
    labels = {r["id"]: f"{r['id']} {r['label'] or ''} · {r['stage']}" for r in runs}
    if "run" not in st.session_state and ids:
        st.session_state.run = ids[0]
    if ids:
        st.session_state.run = st.selectbox("Run", ids, index=ids.index(st.session_state.run)
                                            if st.session_state.get("run") in ids else 0, format_func=labels.get)
    st.markdown("**Status labels**")
    st.markdown(" ".join(f"<span class='b {'mock' if s == 'MOCKED' else 'stub' if s == 'STUBBED' else ''}'>{n}: {s}</span>"
                         for n, s in [("Payments", "MOCKED"), ("Reconciliation", "MOCKED"), ("Public hosting", "STUBBED"),
                                      ("Posting adapters", "STUBBED"), ("Phase 6", "STUBBED"), ("Reddit", "STUBBED")]),
                unsafe_allow_html=True)


# ---- tactical mode -------------------------------------------------------------------
def brief_form() -> None:
    st.subheader("Founder brief")
    pasted = st.text_area("Paste full brief (labelled lines are parsed)", key="paste", height=90)
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Parse brief"):
        for k, v in parse_brief(pasted).items():
            st.session_state[f"f_{k}"] = v
    for name, col in (("weak", c2), ("strong", c3)):
        if col.button(f"Load {name.title()} Brief"):
            text = (ROOT / "briefs" / f"{name}.md").read_text(encoding="utf-8")
            for k, v in parse_brief(text).items():
                st.session_state[f"f_{k}"] = v
    run_mode = c4.selectbox("Mode", ["live", "full"], label_visibility="collapsed")
    cols = st.columns(3)
    for i, f in enumerate(FIELDS):
        cols[i % 3].text_input(f.replace("_", " ").title() + (" (required)" if f == "idea" else ""), key=f"f_{f}")
    if st.button("RUN PIPELINE", type="primary"):
        fields = {f: st.session_state.get(f"f_{f}", "") for f in FIELDS}
        if not fields["idea"].strip():
            st.error("The idea is required.")
        else:
            rid = orchestrator.start("", fields, mode=run_mode)
            st.session_state.run = rid
            advance_bg(rid)
            st.rerun()


@st.fragment(run_every=1)
def run_panel() -> None:
    rid = st.session_state.get("run")
    if not rid:
        st.info("No run yet. Fill in the brief and press RUN PIPELINE.")
        return
    run = orchestrator.load(rid)
    s = run.state
    current = gates.thresholds_sha256(s["thresholds"], run.brief_raw)
    moved = current != run.sha
    st.markdown(f"<span class='b {'red' if moved else 'live'}'>SHA-256 pre-registered: {run.sha[:16]}… "
                f"GOALPOST_MOVED: {'TRUE' if moved else 'FALSE'}</span> <span class='b'>stage: {run.stage}</span> "
                f"<span class='b'>phase {s.get('phase', 1)} / 6</span> <span class='b'>cost: $0.00 · "
                f"{llm.usage(rid).get('calls', 0)} model calls</span>", unsafe_allow_html=True)
    if s.get("override"):
        st.warning("Phases 3-5 shown as a preview after a founder override; demand not yet proven.")
    if s.get("error"):
        st.error(s["error"][:400])
    research = s.get("research", {}).get(str(s.get("variant_n", 1)), {})
    m, th = research.get("metrics"), s["thresholds"]["gate1_evidence"]
    if m:
        c1, c2 = st.columns(2)
        c1.caption(f"Evidence meter: {m['sourced_pain']} weighted pain vs ≥ {th['min_sourced_pain']}")
        c1.progress(min(1.0, m["sourced_pain"] / (2 * th["min_sourced_pain"])))
        c2.caption(f"Source coverage: {m['coverage']} vs ≥ {th['min_coverage']}")
        c2.progress(min(1.0, m["coverage"]))
    for key, title in (("gate1", "Gate 1 · evidence"), ("gate2", "Gate 2 · demand"), ("gate3", "Gate 3 · tests"),
                       ("gate4", "Gate 4 · commercial")):
        g = s.get(key)
        if g:
            st.markdown(f"**{title}** <span class='verdict {g['outcome']}'>{g['outcome'].upper()}</span> "
                        f"· {g['reason']} · {g['rule_fired']}<br>{g['recommendation']}", unsafe_allow_html=True)
    if run.stage == "await_clarify" and st.button("Confirm: digital product, no advice"):
        orchestrator.founder_decide(rid, "clarify_ok")
        advance_bg(rid)
    if run.stage in ("await_founder", "await_override"):
        b = st.columns(5)
        if b[0].button("Accept"):
            orchestrator.founder_decide(rid, "accept")
        if run.stage == "await_founder" and b[1].button("Repeat"):
            orchestrator.founder_decide(rid, "repeat")
            advance_bg(rid)
        if run.stage == "await_founder" and b[2].button("Pivot to next variant"):
            orchestrator.founder_decide(rid, "pivot")
            advance_bg(rid)
        if b[3].button("Stop"):
            orchestrator.founder_decide(rid, "stop")
        reason = st.text_input("Override reason (required, guard-checked, logged)", key="ovr")
        if b[4].button("Founder override"):
            res = orchestrator.founder_decide(rid, "override", reason)
            st.error(res["error"]) if not res.get("ok") else advance_bg(rid)
    if run.stage == "await_gate4":
        c1, c2 = st.columns(2)
        if c1.button("Approve price and policies (Gate 4)", type="primary"):
            orchestrator.founder_decide(rid, "gate4_approve")
            advance_bg(rid)
        if c2.button("Reject (Gate 4)"):
            orchestrator.founder_decide(rid, "gate4_reject")
    if s.get("debate"):
        a, k = st.columns(2)
        a.markdown("**ADVOCATE · case for GO**\n\n" + "\n".join(f"- {x['text']} {x['claim_ids']}" for x in s["debate"]["advocate"]))
        k.markdown("**SKEPTIC · case for STOP**\n\n" + "\n".join(f"- {x['text']} {x['claim_ids']}" for x in s["debate"]["skeptic"]))
    st.subheader("Waiting for your approval (hash-locked)")
    pending = approval.list_approvals(rid, "pending")
    if not pending:
        st.caption("No pending approvals.")
    for ap in pending:
        payload, ctype = approval.blob(ap.payload_sha256)
        st.markdown(f"**{ap.action}** · `{ap.id}` · payload SHA-256 `{ap.payload_sha256}`")
        with st.expander("Exact payload preview"):
            st.code(payload.decode("utf-8", "replace")[:6000], language="html" if "html" in ctype else "json")
        c1, c2 = st.columns(2)
        if c1.button("[ APPROVE (HASH-LOCKED) ]", key="ok" + ap.id, type="primary"):
            approval.decide(ap.id, True, via="ui")
            orchestrator.on_approval_decided(ap.id)
            advance_bg(rid)
        if c2.button("[ REJECT ]", key="no" + ap.id):
            approval.decide(ap.id, False, via="ui")
            orchestrator.on_approval_decided(ap.id)
    st.subheader("Evidence ledger")
    claims = sorted(run.claims(), key=lambda c: -c.weight)
    if claims:
        rows = "".join(f"<tr><td>{c.id}</td><td>{badge(c)}</td><td>{c.kind}<br><small>{c.cue_matched or '-'}</small></td>"
                       f"<td>\"{(c.quote or '')[:300]}\"<br><small style='color:#7E98AC'>{c.claim_text} {c.weight_note}</small></td>"
                       f"<td><a href='{c.url}' target='_blank'>{c.source}</a></td></tr>" for c in claims[:40])
        st.markdown(f"<table>{rows}</table>", unsafe_allow_html=True)
    st.subheader("Artifacts")
    files = sorted(p.name for p in run.dir.iterdir() if p.name.startswith(("phase", "payment")))
    if files:
        pick = st.selectbox("File", files, key="filepick")
        text = (run.dir / pick).read_text(encoding="utf-8")
        st.code(text[:12000], language="html" if pick.endswith(".html") else "markdown")
    with st.expander("Live telemetry"):
        for t in telemetry(rid)[-12:]:
            st.caption(f"[{t['phase']}] {t['kind']}: {t['text']}")


def ask_bar() -> None:
    text = st.chat_input(f"Ask {voice.assistant_name()} about this idea")
    if text:
        res = ask.handle(text, st.session_state.get("run"))
        (st.error if res.get("refused") else st.info)(res["text"])
        st.caption(voice.assistant_name() + ": " + res.get("spoken", ""))
        if res.get("start_run"):
            st.session_state.run = res["start_run"]
            advance_bg(res["start_run"])


if mode.startswith("⌨️"):
    brief_form()
    run_panel()
elif mode.startswith("🎙️"):
    hud_component.render("hud")
else:
    left, right = st.columns([1.2, 1])
    with left:
        brief_form()
        run_panel()
    with right:
        hud_component.render("hud", height=900)
ask_bar()
