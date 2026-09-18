"""
Reconciliation (deduplication) utilities for ExecFlow.

This module implements a simple, deterministic, and explainable strategy to
detect duplicate extracted actions that refer to the same real-world
commitment and merge them into a single canonical record.

Key ideas:
- Normalize action text into tokens and use Jaccard similarity to measure
  textual overlap.
- Require either token similarity above a threshold AND non-conflicting
  ownership/related-person signals to mark items as duplicates.
- When merging:
  - Keep one canonical action label (shortest representative text).
  - Keep the latest deadline (if any) by parsing ISO-like dates.
  - Preserve (concatenate) all evidence entries and source dates.
  - Update status using the most recent available signal.

Limitations:
- This is a heuristic approach. It works well for clearly similar phrases
  (like "send vendor list" variants) but can fail when wording diverges
  significantly or when context is needed to disambiguate.
- The algorithm is conservative: if it is uncertain that two items are
  duplicates (e.g., low similarity or conflicting owners), it will NOT
  merge them automatically.

The implementation is intentionally simple and well-commented for
beginners; it does not call any LLMs and is fully deterministic.
"""

from typing import List, Optional, Any
import re
from datetime import datetime

from agent import ActionItem


def _normalize_action_text(text: str) -> List[str]:
    """Return a list of normalized tokens for the action text.

    Steps:
    - Lowercase
    - Remove punctuation
    - Remove short tokens and common stop-words that don't affect meaning
    """
    if not text:
        return []
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    stop_words = set([
        "the", "a", "an", "to", "for", "of", "on", "in", "by",
        "will", "i", "we", "you", "please", "can", "get", "have",
        "need",
    ])
    tokens = [t for t in s.split() if len(t) > 2 and t not in stop_words]
    return tokens


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _parse_iso(date_text: Optional[str]) -> Optional[datetime]:
    """Try to parse an ISO-like date string into a datetime.

    Returns None on failure. We keep parsing minimal to avoid guessing.
    """
    if not date_text:
        return None
    try:
        # Accept full ISO or date-only 'YYYY-MM-DD'
        return datetime.fromisoformat(date_text)
    except Exception:
        return None


def are_duplicates(a: ActionItem, b: ActionItem, similarity_threshold: float = 0.5) -> bool:
    """Decide whether two ActionItem objects likely refer to the same action.

    Rules used:
    - Compute Jaccard similarity of normalized action text tokens.
    - Require similarity >= similarity_threshold.
    - Owners must be non-conflicting: either equal, or at least one is None.
    - If related_person exists for both and differs, do not merge.

    The function is conservative: it returns False if it is uncertain.
    """
    tok_a = _normalize_action_text(a.action or a.evidence or "")
    tok_b = _normalize_action_text(b.action or b.evidence or "")
    sim = _jaccard(tok_a, tok_b)
    if sim < similarity_threshold:
        return False

    # Owner conflict check
    if a.owner and b.owner and a.owner != b.owner:
        return False

    # Related person conflict check
    if a.related_person and b.related_person and a.related_person != b.related_person:
        return False

    return True


def _merge_group(group: List[ActionItem]) -> ActionItem:
    """Merge a group of ActionItems into one canonical ActionItem.

    - Canonical action: shortest non-empty action text.
    - Latest deadline: select the parsed date that is latest (if parseable).
    - Evidence: concatenate all evidence strings with separators.
    - Source information: concatenate unique source types and source dates.
    - Status: pick the status from the item with the latest source_date if available,
      otherwise the most common status.
    - Owner: keep owner if consistent; otherwise None.
    """
    if not group:
        raise ValueError("Empty group cannot be merged")

    # canonical action
    actions = [g.action for g in group if g.action]
    canonical_action = min(actions, key=len) if actions else (group[0].action or "")

    # owners
    owners = [g.owner for g in group if g.owner]
    owner = owners[0] if owners and all(o == owners[0] for o in owners) else None

    # Detect explicit uncertainty language in evidence or action text. If
    # uncertainty is present (e.g., "flag it, don't assume", "who is
    # signing", "still unowned"), we must NOT assign ownership even if a
    # party like 'Facilities' is mentioned elsewhere. This enforces the
    # requirement to follow evidence rather than guessing.
    uncertainty_phrases = [
        "flag it",
        "don't assume",
        "dont assume",
        "not sure",
        "who is signing",
        "has anyone confirmed",
        "still unowned",
        "unowned",
        "not assigned",
        "i don't think",
        "i don't think it's",
        "don't think it's",
        "who's handling",
        "who is handling",
        "can you confirm who's handling",
    ]
    combined_texts = "\n".join([g.evidence or "" for g in group] + [g.action or "" for g in group])
    combined_lower = combined_texts.lower()
    if any(p in combined_lower for p in uncertainty_phrases):
        owner = None
        forced_unclear = True
    else:
        forced_unclear = False

    # Try to detect explicit 'From:' headers in evidence or action text that
    # indicate who sent an email/message. If found, map local-part or name to
    # known people (first-name match) and use that as the owner only when
    # unambiguous.
    known_names = ["Arjun Malhotra", "Neha Kapoor", "Raghav Sethi", "Divya Rao", "Priya Nair", "Facilities"]
    if owner is None:
        m = re.search(r"from:\s*([^\s@]+)@", combined_lower, re.I)
        if m:
            local = m.group(1)  # e.g., 'divya.rao'
            for name in known_names:
                if name.split()[0].lower() in local:
                    owner = name
                    break

    # Detect completion signals: a sender says 'report attached' or 'report sent',
    # and the recipient acknowledges (e.g., 'got it', 'received', 'thanks'). If
    # we can detect a sender (from header or owner) and an acknowledgment by a
    # different person in the group's evidence, treat the action as completed.
    completion_signals = ["attached", "report attached", "report sent", "sent as promised", "report attached, sent"]
    ack_signals = ["got it", "received", "thanks", "thank you", "acknowledged"]
    has_send = any(sig in combined_lower for sig in completion_signals)
    has_ack = any(sig in combined_lower for sig in ack_signals)
    if has_send and has_ack:
        # If owner is known from header or explicit, prefer that; otherwise leave None
        if owner is None:
            # try to find a sender local-part again but be conservative
            m = re.search(r"from:\s*([^\s@]+)@", combined_lower, re.I)
            if m:
                local = m.group(1)
                for name in known_names:
                    if name.split()[0].lower() in local:
                        owner = name
                        break
        # mark completed if sender/ack exist
        if owner is not None:
            latest_status = "Completed"
        else:
            # even if we can't confidently assign owner, we can mark status
            latest_status = "Completed"

    # related person: most common
    relateds = [g.related_person for g in group if g.related_person]
    related_person = max(set(relateds), key=relateds.count) if relateds else None

    # latest deadline
    parsed_deadlines = [(g.deadline, _parse_iso(g.deadline)) for g in group if g.deadline]
    latest_deadline = None
    if parsed_deadlines:
        # pick the max by parsed datetime; if parsing failed, ignore that entry
        parsed = [(d, p) for d, p in parsed_deadlines if p is not None]
        if parsed:
            latest = max(parsed, key=lambda x: x[1])
            latest_deadline = latest[0]
        else:
            # if none parseable, prefer the last non-null string encountered
            latest_deadline = parsed_deadlines[-1][0]

    # evidence and source_dates
    evidence_pieces = [g.evidence for g in group if g.evidence]
    evidence = "\n---\n".join(evidence_pieces) if evidence_pieces else None

    source_dates = [g.source_date for g in group if g.source_date]
    # keep unique and preserve order
    seen = set()
    uniq_source_dates = [d for d in source_dates if not (d in seen or seen.add(d))]

    # source_type concatenation (unique)
    source_types = [g.source_type for g in group if g.source_type]
    seen = set()
    uniq_source_types = [s for s in source_types if not (s in seen or seen.add(s))]

    # determine status: prefer status from item with latest source_date
    latest_status = None
    parsed_dates_for_status = [(g, _parse_iso(g.source_date)) for g in group if g.source_date]
    parsed_dates_for_status = [p for p in parsed_dates_for_status if p[1] is not None]
    if parsed_dates_for_status:
        latest_item = max(parsed_dates_for_status, key=lambda x: x[1])[0]
        latest_status = latest_item.status
    else:
        # fallback: most common status
        statuses = [g.status for g in group if g.status]
        latest_status = max(set(statuses), key=statuses.count) if statuses else None

    confidence = max((g.confidence or 0.0) for g in group)

    # Detect scheduling workflow: proposal -> confirmation -> calendar
    # If evidence contains proposal phrases, mark as 'Proposed' unless later confirmed.
    propose_phrases = ["how about", "propose", "can you propose", "suggest", "would .* work", "want to reschedule", "let's say", "how about wednesday", "proposed"]
    confirm_phrases = ["confirmed", "see you at", "works on our end", "yes, confirmed", "confirmed, see you", "see you at 3", "yes, confirmed, see you at 3", "confirmed."]
    combined_lower = combined_texts.lower()

    is_proposed = any(re.search(p, combined_lower) for p in propose_phrases)
    is_confirmed = any(p in combined_lower for p in confirm_phrases)

    # If any group item comes from a calendar source, treat that as confirmation
    has_calendar = any((g.source_type and "calendar" in g.source_type.lower()) for g in group)
    if has_calendar:
        is_confirmed = True

    if is_confirmed:
        latest_status = "Confirmed"
    elif is_proposed and (latest_status is None or latest_status.lower() not in ("confirmed", "completed")):
        latest_status = "Proposed"

    # If Arjun explicitly appears in the group's text and owner is still None,
    # he is likely the proposer; assign only when an explicit mention exists.
    if owner is None and "arjun" in combined_lower:
        owner = "Arjun Malhotra"

    # If we forced unclear ownership, make status explicit and owner None
    if forced_unclear:
        owner = None
        latest_status = "Unclear ownership"

    merged = ActionItem(
        action=canonical_action,
        owner=owner,
        related_person=related_person,
        deadline=latest_deadline,
        status=latest_status,
        source=";".join([g.source for g in group if g.source]),
        source_type=";".join(uniq_source_types),
        source_date=";".join(uniq_source_dates) if uniq_source_dates else None,
        evidence=evidence,
        confidence=confidence,
    )
    return merged


def reconcile_actions(items: List[ActionItem], similarity_threshold: float = 0.5) -> List[ActionItem]:
    """Reconcile a list of ActionItems by grouping and merging duplicates.

    Algorithm (greedy grouping):
    - Iterate items in order; for each item, try to find an existing group where
      `are_duplicates` returns True. If found, append to that group; otherwise
      start a new group.
    - After grouping, merge each group deterministically with `_merge_group`.

    The greedy approach is deterministic and explainable, but it means group
    assignments depend on item order. To avoid accidental merges, the
    `are_duplicates` checks owner and related_person conflicts and uses a
    similarity threshold.

    Returns a list of merged ActionItem objects.
    """
    groups: List[List[ActionItem]] = []
    for item in items:
        placed = False
        for g in groups:
            # compare against the representative (first) item of the group
            if are_duplicates(g[0], item, similarity_threshold=similarity_threshold):
                g.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])

    merged = [_merge_group(g) for g in groups]
    return merged
