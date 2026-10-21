# Butler FF

Fantasy football tools for NFL season-long leagues, with no betting data anywhere: no odds, lines, props or sportsbook links.

- **Rankings**: this week and rest of season, by position or overall, with tiers, matchup grades and floor-to-ceiling ranges
- **Start / Sit**: compare up to four players, plus an optimal lineup for your roster
- **Trade Analyzer**: rest-of-season value over a replacement-level starter in your league
- **Waiver Wire**: pickups ranked by value and rising usage; uses your real league rosters after a Sleeper import
- **Draft Room**: mock draft against bots and a tiered cheat sheet
- **Sleeper import**: enter your username, pick a league; brings in your roster, everyone's rosters, and your scoring and lineup settings

## Use it as an app

Open the site, then:

- **Chrome (Windows, Mac, Chromebook):** the install icon in the address bar, or ⋮ › Cast, save and share › Install page as app
- **Android (Chrome):** ⋮ › Add to Home screen › Install
- **iPhone (Safari):** Share › Add to Home Screen

It opens full screen with its own icon and works offline with the last projections it loaded.

## How it updates

A GitHub Action (`.github/workflows/update.yml`) runs every morning at 6:20 AM Central. It downloads the latest public data, rebuilds the projections and redeploys the site. Run it by hand from the **Actions** tab › *Update projections and deploy* › **Run workflow**.

The week projected is the one after the last week whose games are all final. Before Week 1 finishes, the build stops with a message and the previous site stays up.

## Data

| Source | Used for |
| --- | --- |
| [nflverse](https://github.com/nflverse/nflverse-data) | weekly player stats, schedule, injury reports, snap counts, depth charts, player status |
| [DynastyProcess](https://github.com/dynastyprocess/data) | Sleeper ID ↔ NFL ID crosswalk |
| [Sleeper API](https://docs.sleeper.com/) | league import and trending adds, called from your browser (free for non-commercial use) |

The schedule file includes betting columns; `scripts/model.py` drops them before anything else runs.

## Projection method

`scripts/model.py`: per-game volume (attempts, carries, targets) weighted toward recent weeks; efficiency (yards and TDs per opportunity) shrunk toward position averages; adjusted by each defense's fantasy points allowed to the position; discounted for injury status; summed over the remaining schedule with byes. Kickers and defenses project from team scoring and opponent tendencies. Every number is stored as a stat line, so the page rescores it for your league's settings.

## Run locally

```bash
pip install pandas numpy
scripts/fetch_data.sh
python scripts/model.py data data/data.json
python scripts/build.py data/data.json site
python -m http.server -d site 8000   # open http://localhost:8000
```
