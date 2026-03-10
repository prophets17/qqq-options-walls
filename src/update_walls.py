from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class Config:
    symbol: str = "QQQ"
    expiration_count: int = 2
    output_csv: Path = Path(__file__).resolve().parents[1] / "data" / "qqq_walls.csv"


def get_option_chain(symbol: str, expiration_count: int = 2) -> tuple[pd.DataFrame, list[str]]:
    ticker = yf.Ticker(symbol)
    expirations = list(ticker.options)
    if not expirations:
        raise RuntimeError(f"No option expirations returned for {symbol}.")

    use_expirations = expirations[:expiration_count]
    frames: list[pd.DataFrame] = []

    for exp in use_expirations:
        chain = ticker.option_chain(exp)
        calls = chain.calls.copy()
        puts = chain.puts.copy()

        calls["option_type"] = "call"
        puts["option_type"] = "put"
        calls["expiration"] = exp
        puts["expiration"] = exp

        frames.append(calls)
        frames.append(puts)

    raw = pd.concat(frames, ignore_index=True)
    return raw, use_expirations


def compute_levels(df: pd.DataFrame) -> dict[str, float | str | None]:
    required_cols = {"strike", "openInterest", "option_type"}
    missing = required_cols - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing expected columns: {missing}")

    df = df.copy()
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["openInterest"] = pd.to_numeric(df["openInterest"], errors="coerce").fillna(0)
    df = df.dropna(subset=["strike"])

    calls = df[df["option_type"] == "call"]
    puts = df[df["option_type"] == "put"]

    if calls.empty or puts.empty:
        raise RuntimeError("Calls or puts dataframe is empty.")

    call_oi = calls.groupby("strike")["openInterest"].sum().sort_values(ascending=False)
    put_oi = puts.groupby("strike")["openInterest"].sum().sort_values(ascending=False)

    call_walls = [float(x) for x in call_oi.head(3).index.tolist()]
    put_walls = [float(x) for x in put_oi.head(3).index.tolist()]

    call_wall = call_walls[0] if call_walls else None
    put_wall = put_walls[0] if put_walls else None

    gamma_flip = None
    if call_wall is not None and put_wall is not None:
        gamma_flip = float(np.round((call_wall + put_wall) / 2.0, 2))

    return {
        "time": datetime.now().strftime("%Y-%m-%d"),
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_flip": gamma_flip,
        "call_wall_2": call_walls[1] if len(call_walls) > 1 else None,
        "call_wall_3": call_walls[2] if len(call_walls) > 2 else None,
        "put_wall_2": put_walls[1] if len(put_walls) > 1 else None,
        "put_wall_3": put_walls[2] if len(put_walls) > 2 else None,
    }


def main() -> None:
    config = Config()
    raw, exps = get_option_chain(config.symbol, config.expiration_count)
    levels = compute_levels(raw)

    config.output_csv.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame([levels])
    out.to_csv(config.output_csv, index=False)

    print(f"Updated {config.output_csv}")
    print(f"Expirations used: {', '.join(exps)}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
