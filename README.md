# QQQ Options Walls Package (Massive)

This package builds a simple automated workflow for plotting QQQ options walls in TradingView using Massive market data.

## What it includes

- `src/update_walls.py` — pulls the QQQ option-chain snapshot from Massive, calculates call walls, put walls, and an approximate gamma flip, then writes `data/qqq_walls.csv`
- `.github/workflows/update_walls.yml` — GitHub Actions workflow to run the updater automatically
- `pine/QQQ_Auto_Options_Walls.pine` — TradingView Pine Script that reads the CSV values from GitHub using `request.seed()` and plots them
- `.env.example` — environment variable template
- `requirements.txt` — Python dependencies

## Important limitations

- Pine Script cannot directly fetch a live option chain from Massive.
- This setup is designed for scheduled refreshes, usually before the market open.
- The gamma flip in this package is an approximation based on net gamma exposure by strike.

## Setup

### 1) Create a GitHub repo
Create a new **public** GitHub repo, for example:

`qqq-options-walls`

This package expects a repo structure like:

- `data/qqq_walls.csv`
- `pine/QQQ_Auto_Options_Walls.pine`
- `.github/workflows/update_walls.yml`
- `src/update_walls.py`

### 2) Add your Massive API key
For GitHub Actions, add this repo secret:

- `MASSIVE_API_KEY`

For a local run, copy `.env.example` to `.env` and fill in your key.

### 3) Install locally
```bash
pip install -r requirements.txt
```

### 4) Run locally
```bash
python src/update_walls.py
```

This overwrites:

`data/qqq_walls.csv`

### 5) Push the repo to GitHub
Once the files are in GitHub, go to **Actions** and run the workflow once manually.

### 6) Paste the Pine script into TradingView
Open the Pine Editor and paste `pine/QQQ_Auto_Options_Walls.pine`.

Set:

- `repo = YOUR_GITHUB_USERNAME/YOUR_REPO_NAME`
- `seed file = qqq_walls`

## How the script works

The updater uses Massive's option chain snapshot endpoint for the underlying ticker, then:

1. Normalizes the response fields
2. Keeps the nearest `EXPIRATION_COUNT` expirations
3. Finds the top 3 call OI strikes and top 3 put OI strikes
4. Builds an approximate gamma-flip level from net gamma exposure by strike
5. Writes the levels to `data/qqq_walls.csv`

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

## TradingView troubleshooting

### TradingView shows `na`
Check that:

- the repo is public
- the file exists at `data/qqq_walls.csv`
- the repo input matches `username/repo`
- the seed file input is `qqq_walls`

### GitHub Action fails
Check that:

- `MASSIVE_API_KEY` exists in repo secrets
- GitHub Actions permissions allow write access to contents

### Levels look wrong
This can happen when:

- same-day option flow dominates the nearest expiration
- open interest has not updated yet
- your preferred vendor's gamma model differs from this approximation

## Suggested chart stack

For QQQ intraday trading, combine these levels with:

- VWAP
- prior day high and low
- ORB 9:30 to 9:45
- 21 EMA
- VIX behavior
