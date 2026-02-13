"""Quit demo command: exits the main loop."""

from difflib import SequenceMatcher

from hecko.commands.parse import Parse

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


def parse(text):
    t = text.lower().strip().rstrip(".")
    best_score = 0.0
    for phrase in _PHRASES:
        if t == phrase:
            return Parse(command="quit", score=1.0)
        ratio = SequenceMatcher(None, t, phrase).ratio()
        if ratio > best_score:
            best_score = ratio
    if best_score > 0.75:
        return Parse(command="quit", score=best_score)
    return None


def handle(p):
    global quit_requested
    quit_requested = True
    return "Goodbye!"
