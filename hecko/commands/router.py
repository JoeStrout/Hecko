"""Command router: scores all registered commands and dispatches to the best match.

Each command module must provide:
    score(text: str) -> float    # 0.0–1.0, how confident this command matches
    handle(text: str) -> str     # execute the command, return response text
"""

_commands = []
last_response = None  # most recent command response, for "say that again"


def register(command_module):
    """Register a command module (must have score and handle functions)."""
    _commands.append(command_module)


def dispatch(text):
    """Find the best-matching command and run it.

    Args:
        text: Transcribed user input.

    Returns:
        (response, scores): response text and a list of (name, score) tuples
        for all commands that returned a nonzero score, sorted descending.
    """
    scores = []

    for cmd in _commands:
        s = cmd.score(text)
        if s > 0.0:
            scores.append((cmd.__name__.split(".")[-1], s))

    scores.sort(key=lambda x: -x[1])

    if scores:
        best_name = scores[0][0]
        best_cmd = None
        for cmd in _commands:
            if cmd.__name__.split(".")[-1] == best_name:
                best_cmd = cmd
                break
        response = best_cmd.handle(text)
        # Don't overwrite last_response if this was a repeat command
        if best_name != "repeat":
            global last_response
            last_response = response
        return response, scores

    return f"I heard you say: {text}", []
