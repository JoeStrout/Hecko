"""Quit demo command: exits the main loop."""

from difflib import SequenceMatcher

_PHRASES = [
    "quit demo",
    "exit demo",
    "stop demo",
    "end demo",
    "quit the demo",
    "exit the demo",
    "stop the demo",
    # Common STT misheard variants
    "a quick demo",
    "quick demo",
    "quid demo",
    "quit them oh",
    "quit thermal",
]

quit_requested = False


def score(text):
    t = text.lower().strip().rstrip(".")
    # Check exact matches and close fuzzy matches
    for phrase in _PHRASES:
        if t == phrase:
            return 1.0
        ratio = SequenceMatcher(None, t, phrase).ratio()
        if ratio > 0.75:
            return ratio
    return 0.0


def handle(text):
    global quit_requested
    quit_requested = True
    return "Goodbye!"
