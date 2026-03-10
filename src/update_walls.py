from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    tradier_token: str
    tradier_base_url: str = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    symbol: str = os.getenv("SYMBOL", "QQQ")
    expiration_count: int = int(os.getenv("EXPIRATION_COUNT", "2"))
    output_csv: Path = Path(__file__).resolve().parents[1] / "data" / "qqq_walls.csv"


class TradierClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.tradier_token}",
                "Accept": "application/json",
            }
        )

    def get_expirations(self, symbol: str) -> list[str]:
        response = self.session.get(
            f"{self.config.tradier_base_url}/markets/options/expirations",
            params={
                "symbol": symbol,
                "includeAllRoots": "true",
                "strikes": "false",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        dates = payload.get("expirations", {}).get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        return dates

    def get_chain(self, symbol: str, expiration: str) -> pd.DataFrame:
        response = self.session.get(
            f"{self.config.tradier_base_url}/markets/options/chains",
            params={
                "symbol": symbol,
                "expiration": expiration,
                "greeks": "true",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        options = payload.get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]
        return pd.json_normalize(options)


def normalize_chain(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    column_map = {
        "type": "option_type",
        "option_type": "option_type",
        "greeks.gamma": "gamma",
        "gamma": "gamma",
        "open_interest": "open_interest",
        "strike": "strike",
        "expiration_date": "expiration_date",
        "expiration": "expiration_date",
    }

    renamed = {}
    for src, dst in column_map.items():
        if src in out.columns:
            renamed[src] = dst
    out = out.rename(columns=renamed)

    for required in ["strike", "open_interest", "gamma", "option_type"]:
        if required not in out.columns:
            out[required] = 0 if required != "option_type" else ""

    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["open_interest"] = pd.to_numeric(out["open_interest"], errors="coerce").fillna(0)
    out["gamma"] = pd.to_numeric(out["gamma"], errors="coerce").fillna(0)
    out["option_type"] = out["option_type"].astype(str).str.lower()

    out = out.dropna(subset=["strike"]).copy()
    out = out[out["option_type"].isin(["call", "put"])].copy()

    return out


def compute_levels(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        raise ValueError("No option chain data available after normalization.")

    calls = df[df["option_type"] == "call"].copy()
    puts = df[df["option_type"] == "put"].copy()

    call_oi = calls.groupby("strike", as_index=True)["open_interest"].sum().sort_values(ascending=False)
    put_oi = puts.groupby("strike", as_index=True)["open_interest"].sum().sort_values(ascending=False)

    call_walls = [float(x) for x in call_oi.head(3).index.tolist()]
    put_walls = [float(x) for x in put_oi.head(3).index.tolist()]

    calls["gex"] = calls["gamma"] * calls["open_interest"] * 100.0
    puts["gex"] = -puts["gamma"] * puts["open_interest"] * 100.0

    net_gex = pd.concat(
        [
            calls.groupby("strike", as_index=True)["gex"].sum().rename("calls_gex"),
            puts.groupby("strike", as_index=True)["gex"].sum().rename("puts_gex"),
        ],
        axis=1,
    ).fillna(0)

    net_gex["net_gex"] = net_gex["calls_gex"] + net_gex["puts_gex"]
    net_gex = net_gex.sort_index()

    gamma_flip = None
    prev_val = None
    prev_strike = None
    for strike, row in net_gex.iterrows():
        curr_val = float(row["net_gex"])
        if prev_val is not None and ((prev_val < 0 < curr_val) or (prev_val > 0 > curr_val)):
            gamma_flip = float(strike)
            break
        prev_val = curr_val
        prev_strike = strike

    if gamma_flip is None:
        if not net_gex.empty:
            gamma_flip = float(net_gex["net_gex"].abs().idxmin())
        elif prev_strike is not None:
            gamma_flip = float(prev_strike)

    def pick(levels: list[float], idx: int) -> float | None:
        return levels[idx] if len(levels) > idx else None

    return {
        "call_wall": pick(call_walls, 0),
        "call_wall_2": pick(call_walls, 1),
        "call_wall_3": pick(call_walls, 2),
        "put_wall": pick(put_walls, 0),
        "put_wall_2": pick(put_walls, 1),
        "put_wall_3": pick(put_walls, 2),
        "gamma_flip": gamma_flip,
    }


def load_all_selected_expirations(client: TradierClient, symbol: str, expiration_count: int) -> pd.DataFrame:
    expirations = client.get_expirations(symbol)
    if not expirations:
        raise ValueError(f"No expirations returned for {symbol}.")

    selected = expirations[:expiration_count]
    frames: list[pd.DataFrame] = []
    for exp in selected:
        chain = client.get_chain(symbol, exp)
        chain["selected_expiration"] = exp
        frames.append(chain)

    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return normalize_chain(merged)


def write_csv(output_csv: Path, levels: dict[str, Any]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "time": datetime.now().strftime("%Y-%m-%d"),
        **levels,
    }
    pd.DataFrame([row]).to_csv(output_csv, index=False)


def main() -> None:
    token = os.getenv("TRADIER_TOKEN", "").strip()
    if not token:
        raise EnvironmentError("Missing TRADIER_TOKEN environment variable.")

    config = Config(tradier_token=token)
    client = TradierClient(config)

    df = load_all_selected_expirations(client, config.symbol, config.expiration_count)
    levels = compute_levels(df)
    write_csv(config.output_csv, levels)

    print("Updated walls:")
    for key, value in levels.items():
        print(f"  {key}: {value}")
    print(f"Wrote: {config.output_csv}")


if __name__ == "__main__":
    main()
