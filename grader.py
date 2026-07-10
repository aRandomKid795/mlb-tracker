"""
PrizePicks MLB Hitter Fantasy Score grading engine.

Every rule in here was verified against real MLB Stats API boxscore data
across dozens of slips. Do not "simplify" the scoring or void logic without
re-checking against known-good days.

Scoring (Batter Fantasy Score):
    Single 3, Double 5, Triple 8, HR 10, Run 2, RBI 2, BB 2, HBP 2, SB 5

Void rule:
    A leg is VOID (refunded, treated as never placed) if the batter had
    fewer than 3 PLATE APPEARANCES (not at-bats). DNPs are also void.

Push:
    Fantasy score exactly equal to the line -> treated as never placed.

Payout multipliers (total return on a power play, after voids shrink it):
    6/6 = 37.5x, 5/5 = 20x, 4/4 = 10x, 3/3 = 6x
    Occasionally a slip carries a non-standard multiplier; callers can override.
"""

import unicodedata

# ---- Scoring ---------------------------------------------------------------

POINTS = {
    "single": 3, "double": 5, "triple": 8, "hr": 10,
    "run": 2, "rbi": 2, "bb": 2, "hbp": 2, "sb": 5,
}

MIN_PA = 3  # minimum plate appearances for a leg to be live

PAYOUTS = {6: 37.5, 5: 20.0, 4: 10.0, 3: 6.0}


def fantasy_score(stat):
    """stat: dict with keys h, 2b, 3b, hr, r, rbi, bb, hbp, sb."""
    singles = stat["h"] - stat["2b"] - stat["3b"] - stat["hr"]
    return (
        singles * POINTS["single"]
        + stat["2b"] * POINTS["double"]
        + stat["3b"] * POINTS["triple"]
        + stat["hr"] * POINTS["hr"]
        + stat["r"] * POINTS["run"]
        + stat["rbi"] * POINTS["rbi"]
        + stat["bb"] * POINTS["bb"]
        + stat["hbp"] * POINTS["hbp"]
        + stat["sb"] * POINTS["sb"]
    )


# ---- Name matching ---------------------------------------------------------

def normalize(name):
    """Accent- and case-insensitive key for matching slip names to boxscores."""
    return (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


# ---- Grading ---------------------------------------------------------------

def grade_leg(player_name, line, lookup):
    """
    lookup: {normalized_name: stat_dict} built from the day's boxscores.
    Returns (result, pa, score, team) where result is HIT / MISS / PUSH / VOID.
    """
    stat = lookup.get(normalize(player_name))
    if stat is None:
        return "VOID", 0, 0, None  # DNP / not in any boxscore
    pa = stat["pa"]
    score = fantasy_score(stat)
    team = stat.get("team")
    if pa < MIN_PA:
        return "VOID", pa, score, team
    if score > line:
        return "HIT", pa, score, team
    if score == line:
        return "PUSH", pa, score, team
    return "MISS", pa, score, team


def grade_slip(legs, lookup, multiplier_override=None):
    """
    legs: list of (player_name, line).
    Returns a dict with per-leg results and the slip outcome + units.

    A power play needs ALL counting legs to hit. Voids and pushes shrink the
    slip (removed from the count). Payout is based on the shrunken leg count.
    """
    graded = []
    counting = 0
    hits = 0
    for name, line in legs:
        result, pa, score, team = grade_leg(name, line, lookup)
        graded.append({
            "player": name, "line": line, "pa": pa,
            "score": score, "result": result, "team": team,
        })
        if result in ("HIT", "MISS"):
            counting += 1
            if result == "HIT":
                hits += 1

    won = counting > 0 and hits == counting

    if won:
        mult = multiplier_override if multiplier_override else PAYOUTS.get(counting, 0)
    else:
        mult = 0

    return {
        "legs": graded,
        "counting_legs": counting,
        "hits": hits,
        "won": won,
        "multiplier": mult,
        "leg_record": f"{hits}-{counting - hits}",
    }


def grade_day(slips, lookup, overrides=None):
    """
    slips: {slip_number: [(player, line), ...]}
    overrides: optional {slip_number: multiplier} for non-standard payouts.
    Returns full results + day totals.
    """
    overrides = overrides or {}
    results = {}
    total_hits = total_misses = total_push = total_void = 0
    slips_won = 0
    units_staked = len(slips)
    units_returned = 0.0

    for num, legs in slips.items():
        r = grade_slip(legs, lookup, overrides.get(num))
        results[num] = r
        for leg in r["legs"]:
            if leg["result"] == "HIT":
                total_hits += 1
            elif leg["result"] == "MISS":
                total_misses += 1
            elif leg["result"] == "PUSH":
                total_push += 1
            else:
                total_void += 1
        if r["won"]:
            slips_won += 1
            units_returned += r["multiplier"]

    decided = total_hits + total_misses
    leg_win_pct = (total_hits / decided * 100) if decided else 0.0

    return {
        "slips": results,
        "leg_hits": total_hits,
        "leg_misses": total_misses,
        "pushes": total_push,
        "voids": total_void,
        "leg_win_pct": round(leg_win_pct, 1),
        "slips_staked": units_staked,
        "slips_won": slips_won,
        "units_staked": units_staked,
        "units_returned": units_returned,
        "net_units": round(units_returned - units_staked, 1),
    }
