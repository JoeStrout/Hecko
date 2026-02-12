"""Timer command: set, query, and cancel multiple named timers.

Handles:
    "set a timer for 5 minutes"
    "set a 30 second timer"
    "how much time is left"
    "cancel the 5 minute timer"
    "cancel all timers"
"""

import re
import threading
import time

# Active timers: {label: {"end": timestamp, "duration_sec": int}}
_timers = {}
_lock = threading.Lock()

# Callback for announcing expired timers (set by main via set_announce_callback)
_announce_cb = None


def set_announce_callback(cb):
    """Set the function to call when a timer expires. cb(text) -> None."""
    global _announce_cb
    _announce_cb = cb


# --- Timer checker background thread ---

_checker_thread = None


def _start_checker():
    global _checker_thread
    if _checker_thread is not None and _checker_thread.is_alive():
        return

    def _check_loop():
        while True:
            time.sleep(0.5)
            now = time.time()
            expired = []
            with _lock:
                for label, info in list(_timers.items()):
                    if now >= info["end"]:
                        expired.append(label)
                        del _timers[label]
            for label in expired:
                msg = f"[[timer_done.mp3]]Your {label} timer is done![[timer_done.mp3]]"
                if _announce_cb:
                    _announce_cb(msg)

    _checker_thread = threading.Thread(target=_check_loop, daemon=True)
    _checker_thread.start()


# --- Duration parsing ---

def _parse_duration(text):
    """Extract a duration in seconds from text. Returns (seconds, label) or None.

    Handles forms like:
        "5 minutes", "30 seconds", "1 hour", "2 and a half minutes",
        "one minute", "an hour", "a minute and 30 seconds"
    """
    t = text.lower()

    _WORD_NUMS = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
        "forty five": 45, "fifty": 50, "sixty": 60, "ninety": 90,
        "a": 1, "an": 1,
    }

    total_sec = 0
    found = False

    # Match patterns like "N hour(s)", "N minute(s)", "N second(s)"
    # Also handles hyphenated forms from STT like "five-minute"
    # Also "and a half"
    for unit, multiplier in [("hour", 3600), ("minute", 60), ("second", 1)]:
        # Numeric: "5 minutes", "30 seconds", "5-minute"
        m = re.search(rf"(\d+(?:\.\d+)?)[- ]*{unit}", t)
        if m:
            total_sec += float(m.group(1)) * multiplier
            found = True
            continue

        # Word number: "five minutes", "an hour", "five-minute"
        for word, val in _WORD_NUMS.items():
            if re.search(rf"\b{word}[- ]+{unit}", t):
                total_sec += val * multiplier
                found = True
                break

        # "and a half" modifier
        if re.search(rf"{unit}s?\s+and\s+a\s+half", t):
            total_sec += 0.5 * multiplier
            found = True

    if found and total_sec > 0:
        return int(total_sec), _format_duration(int(total_sec))

    return None


def _format_duration(seconds):
    """Format seconds into a human-readable label like '5-minute' or '2-hour'."""
    if seconds >= 3600 and seconds % 3600 == 0:
        n = seconds // 3600
        return f"{n}-hour" if n > 1 else "1-hour"
    elif seconds >= 60 and seconds % 60 == 0:
        n = seconds // 60
        return f"{n}-minute" if n > 1 else "1-minute"
    else:
        return f"{seconds}-second"


def _format_time_remaining(seconds):
    """Format remaining seconds as natural speech."""
    if seconds < 1:
        return "less than a second"

    parts = []
    if seconds >= 3600:
        h = int(seconds // 3600)
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
        seconds %= 3600
    if seconds >= 60:
        m = int(seconds // 60)
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
        seconds %= 60
    if seconds >= 1 and len(parts) < 2:  # skip seconds if we already have hours+minutes
        s = int(seconds)
        parts.append(f"{s} second{'s' if s != 1 else ''}")

    if len(parts) == 1:
        return parts[0]
    return " and ".join([", ".join(parts[:-1]), parts[-1]])


# --- Command scoring and handling ---

def _classify(text):
    """Classify the command type: 'set', 'query', 'cancel', or None."""
    t = text.lower()
    if re.search(r"\bcancel\b.*\btimer", t) or re.search(r"\bstop\b.*\btimer", t):
        if re.search(r"\ball\b", t):
            return "cancel_all"
        return "cancel"
    if re.search(r"\b(set|start|create)\b.*\btimer\b", t) or re.search(r"\btimer\b.*\bfor\b", t):
        return "set"
    if re.search(r"\b(how much|how long|time.*(left|remaining)|what.*(left|remaining))", t):
        return "query"
    return None


def score(text):
    cmd = _classify(text)
    if cmd is not None:
        return 0.9
    # Weak match: mentions "timer" at all
    if "timer" in text.lower():
        return 0.5
    return 0.0


def handle(text):
    _start_checker()

    cmd = _classify(text)

    if cmd == "set":
        result = _parse_duration(text)
        if result is None:
            return "Sorry, I didn't understand the duration."
        seconds, label = result
        with _lock:
            _timers[label] = {"end": time.time() + seconds, "duration_sec": seconds}
        return f"Timer set for {_format_time_remaining(seconds)}."

    elif cmd == "query":
        with _lock:
            if not _timers:
                return "There are currently no timers set."
            parts = []
            now = time.time()
            for label, info in _timers.items():
                remaining = max(0, info["end"] - now)
                parts.append(
                    f"{_format_time_remaining(remaining)} left on your {label} timer"
                )
        if len(parts) == 1:
            return f"You have {parts[0]}."
        return "You have " + ", and ".join([", ".join(parts[:-1]), parts[-1]]) + "."

    elif cmd == "cancel_all":
        with _lock:
            count = len(_timers)
            _timers.clear()
        if count == 0:
            return "You don't have any timers to cancel."
        return f"All {count} timer{'s' if count != 1 else ''} canceled."

    elif cmd == "cancel":
        # Try to match the duration mentioned to an active timer
        result = _parse_duration(text)
        if result:
            _, label = result
            with _lock:
                if label in _timers:
                    del _timers[label]
                    return f"Your {label} timer has been cancelled."
        # If only one timer, cancel it
        with _lock:
            if len(_timers) == 1:
                label = list(_timers.keys())[0]
                del _timers[label]
                return f"Your {label} timer has been cancelled."
            elif len(_timers) == 0:
                return "There are currently no timers set."
        return "Which timer do you want to cancel?"

    return "Sorry, I didn't understand that timer command."
