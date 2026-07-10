"""
Persists the running tracker to a local JSON file so it survives restarts
and can be committed to your repo (so the deployed dashboard shows history).

Each day is stored by date string. Re-grading a date overwrites it.

On Streamlit Cloud, local writes don't survive a restart (ephemeral disk),
so after saving locally this module also pushes the file straight to your
GitHub repo via the API, using a token stored in Streamlit secrets. That
makes the change permanent — the next restart rebuilds from the updated repo.
"""

import base64
import json
import os

import requests

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "tracker_data.json")


def load_tracker():
    if not os.path.exists(TRACKER_FILE):
        return {}
    try:
        with open(TRACKER_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _push_to_github(content_str, github_cfg):
    """
    github_cfg: dict with keys token, repo ("owner/name"), branch, path.
    Commits content_str as tracker_data.json to the repo via the GitHub API.
    Returns (ok: bool, message: str).
    """
    token = github_cfg.get("token")
    repo = github_cfg.get("repo")
    branch = github_cfg.get("branch", "main")
    path = github_cfg.get("path", "tracker_data.json")

    if not token or not repo:
        return False, "GitHub auto-commit not configured (missing token/repo)."

    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    # Need the current file's sha to update it (GitHub requires this for edits)
    sha = None
    r = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=15)
    if r.status_code == 200:
        sha = r.json().get("sha")
    elif r.status_code != 404:
        return False, f"GitHub GET failed: {r.status_code} {r.text[:200]}"

    payload = {
        "message": "Update tracker_data.json via dashboard",
        "content": base64.b64encode(content_str.encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, json=payload, timeout=15)
    if r.status_code in (200, 201):
        return True, "Committed to GitHub."
    return False, f"GitHub PUT failed: {r.status_code} {r.text[:200]}"


def save_day(date, day_result, raw_slips_text="", github_cfg=None):
    """
    Store/overwrite a graded day locally, then (if github_cfg is provided)
    push the updated tracker to GitHub so it persists across restarts.

    Stores day totals PLUS full per-slip/per-leg detail (player, line, PA,
    fantasy score, result, slip number, whether the slip won and its payout)
    so any downstream analysis (slip position, stacks, streaks, etc.) can be
    computed straight from this file without re-fetching boxscores.

    Returns (data, push_ok, push_message).
    """
    data = load_tracker()

    slips_detail = {}
    for num, slip_result in day_result.get("slips", {}).items():
        slips_detail[str(num)] = {
            "legs": slip_result["legs"],  # list of {player, line, pa, score, result}
            "counting_legs": slip_result["counting_legs"],
            "hits": slip_result["hits"],
            "won": slip_result["won"],
            "multiplier": slip_result["multiplier"],
            "leg_record": slip_result["leg_record"],
        }

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
        "slips": slips_detail,
    }
    content_str = json.dumps(data, indent=2, sort_keys=True)
    with open(TRACKER_FILE, "w") as f:
        f.write(content_str)

    push_ok, push_msg = (True, "Local only (no GitHub config).")
    if github_cfg:
        push_ok, push_msg = _push_to_github(content_str, github_cfg)

    return data, push_ok, push_msg


def delete_day(date, github_cfg=None):
    data = load_tracker()
    if date in data:
        del data[date]
        content_str = json.dumps(data, indent=2, sort_keys=True)
        with open(TRACKER_FILE, "w") as f:
            f.write(content_str)
        if github_cfg:
            _push_to_github(content_str, github_cfg)
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


def flatten_props(data=None):
    """
    Returns one row per leg across every stored day:
    {date, slip, player, line, pa, score, result, slip_won, slip_multiplier}

    This is the queryable form for analysis like "hit rate by slip number"
    or "which players/stacks hit" — no boxscore re-fetching needed.
    Only present for days graded after per-leg storage was added; older
    days saved before this feature won't have a "slips" key and are skipped.
    """
    data = data if data is not None else load_tracker()
    rows = []
    for date, day in data.items():
        for slip_num, slip in day.get("slips", {}).items():
            for leg in slip["legs"]:
                rows.append({
                    "date": date,
                    "slip": int(slip_num),
                    "player": leg["player"],
                    "line": leg["line"],
                    "pa": leg["pa"],
                    "score": leg["score"],
                    "result": leg["result"],
                    "slip_won": slip["won"],
                    "slip_multiplier": slip["multiplier"],
                })
    return rows
