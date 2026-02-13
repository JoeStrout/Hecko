"""Parse object for the command system.

Each command module's parse(text) returns a Parse (or None).
The router picks the highest-scoring Parse and passes it to handle(parse).
"""

from dataclasses import dataclass, field


@dataclass
class Parse:
    command: str          # e.g. "add_item", "set_timer", "get_time"
    score: float          # 0.0–1.0
    args: dict = field(default_factory=dict)
    module: object = None  # reference to the module — set by router
