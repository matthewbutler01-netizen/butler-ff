#!/usr/bin/env bash
# Download the public data Butler FF is built from into ./data (nflverse + DynastyProcess ID crosswalk).
set -euo pipefail
SEASON="${SEASON:-$( [ "$(date +%-m)" -ge 8 ] && date +%Y || echo $(( $(date +%Y) - 1 )) )}"
NV=https://github.com/nflverse/nflverse-data/releases/download
mkdir -p data
get() { echo "→ $2"; curl -fsSL --retry 3 -o "data/$2" "$1"; }
get "$NV/stats_player/stats_player_week_${SEASON}.csv" week.csv
get "$NV/stats_player/stats_player_week_$((SEASON - 1)).csv" week_prev.csv
get "$NV/injuries/injuries_${SEASON}.csv"             injuries.csv
get "$NV/snap_counts/snap_counts_${SEASON}.csv"       snap_counts.csv
get "$NV/depth_charts/depth_charts_${SEASON}.csv"     depth_charts.csv
get "$NV/players/players.csv"                          players.csv
get "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv" games.csv
get "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv" db_playerids.csv
