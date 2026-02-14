"""Reminder command: set reminders that announce at a specified time.

Handles:
    "remind me to feed the cat at 3pm"
    "remind me at 12:30 to call my mom"
    "remind me to take my power adapter at 6 o'clock in the morning"
    "remind me on Tuesday at 3pm to go to class"
    "remind me to call mom at noon on Friday"
    "remind me tomorrow at 9am to take out the trash"
    "what reminders do I have"
    "cancel all reminders"
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from hecko.commands.parse import Parse
from hecko.commands.template import TemplatePattern, match_any

# Active reminders: [{"time": datetime, "text": str}, ...]
_reminders = []
_lock = threading.Lock()

# Persistence file: data/reminders.json relative to project root
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SAVE_PATH = _DATA_DIR / "reminders.json"

# Callback for announcing reminders (set by main via set_announce_callback)
_announce_cb = None

_checker_thread = None

_TIME_FMT = "%Y-%m-%d %H:%M"


def _save():
    """Write reminders to disk as JSON. Must be called with _lock held."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = [{"time": r["time"].strftime(_TIME_FMT), "text": r["text"]}
            for r in _reminders]
    tmp = _SAVE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(_SAVE_PATH)


def _load():
    """Load reminders from disk. Called once at startup."""
    if not _SAVE_PATH.exists():
        return
    try:
        data = json.loads(_SAVE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return
    now = datetime.now()
    for entry in data:
        try:
            t = datetime.strptime(entry["time"], _TIME_FMT)
        except (KeyError, ValueError):
            continue
        if t > now:
            _reminders.append({"time": t, "text": entry["text"]})


def set_announce_callback(cb):
    """Set the function to call when a reminder fires. cb(text) -> None."""
    global _announce_cb
    _announce_cb = cb


# --- Background checker ---

def _start_checker():
    global _checker_thread
    if _checker_thread is not None and _checker_thread.is_alive():
        return
    with _lock:
        _load()

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
                if fired:
                    _reminders[:] = remaining
                    _save()
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
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\s*(a\.?\s*m\.?|p\.?\s*m\.?)?\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = (m.group(3) or "").replace(".", "").replace(" ", "")
        hour = _apply_ampm(hour, ampm, t)
        if not ampm and 1 <= hour <= 11:
            return _next_occurrence_12h(hour, minute)
        return _next_occurrence(hour, minute)

    # "HMM am/pm" — no separator, e.g. "845 p.m." from STT
    m = re.search(r"\b(\d{3,4})\s*(a\.?\s*m\.?|p\.?\s*m\.?)\b", t)
    if m:
        digits = m.group(1)
        if len(digits) == 3:
            hour, minute = int(digits[0]), int(digits[1:])
        else:
            hour, minute = int(digits[:2]), int(digits[2:])
        ampm = m.group(2).replace(".", "").replace(" ", "")
        hour = _apply_ampm(hour, ampm, t)
        return _next_occurrence(hour, minute)

    # "H MM am/pm" — space-separated, e.g. "8 50 p.m." from STT
    m = re.search(r"\b(\d{1,2})\s+(\d{2})\s*(a\.?\s*m\.?|p\.?\s*m\.?)\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = m.group(3).replace(".", "").replace(" ", "")
        hour = _apply_ampm(hour, ampm, t)
        return _next_occurrence(hour, minute)

    # "H am/pm" or "H pm" or "H p m" (no minutes; allow space in a/p m)
    m = re.search(r"\b(\d{1,2})\s*(a\.?\s*m\.?|p\.?\s*m\.?)\b", t)
    if m:
        hour = int(m.group(1))
        ampm = m.group(2).replace(".", "").replace(" ", "")
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


# --- Day parsing ---

_DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def _parse_day(text):
    """Parse a day reference to a target date.

    Handles day names (Monday, Tue, etc.), "tomorrow", and "today".
    Returns a date or None.
    """
    t = text.lower().strip()
    if t == "tomorrow":
        return (datetime.now() + timedelta(days=1)).date()
    if t == "today":
        return datetime.now().date()
    # Strip optional "next" prefix
    t = re.sub(r"^next\s+", "", t)
    weekday = _DAY_NAMES.get(t)
    if weekday is not None:
        today = datetime.now().date()
        days_ahead = (weekday - today.weekday()) % 7
        # Same day: return today (time resolution will push to next week if past)
        return today + timedelta(days=days_ahead)
    return None


def _resolve_time_on_day(time_text, target_date):
    """Parse a time expression and place it on target_date.

    Uses parse_time to get the hour/minute, then combines with the target date.
    If the result is in the past, advances by 7 days (for same-day references).
    """
    parsed = parse_time(time_text)
    if parsed is None:
        return None
    target = datetime.combine(target_date, parsed.time())
    if target <= datetime.now():
        target += timedelta(days=7)
    return target


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

def _extract_reminder(fields):
    """Extract reminder text and time from matched template fields.

    Fields may contain:
        - 'reminder_text' and 'time' (and optionally 'day')
        - 'rest' for the fallback pattern where time is embedded in the text

    Returns:
        (reminder_text, parsed_time) or (None, None)
    """
    # Resolve optional day field
    target_day = None
    if "day" in fields:
        target_day = _parse_day(fields["day"])
        if target_day is None:
            return None, None  # $day wasn't a valid day name — fall through

    if "reminder_text" in fields and "time" in fields:
        if target_day:
            parsed = _resolve_time_on_day(fields["time"], target_day)
        else:
            parsed = parse_time(fields["time"])
        if parsed:
            return _flip_pronouns(fields["reminder_text"]), parsed

    # Fallback: time embedded in reminder text (e.g. "remind me to take pills at 6pm")
    if "rest" in fields:
        full = fields["rest"]
        parsed = parse_time(full)
        if parsed:
            # Strip trailing time patterns from the reminder text
            cleaned = re.sub(
                r"\s+at\s+\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.|o['\u2019]?\s*clock)?"
                r"(\s+in the (morning|afternoon|evening)|at night)?\.?$",
                "", full, flags=re.IGNORECASE
            ).strip()
            if cleaned:
                return _flip_pronouns(cleaned), parsed

    return None, None


# --- Command classification via templates ---

# Day-aware set patterns (tried first; fall through if $day isn't a valid day name)
# Non-greedy so $day and $time stay short; $reminder_text absorbs the remainder.
_DAY_SET_PATTERNS = [
    # "remind me on Monday at 3pm to go to class"
    (TemplatePattern("remind [me|us] on $day at $time to $reminder_text"), "set_day"),
    # "remind me Monday at 3pm to go to class" (no "on")
    (TemplatePattern("remind [me|us] $day at $time to $reminder_text"), "set_day"),
    # "remind me to call mom at 3pm on Monday"
    (TemplatePattern("remind [me|us] to $reminder_text at $time on $day", greedy=True), "set_day"),
    # "remind me to call mom on Monday at 3pm"
    (TemplatePattern("remind [me|us] to $reminder_text on $day at $time", greedy=True), "set_day"),
    # "remind me on Monday to call mom at 3pm"
    (TemplatePattern("remind [me|us] on $day to $reminder_text at $time", greedy=True), "set_day"),
]

_SET_PATTERNS = [
    # "remind me to X at TIME" — greedy so $reminder_text grabs everything before "at TIME"
    (TemplatePattern("remind [me|us] to $reminder_text at $time", greedy=True), "set"),
    # "remind me at TIME to X"
    (TemplatePattern("remind [me|us] at $time to $reminder_text"), "set"),
    # "remind me to X" (time embedded in the text, handled by fallback extraction)
    (TemplatePattern("remind [me|us] to $rest"), "set_fallback"),
]

_QUERY_PATTERNS = [
    (TemplatePattern("[what|list|show] $rest [reminder|reminders]"), "query"),
    (TemplatePattern("what reminders do [I|we] have"), "query"),
    (TemplatePattern("[list|show] [my|our|the] reminders"), "query"),
]

_CANCEL_PATTERNS = [
    (TemplatePattern("cancel all [reminder|reminders|my reminders|our reminders]"), "cancel_all"),
    (TemplatePattern("cancel [my|the|our] [reminder|reminders|next reminder]"), "cancel"),
    (TemplatePattern("cancel [reminder|reminders]"), "cancel"),
]

_NON_DAY_PATTERNS = _SET_PATTERNS + _QUERY_PATTERNS + _CANCEL_PATTERNS


def parse(text):
    # Try day-aware patterns first (fall through if $day isn't a valid day name)
    result = match_any(_DAY_SET_PATTERNS, text)
    if result is not None:
        tag, fields = result
        reminder_text, reminder_time = _extract_reminder(fields)
        if reminder_text and reminder_time:
            return Parse(command="set_reminder", score=0.9,
                         args={"text": reminder_text, "time": reminder_time})
        # Day pattern matched structurally but $day was invalid — fall through

    # Try non-day patterns
    result = match_any(_NON_DAY_PATTERNS, text)
    if result is not None:
        tag, fields = result
        if tag in ("set", "set_fallback"):
            reminder_text, reminder_time = _extract_reminder(fields)
            if reminder_text and reminder_time:
                return Parse(command="set_reminder", score=0.9,
                             args={"text": reminder_text, "time": reminder_time})
            # Recognized as set but couldn't parse time
            return Parse(command="set_reminder", score=0.9, args={})
        elif tag == "query":
            return Parse(command="query_reminders", score=0.9)
        elif tag == "cancel_all":
            return Parse(command="cancel_all_reminders", score=0.9)
        elif tag == "cancel":
            return Parse(command="cancel_reminder", score=0.9)

    # Weak match: mentions "remind" at all
    if re.search(r"\bremind", text, re.IGNORECASE):
        return Parse(command="set_reminder", score=0.5, args={})
    return None


def handle(p):
    _start_checker()

    if p.command == "set_reminder":
        reminder_text = p.args.get("text")
        reminder_time = p.args.get("time")
        if reminder_text and reminder_time:
            with _lock:
                _reminders.append({
                    "time": reminder_time,
                    "text": reminder_text,
                })
                _save()
            time_str = reminder_time.strftime("%-I:%M %p")
            if reminder_time.date() == datetime.now().date():
                return f"OK, I'll remind you to {reminder_text} at {time_str}."
            day_str = reminder_time.strftime("%A")
            return f"OK, I'll remind you to {reminder_text} on {day_str} at {time_str}."
        return "Sorry, I didn't understand the time for that reminder."

    elif p.command == "query_reminders":
        with _lock:
            if not _reminders:
                return "You don't have any reminders set."
            parts = []
            today = datetime.now().date()
            for r in sorted(_reminders, key=lambda x: x["time"]):
                time_str = r["time"].strftime("%-I:%M %p")
                if r["time"].date() == today:
                    parts.append(f"{r['text']} at {time_str}")
                else:
                    day_str = r["time"].strftime("%A")
                    parts.append(f"{r['text']} on {day_str} at {time_str}")
        if len(parts) == 1:
            return f"You have one reminder: {parts[0]}."
        listing = ", and ".join([", ".join(parts[:-1]), parts[-1]])
        return f"You have {len(parts)} reminders: {listing}."

    elif p.command == "cancel_all_reminders":
        with _lock:
            count = len(_reminders)
            _reminders.clear()
            _save()
        if count == 0:
            return "You don't have any reminders to cancel."
        return f"All {count} reminder{'s' if count != 1 else ''} canceled."

    elif p.command == "cancel_reminder":
        # For now, cancel the next upcoming one
        with _lock:
            if not _reminders:
                return "You don't have any reminders to cancel."
            _reminders.sort(key=lambda x: x["time"])
            removed = _reminders.pop(0)
            _save()
        time_str = removed["time"].strftime("%-I:%M %p")
        return f"Canceled your reminder to {removed['text']} at {time_str}."

    return "Sorry, I didn't understand that reminder command."


# --- Standalone test ---

if __name__ == "__main__":
    tests = [
        "remind me to feed the cat at 3pm",
        "remind me at 12:30 to call my mom",
        "remind me to take my pills at 6 o'clock in the morning",
        "remind me on Tuesday at 3pm to go to class",
        "remind me to call mom at noon on Friday",
        "remind me tomorrow at 9am to take out the trash",
        "remind me Wednesday at 1pm to go to class",
        "what reminders do I have",
        "cancel all reminders",
        "cancel my next reminder",
    ]
    for t in tests:
        result = parse(t)
        if result:
            print(f"  {t!r:60s} => {result.command} {result.args}")
        else:
            print(f"  {t!r:60s} => None")
