"""Backtest Butler FF projections: for each week W, run the model with only data through W-1 and
record each player's projected PPR points next to what he actually scored.

Usage: python3 scripts/backtest.py data backtest/butler.json 2 6
Scoring is standard PPR (1 per catch, 4 per passing TD, -2 per INT, -2 per fumble lost) to match
nflverse's fantasy_points_ppr and the default PPR projections from Sleeper and ESPN.
"""
import json, os, subprocess, sys, tempfile
import pandas as pd

DATA, OUT, FIRST, LAST = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
HERE = os.path.dirname(os.path.abspath(__file__))
week = pd.read_csv(f"{DATA}/week.csv", low_memory=False)
week = week[week.season_type == "REG"]
xw = pd.read_csv(f"{DATA}/db_playerids.csv", low_memory=False)
sl = {g: str(int(float(s))) for g, s in zip(xw.gsis_id, xw.sleeper_id) if pd.notna(s) and pd.notna(g)}
es = {g: str(int(float(e))) for g, e in zip(xw.gsis_id, xw.espn_id) if pd.notna(e) and pd.notna(g)}

def ppr(c):
    return (c["pass_yd"] * 0.04 + c["pass_td"] * 4 - c["int"] * 2 + c["rush_yd"] * 0.1 + c["rush_td"] * 6
            + c["rec"] + c["rec_yd"] * 0.1 + c["rec_td"] * 6 - c["fum"] * 2)

out = {}
for W in range(FIRST, LAST + 1):
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "d.json")
        env = dict(os.environ, BT_LAST_WEEK=str(W - 1))
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "model.py"), DATA, dst], env=env, check=True,
                       stdout=subprocess.DEVNULL)
        D = json.load(open(dst))
    assert D["meta"]["week"] == W, (D["meta"]["week"], W)
    act = week[week.week == W].set_index("player_id").fantasy_points_ppr.to_dict()
    rows = []
    for p in D["players"]:
        if not p["wk"]["opp"]:
            continue  # bye
        rows.append([p["id"], p["n"], p["p"], p["t"], round(ppr(p["wk"]["c"]), 2),
                     round(float(act.get(p["id"], 0.0)), 2), sl.get(p["id"]), es.get(p["id"])])
    out[W] = rows
    print(f"week {W}: {len(rows)} players projected")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({"scoring": "PPR", "fields": ["gsis", "name", "pos", "team", "butler", "actual", "sleeper_id", "espn_id"], "weeks": out},
          open(OUT, "w"), separators=(",", ":"))
