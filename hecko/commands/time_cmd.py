"""Time/date command: tells the current time, day, or date.

Handles:
    "what time is it"
    "what day is it"
    "what is the date"
    "what's today's date"
"""

import re
from datetime import datetime

from hecko.commands.parse import Parse


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


def parse(text):
    t = text.lower()
    if not re.search(r"\b(what|tell me)\b", t):
        return None
    cls = _classify(t)
    if cls is None:
        return None
    command_map = {"time": "get_time", "date": "get_date", "day": "get_day"}
    return Parse(command=command_map[cls], score=0.9)


def handle(p):
    now = datetime.now()

    if p.command == "get_time":
        hour = now.hour % 12 or 12
        minute = now.minute
        ampm = "AM" if now.hour < 12 else "PM"
        if minute == 0:
            return f"It's {hour} {ampm}."
        elif minute < 10:
            return f"It's {hour} oh {minute} {ampm}."
        else:
            return f"It's {hour} {minute} {ampm}."

    elif p.command == "get_date":
        return f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}."

    elif p.command == "get_day":
        return f"Today is {now.strftime('%A, %B')} {now.day}."

    return f"It's {now.strftime('%I:%M %p')}."


# --- Standalone test ---

if __name__ == "__main__":
    tests = [
        "what time is it",
        "what day is it",
        "what is the date",
        "what's today's date",
        "tell me the time",
        "hello",
    ]
    for t in tests:
        result = parse(t)
        if result:
            print(f"  {t!r:40s} => {result.command} (score={result.score})")
        else:
            print(f"  {t!r:40s} => None")
