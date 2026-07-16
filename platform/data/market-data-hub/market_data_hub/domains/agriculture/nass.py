"""USDA NASS Quick Stats planted-acreage ingestion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import pandas as pd

from market_data_hub.domains.common.http import fetch_bytes


def normalize_quickstats(
    payload: dict,
    *,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    rows = payload.get("data") or []
    if not rows:
        raise ValueError("USDA NASS Quick Stats returned no data rows")
    raw = pd.DataFrame(rows)
    required = {"commodity_desc", "statisticcat_desc", "year", "Value", "unit_desc"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"USDA NASS payload lacks columns: {missing}")
    expected_short_desc = raw["commodity_desc"].astype(str) + " - ACRES PLANTED"
    raw = raw.loc[
        raw["unit_desc"].eq("ACRES")
        & raw.get("short_desc", pd.Series("", index=raw.index)).eq(expected_short_desc)
    ].copy()
    if raw.empty:
        raise ValueError("USDA NASS payload contained no national planted-acre observations")
    retrieved = retrieved_at or datetime.now(timezone.utc)
    frame = pd.DataFrame(
        {
            "commodity": raw["commodity_desc"].astype(str).str.lower(),
            "statistic": raw["statisticcat_desc"].astype(str).str.lower(),
            "short_description": raw.get("short_desc"),
            "aggregation_level": raw.get("agg_level_desc"),
            "region": raw.get("state_name", pd.Series("US", index=raw.index)).replace("", "US"),
            "country": raw.get("country_name", pd.Series("US", index=raw.index)),
            "year": pd.to_numeric(raw["year"], errors="coerce").astype("Int64"),
            "reference_period": raw.get("reference_period_desc"),
            "value": pd.to_numeric(
                raw["Value"].astype(str).str.replace(",", "", regex=False), errors="coerce"
            ),
            "unit": raw["unit_desc"],
            "source": "USDA_NASS_QUICKSTATS",
            "retrieved_at": retrieved,
            "vintage": retrieved.date().isoformat(),
        }
    )
    frame["observation_date"] = pd.to_datetime(
        frame["year"].astype("string") + "-01-01", errors="coerce"
    )
    load_time = raw.get("load_time")
    if load_time is not None:
        frame["available_time"] = pd.to_datetime(load_time, errors="coerce")
        frame["availability_method"] = "nass_load_time"
    else:
        frame["available_time"] = retrieved
        frame["availability_method"] = "retrieval_time_only"
    return frame.dropna(subset=["year", "value"]).sort_values(
        ["commodity", "year", "reference_period"]
    ).reset_index(drop=True)


def download_planted_acres(base_url: str, *, api_key: str, start_year: int) -> pd.DataFrame:
    frames = []
    for commodity in ("CORN", "SOYBEANS"):
        query = urlencode(
            {
                "key": api_key,
                "commodity_desc": commodity,
                "statisticcat_desc": "AREA PLANTED",
                "agg_level_desc": "NATIONAL",
                "year__GE": str(start_year),
                "format": "JSON",
            }
        )
        payload = json.loads(fetch_bytes(f"{base_url}?{query}").decode("utf-8"))
        frames.append(normalize_quickstats(payload))
    return pd.concat(frames, ignore_index=True)
