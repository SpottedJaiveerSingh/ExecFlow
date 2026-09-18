import streamlit as st
from datetime import date, datetime
from models import Commitment
import json

# extraction and reconciliation
from agent import extract_actions, ActionItem
from reconciliation import reconcile_actions
import pathlib
from database import insert_action, init_db, get_all_actions, add_audit_log, get_audit_logs
import rules
from openai import OpenAI
import os
import time

st.set_page_config(page_title="ExecFlow", layout="wide")
# Guard deprecated config option for compatibility across Streamlit versions
try:
    st.set_option('deprecation.showPyplotGlobalUse', False)
except Exception:
    # option not supported in this Streamlit version
    pass

# --- UI Styling (scoped) -------------------------------------------------
st.markdown(
    """
    <style>
        :root{
                --ef-radius:8px;
                --ef-gap:12px;
                --ef-muted:#6b7280;
                --ef-card:#ffffff;
                --ef-border:#e9edf2;
            --ef-accent:#0f61ff;
                --ef-success:#0ea55a;
                --ef-warning:#d97706;
                --ef-danger:#dc2626;
                --ef-surface:#f7f9fb;
            --ef-sidebar:#eef3f8;
                --ef-font-sans: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
                --ef-line-h:1.35;
            }
    /* Page background */
        .stApp {
            background: var(--ef-surface);
            color: #0f172a;
            font-family: var(--ef-font-sans);
            -webkit-font-smoothing:antialiased;
            padding: 14px 20px;
            line-height: var(--ef-line-h);
        }
    /* Header */
    .ef-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 0}
    .ef-title{font-size:32px;font-weight:800;margin:0;color:#0b1220;line-height:1}
    .ef-sub{font-size:13px;color:var(--ef-muted);margin:0;line-height:1.2}

    /* Metric cards */
    .ef-cards{display:flex;gap:var(--ef-gap);flex-wrap:wrap}
    .ef-card{background:var(--ef-card);border:1px solid var(--ef-border);border-radius:var(--ef-radius);padding:12px 14px;min-width:180px;flex:1;box-shadow:0 1px 0 rgba(15,23,42,0.03);display:flex;align-items:center;gap:12px}
    .ef-card .icon{width:34px;height:34px;flex:0 0 34px;border-radius:6px;display:flex;align-items:center;justify-content:center;background:rgba(15,97,255,0.06)}
    .ef-card-label{color:var(--ef-muted);font-size:12px}
    .ef-card-val{font-size:18px;font-weight:700;margin-top:0}
    .ef-card-sub{font-size:12px;color:var(--ef-muted);margin-top:4px}

    /* Task card */
    .ef-task{background:var(--ef-card);border:1px solid var(--ef-border);border-radius:var(--ef-radius);padding:12px;margin-bottom:10px}
    .ef-task-title{font-weight:600;font-size:15px;margin:0;color:#071033}
    .ef-task-meta{font-size:12px;color:var(--ef-muted);margin-top:6px;display:flex;gap:12px;align-items:center}

    /* Badge */
    .ef-badge{display:inline-flex;align-items:center;gap:8px;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:0.2px}
    .ef-badge--success{background:#ecfdf5;color:var(--ef-success);border:1px solid rgba(22,163,74,0.12)}
    .ef-badge--warn{background:#fffbeb;color:var(--ef-warning);color:#92400e;border:1px solid rgba(245,158,11,0.12)}
    .ef-badge--danger{background:#fff1f2;color:var(--ef-danger);border:1px solid rgba(239,68,68,0.12)}
    .ef-badge--info{background:#eef2ff;color:var(--ef-accent);border:1px solid rgba(15,98,254,0.08)}

    /* Table tweaks */
    .stDataFrame table {border-collapse:separate;border-spacing:0 8px}
    .stDataFrame th{background:transparent;color:var(--ef-muted);font-weight:700;padding:8px 12px;text-align:left}
    .stDataFrame td{background:transparent;padding:8px 12px;border-radius:6px}
    .stDataFrame tbody tr td{background:var(--ef-card)}
    .stDataFrame tbody tr{box-shadow:0 1px 0 rgba(15,23,42,0.02);border-radius:6px}

    /* Buttons */
    .stButton>button{background:linear-gradient(180deg, rgba(15,97,255,1), rgba(12,76,200,1));color:#fff;border:0;padding:8px 12px;border-radius:8px;font-weight:700;box-shadow:0 2px 6px rgba(15,23,42,0.04);transition:transform .06s ease,box-shadow .06s ease}
    .stButton>button:disabled{opacity:0.6}
    .stButton>button:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(15,23,42,0.08)}

    /* Expander header styling (our rendered expanders will inherit) */
    .streamlit-expanderHeader{font-weight:600}
    .stExpander{border-radius:var(--ef-radius);overflow:hidden}

    /* Sidebar compact */
    /* Make sidebar visually match the main surface and share font */
    [data-testid="stSidebar"] .sidebar-content, .stSidebar, .css-1d391kg {
        background: var(--ef-sidebar) !important;
        color: #0b1220 !important;
        font-family: var(--ef-font-sans) !important;
        padding: 12px !important;
        border-radius: calc(var(--ef-radius) - 2px) !important;
    }
    /* Agent workflow steps bar */
    .ef-steps{display:flex;gap:8px;align-items:flex-start;overflow:auto;padding:8px 4px}
    .ef-step{background:transparent;min-width:120px;padding:8px;border-radius:8px;border:1px solid transparent;display:flex;flex-direction:column;align-items:flex-start;gap:6px}
    .ef-step .label{font-weight:700;font-size:12px;color:#071033}
    .ef-step .sub{font-size:11px;color:var(--ef-muted)}
    .ef-step--pending{background:transparent;border-color:transparent}
    .ef-step--running{background:rgba(15,97,255,0.06);border-color:rgba(15,97,255,0.12)}
    .ef-step--completed{background:rgba(14,165,90,0.06);border-color:rgba(14,165,90,0.12)}
    .ef-step .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
    .ef-step--pending .dot{background:#94a3b8}
    .ef-step--running .dot{background:#0f61ff}
    .ef-step--completed .dot{background:#0ea55a}
    /* Main ribbon styles */
    .ef-steps-main{display:flex;align-items:center;gap:18px;padding:12px 10px;border-radius:10px;background:linear-gradient(180deg,#ffffff, #fbfdff);box-shadow:0 2px 6px rgba(15,23,42,0.03);margin-bottom:18px;max-width:100%;box-sizing:border-box;overflow-x:auto;-webkit-overflow-scrolling:touch}
    .ef-step-main{flex:0 0 150px;min-width:120px;padding:8px 12px;border-radius:10px;background:transparent;border:1px solid rgba(11,17,34,0.02);display:flex;flex-direction:column;gap:6px;box-sizing:border-box}
    .ef-step-main--pending .label{color:#324158}
    .ef-step-main--running{background:rgba(15,97,255,0.04);border-color:rgba(15,97,255,0.08)}
    .ef-step-main--completed{background:rgba(14,165,90,0.04);border-color:rgba(14,165,90,0.08)}
    .ef-step-main .label{font-weight:700;font-size:13px}
    .ef-step-main .sub{font-size:12px;color:var(--ef-muted)}
    .ef-connector{width:24px;height:2px;background:linear-gradient(90deg,rgba(15,97,255,0.12),rgba(14,165,90,0.10));border-radius:2px;flex:0 0 auto}
    /* reduce step size on narrow viewports to avoid overflow */
    @media (max-width: 980px) {
        .ef-step-main{flex:0 0 120px;min-width:100px;padding:6px 10px}
    }
    /* Steps table */
    .ef-steps-table{width:100%;border-collapse:collapse;margin:10px 0;background:transparent}
    .ef-steps-table th{background:transparent;color:#334155;text-align:left;padding:8px 12px;font-size:12px}
    .ef-steps-table td{padding:10px 12px;border-top:1px solid rgba(11,17,34,0.04);background:var(--ef-card);border-radius:6px}
    .ef-steps-table tbody tr td:first-child{width:220px}
    /* Ensure the sidebar header and controls use the same typography */
    [data-testid="stSidebar"] .css-1d391kg, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] label {
        font-family: var(--ef-font-sans) !important;
        color: #0b1220 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Small UI helpers (presentation-only)
def ef_metric(label: str, value: str, sub: str = ""):
    st.markdown(f"<div class=\"ef-card\">\n  <div class=\"ef-card-label\">{label}</div>\n  <div class=\"ef-card-val\">{value}</div>\n  <div class=\"ef-card-sub\">{sub}</div>\n</div>", unsafe_allow_html=True)

def ef_badge(text: str, kind: str = "info") -> str:
    k = "ef-badge--info"
    color = "#0f61ff"
    if kind == "success":
        k = "ef-badge--success"
        color = "#0ea55a"
    elif kind == "warn":
        k = "ef-badge--warn"
        color = "#d97706"
    elif kind == "danger":
        k = "ef-badge--danger"
        color = "#dc2626"
    # small colored dot + text for better affordance
    dot = f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:8px;vertical-align:middle'></span>"
    return f"<span class=\"ef-badge {k}\">{dot}<span style='vertical-align:middle'>{text}</span></span>"


def ef_badge_kind(status_text: str) -> str:
    try:
        s = (status_text or "").strip().lower()
    except Exception:
        return 'info'
    if s == 'completed':
        return 'success'
    if 'unclear' in s:
        return 'warn'
    if s in ('upcoming', 'due today'):
        return 'warn'
    return 'info'


def render_agent_steps_html(steps: dict, main: bool = False) -> str:
    """Return HTML for agent steps. If main=True use the wide ribbon style."""
    container = 'ef-steps-main' if main else 'ef-steps'
    item_cls = 'ef-step-main' if main else 'ef-step'
    html = [f'<div class="{container}">']
    total = len(steps)
    i = 0
    for name, status in steps.items():
        i += 1
        state = 'pending'
        if status and status.startswith('running'):
            state = 'running'
        elif status and (status.startswith('completed') or status.startswith('stored') or status == 'ok'):
            state = 'completed'
        friendly = status
        if isinstance(status, str) and status.startswith('issues:'):
            friendly = status.split(':',1)[1] + ' issues'
        # add connector for main ribbon except after last
        connector = ''
        if main and i < total:
            connector = '<div class="ef-connector" aria-hidden></div>'
        html.append(f'<div class="{item_cls} {item_cls}--{state}"><div style="display:flex;align-items:center;gap:10px"><span class="dot"></span><div class="label">{name}</div></div><div class="sub">{friendly or "pending"}</div></div>' + connector)
    html.append('</div>')
    return ''.join(html)

# small spacer placeholder (header rendered after sidebar to access sim_date)
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# Use a repository-relative data directory so the app works both locally and when deployed
DATA_DIR = pathlib.Path(__file__).parent / "data"


def _seed_db_from_data(simulation_date: date):
    """If the DB has no rows, ingest the example data files and store reconciled actions.
    This is a safe, idempotent seeding step to ensure the deployed app has initial data to show.
    It uses the same extraction and reconciliation pipeline and preserves evidence.
    """
    try:
        init_db()
        existing = get_all_actions()
        if existing:
            return 0
        all_items: list[ActionItem] = []
        for fp in DATA_DIR.glob("*.txt"):
            content = fp.read_text(encoding="utf-8")
            source_type = fp.stem
            items = extract_actions(content, source_type=source_type, simulation_date=simulation_date)
            for it in items:
                it.source = source_type
                it.source_date = _find_date_in_text(content)
            all_items.extend(items)
        reconciled = reconcile_actions(all_items)
        saved = 0
        for r in reconciled:
            insert_action(
                action=r.action or "",
                owner=r.owner,
                related_person=r.related_person,
                deadline=r.deadline,
                status=r.status,
                source_type=r.source_type or r.source,
                source_date=r.source_date,
                evidence=r.evidence,
                confidence=r.confidence,
            )
            saved += 1
        add_audit_log(f"DB seeded: saved {saved} actions from data/")
        return saved
    except Exception as e:
        add_audit_log(f"DB seed failed: {e}")
        return 0

# Executive name constant
EXECUTIVE_NAME = "Arjun Malhotra"

with st.sidebar:
    st.header("Filters")
    # Simulation date radio for the exercise week 21–25 Sep 2026
    sim_choice = st.radio(
        "SIMULATION DATE",
        (
            "21 Sep 2026",
            "22 Sep 2026",
            "23 Sep 2026",
            "24 Sep 2026",
            "25 Sep 2026",
        ),
        index=2,
    )
    mapping = {
        "21 Sep 2026": date(2026, 9, 21),
        "22 Sep 2026": date(2026, 9, 22),
        "23 Sep 2026": date(2026, 9, 23),
        "24 Sep 2026": date(2026, 9, 24),
        "25 Sep 2026": date(2026, 9, 25),
    }
    sim_date = mapping.get(sim_choice, date(2026, 9, 23))
    sources = st.multiselect(
        "Source filters",
        options=["All", "Neha Kapoor", "Raghav Sethi", "Divya Rao", "Priya Nair", "Facilities"],
        default=["All"],
    )

# --- Header (visual only) ------------------------------------------------
st.markdown('<div class="ef-header">\n  <div>\n    <div class="ef-title">ExecFlow</div>\n    <div class="ef-sub">Executive Productivity Agent</div>\n  </div>\n  <div style="text-align:right">\n    <div style="font-size:12px;color:var(--ef-muted)">Simulation: ' + sim_date.strftime('%d %b %Y') + '</div>\n  </div>\n</div>', unsafe_allow_html=True)

# show executive & simulation header after sidebar input is resolved (Executive below title)
st.markdown(f"**Executive:** {EXECUTIVE_NAME}")
st.markdown(f"**Simulation Date:** {sim_date.strftime('%d %b %Y')}")

# small spacer
st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# Ensure agent_steps exists
if "agent_steps" not in st.session_state:
    st.session_state.agent_steps = {s: "pending" for s in [
        "INGEST",
        "UNDERSTAND",
        "EXTRACT",
        "RECONCILE",
        "VALIDATE",
        "STORE",
        "MONITOR",
        "BRIEF",
        "ANSWER",
    ]}

# Render the main ribbon under the header for visual clarity
st.markdown(render_agent_steps_html(st.session_state.agent_steps, main=True), unsafe_allow_html=True)

# Sidebar navigation
page = st.sidebar.radio("EXECFLOW", ["Daily Brief", "Action Center", "Source Explorer", "Ask ExecFlow", "Audit Log"], index=0)

# Agent workflow UI in sidebar (compact)
with st.sidebar.expander("Agent Workflow", expanded=True):
    st.write("Agentic pipeline — visual ribbon is shown above the dashboard.")
    st.markdown("<div style='display:flex;gap:12px;align-items:center;margin-top:8px'><span style='width:10px;height:10px;background:#94a3b8;border-radius:50%;display:inline-block'></span><small style='margin-right:8px;color:var(--ef-muted)'>Pending</small><span style='width:10px;height:10px;background:#0f61ff;border-radius:50%;display:inline-block'></span><small style='margin-right:8px;color:var(--ef-muted)'>Running</small><span style='width:10px;height:10px;background:#0ea55a;border-radius:50%;display:inline-block'></span><small style='color:var(--ef-muted)'>Completed</small></div>", unsafe_allow_html=True)
    auto_store = st.checkbox("Auto-store results after pipeline", value=False)
    if st.button("Run Agent Pipeline"):
        st.session_state.run_agent = True
    if st.button("Reset Agent State"):
        for k in st.session_state.agent_steps:
            st.session_state.agent_steps[k] = "pending"
        st.session_state.run_agent = False

def _update_step(name: str, status: str):
    st.session_state.agent_steps[name] = status
    add_audit_log(f"Agent step {name}: {status}")

# Compute metrics from the database (deterministic, no hardcoded numbers)
if page == "Daily Brief":
    # Agent explanation
    with st.expander("Why this is agentic — click to expand", expanded=False):
        st.write(
            "I designed it as an agentic workflow rather than simply asking an LLM to summarize the data. "
            "Each step performs a focused role (INGEST, UNDERSTAND, EXTRACT, RECONCILE, VALIDATE, STORE, MONITOR, BRIEF, ANSWER) "
            "so outputs are auditable, deterministic where required, and conservative about ownership and deadlines."
        )

    # small caption: detailed step view is available in the sidebar
    st.markdown("<div style='margin:6px 0 10px 0;color:var(--ef-muted);font-size:13px'>Detailed step statuses are available in the sidebar.</div>", unsafe_allow_html=True)

    # If user has requested a run, execute pipeline
    if st.session_state.get("run_agent"):
        st.info("Agent pipeline running — check Audit Log for details.")
        # Execute pipeline steps sequentially
        data_dir = pathlib.Path("data")
        # INGEST
        _update_step("INGEST", "running")
        all_texts = []
        for fp in data_dir.glob("*.txt"):
            all_texts.append((fp.stem, fp.read_text(encoding="utf-8")))
        _update_step("INGEST", "completed")

        # UNDERSTAND (placeholder — uses extract_actions for NLU)
        _update_step("UNDERSTAND", "running")
        understood = []
        for source, text in all_texts:
            items = extract_actions(text, source_type=source, simulation_date=sim_date)
            for it in items:
                it.source = source
                it.source_date = _find_date_in_text(text)
            understood.extend(items)
        _update_step("UNDERSTAND", "completed")

        # EXTRACT
        _update_step("EXTRACT", "running")
        extracted = understood
        _update_step("EXTRACT", "completed")

        # RECONCILE
        _update_step("RECONCILE", "running")
        reconciled = reconcile_actions(extracted)
        _update_step("RECONCILE", "completed")

        # VALIDATE
        _update_step("VALIDATE", "running")
        issues = []
        for r in reconciled:
            if (not r.owner) or (not r.deadline):
                issues.append({"action": r.action, "owner": r.owner, "deadline": r.deadline})
        if issues:
            add_audit_log(f"Validation found {len(issues)} issues (missing owner/deadline)")
            _update_step("VALIDATE", f"issues:{len(issues)}")
        else:
            _update_step("VALIDATE", "ok")

        # STORE
        _update_step("STORE", "running")
        stored = 0
        if auto_store:
            init_db()
            for r in reconciled:
                insert_action(
                    action=r.action or "",
                    owner=r.owner,
                    related_person=r.related_person,
                    deadline=r.deadline,
                    status=r.status,
                    source_type=r.source_type,
                    source_date=r.source_date,
                    evidence=r.evidence,
                    confidence=r.confidence,
                )
                stored += 1
            add_audit_log(f"Agent stored {stored} actions to DB")
            _update_step("STORE", f"stored:{stored}")
        else:
            _update_step("STORE", "skipped")

        # MONITOR
        _update_step("MONITOR", "running")
        # For now monitoring is audit-log based
        add_audit_log("Agent monitoring checkpoint")
        _update_step("MONITOR", "ok")

        # BRIEF
        _update_step("BRIEF", "running")
        # Refresh counts by reloading DB if stored
        init_db()
        rows = get_all_actions()
        _update_step("BRIEF", f"rows:{len(rows)}")

        # ANSWER
        _update_step("ANSWER", "ready")
        st.success("Agent pipeline completed — see Audit Log and Daily Brief.")
        st.session_state.run_agent = False
    init_db()  # ensure DB and table exist
    rows = get_all_actions()
    # If DB is empty on a fresh deploy, seed it from the repo data files so the UI shows content
    if not rows:
        seeded = _seed_db_from_data(sim_date)
        if seeded:
            rows = get_all_actions()

    # derive counts using rules and classifications
    my_actions = []
    waiting_on_others = []
    overdue_items = []
    unclear_ownership = []

    for r in rows:
        owner = r.get("owner")
        deadline = r.get("deadline")
        status_field = r.get("status")
        # treat certain status strings as completed
        completed = bool(status_field and isinstance(status_field, str) and status_field.lower() == "completed")

        status = rules.calculate_status(deadline, sim_date, completed)
        ownership_status = rules.determine_ownership_status(owner)
        classification = rules.classify_action(owner, EXECUTIVE_NAME)

        if classification == "My Action" and status != "Completed":
            my_actions.append(r)
        if classification == "Waiting on Others" and status != "Completed":
            waiting_on_others.append(r)
        # determine overdue via the rules function (returns True/False/'No deadline')
        od = rules.determine_overdue(deadline, sim_date)
        if od is True and status != "Completed":
            overdue_items.append(r)
        if ownership_status == "Unclear ownership":
            unclear_ownership.append(r)

    # Metric cards (visual only)
    c1, c2, c3, c4 = st.columns([1,1,1,1])
    # include small icons in metric cards
    icon_user = "<svg class='icon' viewBox='0 0 24 24' width='20' height='20' fill='none' xmlns='http://www.w3.org/2000/svg'><path d='M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5z' fill='#0f61ff'/><path d='M4 20c0-3.31 2.69-6 6-6h4c3.31 0 6 2.69 6 6v1H4v-1z' fill='#dbeafe'/></svg>"
    icon_wait = "<svg class='icon' viewBox='0 0 24 24' width='20' height='20' fill='none' xmlns='http://www.w3.org/2000/svg'><circle cx='12' cy='12' r='10' fill='#fff4e6'/><path d='M12 7v6l4 2' stroke='#d97706' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>"
    icon_over = "<svg class='icon' viewBox='0 0 24 24' width='20' height='20' fill='none' xmlns='http://www.w3.org/2000/svg'><rect x='3' y='3' width='18' height='18' rx='4' fill='#fff1f2'/><path d='M8 12h8' stroke='#dc2626' stroke-width='1.6' stroke-linecap='round'/></svg>"
    icon_warn = "<svg class='icon' viewBox='0 0 24 24' width='20' height='20' fill='none' xmlns='http://www.w3.org/2000/svg'><path d='M12 2l10 18H2L12 2z' fill='#fffbeb'/><path d='M12 9v4' stroke='#d97706' stroke-width='1.6' stroke-linecap='round'/><path d='M12 17h.01' stroke='#d97706' stroke-width='1.6' stroke-linecap='round'/></svg>"
    c1.markdown(f"<div class='ef-card'>{icon_user}<div><div class='ef-card-label'>My Actions</div><div class='ef-card-val'>{len(my_actions)}</div><div class='ef-card-sub'>Assigned to you</div></div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='ef-card'>{icon_wait}<div><div class='ef-card-label'>Waiting</div><div class='ef-card-val'>{len(waiting_on_others)}</div><div class='ef-card-sub'>Awaiting responses</div></div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='ef-card'>{icon_over}<div><div class='ef-card-label'>Overdue</div><div class='ef-card-val'>{len(overdue_items)}</div><div class='ef-card-sub'>Past due items</div></div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='ef-card'>{icon_warn}<div><div class='ef-card-label'>Unclear Ownership</div><div class='ef-card-val'>{len(unclear_ownership)}</div><div class='ef-card-sub'>Needs assignment</div></div></div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<h3 style='margin:0 0 8px 0'>Top Actions</h3>", unsafe_allow_html=True)
    # Show a compact list of actions with key metadata
    if my_actions:
        for r in my_actions[:10]:
            owner = r.get('owner') or 'Unclear'
            dl = r.get('deadline') or 'No deadline'
            status = (r.get('status') or 'Unknown')
            badge_kind = 'info'
            if isinstance(status, str) and status.lower() == 'completed':
                badge_kind = 'success'
            elif isinstance(status, str) and ('unclear' in status.lower() or 'unclear' in (owner or '').lower()):
                # unclear ownership should use attention/warning treatment
                badge_kind = 'warn'
            elif isinstance(status, str) and status.lower() in ('upcoming', 'due today'):
                badge_kind = 'warn'
            st.markdown("<div class='ef-task'>", unsafe_allow_html=True)
            st.markdown(f"<div class='ef-task-title'>{r.get('action')}</div>", unsafe_allow_html=True)
            meta = f"Owner: {owner} &nbsp; • &nbsp; Deadline: {dl} &nbsp; • &nbsp; {ef_badge(status, badge_kind)}"
            st.markdown(f"<div class='ef-task-meta'>{meta}</div>", unsafe_allow_html=True)
            with st.expander("Evidence & Context", expanded=False):
                if r.get('evidence'):
                    st.write(r.get('evidence'))
                st.write("Source:", r.get('source_type') or r.get('source'))
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No assigned actions found.")

    st.markdown("---")
    st.markdown("<h3 style='margin:0 0 8px 0'>Waiting & Overdue</h3>", unsafe_allow_html=True)
    # Combine waiting and overdue into two columns
    wcol, ocol = st.columns(2)
    with wcol:
        st.subheader("Waiting on Others")
        if waiting_on_others:
            for r in waiting_on_others[:10]:
                owner = r.get('owner') or r.get('related_person') or 'Unclear'
                st.markdown(f"<div class='ef-task'><div class='ef-task-title'>{r.get('action')}</div><div class='ef-task-meta'>Waiting for: {owner} &nbsp; • &nbsp; {r.get('deadline') or 'No deadline'}</div></div>", unsafe_allow_html=True)
        else:
            st.info("No items waiting on others.")

    with ocol:
        st.subheader("Overdue Items")
        if overdue_items:
            for r in overdue_items[:10]:
                st.markdown(f"<div class='ef-task'><div class='ef-task-title'>{r.get('action')}</div><div class='ef-task-meta'>Due: {r.get('deadline') or 'Unknown'} &nbsp; • &nbsp; Owner: {r.get('owner') or 'Unclear'}</div></div>", unsafe_allow_html=True)
        else:
            st.info("No overdue items.")

    st.markdown("---")
    st.subheader("Completed / History")
    completed = [r for r in rows if isinstance(r.get('status'), str) and r.get('status').lower() == 'completed']
    if completed:
        for r in completed[:20]:
            st.markdown(f"- {r.get('action')} — Completed (Owner: {r.get('owner') or 'Unclear'})")
    else:
        st.info("No completed items recorded.")

elif page == "Action Center":
    st.header("Action Center — All actions")
    rows = get_all_actions()
    import pandas as pd

    df = pd.DataFrame(rows)
    # basic filters
    owner_filter = st.text_input("Filter by owner (leave empty for all)")
    status_filter = st.text_input("Filter by status (leave empty for all)")
    if owner_filter:
        df = df[df["owner"].fillna("").str.contains(owner_filter, case=False)]
    if status_filter:
        df = df[df["status"].fillna("").str.contains(status_filter, case=False)]
    # show a compact dataframe for scanning, and list with expanders for details
    st.dataframe(df, height=240)
    st.markdown("---")
    st.markdown("<div style='display:flex;justify-content:space-between;align-items:center'><h3 style='margin:0'>Actions (details)</h3><small style='color:var(--ef-muted)'>Click to expand evidence</small></div>", unsafe_allow_html=True)
    for idx, row in df.head(50).iterrows():
        action = row.get('action') or '(no action)'
        owner = row.get('owner') or 'Unclear'
        dl = row.get('deadline') or 'No deadline'
        status = row.get('status') or 'Unknown'
        with st.expander(action):
            kind = ef_badge_kind(status)
            st.markdown(f"**Owner:** {owner}  &nbsp; • &nbsp; **Deadline:** {dl}  &nbsp; • &nbsp; {ef_badge(status, kind)}")
            if row.get('evidence'):
                st.markdown("**Evidence & Context**")
                st.write(row.get('evidence'))

elif page == "Source Explorer":
    st.header("Source Explorer")
    data_dir = pathlib.Path("data")
    for fp in data_dir.glob("*.txt"):
        with st.expander(fp.name):
            st.code(fp.read_text(encoding="utf-8"))

    # Keep extraction UI here as well
    st.markdown("---")
    st.subheader("Run Extraction & Reconciliation")
    if st.button("Extract from data files (Source Explorer)"):
        all_items: list[ActionItem] = []
        add_audit_log("Data ingestion started")
        for fp in data_dir.glob("*.txt"):
            content = fp.read_text(encoding="utf-8")
            source_type = fp.stem  # e.g., 'emails', 'meeting'
            items = extract_actions(content, source_type=source_type, simulation_date=sim_date)
            # Attach simple source metadata
            for it in items:
                it.source = f"{source_type}"
                it.source_date = _find_date_in_text(content)
            all_items.extend(items)

        add_audit_log(f"Data ingested: {len(list(data_dir.glob('*.txt')))} files")
        reconciled = reconcile_actions(all_items)
        add_audit_log(f"Extraction complete: {len(all_items)} candidate actions, {len(reconciled)} reconciled")
        st.write(f"Found {len(all_items)} extracted items → {len(reconciled)} reconciled actions")
        for r in reconciled:
            with st.expander(r.action or "(no action)"):
                st.write("**Owner:**", r.owner or "Unclear")
                st.write("**Related person:**", r.related_person or "-")
                st.write("**Deadline:**", r.deadline or "-")
                st.write("**Status:**", r.status or "-")
                st.write("**Confidence:**", f"{r.confidence:.2f}")
                st.write("**Source:**", r.source_type or r.source or "-")
                if r.evidence:
                    if st.button(f"View Evidence — {r.action[:40]}", key=f"evi-{hash(r.evidence)}"):
                        st.markdown("**Evidence pieces:**")
                        for piece in (r.evidence.split('\n---\n')):
                            st.write("- Date:", _find_date_in_text(piece))
                            st.write("- Original evidence:")
                            st.code(piece)

        unclear_count = sum(1 for r in reconciled if r.status and r.status.lower() == 'unclear_ownership')
        add_audit_log(f"Reconciliation: {len(reconciled)} merged actions, {unclear_count} unclear ownership detected")
        if st.button("Save reconciled actions to DB (Source Explorer)"):
            init_db()
            saved = 0
            for r in reconciled:
                insert_action(
                    action=r.action or "",
                    owner=r.owner,
                    related_person=r.related_person,
                    deadline=r.deadline,
                    status=r.status,
                    source_type=r.source_type,
                    source_date=r.source_date,
                    evidence=r.evidence,
                    confidence=r.confidence,
                )
                saved += 1
            add_audit_log(f"Saved {saved} reconciled actions to DB")
            st.success(f"Saved {saved} actions to the database.")

elif page == "Ask ExecFlow":
    # reuse Ask ExecFlow block
    st.markdown("---")
    st.header("Ask ExecFlow")
    question = st.text_input("Ask ExecFlow", placeholder="e.g., What did I promise Raghav?", key="ask_page")
    if st.button("Ask") and question:
        add_audit_log(f"Ask: {question}")
        # simple retrieval from DB based on question
        q_lower = question.lower()
        candidate_rows = get_all_actions()
        selected = []
        if "raghav" in q_lower:
            for r in candidate_rows:
                if r.get("related_person") and "raghav" in (r.get("related_person") or "").lower():
                    selected.append(r)
        elif "what needs action today" in q_lower or "today" in q_lower:
            for r in candidate_rows:
                dl = r.get("deadline")
                due = rules.determine_due_today(dl, sim_date)
                if due is True and (not r.get("status") or r.get("status").lower() != "completed"):
                    selected.append(r)
        else:
            # fallback: return top open items for the executive
            for r in candidate_rows:
                owner = r.get("owner")
                if owner and owner.lower() == EXECUTIVE_NAME.lower() and (not r.get("status") or r.get("status").lower() != "completed"):
                    selected.append(r)

        actions_json = [
            {
                "action": r.get("action"),
                "owner": r.get("owner"),
                "related_person": r.get("related_person"),
                "deadline": r.get("deadline"),
                "status": r.get("status"),
                "source": r.get("source_type") or r.get("source"),
                "evidence": r.get("evidence"),
            }
            for r in selected
        ]

        openai_key = os.environ.get("OPENAI_API_KEY")
        answer_text = ""
        if openai_key:
            try:
                client = OpenAI()
                prompt = f"You are given a question and a list of structured actions as JSON. Answer concisely. Question: {question}\nActions: {json.dumps(actions_json)}"
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], max_tokens=400)
                choices = resp.get("choices") if isinstance(resp, dict) else None
                if choices:
                    answer_text = choices[0]["message"]["content"] if isinstance(choices[0]["message"].get("content"), str) else choices[0]["message"]["content"]["text"]
                else:
                    answer_text = str(resp)
            except Exception:
                answer_text = "(LLM unavailable) " + "\n".join([f"- {a['action']} (Owner: {a['owner']})" for a in actions_json])
        else:
            answer_text = "\n".join([f"- {a['action']} — Owner: {a['owner']} — Deadline: {a['deadline']} — Source: {a['source']}" for a in actions_json])

        st.subheader("Answer")
        st.write(answer_text)
        add_audit_log(f"Ask completed: returned {len(actions_json)} actions")

elif page == "Audit Log":
    st.header("Audit Log")
    logs = get_audit_logs(500)
    for entry in logs:
        st.write(f"{entry['ts']}: {entry['message']}")

st.markdown("---")
st.header("Today's Action Brief")
st.info("No data connected yet — this area will summarize today's prioritized actions.")

st.markdown("### Ask ExecFlow (Quick)")
query = st.text_input("Ask ExecFlow (Quick)", placeholder="e.g., What needs my attention today?", key="ask_quick")
st.button("Submit", key="ask_quick_submit")
if st.session_state.get("ask_quick_submit") and query:
    question = query
    add_audit_log(f"Ask quick: {question}")
    # simple retrieval from DB based on question (reuse Ask ExecFlow logic)
    q_lower = question.lower()
    candidate_rows = get_all_actions()
    selected = []
    if "raghav" in q_lower:
        for r in candidate_rows:
            if r.get("related_person") and "raghav" in (r.get("related_person") or "").lower():
                selected.append(r)
    elif "what needs action today" in q_lower or "today" in q_lower:
        for r in candidate_rows:
            dl = r.get("deadline")
            due = rules.determine_due_today(dl, sim_date)
            if due is True and (not r.get("status") or r.get("status").lower() != "completed"):
                selected.append(r)
    else:
        for r in candidate_rows:
            owner = r.get("owner")
            if owner and owner.lower() == EXECUTIVE_NAME.lower() and (not r.get("status") or r.get("status").lower() != "completed"):
                selected.append(r)

    actions_json = [
        {
            "action": r.get("action"),
            "owner": r.get("owner"),
            "related_person": r.get("related_person"),
            "deadline": r.get("deadline"),
            "status": r.get("status"),
            "source": r.get("source_type") or r.get("source"),
            "evidence": r.get("evidence"),
        }
        for r in selected
    ]

    openai_key = os.environ.get("OPENAI_API_KEY")
    answer_text = ""
    if openai_key and len(actions_json) > 0:
        try:
            client = OpenAI(api_key=openai_key)
            prompt = f"You are given a question and a list of structured actions as JSON. Answer concisely. Question: {question}\nActions: {json.dumps(actions_json)}"
            resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=300)
            choices = resp.get("choices") if isinstance(resp, dict) else None
            if choices:
                answer_text = choices[0]["message"]["content"] if isinstance(choices[0]["message"].get("content"), str) else choices[0]["message"]["content"]["text"]
            else:
                answer_text = str(resp)
        except Exception:
            answer_text = "(LLM unavailable) " + "\n".join([f"- {a['action']} (Owner: {a['owner']})" for a in actions_json])
    else:
        if actions_json:
            answer_text = "\n".join([f"- {a['action']} — Owner: {a['owner']} — Deadline: {a['deadline']} — Source: {a['source']}" for a in actions_json])
        else:
            answer_text = "No matching actions found."

    st.subheader("Answer")
    st.write(answer_text)
    add_audit_log(f"Ask quick completed: returned {len(actions_json)} actions")

# Example: show the structured Commitment model derived from messy sources
if st.button("Show example mapping"):
    example = Commitment.parse_obj(Commitment.Config.schema_extra["example"])  # type: ignore
    st.subheader("Example structured commitment")
    st.json(json.loads(example.json()))


def _find_date_in_text(text: str) -> str:
    """Try to find a human-readable date in the text. Return 'Unknown' if not found."""
    if not text:
        return "Unknown"
    # Look for ISO
    m = None
    import re

    m = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if m:
        return m.group(0)
    # Look for '22 Sep 2026' or '21 September 2026'
    m = re.search(r"\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b", text, re.I)
    if m:
        return m.group(0)
    # Look for weekday + time lines like 'Wed 23 Sep, 1:30 PM'
    m = re.search(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\s+\d{1,2}\s+Sep\s*,?\s*\d{1,2}:\d{2}\s*(AM|PM)?", text, re.I)
    if m:
        return m.group(0)
    return "Unknown"


st.markdown("---")
st.subheader("Run Extraction & Reconciliation")
data_dir = pathlib.Path("data")
if st.button("Extract from data files"):
    all_items: list[ActionItem] = []
    add_audit_log("Data ingestion started")
    for fp in data_dir.glob("*.txt"):
        content = fp.read_text(encoding="utf-8")
        source_type = fp.stem  # e.g., 'emails', 'meeting'
        items = extract_actions(content, source_type=source_type, simulation_date=sim_date)
        # Attach simple source metadata
        for it in items:
            it.source = f"{source_type}"
            it.source_date = _find_date_in_text(content)
        all_items.extend(items)

    add_audit_log(f"Data ingested: {len(list(data_dir.glob('*.txt')))} files")

    # Reconcile duplicates
    reconciled = reconcile_actions(all_items)
    add_audit_log(f"Extraction complete: {len(all_items)} candidate actions, {len(reconciled)} reconciled")

    st.write(f"Found {len(all_items)} extracted items → {len(reconciled)} reconciled actions")

    for r in reconciled:
        with st.expander(r.action or "(no action)"):
            st.write("**Owner:**", r.owner or "Unclear")
            st.write("**Related person:**", r.related_person or "-")
            st.write("**Deadline:**", r.deadline or "-")
            st.write("**Status:**", r.status or "-")
            st.write("**Confidence:**", f"{r.confidence:.2f}")
            st.write("**Source:**", r.source_type or r.source or "-")
            if r.evidence:
                if st.button(f"View Evidence — {r.action[:40]}", key=f"evi-{hash(r.evidence)}"):
                    st.markdown("**Evidence pieces:**")
                    for piece in (r.evidence.split('\n---\n')):
                        st.write("- Date:", _find_date_in_text(piece))
                        st.write("- Original evidence:")
                        st.code(piece)

    # Count unclear ownership detections
    unclear_count = sum(1 for r in reconciled if r.status and r.status.lower() == 'unclear_ownership')
    add_audit_log(f"Reconciliation: {len(reconciled)} merged actions, {unclear_count} unclear ownership detected")

    # Offer to save reconciled actions to DB
    if st.button("Save reconciled actions to DB"):
        init_db()
        saved = 0
        for r in reconciled:
            insert_action(
                action=r.action or "",
                owner=r.owner,
                related_person=r.related_person,
                deadline=r.deadline,
                status=r.status,
                source_type=r.source_type,
                source_date=r.source_date,
                evidence=r.evidence,
                confidence=r.confidence,
            )
            saved += 1
        add_audit_log(f"Saved {saved} reconciled actions to DB")
        st.success(f"Saved {saved} actions to the database.")


# (Ask ExecFlow is implemented on its dedicated page; quick ask is available above.)
