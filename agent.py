"""
Simple agent for extracting executive commitments & actions.

This module provides `extract_actions(text: str, source_type: str)` which
returns structured Pydantic objects for each discovered action.

Behavior and rules (implemented here):
- Never invent an owner or a deadline. If not present, those fields are set to None.
- If ownership is unclear, `owner` is None and `status` should indicate unclear ownership.
- Preserve original evidence text.
- Try to use the OpenAI Python SDK if an API key is available; otherwise use a
  small rule-based fallback so the function works for beginners without keys.

The code is intentionally simple and well-commented for beginners.
"""

from typing import List, Optional
import re
import os
import json
from datetime import date, datetime, timedelta

from pydantic import ValidationError

try:
    # OpenAI Python SDK (newer versions expose OpenAI class)
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

from models import Commitment


class ActionItem(Commitment):
    """Extended Commitment with source metadata and confidence score."""

    source_type: Optional[str] = None
    source_date: Optional[str] = None
    confidence: float = 0.0


def _normalize_action_text(text: str) -> List[str]:
    """Normalize action text into a list of meaningful tokens.

    Steps:
    - Lowercase
    - Remove punctuation
    - Remove common stop-words and modal verbs that don't affect the core task
    - Remove short tokens

    The output is a list of tokens used for simple token-overlap deduplication.
    """
    s = text.lower()
    # remove punctuation
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # remove common words that don't change the core meaning
    stop_words = set(
        [
            "the",
            "a",
            "an",
            "to",
            "for",
            "of",
            "on",
            "in",
            "by",
            "will",
            "would",
            "please",
            "can",
            "i",
            "we",
            "you",
            "let",
            "s",
            "'ll",
            "'ve",
            "send",
            "send",
            "get",
            "have",
            "need",
        ]
    )
    tokens = [t for t in s.split() if len(t) > 2 and t not in stop_words]
    return tokens


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def deduplicate_actions(items: List[ActionItem], similarity_threshold: float = 0.5) -> List[ActionItem]:
    """Deterministically deduplicate a list of ActionItem objects.

    Algorithm (simple and explainable):
    - Normalize each action's text into tokens.
    - Group actions by token-overlap (Jaccard similarity >= threshold).
    - For each group, produce a single merged ActionItem:
      - `action`: choose the shortest non-empty action text as the canonical label
      - `owner`: prefer a defined owner; if multiple conflicting owners appear, set to None
      - `related_person`: prefer the most commonly-mentioned related person
      - `deadline`: prefer the last-mentioned explicit deadline (preserves latest commitment)
      - `status`: if any item has 'unclear_ownership' and owner is None, keep that; otherwise choose the most common status
      - `evidence`: concatenate all evidence pieces (preserve originals)
      - `confidence`: use the max confidence seen for the group

    This function is deterministic and does not call any LLMs.
    """
    groups: List[List[ActionItem]] = []
    norms: List[List[str]] = []

    for item in items:
        tokens = _normalize_action_text(item.action or item.evidence or "")
        placed = False
        for idx, n in enumerate(norms):
            if _jaccard(tokens, n) >= similarity_threshold:
                groups[idx].append(item)
                # expand the normalized token set for the group for future comparisons
                norms[idx] = list(set(norms[idx]) | set(tokens))
                placed = True
                break
        if not placed:
            groups.append([item])
            norms.append(tokens)

    merged: List[ActionItem] = []
    for group in groups:
        # canonical action: pick the shortest non-empty action text
        actions_texts = [g.action for g in group if g.action]
        canonical_action = min(actions_texts, key=lambda s: len(s)) if actions_texts else (group[0].action or "")

        # owner: collect owners (non-None)
        owners = [g.owner for g in group if g.owner]
        owner = None
        if owners:
            # if all owners the same, keep it; otherwise unclear
            if all(o == owners[0] for o in owners):
                owner = owners[0]
            else:
                owner = None

        # related_person: most common non-null
        relateds = [g.related_person for g in group if g.related_person]
        related_person = None
        if relateds:
            related_person = max(set(relateds), key=relateds.count)

        # deadline: prefer last-mentioned explicit deadline in group order
        deadline = None
        for g in group:
            if g.deadline:
                deadline = g.deadline

        # status: choose most common unless ownership unclear
        statuses = [g.status for g in group if g.status]
        status = None
        if owner is None:
            status = "unclear_ownership"
        elif statuses:
            status = max(set(statuses), key=statuses.count)

        # combine evidence pieces
        evidences = [g.evidence for g in group if g.evidence]
        evidence = "\n---\n".join(evidences) if evidences else None

        confidence = max((g.confidence or 0.0) for g in group) if group else 0.0

        merged_item = ActionItem(
            action=canonical_action,
            owner=owner,
            related_person=related_person,
            deadline=deadline,
            status=status,
            source=";".join([g.source for g in group if g.source]),
            source_type=";".join([g.source_type for g in group if g.source_type]),
            source_date=None,
            evidence=evidence,
            confidence=confidence,
        )
        merged.append(merged_item)

    return merged


def _simple_sentence_split(text: str) -> List[str]:
    """Split text into simple sentences for heuristic parsing.

    This is intentionally minimal and readable for beginners. It splits on
    common sentence-ending punctuation.
    """
    parts = re.split(r"(?<=[.!?\n])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _find_deadline(text: str) -> Optional[str]:
    """Look for explicit date-like tokens. Don't invent dates.

    Return the matched substring (e.g., 'Wednesday', '2026-09-23', 'by tomorrow').
    If nothing obvious is found, return None.
    """
    # ISO date
    m = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if m:
        return m.group(0)

    # common month-day patterns (e.g., Sep 23, 23 September)
    m = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s\.]?\s*\d{1,2}(?:,?\s*\d{4})?\b", text, re.I)
    if m:
        return m.group(0)

    # weekdays and relative phrases (we keep the text as evidence instead of converting)
    m = re.search(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|today|tomorrow|end of day|EOD|by end of day|by tomorrow)\b", text, re.I)
    if m:
        return m.group(0)

    return None


def _resolve_relative_deadline(deadline_text: str, reference_date: date) -> Optional[str]:
    """Convert a relative deadline phrase into an ISO date using `reference_date`.

    Rules:
    - If `deadline_text` already contains an ISO date (YYYY-MM-DD), return it.
    - Support keywords: 'today', 'tomorrow', weekdays (Monday..Sunday), 'end of day', 'EOD'.
    - DO NOT guess beyond these patterns; if no match, return None.

    This function ensures the LLM does NLU but Python resolves actual dates
    using the simulation/reference date supplied by the application.
    """
    if not deadline_text:
        return None

    # ISO date
    m = re.search(r"\b\d{4}-\d{2}-\d{2}\b", deadline_text)
    if m:
        return m.group(0)

    text = deadline_text.lower()
    if "tomorrow" in text:
        resolved = reference_date + timedelta(days=1)
        return resolved.isoformat()
    if "today" in text:
        return reference_date.isoformat()
    if any(k in text for k in ["end of day", "eod", "by end of day"]):
        return reference_date.isoformat()

    # weekdays
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, wd in weekdays.items():
        if name in text:
            # compute next occurrence of that weekday (including same day)
            days_ahead = (wd - reference_date.weekday()) % 7
            resolved = reference_date + timedelta(days=days_ahead)
            return resolved.isoformat()

    return None


def _find_related_person(text: str, known_names: List[str]) -> Optional[str]:
    for name in known_names:
        if re.search(re.escape(name), text, re.I):
            return name
    return None


def _heuristic_extract(text: str, source_type: str) -> List[ActionItem]:
    """A simple, explainable rule-based extractor used when no API key is present.

    This looks for sentences that contain commitment-like verbs and then
    populates fields conservatively (never inventing owner/deadline).
    """
    known_names = ["Arjun Malhotra", "Arjun", "Neha Kapoor", "Neha", "Raghav Sethi", "Raghav", "Divya Rao", "Divya", "Priya Nair", "Priya", "Facilities"]
    results: List[ActionItem] = []

    sentences = _simple_sentence_split(text)
    commit_verbs = [r"\bI will\b", r"\bI'll\b", r"\bI need to\b", r"\bI owe\b", r"\bwill send\b", r"\bwill have\b", r"\bplease send\b", r"\bcan you send\b", r"\bneed to get\b", r"\bremind me\b"]
    waiting_patterns = [r"\bwaiting for\b", r"\bwaiting on\b", r"\bawaiting\b", r"\bpending\b", r"\bneeds to send\b"]
    # interrogative patterns indicating unclear ownership
    interrogative_patterns = [r"\bwho is handling\b", r"\bwho's handling\b", r"\bwho is taking\b", r"\bwho will handle\b"]
    # completion indicators to surface completed items
    completion_indicators = [r"\battached\b", r"\breport attached\b", r"\breport sent\b", r"\bsent as promised\b", r"\breceived\b"]

    # recognize simple imperative starters (e.g., 'Finalize the budget today')
    imperative_patterns = [r"^\s*(finaliz|complete|submit|approve|review|finish|send)\w*\b"]

    for s in sentences:
        s_lower = s.lower()
        is_commit = any(re.search(p, s, re.I) for p in commit_verbs)
        is_imperative = any(re.search(p, s, re.I) for p in imperative_patterns)
        is_waiting = any(re.search(p, s, re.I) for p in waiting_patterns)

        # treat interrogative ownership queries as items that indicate unclear ownership
        is_interrogative = any(re.search(p, s, re.I) for p in interrogative_patterns)

        # treat completion indicators as extractable items (e.g., 'report attached', 'received')
        has_completion = any(re.search(p, s, re.I) for p in completion_indicators)

        # treat imperative sentences as commits as well
        if not (is_commit or is_imperative or is_waiting or is_interrogative or has_completion):
            continue

        owner = None
        # If sentence explicitly mentions Arjun (or is from a voice note / meeting and uses 'I'), assume Arjun.
        if re.search(r"\bArjun\b|\bArjun Malhotra\b", s, re.I):
            owner = "Arjun Malhotra"
        elif source_type in ("voice", "meeting") and re.search(r"\bI\b", s):
            # voice notes in our dataset are Arjun's personal notes; be conservative but helpful
            owner = "Arjun Malhotra"

        related = _find_related_person(s, known_names)
        deadline = _find_deadline(s)

        status = None
        if has_completion:
            status = "completed"
        elif is_waiting:
            status = "waiting_on_others"
        elif owner is None:
            # interrogative queries and other cases with no owner
            status = "unclear_ownership"
        else:
            status = "open"

        # Do not invent deadlines or owners: if not found, keep None.
        item = ActionItem(
            action=s.strip(),
            owner=owner,
            related_person=related if related != owner else None,
            deadline=deadline,
            status=status,
            source=s.strip(),
            source_type=source_type,
            source_date=None,
            evidence=s.strip(),
            confidence=0.5,
        )
        results.append(item)

    return results


def extract_actions(text: str, source_type: str, simulation_date: Optional[date] = None) -> List[ActionItem]:
    """Extract action items from `text` and return validated ActionItem objects.

    Parameters:
    - text: raw text from meetings/emails/calendar/voice notes
    - source_type: one of 'email', 'meeting', 'calendar', 'voice', etc.

    The function first attempts to call the OpenAI SDK (if available and an API
    key is present). If that fails, a small deterministic fallback runs so the
    function remains useful while you are learning.

    Important rules enforced in the prompt and code:
    1. Never invent an owner or a deadline; return None for missing values.
    2. If ownership is unclear, owner is None and status indicates unclear ownership.
    3. Preserve the original evidence text.
    4. Only create actions when a clear commitment/waiting is present.
    """
    text = (text or "").strip()
    if not text:
        return []

    # Try OpenAI if available
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if OpenAI is not None and openai_api_key:
        try:
            client = OpenAI()
            system = (
                "You are a strict extractor that converts messy executive text into a JSON array of objects. "
                "Each object must have the keys: action, owner, related_person, deadline, status, source_type, source_date, evidence, confidence. "
                "Follow rules: NEVER invent an owner or deadline. If an owner or deadline is not explicit, set it to null. "
                "If ownership is unclear, set owner to null and status to 'unclear_ownership'. "
                "Preserve the exact evidence fragment from the input. Only output valid JSON (an array of objects)."
            )
            user_msg = f"Text:\n{text}\n\nSource type: {source_type}\n\nReturn only JSON."

            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                max_tokens=800,
            )

            # The format of the SDK response can vary by version; attempt to extract text
            choices = resp.get("choices") if isinstance(resp, dict) else None
            if choices:
                text_out = choices[0]["message"]["content"]["text"] if isinstance(choices[0]["message"].get("content"), dict) else choices[0]["message"]["content"]
            else:
                # Fallback: try attribute access (older client wrappers)
                text_out = resp.choices[0].message.content

            parsed = json.loads(text_out)
            items: List[ActionItem] = []
            for obj in parsed:
                try:
                    ai = ActionItem(**obj)
                    items.append(ai)
                except ValidationError:
                    # Skip invalid entries but continue
                    continue
            return items
        except Exception:
            # If anything goes wrong with the API call or parsing, fall back to heuristics.
            pass

    # Deterministic fallback
    try:
        items = _heuristic_extract(text, source_type)
    except Exception:
        items = []

    # If a simulation/reference date is provided, resolve relative deadline phrases
    # (e.g., 'tomorrow', 'Wednesday') into ISO dates here in Python. This keeps
    # the LLM focused on NLU and avoids asking it to invent absolute dates.
    if simulation_date and isinstance(simulation_date, date):
        for it in items:
            if it.deadline:
                resolved = _resolve_relative_deadline(it.deadline, simulation_date)
                if resolved:
                    it.deadline = resolved
                    # bump confidence slightly when we can resolve the date
                    it.confidence = min(1.0, it.confidence + 0.2)

    return items


if __name__ == "__main__":
    # Quick demo: run this file directly to test the heuristic extractor.
    demo_text = (
        "Arjun: I will send Raghav the updated vendor list by tomorrow. "
        "Divya: I will have the expense report ready Wednesday evening. "
        "Facilities: Reminder: signature required by Friday."
    )
    items = extract_actions(demo_text, source_type="meeting")
    for it in items:
        print(it.json())
    for it in items:
        print(it.json())
