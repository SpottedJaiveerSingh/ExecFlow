"""
Deterministic rules for deadlines, ownership and status calculations.

All functions use Python's `datetime` types and never rely on an LLM.
They are intentionally simple and well-documented for beginners.

Key behaviors:
- If `deadline` is missing (None or empty), functions return the string "No deadline" where specified.
- If `owner` is missing (None or empty), ownership status functions return "Unclear ownership".
- `calculate_status` summarizes the final status using deterministic rules.

The exercise simulation week is 2026-09-21 through 2026-09-25; pass
the simulation date as `current_date` when calling these functions so
they behave deterministically for that week.
"""

from datetime import date, datetime, timedelta
from typing import Optional, Union


def _to_date(d: Union[str, date, datetime, None]) -> Optional[date]:
    """Helper: convert strings or datetimes to a `date` object.

    - Accepts ISO date strings (YYYY-MM-DD), `date`, or `datetime`.
    - Returns `None` for `None` or empty strings.
    - Raises ValueError for unparseable strings.
    """
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        s = d.strip()
        if not s:
            return None
        # Expect ISO format like '2026-09-23'
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            # Let the caller know the string was not ISO; raise a clear error
            raise ValueError(f"Unrecognized date string: {s}. Use YYYY-MM-DD or a date object.")
    raise ValueError("Unsupported date type; pass a date, datetime, ISO string, or None.")


def determine_overdue(deadline: Optional[Union[str, date, datetime]], current_date: Union[str, date, datetime]) -> Union[bool, str]:
    """Return True if `deadline` is before `current_date`.

    - If `deadline` is missing, return the string "No deadline".
    - `current_date` must be provided (string ISO or date/datetime).
    - Comparison is date-only (time-of-day ignored).
    """
    d = _to_date(deadline)
    if d is None:
        return "No deadline"
    today = _to_date(current_date)
    return d < today


def determine_due_today(deadline: Optional[Union[str, date, datetime]], current_date: Union[str, date, datetime]) -> Union[bool, str]:
    """Return True if `deadline` equals `current_date`.

    - If `deadline` is missing, return "No deadline".
    - Comparison is exact on the date (no time component).
    """
    d = _to_date(deadline)
    if d is None:
        return "No deadline"
    today = _to_date(current_date)
    return d == today


def determine_upcoming(deadline: Optional[Union[str, date, datetime]], current_date: Union[str, date, datetime], days: int = 7) -> Union[bool, str]:
    """Return True if `deadline` is within the next `days` days (exclusive of today).

    - If `deadline` is missing, return "No deadline".
    - Default window is 7 days (useful for a typical 'upcoming' bucket).
    - For the exercise week you can pass `current_date=date(2026,9,21)` to view
      items that fall in that week.
    """
    d = _to_date(deadline)
    if d is None:
        return "No deadline"
    today = _to_date(current_date)
    delta = (d - today).days
    return 0 < delta <= days


def determine_ownership_status(owner: Optional[str]) -> str:
    """Return ownership status text.

    - If `owner` is missing or empty, return "Unclear ownership".
    - Otherwise return "Owned".
    """
    if owner is None:
        return "Unclear ownership"
    if isinstance(owner, str) and owner.strip() == "":
        return "Unclear ownership"
    return "Owned"


def classify_action(owner: Optional[str], current_user: str) -> str:
    """Classify an action relative to `current_user`.

    Returns one of:
    - "Unclear ownership" (no owner)
    - "My Action" (owner matches `current_user`, case-insensitive)
    - "Waiting on Others" (owner is someone else)

    This is a simple deterministic classifier useful for UI grouping.
    """
    if owner is None or (isinstance(owner, str) and owner.strip() == ""):
        return "Unclear ownership"
    try:
        return "My Action" if owner.strip().lower() == current_user.strip().lower() else "Waiting on Others"
    except Exception:
        return "Waiting on Others"


def calculate_status(deadline: Optional[Union[str, date, datetime]], current_date: Union[str, date, datetime], completion_status: Optional[bool]) -> str:
    """Return a concise status string for a task.

    Rules (deterministic):
    - If `deadline` is missing -> "No deadline".
    - If `completion_status` is truthy -> "Completed".
    - If deadline < current_date -> "Overdue".
    - If deadline == current_date -> "Due today".
    - If deadline is within the next 7 days -> "Upcoming".
    - Otherwise -> "Future".

    `completion_status` should be a boolean (True means completed). Keep the
    function simple so callers can reason about the result easily.
    """
    d = _to_date(deadline)
    if d is None:
        return "No deadline"
    if completion_status:
        return "Completed"
    today = _to_date(current_date)
    if d < today:
        return "Overdue"
    if d == today:
        return "Due today"
    if 0 < (d - today).days <= 7:
        return "Upcoming"
    return "Future"


if __name__ == "__main__":
    # Quick demo for the exercise week (21–25 Sep 2026)
    sim_day = date(2026, 9, 23)
    examples = [
        ("2026-09-22", False),  # yesterday
        ("2026-09-23", False),  # today
        ("2026-09-24", False),  # upcoming
        (None, False),
    ]
    for dl, done in examples:
        print(f"deadline={dl}, completed={done}")
        print("  overdue:", determine_overdue(dl, sim_day))
        print("  due_today:", determine_due_today(dl, sim_day))
        print("  upcoming:", determine_upcoming(dl, sim_day))
        print("  status:", calculate_status(dl, sim_day, done))
        print()
    for dl, done in examples:
        print(f"deadline={dl}, completed={done}")
        print("  overdue:", determine_overdue(dl, sim_day))
        print("  due_today:", determine_due_today(dl, sim_day))
        print("  upcoming:", determine_upcoming(dl, sim_day))
        print("  status:", calculate_status(dl, sim_day, done))
        print()
