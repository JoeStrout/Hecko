"""Grocery list command: add, remove, check, and count items on Our Groceries.

Handles:
    "add ketchup to the shopping list"
    "put diet 7 up on the grocery list"
    "remove soda from the shopping list"
    "take cream of tartar off the grocery list"
    "do I have eggs on the shopping list?"
    "how many items are on my grocery list?"
    "add eggs to the grocery list and mark it important"

Also accepts "tell Our Groceries to ..." or "ask Our Groceries ..." prefix.
"""

import asyncio
import re
import time
from ourgroceries import OurGroceries
from hecko.og_credentials import OG_USERNAME, OG_PASSWORD
from hecko.commands.parse import Parse

# Cached client and list ID
_og = None
_list_id = None

# Items cache: avoid hammering the Our Groceries API on every command
_items_cache = None   # cached list of items
_items_cache_ts = 0   # timestamp of last fetch
_ITEMS_CACHE_TTL = 120  # seconds — refetch after 2 minutes

# Star prefix used to mark items as important
_STAR = "\u2b50 "


async def _get_client():
    """Get or create the Our Groceries client."""
    global _og
    if _og is None:
        _og = OurGroceries(OG_USERNAME, OG_PASSWORD)
        await _og.login()
    return _og


async def _get_list_id():
    """Find and cache the Shopping List ID."""
    global _list_id
    if _list_id is None:
        og = await _get_client()
        result = await og.get_my_lists()
        for lst in result.get("shoppingLists", []):
            if lst["name"] == "Shopping List":
                _list_id = lst["id"]
                break
        if _list_id is None:
            raise RuntimeError("No list named 'Shopping List' found in Our Groceries")
    return _list_id


async def _get_items(force=False):
    """Get items from the Shopping List, using cache when possible.

    The Our Groceries team asks that we avoid unnecessary API calls.
    We cache the item list and only refetch after _ITEMS_CACHE_TTL seconds
    or when force=True (after we mutate the list).
    """
    global _items_cache, _items_cache_ts
    now = time.time()
    if not force and _items_cache is not None and (now - _items_cache_ts) < _ITEMS_CACHE_TTL:
        return _items_cache

    og = await _get_client()
    list_id = await _get_list_id()
    result = await og.get_list_items(list_id)
    _items_cache = result.get("list", {}).get("items", [])
    _items_cache_ts = now
    return _items_cache


def _invalidate_cache():
    """Invalidate the items cache after a mutation (add/remove)."""
    global _items_cache
    _items_cache = None


def _find_item(items, name):
    """Find an item by name (case-insensitive), ignoring crossed-off items.

    Matches against both the raw value and the value with the star prefix stripped.
    """
    name_lower = name.lower()
    for item in items:
        if item.get("crossedOff"):
            continue
        val = item["value"]
        val_lower = val.lower()
        # Match with or without star prefix
        if val_lower == name_lower or val_lower == (_STAR + name).lower():
            return item
        # Also strip star and compare
        if val_lower.startswith(_STAR.lower()) and val_lower[len(_STAR):] == name_lower:
            return item
    return None


async def _add_item(item_name, important=False):
    """Add an item to the shopping list. Returns a response string."""
    items = await _get_items()
    existing = _find_item(items, item_name)
    if existing:
        return f"{item_name} is already on the shopping list."

    og = await _get_client()
    list_id = await _get_list_id()
    value = (_STAR + item_name) if important else item_name
    await og.add_item_to_list(list_id, value, auto_category=True)
    _invalidate_cache()
    suffix = " and marked it important" if important else ""
    return f"I've added {item_name} to the shopping list{suffix}."


async def _remove_item(item_name):
    """Remove an item from the shopping list. Returns a response string."""
    items = await _get_items()
    existing = _find_item(items, item_name)
    if not existing:
        return f"I don't see {item_name} on the shopping list."

    og = await _get_client()
    list_id = await _get_list_id()
    await og.remove_item_from_list(list_id, existing["id"])
    _invalidate_cache()
    return f"I've removed {item_name} from the shopping list."


async def _check_item(item_name):
    """Check if an item is on the shopping list. Returns a response string."""
    items = await _get_items()
    existing = _find_item(items, item_name)
    if existing:
        return f"Yes, {item_name} is on the shopping list."
    return f"No, {item_name} is not on the shopping list."


async def _count_items():
    """Count non-crossed-off items on the shopping list."""
    items = await _get_items()
    active = [i for i in items if not i.get("crossedOff")]
    n = len(active)
    if n == 0:
        return "Your shopping list is empty."
    elif n == 1:
        return "There is 1 item on your shopping list."
    return f"There are {n} items on your shopping list."


# --- Prefix stripping ---

_OG_PREFIX_RE = re.compile(
    r"^(?:tell|fill|ask)\s+(?:our|their|are|the)\s+groceries\s+(?:to\s+)?",
    re.IGNORECASE)


def _strip_prefix(text):
    """Strip 'tell our groceries to' / 'ask our groceries' prefix if present.

    Returns (stripped_text, had_prefix).
    """
    t = text.strip()
    m = _OG_PREFIX_RE.match(t)
    if m:
        return t[m.end():], True
    return t, False


# --- Command classification ---

_LIST_WORDS = r"(shopping|grocery|groceries)\s+list"

# Patterns: (regex, action)
_PATTERNS = [
    # "add X to the list" / "put X on the list" ("and" = Whisper mishearing of "add")
    (re.compile(rf"(?:add|and|put)\s+(.+?)\s+(?:to|on)\s+(?:the\s+|my\s+)?{_LIST_WORDS}",
                re.IGNORECASE), "add"),
    # "remove X from the list" / "take X off the list"
    (re.compile(rf"(?:remove|take|delete)\s+(.+?)\s+(?:from|off)\s+(?:the\s+|my\s+)?{_LIST_WORDS}",
                re.IGNORECASE), "remove"),
    # "do I have X on the list" / "do we have X" / "is X on the list"
    (re.compile(rf"(?:do\s+(?:I|we)\s+have|is|are)\s+(.+?)\s+(?:on|in)\s+(?:the\s+|my\s+)?{_LIST_WORDS}",
                re.IGNORECASE), "check"),
    # "how many items on the list"
    (re.compile(rf"how\s+many\s+(?:items?|things?)\s+(?:are\s+)?(?:on|in)\s+(?:the\s+|my\s+)?{_LIST_WORDS}",
                re.IGNORECASE), "count"),
    # "what's on the list" / "what is on the list"
    (re.compile(rf"what(?:'s|\s+is)\s+on\s+(?:the\s+|my\s+)?{_LIST_WORDS}",
                re.IGNORECASE), "count"),
]


# Bare patterns for use after "tell our groceries to" prefix (no list name needed)
_BARE_PATTERNS = [
    # "add X"
    (re.compile(r"(?:add|put)\s+(.+?)\.?$", re.IGNORECASE), "add"),
    # "remove X" / "take off X"
    (re.compile(r"(?:remove|take\s+off|delete)\s+(.+?)\.?$", re.IGNORECASE), "remove"),
    # "do I have X" / "is X on there" / "check for X"
    (re.compile(r"(?:do\s+(?:I|we)\s+have|is\s+there|check\s+for)\s+(.+?)\.?\??$",
                re.IGNORECASE), "check"),
    # "how many items"
    (re.compile(r"how\s+many\s+(?:items?|things?)", re.IGNORECASE), "count"),
]


def _classify(text):
    """Classify the command. Returns (action, item_name, important) or None.

    Actions: 'add', 'remove', 'check', 'count'
    """
    t, had_prefix = _strip_prefix(text)

    # Try full patterns (with list name) first
    for pattern, action in _PATTERNS:
        m = pattern.search(t)
        if m:
            if action == "count":
                return ("count", None, False)

            item_name = m.group(1).strip()
            important = False

            if action == "add":
                # Check for "and mark it important" / "and star it" etc.
                # This may appear after the list name, so check the full text
                imp_match = re.search(
                    r"and\s+(?:mark\s+(?:it\s+)?(?:as\s+)?important"
                    r"|mark\s+(?:it\s+)?starred"
                    r"|star\s+it|make\s+it\s+important)",
                    t, re.IGNORECASE)
                if imp_match:
                    important = True

            return (action, item_name, important)

    # If OG prefix was present, try bare patterns (no list name needed)
    if had_prefix:
        for pattern, action in _BARE_PATTERNS:
            m = pattern.search(t)
            if m:
                if action == "count":
                    return ("count", None, False)

                item_name = m.group(1).strip()
                important = False

                if action == "add":
                    imp_match = re.search(
                        r"and\s+(?:mark\s+(?:it\s+)?(?:as\s+)?important"
                        r"|mark\s+(?:it\s+)?starred"
                        r"|star\s+it|make\s+it\s+important)",
                        t, re.IGNORECASE)
                    if imp_match:
                        item_name = re.sub(
                            r"\s+and\s+(?:mark|star|make)\s.*$", "",
                            item_name, flags=re.IGNORECASE).strip()
                        important = True

                return (action, item_name, important)

    return None


def parse(text):
    t, had_prefix = _strip_prefix(text)
    result = _classify(text)
    if result is not None:
        action, item_name, important = result
        command_map = {
            "add": "add_item", "remove": "remove_item",
            "check": "check_item", "count": "count_items",
        }
        args = {}
        if item_name is not None:
            args["item_name"] = item_name
        if action == "add":
            args["important"] = important
        return Parse(command=command_map[action], score=0.9, args=args)

    # Weak match: mentions shopping/grocery list at all
    if re.search(_LIST_WORDS, t, re.IGNORECASE):
        return None  # recognized topic but can't classify action
    if re.search(r"\b(?:our|their|are|the)\s+groceries\b", text, re.IGNORECASE):
        return None
    return None


def handle(p):
    try:
        if p.command == "add_item":
            return asyncio.run(_add_item(p.args["item_name"], p.args.get("important", False)))
        elif p.command == "remove_item":
            return asyncio.run(_remove_item(p.args["item_name"]))
        elif p.command == "check_item":
            return asyncio.run(_check_item(p.args["item_name"]))
        elif p.command == "count_items":
            return asyncio.run(_count_items())
    except Exception as e:
        return f"Sorry, I had trouble reaching Our Groceries: {e}"

    return "Sorry, I didn't understand that grocery list command."


# --- Standalone test ---

if __name__ == "__main__":
    tests = [
        "add ketchup to the shopping list",
        "put diet 7 up on the grocery list",
        "add eggs to the grocery list",
        "remove soda from the shopping list",
        "take cream of tartar off the grocery list",
        "do I have eggs on the shopping list?",
        "how many items are on my grocery list?",
        "tell Our Groceries to add milk to the shopping list",
        "ask Our Groceries to remove bread from the grocery list",
        "add butter to the shopping list and mark it important",
        # Bare commands with OG prefix (no list name)
        "tell Our Groceries to add cranberry juice",
        "fill our groceries to add cranberry juice.",
        "ask Our Groceries to remove milk",
        "tell Our Groceries to add eggs and mark it important",
        "tell our groceries do I have eggs",
        "tell our groceries how many items",
    ]
    for t in tests:
        result = parse(t)
        if result:
            print(f"  {t!r:60s} => {result.command} {result.args}")
        else:
            print(f"  {t!r:60s} => None")
