"""SEC Company Facts ingestion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from market_data_hub.domains.common.http import fetch_bytes


ALLOWED_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K"}


def normalize_companyfacts(
    payload: dict[str, Any],
    *,
    ticker: str,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    retrieved = retrieved_at or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for taxonomy, concepts in (payload.get("facts") or {}).items():
        for concept, definition in concepts.items():
            label = definition.get("label")
            description = definition.get("description")
            for unit, facts in (definition.get("units") or {}).items():
                for fact in facts:
                    form = fact.get("form")
                    if form not in ALLOWED_FORMS or fact.get("val") is None:
                        continue
                    rows.append(
                        {
                            "ticker": ticker.upper(),
                            "cik": str(payload.get("cik", "")),
                            "taxonomy": taxonomy,
                            "concept": concept,
                            "label": label,
                            "description": description,
                            "unit": unit,
                            "value": fact["val"],
                            "period_start": fact.get("start"),
                            "period_end": fact.get("end"),
                            "filing_date": fact.get("filed"),
                            "form": form,
                            "fiscal_year": fact.get("fy"),
                            "fiscal_period": fact.get("fp"),
                            "frame": fact.get("frame"),
                            "accession": fact.get("accn"),
                            "source": "SEC_COMPANYFACTS",
                            "retrieved_at": retrieved,
                            "vintage": retrieved.date().isoformat(),
                        }
                    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("SEC Company Facts payload contained no supported filing facts")
    for column in ("period_start", "period_end", "filing_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return (
        frame.sort_values(["filing_date", "taxonomy", "concept", "period_end"])
        .drop_duplicates(
            ["accession", "taxonomy", "concept", "unit", "period_start", "period_end"],
            keep="last",
        )
        .reset_index(drop=True)
    )


def download_companyfacts(
    url: str,
    *,
    ticker: str,
    user_agent: str,
    retrieved_at: datetime | None = None,
) -> pd.DataFrame:
    payload = json.loads(fetch_bytes(url, user_agent=user_agent).decode("utf-8"))
    return normalize_companyfacts(payload, ticker=ticker, retrieved_at=retrieved_at)
