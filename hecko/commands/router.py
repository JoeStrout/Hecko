"""Command router: parses input with all registered commands, dispatches to best match.

Each command module must provide:
    parse(text: str) -> Parse | None   # classify + extract args, return None if no match
    handle(parse: Parse) -> str        # execute the command using pre-extracted args
"""

import os
from datetime import datetime

_commands = []
last_response = None  # most recent command response, for "say that again"

# Log file: lives next to the hecko package directory
_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "hecko.log")


def _log_request(text, best_parse, source="[voice]"):
    """Append a compact 2-line entry to the log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if best_parse is None:
        parse_line = "  -> none"
    else:
        mod = best_parse.module.__name__.split(".")[-1]
        parts = [f"{mod}.{best_parse.command}", f"score={best_parse.score:.2f}"]
        for k, v in best_parse.args.items():
            parts.append(f"{k}={v!r}")
        parse_line = f"  -> {', '.join(parts)}"
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(f"{ts} {source}  {text}\n{parse_line}\n")
    except OSError:
        pass


def register(command_module):
    """Register a command module (must have parse and handle functions)."""
    _commands.append(command_module)


def dispatch(text, source="[voice]"):
    """Find the best-matching command and run it.

    Args:
        text: Transcribed user input.
        source: Source tag for logging, e.g. "[voice]" or "[Telegram:Joe]".

    Returns:
        (response, scores): response text and a list of (name, score) tuples
        for all commands that returned a non-None parse, sorted descending.
        Returns (None, []) when sleeping and input is ignored.
    """
    # While sleeping, only the sleep module can handle input (to wake up)
    from hecko.commands import sleep
    if sleep.sleeping:
        p = sleep.parse(text)
        if p is not None:
            p.module = sleep
            _log_request(text, p, source)
            response = sleep.handle(p)
            return response, [("sleep", p.score)]
        return None, []

    parses = []

    for cmd in _commands:
        p = cmd.parse(text)
        if p is not None:
            p.module = cmd
            parses.append(p)

    if not parses:
        _log_request(text, None, source)
        return f"I heard you say: {text}", []

    parses.sort(key=lambda p: -p.score)

    scores = [(p.module.__name__.split(".")[-1], p.score) for p in parses]

    best = parses[0]
    _log_request(text, best, source)
    response = best.module.handle(best)

    # Don't overwrite last_response if this was a repeat command
    if best.module.__name__.split(".")[-1] != "repeat":
        global last_response
        last_response = response

    return response, scores
