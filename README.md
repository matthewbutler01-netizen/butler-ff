# Butler FF

Fantasy football tools for NFL season-long leagues, with no betting data anywhere: no odds, lines, props or sportsbook links.

- **Rankings**: this week and rest of season, by position or overall, with tiers, matchup grades and floor-to-ceiling ranges
- **Start / Sit**: your best lineup from your actual roster, built from the consensus of Butler FF, Sleeper and ESPN projections and checked against the lineup you have set in Sleeper (with the exact changes to make, and warnings for starters who are out or on bye). Each starting spot shows your best bench alternative and how close the call is; the closest call opens automatically in the comparison tool. Compare up to four players across several lenses: projections from Butler FF, Sleeper and ESPN (averaged into a consensus), recent form, usage-based expected points, matchup, every game against this week's opponent since two seasons ago, home/road splits, and last season. Plus an optimal lineup for your roster
- **Trade Analyzer**: rest-of-season value over a replacement-level starter in your league
- **Waiver Wire**: pickups ranked by value and rising usage; uses your real league rosters after a Sleeper import
- **Draft Room**: mock draft against bots and a tiered cheat sheet
- **Dynasty and keeper leagues**: dynasty rankings, values that count future seasons (age curves, draft capital, last season's production), rookie picks in the trade analyzer, a contending/balanced/rebuilding switch, and taxi-squad and IR-slot players kept out of your lineup
- **Sleeper import**: enter your username, pick a league; brings in your roster, everyone's rosters, scoring and lineup settings, league type, and every team's rookie picks (including traded ones). Re-syncs automatically each time you open the app

## Use it as an app

Open the site, then:

- **Chrome (Windows, Mac, Chromebook):** the install icon in the address bar, or ⋮ › Cast, save and share › Install page as app
- **Android (Chrome):** ⋮ › Add to Home screen › Install
- **iPhone (Safari):** Share › Add to Home Screen

It opens full screen with its own icon and works offline with the last projections it loaded.

## How it updates

- **Every hour**, a GitHub Action (`.github/workflows/update.yml`) downloads the latest public data and rebuilds the projections. It redeploys only when something changed, so most hourly runs finish without a deploy.
- **Every time you open or refresh the app**, it loads the newest projections (`data.json`, never from the browser cache) and re-syncs your Sleeper league. If the app has been sitting open in the background, it checks again when you come back to it.
- Run an update by hand from the **Actions** tab › *Update projections and deploy* › **Run workflow**.

The week projected is the one after the last week whose games are all final. Before Week 1 finishes, the build stops with a message and the previous site stays up.

## Data

| Source | Used for |
| --- | --- |
| [nflverse](https://github.com/nflverse/nflverse-data) | weekly player stats (this season and the two before), schedule, injury reports, snap counts, depth charts, player status, age and draft capital |
| [DynastyProcess](https://github.com/dynastyprocess/data) | Sleeper ID ↔ NFL ID crosswalk |
| [Sleeper API](https://docs.sleeper.com/) | league import and trending adds, called from your browser (free for non-commercial use) |
| Sleeper projections | weekly projections in Start / Sit, loaded in your browser from Sleeper's public projections feed (not part of the documented API, so it can change) |
| ESPN | weekly projections in Start / Sit, loaded in your browser from ESPN's public fantasy feed (unofficial; can change) |
| [ffopportunity](https://github.com/ffverse/ffopportunity) | expected fantasy points from each player's usage |

The schedule file includes betting columns; `scripts/model.py` drops them before anything else runs.

## Projection method

`scripts/model.py`: per-game volume (attempts, carries, targets) weighted toward recent weeks; efficiency (yards and TDs per opportunity) shrunk toward position averages; adjusted by each defense's fantasy points allowed to the position; discounted for injury status; summed over the remaining schedule with byes. Kickers and defenses project from team scoring and opponent tendencies. Every number is stored as a stat line, so the page rescores it for your league's settings.

Dynasty values (computed in the page, so they follow your scoring): this season's points over a replacement starter, plus the next four seasons. Each future season starts from a healthy per-game level (this season, plus last season at half weight, pulled toward replacement on small samples; rookies with no games start from draft round and position), ages by position (RBs fall off from 27, WRs from 28, TEs from 29, QBs from 33), gets a lift for young high picks, and counts expected points over replacement with uncertainty that widens each year out. Seasons are weighted by team outlook: contending, balanced or rebuilding. In superflex leagues QB replacement sits deeper, since nearly every team rosters a third QB. A rookie pick is worth about what the player taken in that slot becomes; next year's slots are estimated from current standings.

## Run locally

```bash
pip install pandas numpy
scripts/fetch_data.sh
python scripts/model.py data data/data.json
python scripts/build.py data/data.json site
python -m http.server -d site 8000   # open http://localhost:8000
```
