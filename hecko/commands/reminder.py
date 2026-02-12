"""Reminder command: set reminders that announce at a specified time.

Handles:
    "remind me to feed the cat at 3pm"
    "remind me at 12:30 to call my mom"
    "remind me to take my power adapter at 6 o'clock in the morning"
    "what reminders do I have"
    "cancel all reminders"
"""

import re
import threading
import time
from datetime import datetime, timedelta

# Active reminders: [{time: datetime, text: str, original: str}, ...]
_reminders = []
_lock = threading.Lock()

# Callback for announcing reminders (set by main via set_announce_callback)
_announce_cb = None

_checker_thread = None


def set_announce_callback(cb):
    """Set the function to call when a reminder fires. cb(text) -> None."""
    global _announce_cb
    _announce_cb = cb


# --- Background checker ---

def _start_checker():
    global _checker_thread
    if _checker_thread is not None and _checker_thread.is_alive():
        return

    def _check_loop():
        while True:
            time.sleep(5)
            now = datetime.now()
            fired = []
            with _lock:
                remaining = []
                for r in _reminders:
                    if now >= r["time"]:
                        fired.append(r)
                    else:
                        remaining.append(r)
                _reminders[:] = remaining
            for r in fired:
                msg = f"[[reminder.mp3]]This is a reminder: {r['text']}."
                if _announce_cb:
                    _announce_cb(msg)

    _checker_thread = threading.Thread(target=_check_loop, daemon=True)
    _checker_thread.start()


# --- Time parsing ---

def parse_time(text):
    """Parse a time expression from text, returning the next occurrence as a datetime.

    Handles:
        "3pm", "3 pm", "3:30pm", "12:30", "6 o'clock in the morning",
        "6 o'clock", "noon", "midnight", "3 in the afternoon",
        "6 in the morning", "10 at night"

    Returns:
        datetime or None
    """
    t = text.lower().strip()

    # "noon"
    if re.search(r"\bnoon\b", t):
        return _next_occurrence(12, 0)

    # "midnight"
    if re.search(r"\bmidnight\b", t):
        return _next_occurrence(0, 0)

    # "H:MM am/pm", "H.MM am/pm", "H:MM", "H.MM" (STT sometimes uses period)
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\s*(a\.?m\.?|p\.?m\.?)?\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = (m.group(3) or "").replace(".", "")
        hour = _apply_ampm(hour, ampm, t)
        return _next_occurrence(hour, minute)

    # "HMM am/pm" — no separator, e.g. "845 p.m." from STT
    m = re.search(r"\b(\d{3,4})\s*(a\.?m\.?|p\.?m\.?)\b", t)
    if m:
        digits = m.group(1)
        if len(digits) == 3:
            hour, minute = int(digits[0]), int(digits[1:])
        else:
            hour, minute = int(digits[:2]), int(digits[2:])
        ampm = m.group(2).replace(".", "")
        hour = _apply_ampm(hour, ampm, t)
        return _next_occurrence(hour, minute)

    # "H MM am/pm" — space-separated, e.g. "8 50 p.m." from STT
    m = re.search(r"\b(\d{1,2})\s+(\d{2})\s*(a\.?m\.?|p\.?m\.?)\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = m.group(3).replace(".", "")
        hour = _apply_ampm(hour, ampm, t)
        return _next_occurrence(hour, minute)

    # "H am/pm" or "H pm" (no minutes)
    m = re.search(r"\b(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)\b", t)
    if m:
        hour = int(m.group(1))
        ampm = m.group(2).replace(".", "")
        hour = _apply_ampm(hour, ampm, t)
        return _next_occurrence(hour, 0)

    # Bare "HMM" or "HHMM" with no am/pm — e.g. "at 846" or just "846" from STT
    # Treat as 12-hour time: try both AM and PM, pick whichever is next.
    m = re.search(r"\b(\d{3,4})\b", t)
    if m:
        digits = m.group(1)
        if len(digits) == 3:
            hour, minute = int(digits[0]), int(digits[1:])
        else:
            hour, minute = int(digits[:2]), int(digits[2:])
        if hour <= 12:
            return _next_occurrence_12h(hour, minute)
        return _next_occurrence(hour, minute)

    # "N o'clock [in the morning/afternoon/evening/at night]"
    m = re.search(r"\b(\d{1,2})\s*o['\u2019]?\s*clock\b", t)
    if m:
        hour = int(m.group(1))
        hour = _apply_ampm(hour, "", t)
        return _next_occurrence(hour, 0)

    # Bare number with "in the morning/afternoon/evening/at night"
    m = re.search(r"\b(\d{1,2})\s+(?:in the |at )", t)
    if m:
        hour = int(m.group(1))
        hour = _apply_ampm(hour, "", t)
        return _next_occurrence(hour, 0)

    return None


def _apply_ampm(hour, ampm, text):
    """Resolve hour to 24h based on explicit am/pm or context clues in text."""
    ampm = ampm.lower().strip()
    if ampm == "pm" and hour != 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    if ampm:
        return hour

    # No explicit am/pm — check for context phrases
    if re.search(r"in the morning", text):
        return hour if hour != 12 else 0
    if re.search(r"in the afternoon", text):
        return hour + 12 if hour != 12 else 12
    if re.search(r"in the evening", text):
        return hour + 12 if hour != 12 else 12
    if re.search(r"at night", text):
        return hour + 12 if hour < 12 else hour

    # Ambiguous — return as-is (assume 24h or closest next match will handle it)
    return hour


def _next_occurrence(hour, minute):
    """Return the next datetime matching this hour:minute (24h)."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _next_occurrence_12h(hour, minute):
    """Return the soonest upcoming time for an ambiguous 12-hour time.

    Tries both AM and PM interpretations, returns whichever comes next.
    """
    now = datetime.now()
    am_hour = hour if hour != 12 else 0
    pm_hour = hour + 12 if hour != 12 else 12

    am_target = now.replace(hour=am_hour, minute=minute, second=0, microsecond=0)
    if am_target <= now:
        am_target += timedelta(days=1)

    pm_target = now.replace(hour=pm_hour, minute=minute, second=0, microsecond=0)
    if pm_target <= now:
        pm_target += timedelta(days=1)

    return min(am_target, pm_target)


# --- Pronoun flipping ---

_PRONOUN_MAP = [
    # Order matters: longer phrases first to avoid partial matches
    (r"\bremind me\b", ""),
    (r"\bmy\b", "your"),
    (r"\bme\b", "you"),
    (r"\bmyself\b", "yourself"),
    (r"\bmine\b", "yours"),
    (r"\bi am\b", "you are"),
    (r"\bi'm\b", "you're"),
    (r"\bi\b", "you"),
]


def _flip_pronouns(text):
    """Convert first-person pronouns to second-person."""
    result = text
    for pattern, replacement in _PRONOUN_MAP:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    # Clean up extra whitespace
    result = re.sub(r"  +", " ", result).strip()
    return result


# --- Reminder text extraction ---

def _extract_reminder(text):
    """Extract the reminder text and time from the input.

    Returns:
        (reminder_text, parsed_time) or (None, None)
    """
    t = text

    # Try "remind me to X at TIME" pattern
    m = re.search(r"remind me\s+to\s+(.+?)\s+at\s+(.+)", t, re.IGNORECASE)
    if m:
        reminder_text = m.group(1).strip().rstrip(".")
        time_part = m.group(2).strip().rstrip(".")
        parsed = parse_time(time_part)
        if parsed:
            return _flip_pronouns(reminder_text), parsed

    # Try "remind me at TIME to X" pattern
    m = re.search(r"remind me\s+at\s+(.+?)\s+to\s+(.+)", t, re.IGNORECASE)
    if m:
        time_part = m.group(1).strip()
        reminder_text = m.group(2).strip().rstrip(".")
        parsed = parse_time(time_part)
        if parsed:
            return _flip_pronouns(reminder_text), parsed

    # Try "remind me to X" with time embedded anywhere
    m = re.search(r"remind me\s+to\s+(.+)", t, re.IGNORECASE)
    if m:
        full = m.group(1).strip().rstrip(".")
        parsed = parse_time(full)
        if parsed:
            # Remove the time portion from the reminder text
            # Strip trailing time patterns
            cleaned = re.sub(
                r"\s+at\s+\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.|o['\u2019]?\s*clock)?"
                r"(\s+in the (morning|afternoon|evening)|at night)?\.?$",
                "", full, flags=re.IGNORECASE
            ).strip()
            if cleaned:
                return _flip_pronouns(cleaned), parsed

    return None, None


# --- Command scoring and handling ---

def _classify(text):
    t = text.lower()
    if re.search(r"\bremind\s+me\b", t):
        return "set"
    if re.search(r"\b(what|list|show).*\breminder", t):
        return "query"
    if re.search(r"\bcancel\b.*\breminder", t):
        if re.search(r"\ball\b", t):
            return "cancel_all"
        return "cancel"
    return None


def score(text):
    cmd = _classify(text)
    if cmd is not None:
        return 0.9
    if re.search(r"\bremind", text.lower()):
        return 0.5
    return 0.0


def handle(text):
    _start_checker()

    cmd = _classify(text)

    if cmd == "set":
        reminder_text, reminder_time = _extract_reminder(text)
        if reminder_text and reminder_time:
            with _lock:
                _reminders.append({
                    "time": reminder_time,
                    "text": reminder_text,
                    "original": text,
                })
            time_str = reminder_time.strftime("%-I:%M %p")
            return f"OK, I'll remind you to {reminder_text} at {time_str}."
        return "Sorry, I didn't understand the time for that reminder."

    elif cmd == "query":
        with _lock:
            if not _reminders:
                return "You don't have any reminders set."
            parts = []
            for r in sorted(_reminders, key=lambda x: x["time"]):
                time_str = r["time"].strftime("%-I:%M %p")
                parts.append(f"{r['text']} at {time_str}")
        if len(parts) == 1:
            return f"You have one reminder: {parts[0]}."
        listing = ", and ".join([", ".join(parts[:-1]), parts[-1]])
        return f"You have {len(parts)} reminders: {listing}."

    elif cmd == "cancel_all":
        with _lock:
            count = len(_reminders)
            _reminders.clear()
        if count == 0:
            return "You don't have any reminders to cancel."
        return f"All {count} reminder{'s' if count != 1 else ''} canceled."

    elif cmd == "cancel":
        # For now, cancel the next upcoming one
        with _lock:
            if not _reminders:
                return "You don't have any reminders to cancel."
            _reminders.sort(key=lambda x: x["time"])
            removed = _reminders.pop(0)
        time_str = removed["time"].strftime("%-I:%M %p")
        return f"Canceled your reminder to {removed['text']} at {time_str}."

    return "Sorry, I didn't understand that reminder command."
