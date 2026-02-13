"""Repeat command: repeat the last spoken response.

Handles:
    "say that again"
    "repeat that"
    "can you repeat that"
    "what did you say"
    "come again"
"""

import re

from hecko.commands.parse import Parse

_PATTERNS = re.compile(
    r"\b(?:"
    r"say\s+that\s+again"
    r"|repeat\s+that"
    r"|(?:can|could)\s+you\s+(?:repeat|say)\s+that"
    r"|what\s+did\s+you\s+(?:say|just\s+say)"
    r"|what\s+was\s+that"
    r"|come\s+again"
    r"|one\s+more\s+time"
    r"|say\s+it\s+again"
    r"|repeat\s+(?:yourself|the\s+last)"
    r"|I\s+didn'?t\s+(?:catch|hear|get)\s+that"
    r"|pardon"
    r")\b",
    re.IGNORECASE)


def parse(text):
    if _PATTERNS.search(text):
        return Parse(command="repeat", score=0.95)
    return None


def handle(p):
    from hecko.commands.router import last_response
    if last_response:
        return last_response
    return "I haven't said anything yet."


if __name__ == "__main__":
    tests = [
        "say that again",
        "repeat that",
        "can you repeat that",
        "what did you say",
        "what was that",
        "come again",
        "one more time",
        "say it again",
        "I didn't catch that",
        "I didn't hear that",
        "pardon",
        "could you say that again",
        "hello",
    ]
    for t in tests:
        result = parse(t)
        if result:
            print(f"  {t!r:45s} => {result.command} (score={result.score})")
        else:
            print(f"  {t!r:45s} => None")
