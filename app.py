"""
PrizePicks MLB tracker dashboard.

Public view: anyone with the link sees the running tracker (read-only).
Admin view: unlock with a password (set in Streamlit secrets) to paste slips
and grade a day, which updates the tracker everyone sees.

Run locally:   streamlit run app.py
Deploy:        push to GitHub, connect Streamlit Community Cloud.
"""

import datetime as dt

import pandas as pd
import streamlit as st

from grader import grade_day
from mlb_data import build_lookup
from parser import parse_slips
from storage import load_tracker, save_day, delete_day, overall_totals

st.set_page_config(page_title="Slip Tracker", page_icon="⚾", layout="wide")

# ---- Styling ---------------------------------------------------------------
# Scoreboard aesthetic: dark field-green base, chalk-white type, amber accent
# like a stadium out-of-town board. Mono for numbers so columns align.
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&family=Roboto+Mono:wght@400;600&display=swap');
  html, body, [class*="css"] { font-family: 'Archivo', sans-serif; }
  .stApp { background: #0f1a14; }
  h1, h2, h3 { font-family: 'Archivo', sans-serif; font-weight: 800; letter-spacing: -0.02em; color: #f4f1e8; }
  .metric-big { font-family: 'Roboto Mono', monospace; font-weight: 600; }
  .board {
    background: #14251b; border: 1px solid #24422f; border-radius: 10px;
    padding: 18px 22px; margin-bottom: 8px;
  }
  .accent { color: #f0b429; }
  .pos { color: #4ade80; }
  .neg { color: #f87171; }
  .stDataFrame { font-family: 'Roboto Mono', monospace; }
  [data-testid="stMetricValue"] { font-family: 'Roboto Mono', monospace; }
</style>
""", unsafe_allow_html=True)


# ---- Header ----------------------------------------------------------------
st.markdown("# ⚾ Slip Tracker")
st.markdown("<p style='color:#8aa896; margin-top:-12px;'>MLB hitter fantasy score — daily grades, units, and win rate.</p>", unsafe_allow_html=True)


# ---- Overall board (everyone sees this) ------------------------------------
data = load_tracker()
totals = overall_totals(data)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Leg record", totals["leg_record"], f"{totals['leg_win_pct']}%")
c2.metric("Net units", f"{totals['net_units']:+.1f}u")
c3.metric("ROI", f"{totals['roi_pct']:+.1f}%")
c4.metric("Slips won", f"{totals['slips_won']}/{totals['slips_staked']}")


# ---- Full day-by-day table -------------------------------------------------
st.markdown("### Day by day")
if data:
    rows = []
    for date in sorted(data.keys(), reverse=True):  # newest day on top
        d = data[date]
        rows.append({
            "Date": date,
            "Record": f"{d['leg_hits']}-{d['leg_misses']}",
            "Leg %": f"{d['leg_win_pct']}%",
            "Slips": d["slips_staked"],
            "Won": d["slips_won"],
            "Net": f"{d['net_units']:+.1f}u",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # simple cumulative units chart
    cum = []
    running = 0.0
    for date in sorted(data.keys()):
        running += data[date]["net_units"]
        cum.append({"Date": date, "Cumulative units": round(running, 1)})
    st.line_chart(pd.DataFrame(cum).set_index("Date"))
else:
    st.info("No days graded yet. Unlock the admin panel below to grade your first day.")


# ---- Admin panel (grading) -------------------------------------------------
st.markdown("---")
with st.expander("🔒 Admin — grade a day"):
    pw = st.text_input("Password", type="password")
    admin_pw = st.secrets.get("admin_password", "changeme")

    if pw and pw == admin_pw:
        st.success("Unlocked.")

        date = st.date_input("Game date", value=dt.date.today() - dt.timedelta(days=1))
        date_str = date.isoformat()

        slips_text = st.text_area(
            "Paste slips",
            height=280,
            placeholder="Slip 1\n1. Player Name - More 5.5 Hitter Fantasy Score\n...",
        )

        # optional non-standard multipliers, e.g. "9:8" means slip 9 pays 8x
        overrides_text = st.text_input(
            "Multiplier overrides (optional)",
            placeholder="e.g. 9:8  (slip 9 pays 8x instead of default)",
        )

        if st.button("Grade this day", type="primary"):
            slips, warnings = parse_slips(slips_text)
            if not slips:
                st.error("Couldn't parse any slips. Check the format.")
            else:
                overrides = {}
                for chunk in overrides_text.replace(",", " ").split():
                    if ":" in chunk:
                        s, m = chunk.split(":")
                        try:
                            overrides[int(s)] = float(m)
                        except ValueError:
                            pass

                bar = st.progress(0.0, "Fetching boxscores…")
                lookup, ngames = build_lookup(
                    date_str, progress=lambda f, msg: bar.progress(f, msg)
                )
                bar.empty()

                if ngames == 0:
                    st.error(f"No games found for {date_str}. Are they final yet?")
                else:
                    result = grade_day(slips, lookup, overrides)

                    github_cfg = None
                    if "github_token" in st.secrets:
                        github_cfg = {
                            "token": st.secrets["github_token"],
                            "repo": st.secrets.get("github_repo", ""),
                            "branch": st.secrets.get("github_branch", "main"),
                            "path": st.secrets.get("github_path", "tracker_data.json"),
                        }

                    data_after, push_ok, push_msg = save_day(
                        date_str, result, slips_text, github_cfg
                    )

                    st.success(
                        f"Graded {date_str}: {result['leg_hits']}-{result['leg_misses']} "
                        f"({result['leg_win_pct']}%), {result['slips_won']} slips won, "
                        f"net {result['net_units']:+.1f}u"
                    )
                    if github_cfg:
                        (st.success if push_ok else st.error)(push_msg)
                    else:
                        st.info("Saved locally only — add github_token in Secrets to persist across restarts.")

                    for warn in warnings:
                        st.warning(warn)

                    # per-slip detail
                    for num in sorted(result["slips"]):
                        r = result["slips"][num]
                        tag = "✅" if r["won"] else "❌"
                        st.markdown(
                            f"**Slip {num}** {tag} {r['leg_record']}"
                            + (f" → {r['multiplier']}x" if r["won"] else "")
                        )
                        leg_rows = [{
                            "Player": leg["player"], "Line": leg["line"],
                            "PA": leg["pa"], "FS": leg["score"], "Result": leg["result"],
                        } for leg in r["legs"]]
                        st.dataframe(pd.DataFrame(leg_rows), use_container_width=True, hide_index=True)

                    st.rerun()

        st.markdown("###### Remove a day")
        if data:
            del_date = st.selectbox("Date to delete", [""] + sorted(data.keys()))
            if del_date and st.button("Delete", type="secondary"):
                github_cfg = None
                if "github_token" in st.secrets:
                    github_cfg = {
                        "token": st.secrets["github_token"],
                        "repo": st.secrets.get("github_repo", ""),
                        "branch": st.secrets.get("github_branch", "main"),
                        "path": st.secrets.get("github_path", "tracker_data.json"),
                    }
                delete_day(del_date, github_cfg)
                st.rerun()

    elif pw:
        st.error("Wrong password.")
