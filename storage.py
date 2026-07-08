"""
Persists the running tracker to a local JSON file so it survives restarts
and can be committed to your repo (so the deployed dashboard shows history).

Each day is stored by date string. Re-grading a date overwrites it.
"""

import json
import os

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "tracker_data.json")


def load_tracker():
    if not os.path.exists(TRACKER_FILE):
        return {}
    try:
        with open(TRACKER_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_day(date, day_result, raw_slips_text=""):
    """Store/overwrite a graded day. Keeps only the summary the dashboard needs."""
    data = load_tracker()
    data[date] = {
        "leg_hits": day_result["leg_hits"],
        "leg_misses": day_result["leg_misses"],
        "pushes": day_result["pushes"],
        "voids": day_result["voids"],
        "leg_win_pct": day_result["leg_win_pct"],
        "slips_staked": day_result["slips_staked"],
        "slips_won": day_result["slips_won"],
        "units_staked": day_result["units_staked"],
        "units_returned": day_result["units_returned"],
        "net_units": day_result["net_units"],
        "slips_text": raw_slips_text,
    }
    with open(TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return data


def delete_day(date):
    data = load_tracker()
    if date in data:
        del data[date]
        with open(TRACKER_FILE, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    return data


def overall_totals(data=None):
    """Aggregate every stored day into all-time totals."""
    data = data if data is not None else load_tracker()
    h = sum(d["leg_hits"] for d in data.values())
    m = sum(d["leg_misses"] for d in data.values())
    staked = sum(d["units_staked"] for d in data.values())
    returned = sum(d["units_returned"] for d in data.values())
    slips_won = sum(d["slips_won"] for d in data.values())
    decided = h + m
    return {
        "leg_record": f"{h}-{m}",
        "leg_win_pct": round(h / decided * 100, 1) if decided else 0.0,
        "slips_staked": staked,
        "slips_won": slips_won,
        "net_units": round(returned - staked, 1),
        "roi_pct": round((returned - staked) / staked * 100, 1) if staked else 0.0,
    }
