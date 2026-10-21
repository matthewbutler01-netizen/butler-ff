"""Build next-week + rest-of-season projections from nflverse data (no betting inputs).

Usage: python3 -I model.py <data_dir> <out_json>
The season defaults to the current NFL season (set SEASON to override). The projected week is the
week after the last one whose games have all been played.
"""
import sys, json, math, os, datetime
import numpy as np
import pandas as pd

DATA, OUT = sys.argv[1], sys.argv[2]
_today = datetime.date.today()
SEASON = int(os.environ.get("SEASON") or (_today.year if _today.month >= 8 else _today.year - 1))
DECAY = 0.78          # recency weight per week back
SKILL = ["QB", "RB", "WR", "TE"]

g = pd.read_csv(f"{DATA}/games.csv")
g = g[(g.season == SEASON) & (g.game_type == "REG")].copy()
_done = g.groupby("week").home_score.apply(lambda s: s.notna().all())
LAST_WEEK = int(max([wk for wk, ok in _done.items() if ok], default=0))   # last fully completed week
CUR_WEEK = min(LAST_WEEK + 1, 18)                                         # week being projected
if LAST_WEEK < 1:
    sys.exit(f"No completed {SEASON} regular-season weeks yet; projections need at least one week of games.")
w = pd.read_csv(f"{DATA}/week.csv", low_memory=False)
w = w[(w.season == SEASON) & (w.season_type == "REG") & (w.week <= LAST_WEEK)].copy()
# Drop every betting column up front so nothing downstream can touch it.
g = g.drop(columns=[c for c in g.columns if any(k in c for k in
                    ["moneyline", "spread", "odds", "total_line", "over", "under"])])
inj = pd.read_csv(f"{DATA}/injuries.csv")
players = pd.read_csv(f"{DATA}/players.csv", low_memory=False)
dc = pd.read_csv(f"{DATA}/depth_charts.csv", low_memory=False)
dc = dc[dc.dt == dc.dt.max()]
snaps = pd.read_csv(f"{DATA}/snap_counts.csv")

num = lambda s: pd.to_numeric(s, errors="coerce").fillna(0)
for c in ["attempts", "completions", "passing_yards", "passing_tds", "passing_interceptions",
          "carries", "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards",
          "receiving_tds", "rushing_fumbles_lost", "receiving_fumbles_lost", "sack_fumbles_lost",
          "passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions",
          "target_share", "fantasy_points", "fantasy_points_ppr", "fg_made", "fg_att", "pat_made",
          "pat_missed", "fg_missed", "fg_made_0_19", "fg_made_20_29", "fg_made_30_39",
          "fg_made_40_49", "fg_made_50_59", "fg_made_60_", "def_sacks", "def_interceptions",
          "fumble_recovery_opp", "def_tds", "def_safeties", "special_teams_tds", "fumble_recovery_tds"]:
    w[c] = num(w[c])
w["fum"] = w.rushing_fumbles_lost + w.receiving_fumbles_lost + w.sack_fumbles_lost
w["two"] = w.passing_2pt_conversions + w.rushing_2pt_conversions + w.receiving_2pt_conversions
w["half"] = (w.fantasy_points + w.fantasy_points_ppr) / 2
w["wt"] = DECAY ** (LAST_WEEK - w.week)

teams = sorted(set(g.home_team) | set(g.away_team))

# ---------- schedule ----------
sched = {}   # (team, week) -> (opp, home bool)
for r in g.itertuples():
    sched[(r.home_team, r.week)] = (r.away_team, True)
    sched[(r.away_team, r.week)] = (r.home_team, False)
bye = {t: next(wk for wk in range(1, 19) if (t, wk) not in sched) for t in teams}

# points scored / allowed per game
pf, pa = {t: [] for t in teams}, {t: [] for t in teams}
for r in g[g.home_score.notna()].itertuples():
    pf[r.home_team].append(r.home_score); pa[r.home_team].append(r.away_score)
    pf[r.away_team].append(r.away_score); pa[r.away_team].append(r.home_score)
lg_ppg = np.mean([x for t in teams for x in pf[t]])
off_f = {t: (sum(pf[t]) + 2 * lg_ppg) / (len(pf[t]) + 2) / lg_ppg for t in teams}
def_f = {t: (sum(pa[t]) + 2 * lg_ppg) / (len(pa[t]) + 2) / lg_ppg for t in teams}

# ---------- defense vs position (PPR pts allowed) ----------
sk = w[w.position.isin(SKILL)]
dvp_raw = sk.groupby(["opponent_team", "position", "week"]).fantasy_points_ppr.sum().reset_index()
dvp = dvp_raw.groupby(["opponent_team", "position"]).fantasy_points_ppr.agg(["sum", "count"]).reset_index()
lg_pos = dvp_raw.groupby("position").fantasy_points_ppr.mean()
DVP = {}
for r in dvp.itertuples():
    ratio = (r.sum + 2 * lg_pos[r.position]) / (r.count + 2) / lg_pos[r.position]
    DVP[(r.opponent_team, r.position)] = float(np.clip(1 + 0.6 * (ratio - 1), 0.78, 1.22))
mult = lambda opp, pos: DVP.get((opp, pos), 1.0)

# ---------- league efficiency priors by position ----------
def lg_rate(pos, num_c, den_c):
    d = w[w.position == pos]
    return d[num_c].sum() / max(d[den_c].sum(), 1)

prior = {}
for p in SKILL:
    prior[p] = dict(
        ypa=lg_rate("QB", "passing_yards", "attempts"), ptd=lg_rate("QB", "passing_tds", "attempts"),
        pint=lg_rate("QB", "passing_interceptions", "attempts"), cmp=lg_rate("QB", "completions", "attempts"),
        ypc=lg_rate(p, "rushing_yards", "carries"), rtd=lg_rate(p, "rushing_tds", "carries"),
        crate=lg_rate(p, "receptions", "targets"), ypt=lg_rate(p, "receiving_yards", "targets"),
        retd=lg_rate(p, "receiving_tds", "targets"),
    )
fum_rate = w.fum.sum() / max((w.carries + w.receptions + w.attempts).sum(), 1)

def shrink(made, opp, mean, k):
    return (made + k * mean) / (opp + k)

# ---------- current team, status ----------
dc_team = dc.drop_duplicates("gsis_id").set_index("gsis_id").team.to_dict()
dc_rank = dc[dc.pos_abb.isin(SKILL + ["PK"])].sort_values("pos_rank").drop_duplicates("gsis_id") \
    .set_index("gsis_id")[["pos_abb", "pos_rank"]].to_dict("index")
pstat = players.set_index("gsis_id")[["status", "birth_date", "years_of_experience", "jersey_number"]].to_dict("index")
inj_last = inj[inj.week == inj.week.max()].dropna(subset=["report_status"]) \
    .drop_duplicates("gsis_id", keep="last").set_index("gsis_id")[["report_status", "report_primary_injury"]].to_dict("index")

snaps["key"] = snaps.player.str.lower().str.replace(r"[^a-z]", "", regex=True) + "|" + snaps.team
snap_map = snaps.groupby("key").apply(lambda d: {int(r.week): round(float(r.offense_pct) * 100) for r in d.itertuples()},
                                       include_groups=False).to_dict()

# ---------- skill player projections ----------
def wavg(d, c):
    return float((d[c] * d.wt).sum() / d.wt.sum())

out_players = []
for pid, d in sk.groupby("player_id"):
    d = d.sort_values("week")
    last = d.iloc[-1]
    pos = last.position
    team = dc_team.get(pid, last.team)
    st = pstat.get(pid, {})
    roster_status = st.get("status", "ACT") if isinstance(st.get("status"), str) else "ACT"
    in_dc = pid in dc_team
    played_recent = d.week.max() >= LAST_WEEK - 1
    if not in_dc and not played_recent and roster_status == "ACT":
        continue  # cut / off roster
    if roster_status in ("CUT", "RET"):
        continue
    if d.fantasy_points_ppr.sum() < 3 and d.week.max() < LAST_WEEK - 1:
        continue
    pr = prior[pos]
    n = len(d)

    att = wavg(d, "attempts") if pos == "QB" else 0.0
    car, tgt = wavg(d, "carries"), wavg(d, "targets")
    # a player whose team role clearly ended (no stats in last 2 weeks while team played) gets volume cut
    gap = LAST_WEEK - d.week.max() - (1 if bye[team] in range(d.week.max() + 1, LAST_WEEK + 1) else 0)
    vol_f = 1.0 if gap <= 0 else (0.6 if gap == 1 else 0.35)

    _rep = inj_last.get(pid, {})
    if roster_status in ("RES", "PUP", "NWT", "RSN", "RSR", "SUS") or _rep.get("report_status") in ("Out", "Doubtful", "Questionable"):
        vol_f = 1.0  # absence explained by injury, not a lost role
    S = lambda c: float(d[c].sum())
    proj = dict(
        pass_att=att, pass_yd=att * shrink(S("passing_yards"), S("attempts"), pr["ypa"], 80),
        pass_td=att * shrink(S("passing_tds"), S("attempts"), pr["ptd"], 200),
        int=att * shrink(S("passing_interceptions"), S("attempts"), pr["pint"], 200),
        car=car, rush_yd=car * shrink(S("rushing_yards"), S("carries"), pr["ypc"], 40),
        rush_td=car * shrink(S("rushing_tds"), S("carries"), pr["rtd"], 60),
        tgt=tgt, rec=tgt * shrink(S("receptions"), S("targets"), pr["crate"], 30),
        rec_yd=tgt * shrink(S("receiving_yards"), S("targets"), pr["ypt"], 40),
        rec_td=tgt * shrink(S("receiving_tds"), S("targets"), pr["retd"], 60),
    )
    if pos != "QB":
        for k in ("pass_att", "pass_yd", "pass_td", "int"):
            proj[k] = 0.0
    proj["fum"] = (proj["car"] + proj["rec"] + proj["pass_att"]) * fum_rate
    proj = {k: v * vol_f for k, v in proj.items()}

    # availability
    rep = inj_last.get(pid, {})
    tag, avail = "", 1.0
    if roster_status in ("RES", "PUP", "NWT", "RSN", "RSR"):
        tag, avail = "IR", 0.0
    elif roster_status == "SUS":
        tag, avail = "SUSP", 0.0
    elif rep.get("report_status") in ("Out", "Doubtful"):
        tag, avail = rep["report_status"][0], 0.5
    elif rep.get("report_status") == "Questionable":
        tag, avail = "Q", 0.92
    injury = rep.get("report_primary_injury", "") if tag else ""

    def week_proj(wk):
        if (team, wk) not in sched:
            return None, None, 0.0
        opp, home = sched[(team, wk)]
        m = mult(opp, pos)
        c = dict(proj)
        for k in ("pass_yd", "pass_td", "rush_yd", "rush_td", "rec_yd", "rec_td"):
            c[k] *= m
        c["rec"] *= 1 + 0.4 * (m - 1)
        c["int"] *= 2 - m
        return opp, home, m, c

    wp = week_proj(CUR_WEEK)
    if wp[0] is None:
        w_opp, w_home, w_mult, w_comp = None, None, 1.0, {k: 0.0 for k in proj}
    else:
        w_opp, w_home, w_mult, w_comp = wp
        w_comp = {k: v * avail for k, v in w_comp.items()}

    # ROS: weeks CUR_WEEK..18
    ros_avail_now = {"IR": 0.0, "SUSP": 0.0}.get(tag, avail)
    ros = {k: 0.0 for k in proj}
    games_left, sos = 0, []
    for wk in range(CUR_WEEK, 19):
        r_ = week_proj(wk)
        if r_[0] is None:
            continue
        games_left += 1
        sos.append(r_[2])
        # availability recovers: IR assumed back ~wk+5, Out/D back ~next week
        if tag == "IR":
            a = 0.0 if wk < CUR_WEEK + 4 else 0.7
        elif tag == "SUSP":
            a = 0.0 if wk < CUR_WEEK + 2 else 1.0
        elif wk == CUR_WEEK:
            a = avail
        else:
            a = 0.97
        for k in ros:
            ros[k] += r_[3][k] * a

    # weekly history (component-level so the app can rescore)
    hist = {}
    for r in d.itertuples():
        hist[int(r.week)] = [round(x, 1) for x in (
            r.passing_yards, r.passing_tds, r.passing_interceptions, r.rushing_yards, r.rushing_tds,
            r.receptions, r.receiving_yards, r.receiving_tds, r.fum, r.two)] + [r.opponent_team]

    key = "".join(ch for ch in str(last.player_display_name).lower() if ch.isalpha()) + "|" + str(last.team)
    sn = snap_map.get(key, {})

    # usage trend: opportunities (targets + carries, QB: dropbacks) last 2 games vs earlier
    opp_series = (d.targets + d.carries + (d.attempts if pos == "QB" else 0)).tolist()
    trend = 0.0
    if len(opp_series) >= 3:
        trend = float(np.mean(opp_series[-2:]) - np.mean(opp_series[:-2]))
    ts = d.target_share.tolist()

    dcr = dc_rank.get(pid)
    out_players.append(dict(
        id=pid, n=str(last.player_display_name), p=pos, t=team, prevT=str(last.team) if team != last.team else "",
        gp=n, tag=tag, inj=injury if isinstance(injury, str) else "",
        dc=f"{dcr['pos_abb']}{dcr['pos_rank']}" if dcr else "",
        wk=dict(opp=w_opp, home=w_home, m=round(w_mult, 3),
                c={k: round(v, 2) for k, v in w_comp.items()}),
        ros=dict(c={k: round(v, 1) for k, v in ros.items()}, g=games_left,
                 sos=round(float(np.mean(sos)), 3) if sos else 1.0),
        pg={k: round(v, 2) for k, v in proj.items()},
        h=hist, sn=sn, tr=round(trend, 1),
        ts=round(float(np.nanmean(ts[-2:])), 3) if len(ts) and pos != "QB" else None,
        exp=int(st.get("years_of_experience")) if pd.notna(st.get("years_of_experience")) else None,
    ))

# ---------- kickers ----------
k = w[w.position == "K"].copy()
k["kpts"] = (k.fg_made_0_19 + k.fg_made_20_29 + k.fg_made_30_39) * 3 + k.fg_made_40_49 * 4 + \
            (k.fg_made_50_59 + k.fg_made_60_) * 5 + k.pat_made - k.fg_missed - k.pat_missed
lg_k = k.kpts.mean()
kickers = []
for pid, d in k.groupby("player_id"):
    team = dc_team.get(pid, d.iloc[-1].team)
    if d.week.max() < LAST_WEEK - 1 and pid not in dc_team:
        continue
    base = (float((d.kpts * d.wt).sum()) + 2 * lg_k) / (float(d.wt.sum()) + 2)
    def kp(wk):
        if (team, wk) not in sched: return None
        opp = sched[(team, wk)][0]
        return opp, base * math.sqrt(off_f[team] * def_f[opp]) ** 0.5
    r7 = kp(CUR_WEEK)
    ros = sum(kp(wk)[1] for wk in range(CUR_WEEK, 19) if kp(wk))
    kickers.append(dict(id=pid, n=str(d.iloc[-1].player_display_name), p="K", t=team,
                        gp=len(d), wk=dict(opp=r7[0] if r7 else None, home=sched.get((team, CUR_WEEK), (0, None))[1],
                                           pts=round(r7[1], 2) if r7 else 0),
                        ros=dict(pts=round(ros, 1), g=sum(1 for wk in range(CUR_WEEK, 19) if (team, wk) in sched)),
                        h={int(r.week): [round(r.kpts, 1), r.opponent_team] for r in d.itertuples()}))

# ---------- team defenses ----------
dfn = w.groupby(["team", "week"])[["def_sacks", "def_interceptions", "fumble_recovery_opp",
                                   "def_tds", "def_safeties", "special_teams_tds", "fumble_recovery_tds"]].sum().reset_index()
# offensive giveaways per team (to scale opponent turnover chances)
give = w.groupby(["team", "week"])[["passing_interceptions", "fum"]].sum().reset_index()
give_rate = give.groupby("team")[["passing_interceptions", "fum"]].mean().sum(axis=1)
lg_give = give_rate.mean()
w["sacks_suffered"] = num(w["sacks_suffered"])
sacked = w.groupby(["team", "week"]).sacks_suffered.sum().groupby("team").mean()
lg_sacked = sacked.mean()

def pa_pts(x):  # standard points-allowed tiers
    return 10 if x == 0 else 7 if x <= 6 else 4 if x <= 13 else 1 if x <= 20 else 0 if x <= 27 else -1 if x <= 34 else -4

def exp_pa_pts(mu, sd=9.5):
    xs = np.arange(0, 70)
    pdf = np.exp(-0.5 * ((xs - mu) / sd) ** 2); pdf /= pdf.sum()
    return float(sum(p * pa_pts(x) for x, p in zip(xs, pdf)))

defs = []
for t in teams:
    d = dfn[dfn.team == t].copy()
    d["wt"] = DECAY ** (LAST_WEEK - d.week)
    wa = lambda c: float((d[c] * d.wt).sum() / d.wt.sum())
    sacks, ints, fr = wa("def_sacks"), wa("def_interceptions"), wa("fumble_recovery_opp")
    tds = wa("def_tds") + wa("special_teams_tds")
    def dp(wk):
        if (t, wk) not in sched: return None
        opp = sched[(t, wk)][0]
        pa_mu = lg_ppg * def_f[t] * off_f[opp]
        s = sacks * (sacked.get(opp, lg_sacked) / lg_sacked) ** 0.6
        to = (ints * 2 + fr * 2) * (give_rate.get(opp, lg_give) / lg_give) ** 0.6
        return opp, dict(sack=s, to=to, td=tds * 6 * 0.8, pa=exp_pa_pts(pa_mu), pa_mu=pa_mu)
    r7 = dp(CUR_WEEK)
    tot = lambda x: x["sack"] + x["to"] + x["td"] + x["pa"]
    ros = sum(tot(dp(wk)[1]) for wk in range(CUR_WEEK, 19) if dp(wk))
    hist = {}
    for r in d.itertuples():
        opp, _ = sched[(t, r.week)]
        gm = g[(g.week == r.week) & ((g.home_team == t) | (g.away_team == t))].iloc[0]
        pa_ = gm.away_score if gm.home_team == t else gm.home_score
        hist[int(r.week)] = [round(r.def_sacks + 2 * (r.def_interceptions + r.fumble_recovery_opp) +
                                   6 * (r.def_tds + r.special_teams_tds) + 2 * r.def_safeties + pa_pts(pa_), 1), opp]
    defs.append(dict(id="DST-" + t, n=f"{t} D/ST", p="DST", t=t, gp=len(d),
                     wk=dict(opp=r7[0] if r7 else None, home=sched.get((t, CUR_WEEK), (0, None))[1],
                             pts=round(tot(r7[1]), 2) if r7 else 0,
                             pa=round(r7[1]["pa_mu"], 1) if r7 else None),
                     ros=dict(pts=round(ros, 1), g=sum(1 for wk in range(CUR_WEEK, 19) if (t, wk) in sched)),
                     h=hist))

# schedule for the app (remaining weeks)
sched_out = {t: {wk: sched[(t, wk)][0] if (t, wk) in sched else "BYE" for wk in range(1, 19)} for t in teams}
dvp_out = {f"{a}|{b}": v for (a, b), v in DVP.items()}

_days = pd.to_datetime(g[g.week == CUR_WEEK].gameday)
_a, _b = _days.min(), _days.max()
week_dates = f"{_a:%b} {_a.day}–{_b.day}" if _a.month == _b.month else f"{_a:%b} {_a.day}–{_b:%b} {_b.day}"
meta = dict(season=SEASON, week=CUR_WEEK, weekDates=week_dates, lastWeek=LAST_WEEK, built=pd.Timestamp.now(tz="America/Chicago").strftime("%b %-d, %Y %-I:%M %p CT"),
            depthAsOf=str(dc.dt.max()), injWeek=int(inj.week.max()),
            byes={t: bye[t] for t in teams}, offF={t: round(off_f[t], 3) for t in teams},
            defF={t: round(def_f[t], 3) for t in teams})

# Sleeper player id -> gsis id (dynastyprocess crosswalk), so a Sleeper roster import matches our players.
sl = {}
import os
xw = os.path.join(DATA, "db_playerids.csv")
if os.path.exists(xw):
    x = pd.read_csv(xw, low_memory=False)
    ours = {p["id"] for p in out_players + kickers}
    x = x[x.gsis_id.isin(ours) & x.sleeper_id.notna()]
    sl = {str(int(float(s))): gid for s, gid in zip(x.sleeper_id, x.gsis_id)}

json.dump(dict(meta=meta, players=out_players, k=kickers, dst=defs, sched=sched_out, dvp=dvp_out, sl=sl),
          open(OUT, "w"), separators=(",", ":"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
print("players", len(out_players), "K", len(kickers), "DST", len(defs))
