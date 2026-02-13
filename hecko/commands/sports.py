"""Sports command: check upcoming games for followed teams.

Handles:
    "when's the next U of A basketball game"
    "when do the wildcats play next"
    "is there a basketball game this week"
    "any games next week"
    "who won the last Arizona game"
    "what was the score of the last basketball game"
    "how did the cats do"

Uses ESPN's undocumented public API (no key required).
"""

import re
import urllib.request
import json
import time
from datetime import datetime, timedelta, timezone

from hecko.commands.parse import Parse

# --- Team registry ---
# Each entry has: sport path, team_id, names, aliases (specific team match),
# and sport_keywords (match when no team name given).

_TEAMS = [
    {
        "sport": "basketball/mens-college-basketball",
        "team_id": 12,
        "name": "Arizona Wildcats men's basketball",
        "short_name": "Arizona basketball",
        "sport_keywords": ["basketball"],
        # Patterns that match this team specifically in user speech
        "aliases": re.compile(
            r"\b(?:u\s*of\s*a|arizona|wildcats|cats)\b", re.IGNORECASE),
    },
]

# Generic sport-related words that trigger a search even without a team name
_SPORT_TRIGGER = re.compile(
    r"\b(?:game|games|play|playing|score|schedule|match)\b", re.IGNORECASE)

# Cache: {cache_key: (timestamp, data)}
_cache = {}
_CACHE_TTL = 600  # 10 minutes


def _fetch_schedule(sport, team_id):
    """Fetch team schedule from ESPN API, with caching."""
    cache_key = f"{sport}/{team_id}"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    url = (f"http://site.api.espn.com/apis/site/v2/sports/{sport}"
           f"/teams/{team_id}/schedule")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        _cache[cache_key] = (now, data)
        return data
    except Exception:
        # Return stale cache if available
        if cache_key in _cache:
            return _cache[cache_key][1]
        raise


def _get_opponent_name(comp, team_display_name):
    """Extract our team and opponent from a competition.

    Returns (our_competitor, opponent_name, home_away) or (None, None, None).
    """
    our_team = None
    opponent = None
    for c in comp["competitors"]:
        if c["team"]["displayName"] == team_display_name:
            our_team = c
        else:
            opponent = c

    if not opponent:
        return our_team, None, None

    opp_name = opponent["team"]["displayName"]
    # Simplify "Texas Tech Red Raiders" to "Texas Tech"
    opp_words = opp_name.split()
    if len(opp_words) > 2:
        opp_name = " ".join(opp_words[:2])

    home_away = our_team["homeAway"] if our_team else "home"
    return our_team, opp_name, home_away


def _format_game_time(event):
    """Parse event date and return (day_name, month_day, time_str, local_dt)."""
    game_dt = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    local_dt = game_dt.astimezone()
    day_name = local_dt.strftime("%A")
    month_day = local_dt.strftime("%B %-d")
    time_str = local_dt.strftime("%-I:%M %p").lower()
    return day_name, month_day, time_str, local_dt


def _format_upcoming_game(event, data, team_name):
    """Format a single upcoming game as a speech string."""
    comp = event["competitions"][0]
    day_name, month_day, time_str, _ = _format_game_time(event)

    _, opp_name, home_away = _get_opponent_name(
        comp, data["team"]["displayName"])

    if not opp_name:
        return (f"{team_name}: {day_name}, {month_day} at {time_str}.")

    if home_away == "home":
        loc = f"at home against {opp_name}"
    else:
        loc = f"at {opp_name}"

    return (f"{team_name}: {day_name}, {month_day} at {time_str}, {loc}.")


def _find_next_game(data, team_name):
    """Find the next upcoming game from schedule data."""
    for event in data.get("events", []):
        comp = event["competitions"][0]
        status = comp["status"]["type"]
        if status["state"] == "pre":
            return _format_upcoming_game(event, data, team_name)
    return None


def _find_games_in_range(data, team_name, start_dt, end_dt):
    """Find all upcoming games within a datetime range."""
    results = []
    for event in data.get("events", []):
        comp = event["competitions"][0]
        status = comp["status"]["type"]
        if status["state"] == "pre":
            _, _, _, local_dt = _format_game_time(event)
            if start_dt <= local_dt < end_dt:
                results.append(_format_upcoming_game(event, data, team_name))
    return results


def _find_last_game(data, team_name):
    """Find the most recent completed game and report the result."""
    last_event = None
    for event in data.get("events", []):
        comp = event["competitions"][0]
        status = comp["status"]["type"]
        if status["state"] == "post":
            last_event = event  # keep going to find the most recent

    if not last_event:
        return None

    comp = last_event["competitions"][0]
    team_display = data["team"]["displayName"]

    our_team = None
    opponent = None
    for c in comp["competitors"]:
        if c["team"]["displayName"] == team_display:
            our_team = c
        else:
            opponent = c

    if not our_team or not opponent:
        return None

    our_score = our_team.get("score", {}).get("displayValue", "?")
    opp_score = opponent.get("score", {}).get("displayValue", "?")

    opp_name = opponent["team"]["displayName"]
    opp_words = opp_name.split()
    if len(opp_words) > 2:
        opp_name = " ".join(opp_words[:2])

    won = our_team.get("winner", False)
    if won:
        return f"{team_name} beat {opp_name}, {our_score} to {opp_score}."
    else:
        return f"{team_name} lost to {opp_name}, {opp_score} to {our_score}."


# --- Team matching ---

def _find_teams(text):
    """Find which team(s) the user is asking about.

    Returns a list of team dicts. If a specific team alias matches, returns
    just that team. If only sport keywords match, returns all teams for that
    sport. If only generic words like "game", returns all followed teams.
    """
    t = text.lower()

    # First: check for specific team aliases
    specific = [team for team in _TEAMS if team["aliases"].search(text)]
    if specific:
        return specific

    # Second: check for sport keywords
    for team in _TEAMS:
        for kw in team["sport_keywords"]:
            if re.search(r"\b" + kw + r"\b", t):
                # Return all teams matching this sport keyword
                return [tm for tm in _TEAMS
                        if kw in tm["sport_keywords"]]

    # Third: generic sport trigger words → all followed teams
    if _SPORT_TRIGGER.search(text):
        return list(_TEAMS)

    return []


# --- Command classification ---

def _classify(text):
    """Classify the sports command.

    Returns (action, teams_list) or None.
    Actions: 'next_game', 'this_week', 'next_week', 'last_game'
    """
    t = text.lower()
    teams = _find_teams(text)
    if not teams:
        return None

    # Last game / score queries
    if re.search(r"\b(?:last\s+game|most\s+recent|who\s+won|what\s+was\s+the\s+score"
                 r"|how\s+did\s+.+\s+do|did\s+.+\s+win)\b", t):
        return ("last_game", teams)

    # This week
    if re.search(r"\bthis\s+week\b", t):
        return ("this_week", teams)

    # Next week
    if re.search(r"\bnext\s+week\b", t):
        return ("next_week", teams)

    # Default: next game
    return ("next_game", teams)


def parse(text):
    result = _classify(text)
    if result is None:
        return None
    action, teams = result
    command_map = {
        "next_game": "next_game", "this_week": "this_week",
        "next_week": "next_week", "last_game": "last_game",
    }
    return Parse(command=command_map[action], score=0.9,
                 args={"teams": teams})


def handle(p):
    teams = p.args.get("teams", [])
    responses = []

    for team in teams:
        try:
            data = _fetch_schedule(team["sport"], team["team_id"])

            if p.command == "next_game":
                resp = _find_next_game(data, team["short_name"])
                if resp:
                    responses.append(resp)
                else:
                    responses.append(
                        f"I couldn't find any upcoming {team['short_name']} games.")

            elif p.command == "this_week":
                now = datetime.now().astimezone()
                start = now
                # End of this week (next Sunday at midnight)
                days_until_sunday = (6 - now.weekday()) % 7 + 1
                end = (now + timedelta(days=days_until_sunday)).replace(
                    hour=0, minute=0, second=0, microsecond=0)
                games = _find_games_in_range(data, team["short_name"],
                                             start, end)
                if games:
                    responses.extend(games)
                else:
                    responses.append(
                        f"No {team['short_name']} games this week.")

            elif p.command == "next_week":
                now = datetime.now().astimezone()
                # Next Sunday
                days_until_sunday = (6 - now.weekday()) % 7 + 1
                start = (now + timedelta(days=days_until_sunday)).replace(
                    hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=7)
                games = _find_games_in_range(data, team["short_name"],
                                             start, end)
                if games:
                    responses.extend(games)
                else:
                    responses.append(
                        f"No {team['short_name']} games next week.")

            elif p.command == "last_game":
                resp = _find_last_game(data, team["short_name"])
                if resp:
                    responses.append(resp)
                else:
                    responses.append(
                        f"I couldn't find a recent {team['short_name']} game.")

        except Exception as e:
            responses.append(
                f"Sorry, I had trouble checking the {team['short_name']} schedule: {e}")

    if responses:
        return " ".join(responses)
    return "Sorry, I didn't understand that sports question."


# --- Standalone test ---

if __name__ == "__main__":
    tests = [
        "when's the next U of A basketball game",
        "when do the wildcats play next",
        "when's the next Arizona game",
        "when is the next Arizona basketball game",
        "what's the Arizona basketball schedule",
        "when do the cats play",
        "is there a basketball game this week",
        "any games next week",
        "who won the last Arizona game",
        "what was the score of the last basketball game",
        "how did the cats do",
        "when's the next game",
    ]
    for t in tests:
        result = parse(t)
        if result:
            team_names = ", ".join(tm["short_name"] for tm in result.args["teams"])
            print(f"  {t!r:55s} => {result.command}, [{team_names}]")
        else:
            print(f"  {t!r:55s} => None")

    print()
    print("Live tests:")
    live_tests = [
        "when's the next U of A basketball game",
        "is there a basketball game this week",
        "who won the last Arizona game",
        "when's the next game",
    ]
    for t in live_tests:
        print(f"  Q: {t}")
        p = parse(t)
        if p:
            print(f"  A: {handle(p)}")
        else:
            print(f"  A: (no parse)")
        print()
