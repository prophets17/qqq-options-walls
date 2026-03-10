# QQQ Options Walls Package (Yahoo Finance / yfinance)

This package builds a simple automated workflow for plotting QQQ options walls in TradingView using `yfinance`.

## Important notes

- This version uses Yahoo Finance data via the open-source `yfinance` library.
- It is intended for personal/research use and may break if Yahoo changes its public endpoints.
- It computes:
  - call wall (highest call open interest)
  - put wall (highest put open interest)
  - an approximate gamma flip proxy (midpoint between the largest call and put OI strikes)
- Because `yfinance` does not provide full greeks in the option chain, the gamma flip is a simple proxy, not institutional dealer GEX.

## What it includes

- `src/update_walls.py` — pulls QQQ option-chain data from Yahoo Finance, calculates walls, writes `data/qqq_walls.csv`
- `.github/workflows/update_walls.yml` — GitHub Actions workflow to run the updater automatically
- `pine/QQQ_Auto_Options_Walls.pine` — TradingView Pine Script that reads the CSV values from GitHub using `request.seed()` and plots them
- `requirements.txt`
- `data/qqq_walls.csv` starter file

## Repo structure

```text
qqq-options-walls/
├── .github/
│   └── workflows/
│       └── update_walls.yml
├── data/
│   └── qqq_walls.csv
├── pine/
│   └── QQQ_Auto_Options_Walls.pine
├── src/
│   └── update_walls.py
├── README.md
└── requirements.txt
```

## Setup

1. Upload these files to a **public** GitHub repo.
2. Open the **Actions** tab and run **Update QQQ Options Walls**.
3. Confirm `data/qqq_walls.csv` updates.
4. Paste `pine/QQQ_Auto_Options_Walls.pine` into TradingView.
5. Set the repo input to your repo, e.g. `prophets17/qqq-options-walls`.

## How the levels are computed

- **Call wall:** strike with the highest call open interest across the nearest two expirations
- **Put wall:** strike with the highest put open interest across the nearest two expirations
- **Gamma flip proxy:** midpoint between the top call-wall and put-wall strikes

You can later upgrade the logic to include max pain, top 5 walls, or more sophisticated weighting.
