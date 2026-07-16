"""FRED-hosted Henry Hub natural-gas series."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd

from market_data_hub.domains.common.http import fetch_bytes


def parse_fred_series(
    payload: bytes,
    *,
    series_id: str,
    product: str,
    unit: str,
    source: str,
    availability_lag_business_days: int = 1,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    """Normalize a two-column FRED CSV export.

    FRED uses either ``DATE`` or ``observation_date`` for the date column depending on the
    endpoint version. Missing observations are represented by ``.``.
    """
    raw = pd.read_csv(BytesIO(payload), na_values=["."])
    date_candidates = [column for column in ("DATE", "observation_date") if column in raw]
    if not date_candidates or series_id not in raw:
        raise ValueError(
            f"FRED payload must contain a date column and {series_id!r}; columns={list(raw)}"
        )
    retrieved = retrieved_at or datetime.now(timezone.utc)
    observation_date = pd.to_datetime(raw[date_candidates[0]], errors="coerce")
    values = pd.to_numeric(raw[series_id], errors="coerce")
    frame = pd.DataFrame(
        {
            "series_id": series_id,
            "product": product,
            "geography": "US_HENRY_HUB",
            "market_level": "spot",
            "price_basis": "daily_spot",
            "value": values,
            "unit": unit,
            "currency": "USD",
            "observation_date": observation_date,
            "source": source,
            "retrieved_at": retrieved,
            "vintage": retrieved.date().isoformat(),
            "availability_method": "estimated_business_day_lag",
        }
    )
    frame["available_time"] = frame["observation_date"] + pd.offsets.BDay(
        availability_lag_business_days
    )
    return (
        frame.dropna(subset=["observation_date", "value"])
        .sort_values("observation_date")
        .drop_duplicates(["series_id", "observation_date"], keep="last")
        .reset_index(drop=True)
    )


def download_henry_hub(
    url: str,
    *,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    return parse_fred_series(
        fetch_bytes(url),
        series_id="DHHNGSP",
        product="henry_hub_natural_gas",
        unit="USD_per_MMBtu",
        source="FRED_EIA",
        retrieved_at=retrieved_at,
    )
