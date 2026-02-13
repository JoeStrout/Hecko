"""Music command: control Spotify playback via voice.

Handles:
    "play some music"                           -> shuffle Liked Songs / favorites
    "play my Birthday Favorites playlist"       -> shuffle a named playlist
    "play Pour Some Sugar on Me"                -> search + play a track
    "play Ordinary by Alex Warren"              -> search + play track by artist
    "pause music" / "pause the music"
    "resume music" / "unpause"
    "stop music" / "stop the music"
    "skip" / "next song"
    "what's playing" / "what song is this"
"""

import os
import random
import re
import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from hecko.spotify_credentials import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
)
from hecko.commands.parse import Parse

# Spotify OAuth scopes we need
_SCOPES = " ".join([
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-library-read",
])

# Cache file lives next to this module's package root
_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".spotipy_cache")

# Lazy-init Spotify client
_sp = None

# Playlist cache: list of (name, id) tuples, refreshed periodically
_playlist_cache = []
_playlist_cache_time = 0
_PLAYLIST_CACHE_TTL = 600  # 10 minutes


def _get_sp():
    """Get or create the authenticated Spotify client."""
    global _sp
    if _sp is None:
        auth = SpotifyOAuth(
            scope=_SCOPES,
            open_browser=True,
            cache_path=_CACHE_PATH,
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
        )
        _sp = spotipy.Spotify(auth_manager=auth)
    return _sp


def _get_device_id():
    """Find an active Spotify device, or fall back to the first available."""
    sp = _get_sp()
    devices = sp.devices().get("devices", [])
    if not devices:
        raise RuntimeError("No Spotify devices found. Open Spotify on your Mac first.")
    for d in devices:
        if d.get("is_active"):
            return d["id"]
    return devices[0]["id"]


# --- Volume ducking ---

_saved_volume = None


def duck_volume(level=10):
    """Lower Spotify volume, saving the current level for later restore."""
    global _saved_volume
    try:
        sp = _get_sp()
        pb = sp.current_playback()
        if pb and pb.get("device"):
            _saved_volume = pb["device"].get("volume_percent")
            sp.volume(level, device_id=pb["device"]["id"])
    except Exception:
        pass


def restore_volume():
    """Restore Spotify volume to the level saved by duck_volume()."""
    global _saved_volume
    if _saved_volume is None:
        return
    try:
        sp = _get_sp()
        device_id = _get_device_id()
        sp.volume(_saved_volume, device_id=device_id)
    except Exception:
        pass
    finally:
        _saved_volume = None


def _get_playlists():
    """Return cached list of (name, id) tuples, refreshing if stale."""
    global _playlist_cache, _playlist_cache_time
    now = time.time()
    if _playlist_cache and (now - _playlist_cache_time) < _PLAYLIST_CACHE_TTL:
        return _playlist_cache

    sp = _get_sp()
    playlists = []
    offset = 0
    limit = 50
    while True:
        page = sp.current_user_playlists(limit=limit, offset=offset)
        items = page.get("items", [])
        for p in items:
            playlists.append((p["name"], p["id"]))
        if not items or len(items) < limit:
            break
        offset += limit

    _playlist_cache = playlists
    _playlist_cache_time = now
    return playlists


def _normalize(s):
    """Lowercase and strip punctuation for fuzzy comparison."""
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def _word_set(s):
    """Split normalized string into a set of words."""
    return set(_normalize(s).split())


def _find_playlist(name):
    """Find the best-matching playlist. Returns (playlist_name, id) or None.

    Matching strategy (in priority order):
    1. Exact match (case-insensitive)
    2. Query words are a subset of playlist name words
    3. Playlist name words are a subset of query words
    4. Any word overlap, ranked by fraction of shared words
    """
    playlists = _get_playlists()
    query_norm = _normalize(name)
    query_words = _word_set(name)

    # 1. Exact match
    for pname, pid in playlists:
        if _normalize(pname) == query_norm:
            return (pname, pid)

    # 2. Query is a substring of (or contains) the playlist name
    for pname, pid in playlists:
        pnorm = _normalize(pname)
        if query_norm in pnorm or pnorm in query_norm:
            return (pname, pid)

    # 3-5. Word-overlap matching
    best = None
    best_score = 0
    for pname, pid in playlists:
        pw = _word_set(pname)
        if not pw or not query_words:
            continue
        overlap = query_words & pw
        if not overlap:
            continue
        # Query words all appear in playlist name
        if query_words <= pw:
            s = 0.9 + len(overlap) / (len(pw) + 10)  # prefer tighter matches
        # Playlist name words all appear in query
        elif pw <= query_words:
            s = 0.8 + len(overlap) / (len(query_words) + 10)
        # Partial overlap
        else:
            s = len(overlap) / max(len(query_words), len(pw))
        if s > best_score:
            best_score = s
            best = (pname, pid)

    # Require decent quality: subset matches always pass (score >= 0.8),
    # partial overlap needs more than half the query words to match
    if best and best_score >= 0.6:
        return best
    return None


def _play_liked_songs():
    """Fetch Liked Songs and play them shuffled."""
    sp = _get_sp()
    # Fetch up to 200 liked songs (4 pages of 50)
    uris = []
    offset = 0
    limit = 50
    max_tracks = 200
    while offset < max_tracks:
        page = sp.current_user_saved_tracks(limit=limit, offset=offset)
        items = page.get("items", [])
        for item in items:
            track = item.get("track")
            if track and track.get("uri"):
                uris.append(track["uri"])
        if not items or len(items) < limit:
            break
        offset += limit

    if not uris:
        raise RuntimeError("Your Liked Songs library is empty.")

    random.shuffle(uris)
    # Spotify allows max 800 URIs per request; 200 is fine
    device_id = _get_device_id()
    sp.start_playback(device_id=device_id, uris=uris)
    return len(uris)


# --- Command classification ---

def _classify(text):
    """Classify the music command.

    Returns (action, detail) where action is one of:
        'play_music'    - generic "play some music", detail=None
        'play_playlist' - play a named playlist, detail=playlist_name
        'play_track'    - play a specific song, detail=(title, artist_or_None)
        'pause'         - pause playback
        'resume'        - resume playback
        'stop'          - stop playback
        'skip'          - skip to next track
        'now_playing'   - what's currently playing
    Or None if not a music command.
    """
    t = text.strip()

    # Pause
    if re.search(r"\b(pause|hold)\b.*\b(music|song|spotify|playback)\b", t, re.I) or \
       re.search(r"\b(pause|hold)\b\s*(the\s+)?(music|song)", t, re.I) or \
       t.strip().lower() in ("pause", "pause music", "pause the music"):
        return ("pause", None)

    # Resume / unpause
    if re.search(r"\b(resume|unpause|continue)\b.*\b(music|song|spotify|playback)\b", t, re.I) or \
       re.search(r"\b(resume|unpause|continue)\b\s*(the\s+)?(music|song)", t, re.I) or \
       t.strip().lower() in ("resume", "resume music", "unpause", "resume the music"):
        return ("resume", None)

    # Stop
    if re.search(r"\b(stop)\b.*\b(music|song|spotify|playback)\b", t, re.I) or \
       re.search(r"\bstop\b\s*(the\s+)?(music|song)", t, re.I):
        return ("stop", None)

    # Skip / next
    if re.search(r"\b(skip|next)\b.*\b(song|track)\b", t, re.I) or \
       t.strip().lower() in ("skip", "next", "next song", "skip song"):
        return ("skip", None)

    # What's playing
    if re.search(r"\bwhat(?:'s|\s+is)\s+playing\b", t, re.I) or \
       re.search(r"\bwhat\s+song\s+is\s+this\b", t, re.I):
        return ("now_playing", None)

    # Generic "play some music" variants (before specific "play X" parsing)
    if re.search(
        r"\b(play|have|hear|put on|throw on|turn on|start|how about|i want|i'd like)"
        r"\s+(?:some|the)?\s*music\b", t, re.I):
        return ("play_music", None)
    if re.search(
        r"\blet(?:'s|s| us)\s+(?:play|have|hear|listen to|get)\s+(?:some\s+)?music\b",
        t, re.I):
        return ("play_music", None)
    if re.search(r"\bmusic\s*,?\s*please\b", t, re.I):
        return ("play_music", None)

    # Play commands — must start with "play"
    m = re.match(r"(?:.*?\b)?play\s+(.*)", t, re.I)
    if not m:
        return None
    rest = m.group(1).strip().rstrip(".")

    # "play some music" / "play music" (fallback for edge cases)
    if re.match(r"(?:some\s+)?music$", rest, re.I):
        return ("play_music", None)

    # "play my X playlist" / "play the X playlist"
    pm = re.match(r"(?:my|the)\s+(.+?)\s+playlist$", rest, re.I)
    if pm:
        return ("play_playlist", pm.group(1).strip())

    # "play X playlist"
    pm = re.match(r"(.+?)\s+playlist$", rest, re.I)
    if pm:
        return ("play_playlist", pm.group(1).strip())

    # "play TITLE by ARTIST"
    pm = re.match(r"(.+?)\s+by\s+(.+)$", rest, re.I)
    if pm:
        return ("play_track", (pm.group(1).strip(), pm.group(2).strip()))

    # "play TITLE" (bare track search)
    if rest:
        return ("play_track", (rest, None))

    return None


def parse(text):
    result = _classify(text)
    if result is not None:
        action, detail = result
        args = {}
        if action == "play_playlist":
            args["name"] = detail
        elif action == "play_track":
            args["title"] = detail[0]
            args["artist"] = detail[1]
        return Parse(command=action, score=0.9, args=args)

    # Weak: mentions music/spotify/song
    if re.search(r"\b(music|spotify|song|playlist)\b", text, re.I):
        return Parse(command="play_music", score=0.4, args={})
    return None


def handle(p):
    try:
        if p.command == "pause":
            sp = _get_sp()
            sp.pause_playback(device_id=_get_device_id())
            return "Music paused."

        elif p.command == "resume":
            sp = _get_sp()
            sp.start_playback(device_id=_get_device_id())
            return "Resuming music."

        elif p.command == "stop":
            sp = _get_sp()
            device_id = _get_device_id()
            sp.pause_playback(device_id=device_id)
            sp.seek_track(0, device_id=device_id)
            return "Music stopped."

        elif p.command == "skip":
            sp = _get_sp()
            sp.next_track(device_id=_get_device_id())
            return "Skipping to the next song."

        elif p.command == "now_playing":
            sp = _get_sp()
            pb = sp.current_playback()
            if not pb or not pb.get("item"):
                return "Nothing is playing right now."
            item = pb["item"]
            title = item.get("name", "unknown")
            artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
            state = "playing" if pb.get("is_playing") else "paused"
            return f"Currently {state}: {title} by {artists}."

        elif p.command == "play_music":
            count = _play_liked_songs()
            return f"Playing your liked songs. {count} tracks shuffled."

        elif p.command == "play_playlist":
            playlist_name = p.args["name"]
            # "liked songs" is special — not a real playlist
            if _normalize(playlist_name) in ("liked songs", "liked", "favorites",
                                              "my liked songs", "my favorites"):
                count = _play_liked_songs()
                return f"Playing your liked songs. {count} tracks shuffled."
            match = _find_playlist(playlist_name)
            if not match:
                return f"I couldn't find a playlist called {playlist_name}."
            matched_name, pid = match
            sp = _get_sp()
            device_id = _get_device_id()
            sp.shuffle(True, device_id=device_id)
            sp.start_playback(device_id=device_id, context_uri=f"spotify:playlist:{pid}")
            return f"Playing your {matched_name} playlist."

        elif p.command == "play_track":
            title = p.args["title"]
            artist = p.args.get("artist")
            sp = _get_sp()
            q = f'track:"{title}"'
            if artist:
                q += f' artist:"{artist}"'
            res = sp.search(q=q, type="track", limit=1)
            items = res.get("tracks", {}).get("items", [])
            if not items:
                return f"I couldn't find a song called {title}." + \
                       (f" by {artist}" if artist else "")
            track = items[0]
            track_name = track.get("name", title)
            track_artist = ", ".join(a.get("name", "") for a in track.get("artists", []))
            sp.start_playback(device_id=_get_device_id(), uris=[track["uri"]])
            return f"Playing {track_name} by {track_artist}."

    except Exception as e:
        return f"Sorry, I had trouble with Spotify: {e}"

    return "Sorry, I didn't understand that music command."


# --- Standalone test ---

if __name__ == "__main__":
    tests = [
        "Play some music.",
        "Play music.",
        "Let's have some music.",
        "Play my Birthday Favorites playlist.",
        "Play Pour Some Sugar on Me.",
        "Play Ordinary by Alex Warren.",
        "Pause music.",
        "Resume music.",
        "Stop the music.",
        "Skip song.",
        "Next song.",
        "What's playing?",
        "What song is this?",
    ]
    for t in tests:
        result = parse(t)
        if result:
            print(f"  {t!r:55s} => {result.command} {result.args}")
        else:
            print(f"  {t!r:55s} => None")
