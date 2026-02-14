"""Sleep/wake command: pause and resume the assistant.

Handles:
    "go to sleep"
    "stop listening"
    "pause operation"
    "enter privacy mode"
    "wake up"

While sleeping, the router ignores and does not log all other commands.
"""

from hecko.commands.parse import Parse
from hecko.commands.template import TemplatePattern

sleeping = False

_SLEEP_PATTERNS = [
    TemplatePattern("go to sleep"),
    TemplatePattern("stop listening"),
    TemplatePattern("[pause|suspend] [operation|operations]"),
    TemplatePattern("enter privacy mode"),
    TemplatePattern("privacy mode"),
    TemplatePattern("go [to|into] sleep [mode|]"),
    TemplatePattern("sleep mode"),
    TemplatePattern("be quiet"),
    TemplatePattern("shut up"),
    TemplatePattern("mute"),
]

_WAKE_PATTERNS = [
    TemplatePattern("wake up"),
    TemplatePattern("I'm back"),
    TemplatePattern("[resume|start] listening"),
    TemplatePattern("[exit|leave] [privacy|sleep] mode"),
    TemplatePattern("resume [operation|operations]"),
]


def parse(text):
    t = text.strip().rstrip(".!").lower()
    if sleeping:
        for p in _WAKE_PATTERNS:
            if p.match(t) is not None:
                return Parse(command="wake", score=0.95)
        return None

    for p in _SLEEP_PATTERNS:
        if p.match(t) is not None:
            return Parse(command="sleep", score=0.95)
    return None


def handle(p):
    global sleeping
    if p.command == "sleep":
        sleeping = True
        return "Going to sleep. Say \"wake up\" when you need me."
    elif p.command == "wake":
        sleeping = False
        return "I'm back! How can I help you?"
    return None


# --- Standalone tests ---

if __name__ == "__main__":
    tests_awake = [
        ("go to sleep", "sleep"),
        ("stop listening", "sleep"),
        ("pause operation", "sleep"),
        ("enter privacy mode", "sleep"),
        ("privacy mode", "sleep"),
        ("sleep mode", "sleep"),
        ("be quiet", "sleep"),
        ("mute", "sleep"),
        ("hello", None),
        ("what time is it", None),
        ("wake up", None),  # shouldn't match when awake
    ]

    tests_asleep = [
        ("wake up", "wake"),
        ("I'm back", "wake"),
        ("resume listening", "wake"),
        ("exit privacy mode", "wake"),
        ("exit sleep mode", "wake"),
        ("hello", None),  # ignored while sleeping
        ("what time is it", None),  # ignored while sleeping
        ("go to sleep", None),  # already sleeping
    ]

    passed = 0
    failed = 0

    def check(label, got_cmd, expected_cmd):
        global passed, failed
        if got_cmd == expected_cmd:
            passed += 1
            print(f"  PASS: {label}")
        else:
            failed += 1
            print(f"  FAIL: {label} — expected {expected_cmd}, got {got_cmd}")

    print("=== Sleep/wake tests (awake) ===\n")
    sleeping = False
    for text, expected in tests_awake:
        result = parse(text)
        check(f"awake: {text!r}", result.command if result else None, expected)

    print("\n=== Sleep/wake tests (asleep) ===\n")
    sleeping = True
    for text, expected in tests_asleep:
        result = parse(text)
        check(f"asleep: {text!r}", result.command if result else None, expected)

    sleeping = False  # reset
    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests")
