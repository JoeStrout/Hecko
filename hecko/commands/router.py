"""Command router: parses input with all registered commands, dispatches to best match.

Each command module must provide:
    parse(text: str) -> Parse | None   # classify + extract args, return None if no match
    handle(parse: Parse) -> str        # execute the command using pre-extracted args
"""

_commands = []
last_response = None  # most recent command response, for "say that again"


def register(command_module):
    """Register a command module (must have parse and handle functions)."""
    _commands.append(command_module)


def dispatch(text):
    """Find the best-matching command and run it.

    Args:
        text: Transcribed user input.

    Returns:
        (response, scores): response text and a list of (name, score) tuples
        for all commands that returned a non-None parse, sorted descending.
    """
    parses = []

    for cmd in _commands:
        p = cmd.parse(text)
        if p is not None:
            p.module = cmd
            parses.append(p)

    if not parses:
        return f"I heard you say: {text}", []

    parses.sort(key=lambda p: -p.score)

    scores = [(p.module.__name__.split(".")[-1], p.score) for p in parses]

    best = parses[0]
    response = best.module.handle(best)

    # Don't overwrite last_response if this was a repeat command
    if best.module.__name__.split(".")[-1] != "repeat":
        global last_response
        last_response = response

    return response, scores
