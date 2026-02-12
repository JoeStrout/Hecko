"""Greeting command: responds to hello, hi, good morning, etc."""

from datetime import datetime

_GREETINGS = [
    "hello", "hi", "hey", "howdy", "greetings",
    "good morning", "good afternoon", "good evening",
    "what's up", "whats up",
]


def score(text):
    t = text.lower().strip()
    # Exact or near-exact match
    for g in _GREETINGS:
        if t == g or t == g + " alexa":
            return 1.0
    # Starts with a greeting
    for g in _GREETINGS:
        if t.startswith(g):
            return 0.8
    # Contains a greeting
    for g in _GREETINGS:
        if g in t:
            return 0.4
    return 0.0


def _time_of_day():
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"


def handle(text):
    return f"Good {_time_of_day()}! How can I help you?"
