from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    api_key: str
    symbol: str = os.getenv("SYMBOL", "QQQ")
    expiration_count: int = int(os.getenv("EXPIRATION_COUNT", "2"))
    base_url: str = os.getenv("MASSIVE_BASE_URL", "https://api.massive.com").rstrip("/")
    output_csv: Path = Path(__file__).resolve().parents[1] / "data" / "qqq_walls.csv"


class MassiveClient:
    """Thin client for Massive option chain snapshot data."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _append_api_key(self, url: str) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("apiKey", self.config.api_key)
        return urlunparse(parsed._replace(query=urlencode(query)))

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        params.setdefault("apiKey", self.config.api_key)
        response = self.session.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "ERROR":
            raise RuntimeError(payload.get("error", "Massive API returned an error."))
        return payload

    def get_option_chain_snapshot(self, symbol: str) -> pd.DataFrame:
        url = f"{self.config.base_url}/v3/snapshot/options/{symbol}"
        params: dict[str, Any] = {"limit": 250}
        rows: list[dict[str, Any]] = []

        while True:
            payload = self._get_json(url, params=params)
            results = payload.get("results", []) or []
            rows.extend(results)

            next_url = payload.get("next_url")
            if not next_url:
                break
            url = self._append_api_key(next_url)
            params = None

        return pd.json_normalize(rows)


def _first_existing(row: pd.Series, keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in row and pd.notna(row[key]):
            return row[key]
    return default


def normalize_chain(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out_rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        out_rows.append(
            {
                "strike": _first_existing(row, ["details.strike_price", "strike_price", "strike"], None),
                "option_type": str(_first_existing(row, ["details.contract_type", "contract_type", "option_type"], "")).lower(),
                "expiration_date": _first_existing(row, ["details.expiration_date", "expiration_date", "expiration"], None),
                "open_interest": _first_existing(row, ["open_interest", "day.open_interest"], 0),
                "gamma": _first_existing(row, ["greeks.gamma", "gamma"], 0),
            }
        )

    out = pd.DataFrame(out_rows)
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["open_interest"] = pd.to_numeric(out["open_interest"], errors="coerce").fillna(0)
    out["gamma"] = pd.to_numeric(out["gamma"], errors="coerce").fillna(0)
    out["expiration_date"] = pd.to_datetime(out["expiration_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["option_type"] = out["option_type"].str.lower()

    out = out.dropna(subset=["strike", "expiration_date"]).copy()
    out = out[out["option_type"].isin(["call", "put"])].copy()
    return out


def select_expirations(df: pd.DataFrame, expiration_count: int) -> pd.DataFrame:
    expirations = sorted(x for x in df["expiration_date"].dropna().unique().tolist())
    if not expirations:
        raise ValueError("No expirations available in Massive snapshot response.")
    selected = set(expirations[:expiration_count])
    return df[df["expiration_date"].isin(selected)].copy()


def compute_levels(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        raise ValueError("No option chain data available after normalization/filtering.")

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

    gamma_flip: float | None = None
    prev_val: float | None = None
    for strike, row in net_gex.iterrows():
        curr_val = float(row["net_gex"])
        if prev_val is not None and ((prev_val < 0 < curr_val) or (prev_val > 0 > curr_val)):
            gamma_flip = float(strike)
            break
        prev_val = curr_val

    if gamma_flip is None and not net_gex.empty:
        gamma_flip = float(net_gex["net_gex"].abs().idxmin())

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


def write_csv(output_csv: Path, levels: dict[str, Any]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "time": datetime.now().strftime("%Y-%m-%d"),
        **levels,
    }
    pd.DataFrame([row]).to_csv(output_csv, index=False)


def main() -> None:
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing MASSIVE_API_KEY environment variable.")

    config = Config(api_key=api_key)
    client = MassiveClient(config)

    raw = client.get_option_chain_snapshot(config.symbol)
    normalized = normalize_chain(raw)
    selected = select_expirations(normalized, config.expiration_count)
    levels = compute_levels(selected)
    write_csv(config.output_csv, levels)

    print("Updated walls:")
    for key, value in levels.items():
        print(f"  {key}: {value}")
    print(f"Wrote: {config.output_csv}")


if __name__ == "__main__":
    main()
