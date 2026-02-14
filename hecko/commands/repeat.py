"""Repeat command: repeat the last spoken response.

Handles:
    "say that again"
    "repeat that"
    "can you repeat that"
    "what did you say"
    "come again"
"""

from hecko.commands.parse import Parse
from hecko.commands.template import TemplatePattern

_PATTERNS = [
    TemplatePattern("say that again"),
    TemplatePattern("repeat that"),
    TemplatePattern("[can|could] you [repeat|say] that"),
    TemplatePattern("what did you [say|just say]"),
    TemplatePattern("what was that"),
    TemplatePattern("come again"),
    TemplatePattern("one more time"),
    TemplatePattern("say it again"),
    TemplatePattern("repeat [yourself|the last]"),
    TemplatePattern("I [didn't|didn't|did not] [catch|hear|get] that"),
    TemplatePattern("pardon"),
    TemplatePattern("[could|can] you say that again"),
]


def parse(text):
    for p in _PATTERNS:
        if p.match(text) is not None:
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
