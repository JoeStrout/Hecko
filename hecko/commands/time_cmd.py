"""Time/date command: tells the current time, day, or date.

Handles:
    "what time is it"
    "what day is it"
    "what is the date"
    "what's today's date"
"""

import re
from datetime import datetime


def _classify(text):
    """Classify: 'time', 'day', 'date', or None."""
    t = text.lower()
    if re.search(r"\btime\b", t):
        return "time"
    if re.search(r"\bdate\b", t):
        return "date"
    if re.search(r"\bday\b", t):
        return "day"
    return None


def score(text):
    t = text.lower()
    # Must ask a question about time/day/date
    if re.search(r"\b(what|tell me)\b", t) and _classify(t) is not None:
        return 0.9
    return 0.0


def handle(text):
    now = datetime.now()
    cmd = _classify(text)

    if cmd == "time":
        hour = now.hour % 12 or 12
        minute = now.minute
        ampm = "AM" if now.hour < 12 else "PM"
        if minute == 0:
            return f"It's {hour} {ampm}."
        elif minute < 10:
            return f"It's {hour} oh {minute} {ampm}."
        else:
            return f"It's {hour} {minute} {ampm}."

    elif cmd == "date":
        return f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}."

    elif cmd == "day":
        return f"Today is {now.strftime('%A, %B')} {now.day}."

    return f"It's {now.strftime('%I:%M %p')}."
