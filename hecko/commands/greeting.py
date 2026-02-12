"""Greeting command: responds to hello, hi, good morning, thank you, goodbye, etc."""

import re
from datetime import datetime

_GREETINGS = [
    "hello", "hi", "hey", "howdy", "greetings",
    "good morning", "good afternoon", "good evening",
    "what's up", "whats up",
]

_THANKS = re.compile(
    r"\b(?:thank\s*you|thanks|thank\s*ya|much\s+appreciated)\b", re.IGNORECASE)

_GOODBYE = re.compile(
    r"\b(?:goodbye|good\s*bye|bye\s*bye|bye|see\s+you\s+later|see\s+ya"
    r"|good\s*night|later|take\s+care|have\s+a\s+good\s+(?:one|night|day|evening)"
    r"|until\s+next\s+time|so\s+long|adios|ciao"
    r"|I'?m\s+done|that'?s?\s+all|that\s+is\s+all|that(?:'?ll|\s+will)\s+be\s+all)\b",
    re.IGNORECASE)

_YOURE_WELCOME = [
    "You're welcome!",
    "Happy to help!",
    "Anytime!",
    "Of course!",
    "My pleasure!",
    "No problem!",
]

_FAREWELL = [
    "See you later!",
    "Goodbye!",
    "Take care!",
    "Until next time!",
]

_welcome_idx = 0
_farewell_idx = 0


def _classify(text):
    """Classify: 'greeting', 'thanks', 'goodbye', or None."""
    t = text.lower().strip()

    if _THANKS.search(t):
        return "thanks"
    if _GOODBYE.search(t):
        return "goodbye"

    for g in _GREETINGS:
        if t == g or t == g + " alexa" or t.startswith(g) or g in t:
            return "greeting"

    return None


def score(text):
    cls = _classify(text)
    if cls is None:
        return 0.0
    t = text.lower().strip()
    if cls == "thanks" or cls == "goodbye":
        return 0.9
    # Greeting scoring (preserve original logic)
    for g in _GREETINGS:
        if t == g or t == g + " alexa":
            return 1.0
    for g in _GREETINGS:
        if t.startswith(g):
            return 0.8
    for g in _GREETINGS:
        if g in t:
            return 0.4
    return 0.4


def _time_of_day():
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"


def handle(text):
    global _welcome_idx, _farewell_idx

    cls = _classify(text)

    if cls == "thanks":
        resp = _YOURE_WELCOME[_welcome_idx % len(_YOURE_WELCOME)]
        _welcome_idx += 1
        return resp

    if cls == "goodbye":
        resp = _FAREWELL[_farewell_idx % len(_FAREWELL)]
        _farewell_idx += 1
        return resp

    return f"Good {_time_of_day()}! How can I help you?"
