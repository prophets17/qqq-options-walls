# QQQ Options Walls Package

This package builds a simple automated workflow for plotting QQQ options walls in TradingView.

## What it includes

- `src/update_walls.py` — pulls options chain data from Tradier, calculates call walls, put walls, and an approximate gamma flip, then writes `data/qqq_walls.csv`
- `.github/workflows/update_walls.yml` — GitHub Actions workflow to run the updater automatically
- `pine/QQQ_Auto_Options_Walls.pine` — TradingView Pine Script that reads the CSV values from GitHub using `request.seed()` and plots them
- `.env.example` — environment variable template
- `requirements.txt` — Python dependencies

## Important limitations

- Pine Script cannot directly fetch live option chain data from Tradier or Polygon.
- This setup is designed for scheduled refreshes, usually before the market open.
- The gamma flip in this package is an approximation based on net gamma exposure by strike.

## Setup

### 1) Create a GitHub repo
Create a new public GitHub repo. A simple name like:

`qqq-options-walls`

This package expects a repo structure like:

- `data/qqq_walls.csv`
- `pine/QQQ_Auto_Options_Walls.pine`
- `.github/workflows/update_walls.yml`
- `src/update_walls.py`

### 2) Add your Tradier API token
Create a Tradier account and generate an API token.

For local runs, copy `.env.example` to `.env` and fill in your token.

For GitHub Actions, add this repo secret:

- `TRADIER_TOKEN`

### 3) Install locally
```bash
pip install -r requirements.txt
```

### 4) Run locally
```bash
python src/update_walls.py
```

This will overwrite:

`data/qqq_walls.csv`

### 5) Push the repo to GitHub
After that, paste the Pine script into TradingView and set the repo input to:

`YOUR_GITHUB_USERNAME/YOUR_REPO_NAME`

Example:

`jrodriguez/qqq-options-walls`

## Tradier API notes

By default the script uses:

- symbol: `QQQ`
- expirations: nearest 2 expirations
- market session assumptions suitable for a premarket run

You can change this inside `src/update_walls.py`.

## CSV format

The generated file looks like this:

```csv
time,call_wall,put_wall,gamma_flip,call_wall_2,call_wall_3,put_wall_2,put_wall_3
2026-03-10,610,600,607,612,615,598,595
```

## GitHub Actions

The workflow is scheduled on weekdays and can also be run manually.

It will:

1. Install Python
2. Install dependencies
3. Run the updater
4. Commit and push the new CSV if changed

## TradingView

Open the Pine Editor and paste `pine/QQQ_Auto_Options_Walls.pine`.

Then set:

- repo = `YOUR_GITHUB_USERNAME/YOUR_REPO_NAME`
- seed file = `qqq_walls`

## Suggested use with your chart

For intraday QQQ trading, combine these levels with:

- VWAP
- prior day high and low
- ORB 9:30 to 9:45
- 21 EMA
- VIX behavior

## Troubleshooting

### TradingView shows `na`

Check:

- the repo is public
- the file is inside `data/qqq_walls.csv`
- the repo input matches `username/repo`
- the seed file input is `qqq_walls`

### GitHub Action fails

Check:

- `TRADIER_TOKEN` is present in repo secrets
- GitHub Actions permissions allow write access to contents

### Levels look wrong

This can happen when:

- nearest expiry has unusual same-day flows
- gamma calculations differ from institutional vendor models
- open interest updates lag intraday

## Next upgrades

Good improvements for a v2:

- include next 3 expirations and weighted aggregation
- add a volatility trigger
- add nearest wall above and below spot to the CSV
- add JSON export for a custom dashboard
- add SPY support alongside QQQ
