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
from hecko.commands.template import TemplatePattern, match_any

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


# --- Command classification via templates ---

_LIST = "[the|my] [shopping|grocery|groceries] list"

# Full patterns (with list name): (TemplatePattern, action)
_PATTERNS = [
    (TemplatePattern(f"[add|and|put] $item [to|on] {_LIST}"), "add"),
    (TemplatePattern(f"Hello Grishory's Dad, $item"), "add"),
    (TemplatePattern(f"[remove|take|delete] $item [from|off] {_LIST}"), "remove"),
    (TemplatePattern(f"[do I have|do we have|is|are] $item [on|in] {_LIST}"), "check"),
    (TemplatePattern(f"how many [items|things] [are |][on|in] {_LIST}"), "count"),
    (TemplatePattern(f"[what's|what is] on {_LIST}"), "count"),
]

# Bare patterns for use after "tell our groceries to" prefix (no list name)
_BARE_PATTERNS = [
    (TemplatePattern("[add|put|have] $item"), "add"),
    (TemplatePattern("[remove|take off|delete] $item"), "remove"),
    (TemplatePattern("[do I have|do we have|is there|check for] $item"), "check"),
    (TemplatePattern("how many [items|things]"), "count"),
]

# "and mark it important" suffix detector
_IMPORTANT_RE = re.compile(
    r"\s+and\s+(?:mark\s+(?:it\s+)?(?:as\s+)?important"
    r"|mark\s+(?:it\s+)?starred"
    r"|star\s+it|make\s+it\s+important)\.?$",
    re.IGNORECASE)


def _classify(text):
    """Classify the command. Returns (action, item_name, important) or None.

    Actions: 'add', 'remove', 'check', 'count'
    """
    t, had_prefix = _strip_prefix(text)

    # Strip trailing punctuation and "important" suffix before matching
    important = False
    clean = t.rstrip(".?!")
    imp = _IMPORTANT_RE.search(clean)
    if imp:
        important = True
        clean = clean[:imp.start()].strip()

    # Try full patterns (with list name) first, then bare if prefixed
    pattern_lists = [_PATTERNS]
    if had_prefix:
        pattern_lists.append(_BARE_PATTERNS)

    for patterns in pattern_lists:
        for tmpl, action in patterns:
            fields = tmpl.match(clean)
            if fields is not None:
                if action == "count":
                    return ("count", None, False)

                item_name = fields["item"]
                # Also strip "important" suffix from captured item name
                item_cleaned = _IMPORTANT_RE.sub("", item_name).strip()
                if item_cleaned != item_name:
                    important = True
                    item_name = item_cleaned

                return (action, item_name, action == "add" and important)

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
