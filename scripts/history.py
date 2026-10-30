"""Butler FF's projections for every completed week, as they stood before that week's games.

For each week W from 2 through the last completed week, the model runs with BT_LAST_WEEK=W-1, so it
sees only games, snaps, injury reports and depth charts available before W kicked off. Week 1 has no
Butler projection (no games yet). Stat lines are stored raw so the site can score them with each
league's own settings.

Usage: python3 scripts/history.py data site/history.json
Output: {"weeks": {"<W>": {"<id>": [pass_yd, pass_td, int, rush_yd, rush_td, rec, rec_yd, rec_td, fum, tag]
                           or {"pts": x} for kickers and defenses}},
         "sl": {sleeper_id: id}, "es": {espn_id: id}}   (ids not already in data.json's maps)
"""
import json, os, subprocess, sys, tempfile
import pandas as pd

DATA, OUT = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
g = pd.read_csv(f"{DATA}/games.csv")
SEASON = int(os.environ.get("SEASON") or json.load(open(f"{DATA}/data.json"))["meta"]["season"])
g = g[(g.season == SEASON) & (g.game_type == "REG")]
done = g.groupby("week").home_score.apply(lambda s: s.notna().all())
LAST = int(max([w for w, ok in done.items() if ok], default=0))

weeks, ids = {}, set()
for W in range(2, LAST + 1):
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "d.json")
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "model.py"), DATA, dst],
                       env=dict(os.environ, BT_LAST_WEEK=str(W - 1)), check=True, stdout=subprocess.DEVNULL)
        D = json.load(open(dst))
    assert D["meta"]["week"] == W
    wk = {}
    for p in D["players"]:
        c = p["wk"]["c"]
        if not p["wk"]["opp"]:
            continue
        line = [c["pass_yd"], c["pass_td"], c["int"], c["rush_yd"], c["rush_td"], c["rec"], c["rec_yd"], c["rec_td"], c["fum"]]
        if sum(line[:8]) < 0.5:
            continue
        wk[p["id"]] = [round(x, 2) for x in line] + [p["tag"]]
        ids.add(p["id"])
    for p in D["k"] + D["dst"]:
        if p["wk"]["opp"]:
            wk[p["id"]] = {"pts": round(p["wk"]["pts"], 2)}
            ids.add(p["id"])
    weeks[str(W)] = wk
    print(f"week {W}: {len(wk)} players")

xw = pd.read_csv(f"{DATA}/db_playerids.csv", low_memory=False)
xw = xw[xw.gsis_id.isin(ids)]
sl = {str(int(float(s))): gid for s, gid in zip(xw.sleeper_id, xw.gsis_id) if pd.notna(s)}
es = {str(int(float(e))): gid for e, gid in zip(xw.espn_id, xw.gsis_id) if pd.notna(e)}
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
json.dump({"season": SEASON, "lastWeek": LAST, "weeks": weeks, "sl": sl, "es": es}, open(OUT, "w"), separators=(",", ":"))
print(f"wrote {OUT}: weeks 2-{LAST}, {os.path.getsize(OUT)//1024} KB")
