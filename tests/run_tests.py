import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from agent import extract_actions
from reconciliation import reconcile_actions
import database
import rules


def reset_db():
    if database.DB_PATH.exists():
        database.DB_PATH.unlink()
    database.init_db()


SIM_DATE = date(2026, 9, 22)  # simulation reference date


def run_test_duplicate():
    texts = [
        ("I will send the updated vendor list to Raghav by tomorrow morning.", "meeting"),
        ("Please find the updated vendor list attached — will send to Raghav tomorrow.", "email"),
        ("I will send Raghav the updated vendor list tomorrow morning.", "voice"),
    ]
    items = []
    for t, s in texts:
        items.extend(extract_actions(t, s, simulation_date=SIM_DATE))
    merged = reconcile_actions(items)
    for m in merged:
        database.insert_action(m.action, m.owner, m.related_person, m.deadline, m.status, m.source_type, m.source_date, m.evidence, m.confidence)
    all_actions = database.get_all_actions()
    passed = len(merged) == 1
    print(f"Test Duplicate: {'PASS' if passed else 'FAIL'} — merged_count={len(merged)} db_count={len(all_actions)}")
    return passed


def run_test_ownership_unclear():
    text = "Mumbai lease: Need confirmation — who is handling the Mumbai lease?"
    items = extract_actions(text, "email", simulation_date=SIM_DATE)
    merged = reconcile_actions(items)
    if merged:
        m = merged[0]
        database.insert_action(m.action, m.owner, m.related_person, m.deadline, m.status, m.source_type, m.source_date, m.evidence, m.confidence)
        owner_ok = m.owner is None
        status_ok = m.status and "unclear" in m.status.lower()
        passed = owner_ok and status_ok
    else:
        passed = False
    print(f"Test Ownership Unclear: {'PASS' if passed else 'FAIL'} — owner={merged[0].owner if merged else None} status={merged[0].status if merged else None}")
    return passed


def run_test_deadline_resolution():
    text = "Please send the vendor list by Wednesday morning."
    items = extract_actions(text, "email", simulation_date=SIM_DATE)
    merged = reconcile_actions(items)
    passed = False
    if merged:
        m = merged[0]
        database.insert_action(m.action, m.owner, m.related_person, m.deadline, m.status, m.source_type, m.source_date, m.evidence, m.confidence)
        # Expect ISO date for 2026-09-23 and 'morning' preserved in evidence/action
        dl_ok = m.deadline == "2026-09-23"
        morning_ok = ("morning" in (m.evidence or "").lower()) or ("morning" in (m.action or "").lower())
        passed = dl_ok and morning_ok
    print(f"Test Deadline Resolution: {'PASS' if passed else 'FAIL'} — deadline={merged[0].deadline if merged else None} evidence_contains_morning={morning_ok if merged else False}")
    return passed


def run_test_completed_detection():
    texts = [
        ("Expense report attached.", "email"),
        ("Received Wed evening.", "email"),
    ]
    items = []
    for t, s in texts:
        items.extend(extract_actions(t, s, simulation_date=SIM_DATE))
    merged = reconcile_actions(items)
    passed = False
    if merged:
        m = merged[0]
        database.insert_action(m.action, m.owner, m.related_person, m.deadline, m.status, m.source_type, m.source_date, m.evidence, m.confidence)
        passed = m.status is not None and "completed" in m.status.lower()
    print(f"Test Completed Detection: {'PASS' if passed else 'FAIL'} — status={merged[0].status if merged else None}")
    return passed


def run_test_qa_raghav():
    # Use vendor list example which mentions Raghav
    text = "I will send the updated vendor list to Raghav by tomorrow morning."
    items = extract_actions(text, "meeting", simulation_date=SIM_DATE)
    merged = reconcile_actions(items)
    for m in merged:
        database.insert_action(m.action, m.owner, m.related_person, m.deadline, m.status, m.source_type, m.source_date, m.evidence, m.confidence)
    # Query DB for actions mentioning Raghav or updated vendor list
    rows = database.get_all_actions()
    found = any((row.get("related_person") and "raghav" in row.get("related_person").lower()) or (row.get("evidence") and "vendor" in row.get("evidence").lower()) for row in rows)
    print(f"Test Q&A Raghav: {'PASS' if found else 'FAIL'} — matched_rows={sum(1 for r in rows if (r.get('related_person') and 'raghav' in r.get('related_person','').lower()) or ('vendor' in (r.get('evidence') or '').lower()))}")
    return found


def run_test_qa_today():
    text = "Finalize the budget today."
    items = extract_actions(text, "voice", simulation_date=SIM_DATE)
    merged = reconcile_actions(items)
    for m in merged:
        database.insert_action(m.action, m.owner, m.related_person, m.deadline, m.status, m.source_type, m.source_date, m.evidence, m.confidence)
    rows = database.get_all_actions()
    # Check that at least one action is due today according to rules.determine_due_today
    due_today = False
    for r in rows:
        dl = r.get("deadline")
        try:
            dt = rules.determine_due_today(dl, SIM_DATE)
        except Exception:
            dt = False
        if dt is True:
            due_today = True
            break
    print(f"Test Q&A Today Simulation: {'PASS' if due_today else 'FAIL'} — due_today_found={due_today}")
    return due_today


def main():
    reset_db()
    results = []
    results.append(run_test_duplicate())
    results.append(run_test_ownership_unclear())
    results.append(run_test_deadline_resolution())
    results.append(run_test_completed_detection())
    results.append(run_test_qa_raghav())
    results.append(run_test_qa_today())

    passed = sum(1 for r in results if r)
    total = len(results)
    database.add_audit_log(f"Test run: {passed}/{total} passed")
    print(f"\nSummary: {passed}/{total} tests passed")


if __name__ == "__main__":
    main()
