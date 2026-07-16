"""World Bank Pink Sheet monthly fertilizer-price ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd

from market_data_hub.domains.common.http import fetch_bytes


def parse_monthly_urea(
    payload: bytes,
    *,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    """Extract the monthly urea column from the World Bank workbook.

    The workbook contains title and unit rows above the tabular header, so the parser searches the
    first rows instead of relying on a fixed row number.
    """
    raw = pd.read_excel(BytesIO(payload), sheet_name="Monthly Prices", header=None)
    header_row = _find_header_row(raw)
    headers = [_clean_header(value) for value in raw.iloc[header_row].tolist()]
    if headers and not headers[0]:
        headers[0] = "Date"
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = headers
    date_column = next((column for column in headers if column.lower() in {"date", "month"}), None)
    urea_column = next((column for column in headers if "urea" in column.lower()), None)
    if date_column is None or urea_column is None:
        raise ValueError(f"Pink Sheet monthly workbook lacks date/urea columns: {headers}")

    retrieved = retrieved_at or datetime.now(timezone.utc)
    observation_date = _parse_month(data[date_column])
    frame = pd.DataFrame(
        {
            "series_id": "WORLD_BANK_UREA_MONTHLY",
            "product": "urea",
            "geography": "WORLD_BANK_BENCHMARK",
            "market_level": "global_benchmark",
            "price_basis": "monthly_average",
            "value": pd.to_numeric(data[urea_column], errors="coerce"),
            "unit": "USD_per_metric_ton",
            "currency": "USD",
            "observation_date": observation_date,
            "source": "WORLD_BANK_PINK_SHEET",
            "retrieved_at": retrieved,
            "vintage": retrieved.date().isoformat(),
            "availability_method": "estimated_month_end_plus_10_business_days",
        }
    )
    frame["available_time"] = frame["observation_date"] + pd.offsets.MonthEnd(0) + pd.offsets.BDay(10)
    return (
        frame.dropna(subset=["observation_date", "value"])
        .sort_values("observation_date")
        .drop_duplicates(["series_id", "observation_date"], keep="last")
        .reset_index(drop=True)
    )


def download_monthly_urea(
    url: str,
    *,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    return parse_monthly_urea(fetch_bytes(url), retrieved_at=retrieved_at)


def _find_header_row(raw: pd.DataFrame) -> int:
    for index in range(min(len(raw), 20)):
        values = [_clean_header(value).lower() for value in raw.iloc[index].tolist()]
        has_date_axis = any(value in {"date", "month"} for value in values) or not values[0]
        if has_date_axis and any("urea" in value for value in values):
            return index
    raise ValueError("Could not locate Pink Sheet monthly header row")


def _clean_header(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).split())


def _parse_month(values: pd.Series) -> pd.Series:
    text = values.astype(str).str.strip()
    parsed = pd.to_datetime(text, format="%YM%m", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(values.loc[missing], errors="coerce")
    return parsed
