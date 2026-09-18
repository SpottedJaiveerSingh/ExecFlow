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

st.title("EXECFLOW")
st.subheader("Executive Daily Action Brief")

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

# show executive & simulation header after sidebar input is resolved
st.markdown(f"**Executive:** {EXECUTIVE_NAME}")
st.markdown(f"**Simulation Date:** {sim_date.strftime('%d %b %Y')}")

# Sidebar navigation
page = st.sidebar.radio("EXECFLOW", ["Daily Brief", "Action Center", "Source Explorer", "Ask ExecFlow", "Audit Log"], index=0)

# Agent workflow UI in sidebar
with st.sidebar.expander("Agent Workflow", expanded=True):
    st.write("Agentic pipeline: INGEST → UNDERSTAND → EXTRACT → RECONCILE → VALIDATE → STORE → MONITOR → BRIEF → ANSWER")
    # initialize session state for steps
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

    # show small stepper status
    cols = st.columns(len(st.session_state.agent_steps))
    for i, (k, v) in enumerate(st.session_state.agent_steps.items()):
        cols[i].markdown(f"**{k}**\n- {v}")

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

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("MY ACTIONS", str(len(my_actions)))
    col2.metric("WAITING", str(len(waiting_on_others)))
    col3.metric("OVERDUE", str(len(overdue_items)))
    col4.metric("UNCLEAR", str(len(unclear_ownership)))

    st.markdown("---")
    st.header("My Actions")
    for r in my_actions:
        st.write(f"- {r.get('action')} \n  Owner: {r.get('owner')}")

    st.markdown("---")
    st.header("Waiting on Others")
    for r in waiting_on_others:
        st.write(f"- {r.get('action')} \n  Waiting for: {r.get('owner') or r.get('related_person')}")

    st.markdown("---")
    st.header("Completed / History")
    completed = [r for r in rows if isinstance(r.get('status'), str) and r.get('status').lower() == 'completed']
    for r in completed:
        st.write(f"- {r.get('action')} — Completed (Owner: {r.get('owner')})")

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
    st.dataframe(df)

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
    question = st.text_input("Ask ExecFlow", placeholder="e.g., What did I promise Raghav?")
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

if query:
    st.write("(No AI connected yet) You asked:", query)

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
