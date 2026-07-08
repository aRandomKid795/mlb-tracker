"""
Pulls MLB boxscore data from the public MLB Stats API and builds a
{normalized_name: stat} lookup for a given date.

Runs from wherever you deploy it (Streamlit Cloud, your Mac) since those
can reach statsapi.mlb.com. No API key required.
"""

import requests
from grader import normalize

SCHEDULE = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
BOXSCORE = "https://statsapi.mlb.com/api/v1/game/{pk}/boxscore"

TIMEOUT = 20


def get_game_pks(date):
    """date: 'YYYY-MM-DD'. Returns list of gamePk ints for that day."""
    r = requests.get(SCHEDULE.format(date=date), timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return [g["gamePk"] for day in data.get("dates", []) for g in day.get("games", [])]


def _batter_stat(batting):
    return {
        "ab": batting.get("atBats", 0),
        "pa": batting.get("plateAppearances", 0),
        "h": batting.get("hits", 0),
        "2b": batting.get("doubles", 0),
        "3b": batting.get("triples", 0),
        "hr": batting.get("homeRuns", 0),
        "r": batting.get("runs", 0),
        "rbi": batting.get("rbi", 0),
        "bb": batting.get("baseOnBalls", 0),
        "hbp": batting.get("hitByPitch", 0),
        "sb": batting.get("stolenBases", 0),
    }


def build_lookup(date, progress=None):
    """
    Fetches every game's boxscore for the date and returns
    {normalized_name: stat_dict} for all batters who appeared.

    progress: optional callback(fraction, message) for UI progress bars.
    """
    pks = get_game_pks(date)
    lookup = {}
    total = len(pks)
    if total == 0:
        return lookup, 0

    for i, pk in enumerate(pks):
        try:
            r = requests.get(BOXSCORE.format(pk=pk), timeout=TIMEOUT)
            r.raise_for_status()
            box = r.json()
        except Exception:
            continue
        for side in ("home", "away"):
            team = box.get("teams", {}).get(side, {})
            for player in team.get("players", {}).values():
                batting = player.get("stats", {}).get("batting", {})
                if batting:  # only players who batted
                    name = player["person"]["fullName"]
                    lookup[normalize(name)] = _batter_stat(batting)
        if progress:
            progress((i + 1) / total, f"Fetched {i + 1}/{total} games")

    return lookup, total
