"""Location command: find devices via Apple's Find My service.

Handles:
    "where is Joe?"              -> chime Joe's phone
    "find my phone"              -> chime the speaker's phone
    "ping Michelle's iPad"       -> chime Michelle's iPad
    "locate Joe's MacBook Pro"   -> GPS location
    "geolocate Michelle's phone" -> GPS location
    "list iCloud devices"        -> print device list to terminal (or reply via Telegram)
"""

import math
import threading

from hecko.commands.parse import Parse
from hecko.commands.template import TemplatePattern, match_any

# --- iCloud connection (lazy-initialized) ---

_api = None


def _get_api():
    """Lazy-init and return a PyiCloudService instance."""
    global _api
    if _api is not None:
        return _api
    try:
        from pyicloud import PyiCloudService
        from hecko.icloud_credentials import APPLE_ID, APPLE_PASSWORD
        _api = PyiCloudService(APPLE_ID, APPLE_PASSWORD, accept_terms=True)
        return _api
    except Exception as e:
        print(f"  [location] iCloud auth failed: {e}", flush=True)
        return None


# --- Home location (fetched on startup) ---

_home_lat = None
_home_lon = None
_HOME_DEVICE = ("joe", "macbook")  # device used to determine "here"

_FEET_PER_MILE = 5280
_ON_SITE_FEET = 500


def fetch_home_location():
    """Fetch the home location from the MacBook. Call from a background thread."""
    global _home_lat, _home_lon
    api = _get_api()
    if api is None:
        print("  [location] Can't fetch home location: no iCloud connection.", flush=True)
        return
    device, error = _find_device(api, *_HOME_DEVICE)
    if error:
        print(f"  [location] Can't fetch home location: {error}", flush=True)
        return
    loc = device.location
    if loc and loc.get("latitude") and loc.get("longitude"):
        _home_lat = loc["latitude"]
        _home_lon = loc["longitude"]
        print(f"  [location] Home location: {_home_lat:.4f}, {_home_lon:.4f}", flush=True)
    else:
        print("  [location] Home location not available.", flush=True)


def start_home_location_fetch():
    """Start a background thread to fetch home location. Called from main."""
    t = threading.Thread(target=fetch_home_location, daemon=True)
    t.start()


def _haversine(lat1, lon1, lat2, lon2):
    """Return distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1, lon1, lat2, lon2):
    """Return compass bearing in degrees from point 1 to point 2."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = (math.cos(rlat1) * math.sin(rlat2) -
         math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _compass_direction(degrees):
    """Convert bearing in degrees to a compass direction string."""
    dirs = ["north", "north-northeast", "northeast", "east-northeast",
            "east", "east-southeast", "southeast", "south-southeast",
            "south", "south-southwest", "southwest", "west-southwest",
            "west", "west-northwest", "northwest", "north-northwest"]
    idx = round(degrees / 22.5) % 16
    return dirs[idx]


def _describe_relative_location(lat, lon):
    """Describe a location relative to home. Returns a string like 'on site' or '2.3 miles northwest'."""
    if _home_lat is None or _home_lon is None:
        return f"at latitude {lat:.4f}, longitude {lon:.4f}"
    dist_miles = _haversine(_home_lat, _home_lon, lat, lon)
    dist_feet = dist_miles * _FEET_PER_MILE
    if dist_feet < _ON_SITE_FEET:
        return "on site"
    direction = _compass_direction(_bearing(_home_lat, _home_lon, lat, lon))
    # Format to 2 significant digits
    if dist_miles >= 10:
        return f"about {dist_miles:.0f} miles to the {direction}"
    elif dist_miles >= 1:
        return f"about {dist_miles:.1f} miles to the {direction}"
    else:
        return f"about {dist_miles:.2f} miles to the {direction}"


# --- Device mapping ---
# Maps (owner, device_type) -> substring to match against pyicloud device displayName.
# "phone" is the default when only a person name is given.

_DEVICE_MAP = {
    ("joe", "phone"): "Joe's iPhone (2)",
    ("joe", "ipad"): "iPad (5)",
    ("joe", "watch"): "Joseph's Apple Watch",
    ("joe", "macbook"): "Joe's MacBook Pro",
    ("michelle", "phone"): "Michelle iPhone",
    ("michelle", "ipad"): "iPad (5)",
    ("michelle", "watch"): "Michelle's Apple Watch",
    ("michelle", "macbook"): "Michelle's Air",
}

# Default device type when just a person name is given (e.g., "where is Joe?")
_DEFAULT_DEVICE = "phone"

# Recognized device type keywords -> canonical type
_DEVICE_KEYWORDS = {
    "phone": "phone", "iphone": "phone",
    "ipad": "ipad", "tablet": "ipad",
    "macbook": "macbook", "laptop": "macbook", "mac": "macbook",
    "watch": "watch", "apple watch": "watch",
    "airtag": "airtag", "air tag": "airtag",
}

# Recognized person names
_PEOPLE = ["joe", "michelle"]

# Telegram username -> owner mapping for resolving "my"
_TELEGRAM_OWNERS = {
    "joe": "joe",
    "michelle": "michelle",
}


# --- Template patterns ---

# Chime patterns (default action)
_CHIME_PATTERNS = [
    (TemplatePattern("[where is|where's] $target"), "chime"),
    (TemplatePattern("[find|ping|pink|ring|ding] $target"), "chime"),
    (TemplatePattern("make $target [ring|ding|ping|pink|chime]"), "chime"),
]

# GPS patterns (only "locate" / "geolocate")
_GPS_PATTERNS = [
    (TemplatePattern("[locate|geolocate|geo-locate] $target"), "locate"),
]

# List devices helper
_LIST_PATTERNS = [
    (TemplatePattern("list [icloud|my|the] devices"), "list"),
    (TemplatePattern("list devices"), "list"),
]

_ALL_PATTERNS = _LIST_PATTERNS + _GPS_PATTERNS + _CHIME_PATTERNS


# --- Target resolution ---

def _owner_for_my(source):
    """Determine who 'my' refers to based on source.

    Returns owner string, or an error string starting with "!" if unrecognized.
    For voice, defaults to Joe.
    """
    if "Telegram:" not in source:
        return "joe"
    # Extract username from "[Telegram:Joe]"
    username = source.split("Telegram:", 1)[1].rstrip("]").lower()
    owner = _TELEGRAM_OWNERS.get(username)
    if owner:
        return owner
    return f"!Unrecognized Telegram user '{username}', unable to interpret 'my'."


def _resolve_target(target_text, source="[voice]"):
    """Resolve a captured target phrase like "Joe's MacBook" to (owner, device_type).

    Returns (owner, device_type), or (None, error_message), or (None, None).
    """
    t = target_text.lower().strip()

    # Check for "<person>'s <device>" or "<person> <device>"
    for person in _PEOPLE:
        if person not in t:
            continue
        # Strip the person name and any possessive to get the device part
        rest = t.replace(f"{person}'s", "").replace(f"{person}s", "").replace(person, "").strip()
        if rest:
            for kw, dtype in _DEVICE_KEYWORDS.items():
                if kw in rest:
                    return (person, dtype)
        # Person name with no recognized device -> default to phone
        return (person, _DEFAULT_DEVICE)

    # "my <device>" — resolve owner from source
    if t.startswith("my "):
        owner = _owner_for_my(source)
        if owner.startswith("!"):
            return (None, owner[1:])
        rest = t[3:]
        for kw, dtype in _DEVICE_KEYWORDS.items():
            if kw in rest:
                return (owner, dtype)
        return (owner, _DEFAULT_DEVICE)

    # Bare "the <device>" or just a device keyword
    for kw, dtype in _DEVICE_KEYWORDS.items():
        if kw in t:
            owner = _owner_for_my(source)
            if owner.startswith("!"):
                return (None, owner[1:])
            return (owner, dtype)

    # Bare person name (e.g. just "Joe")
    for person in _PEOPLE:
        if person in t:
            return (person, _DEFAULT_DEVICE)

    return (None, None)


# --- Parsing ---

def parse(text):
    result = match_any(_ALL_PATTERNS, text)
    if result is None:
        return None

    tag, fields = result

    if tag == "list":
        return Parse(command="list_devices", score=0.9)

    target_text = fields.get("target", "")
    # Quick check: does the target contain a person name, "my", or a device keyword?
    t = target_text.lower()
    has_person = any(p in t for p in _PEOPLE)
    has_device = any(kw in t for kw in _DEVICE_KEYWORDS)
    has_my = t.startswith("my ") or t == "my"
    if not (has_person or has_device or has_my):
        return None

    return Parse(
        command=f"{tag}_device",
        score=0.9,
        args={"target": target_text, "action": tag},
    )


# --- Handling ---

def _normalize(s):
    """Normalize curly quotes/apostrophes to straight ones for comparison."""
    return s.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')


def _find_device(api, owner, device_type):
    """Find a matching device from the iCloud account."""
    target_name = _DEVICE_MAP.get((owner, device_type))
    if target_name is None:
        return None, f"I don't know about {owner}'s {device_type}."

    target_lower = _normalize(target_name).lower()
    for device in api.devices:
        d = device.data
        name = _normalize(d.get("name", "")).lower()
        if target_lower in name:
            return device, None

    return None, f"I can't find {target_name} on the iCloud account."


def _format_device_list(api):
    """Build a human-readable list of all devices on the iCloud account."""
    lines = []
    for i, device in enumerate(api.devices):
        d = device.data
        name = d.get("name", "?")
        model = d.get("deviceDisplayName", "?")
        battery = d.get("batteryLevel")
        status = d.get("deviceStatus", "?")
        bat_str = f"  battery={battery:.0%}" if battery is not None else ""
        lines.append(f"  {i}: {name} ({model}){bat_str}  [{status}]")
    return "\n".join(lines) if lines else "  (no devices found)"


def handle(p):
    if p.command == "list_devices":
        api = _get_api()
        if api is None:
            return "I'm having trouble connecting to iCloud."
        if api.requires_2fa:
            return "iCloud requires two-factor authentication. Please approve on a trusted device."
        device_list = _format_device_list(api)
        from_telegram = "Telegram" in p.source
        if from_telegram:
            return f"iCloud devices:\n{device_list}"
        else:
            print(f"\niCloud devices:\n{device_list}\n", flush=True)
            return "Device list sent to terminal."

    action = p.args["action"]
    owner, device_type = _resolve_target(p.args["target"], p.source)
    if owner is None:
        # device_type contains an error message, or None for no match
        return device_type or "I couldn't figure out which device you mean."

    api = _get_api()
    if api is None:
        return "I'm having trouble connecting to iCloud."

    # Check for 2FA requirement
    if api.requires_2fa:
        return "iCloud requires two-factor authentication. Please approve on a trusted device."

    device, error = _find_device(api, owner, device_type)
    if error:
        return error

    friendly = _DEVICE_MAP.get((owner, device_type), f"{owner}'s {device_type}")

    if action == "chime":
        try:
            device.play_sound()
            return f"Ringing {friendly} now."
        except Exception as e:
            print(f"  [location] play_sound failed: {e}", flush=True)
            return f"I couldn't ring {friendly}."

    elif action == "locate":
        try:
            loc = device.location
            if loc and loc.get("latitude") and loc.get("longitude"):
                lat = loc["latitude"]
                lon = loc["longitude"]
                desc = _describe_relative_location(lat, lon)
                return f"{friendly} is {desc}."
            else:
                return f"The location of {friendly} isn't available right now."
        except Exception as e:
            print(f"  [location] locate failed: {e}", flush=True)
            return f"I couldn't get the location of {friendly}."

    return "Sorry, I didn't understand that location command."


# --- Standalone test ---

if __name__ == "__main__":
    # Test parsing only (no iCloud connection needed)
    tests = [
        "where is Joe",
        "where is Michelle",
        "find my phone",
        "ping Joe's phone",
        "find Michelle's iPad",
        "locate Joe's MacBook Pro",
        "geolocate Michelle's phone",
        "where is Joe's laptop",
        "make my phone ring",
        "ring Michelle's phone",
        "where's my iPad",
        "find the MacBook",
        "list iCloud devices",
        "list my devices",
        "list devices",
        # Should NOT match:
        "set a timer for 5 minutes",
        "what's the weather",
    ]
    for t in tests:
        result = parse(t)
        if result:
            print(f"  {t!r:45s} => {result.command:20s} {result.args}")
        else:
            print(f"  {t!r:45s} => None")
