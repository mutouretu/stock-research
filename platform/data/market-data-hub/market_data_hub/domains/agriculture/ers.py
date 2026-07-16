"""USDA Economic Research Service crop cost-and-return ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd

from market_data_hub.domains.common.http import fetch_bytes


def parse_crop_costs_returns(
    payload: bytes,
    *,
    crop: str,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    raw = pd.read_csv(BytesIO(payload))
    required = {
        "Commodity",
        "Category",
        "Item",
        "Units",
        "Region",
        "Country",
        "Year",
        "Value",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"USDA ERS crop CSV lacks columns: {missing}")
    retrieved = retrieved_at or datetime.now(timezone.utc)
    frame = raw.rename(
        columns={
            "Commodity": "commodity",
            "Category": "category",
            "Item": "item",
            "Units": "unit",
            "Size": "size",
            "Region": "region",
            "Country": "country",
            "Year": "year",
            "Value": "value",
            "Survey base year": "survey_base_year",
        }
    ).copy()
    frame["commodity"] = crop.lower()
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["observation_date"] = pd.to_datetime(
        frame["year"].astype("string") + "-12-31", errors="coerce"
    )
    frame["available_time"] = pd.to_datetime(
        (frame["year"] + 1).astype("string") + "-05-01", errors="coerce"
    )
    frame["source"] = "USDA_ERS_COMMODITY_COSTS_RETURNS"
    frame["retrieved_at"] = retrieved
    frame["vintage"] = retrieved.date().isoformat()
    frame["availability_method"] = "estimated_next_year_may_release"
    return (
        frame.dropna(subset=["year", "category", "item", "value"])
        .sort_values(["year", "region", "category", "item"])
        .reset_index(drop=True)
    )


def download_crop_costs_returns(url: str, *, crop: str) -> pd.DataFrame:
    return parse_crop_costs_returns(fetch_bytes(url), crop=crop)
