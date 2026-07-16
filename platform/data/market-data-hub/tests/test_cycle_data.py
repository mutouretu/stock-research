from datetime import datetime, timezone

import pandas as pd

from market_data_hub.domains.agriculture.ers import parse_crop_costs_returns
from market_data_hub.domains.agriculture.nass import normalize_quickstats
from market_data_hub.domains.commodities.henry_hub import parse_fred_series
from market_data_hub.domains.commodities.world_bank import parse_monthly_urea
from market_data_hub.domains.fundamentals.sec_companyfacts import normalize_companyfacts


RETRIEVED_AT = datetime(2026, 7, 16, tzinfo=timezone.utc)


def test_parse_henry_hub_fred_csv() -> None:
    frame = parse_fred_series(
        b"observation_date,DHHNGSP\n2026-07-01,3.21\n2026-07-02,.\n",
        series_id="DHHNGSP",
        product="henry_hub_natural_gas",
        unit="USD_per_MMBtu",
        source="FRED_EIA",
        retrieved_at=RETRIEVED_AT,
    )

    assert len(frame) == 1
    assert frame.loc[0, "value"] == 3.21
    assert frame.loc[0, "available_time"] == pd.Timestamp("2026-07-02")
    assert frame.loc[0, "unit"] == "USD_per_MMBtu"


def test_normalize_sec_companyfacts() -> None:
    payload = {
        "cik": 1324404,
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "description": "Revenue description",
                    "units": {
                        "USD": [
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 100,
                                "accn": "0001",
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-05-01",
                                "frame": "CY2026Q1",
                            },
                            {
                                "end": "2026-03-31",
                                "val": 999,
                                "accn": "0002",
                                "form": "S-8",
                                "filed": "2026-05-02",
                            },
                        ]
                    },
                }
            }
        },
    }

    frame = normalize_companyfacts(payload, ticker="CF", retrieved_at=RETRIEVED_AT)

    assert len(frame) == 1
    assert frame.loc[0, "ticker"] == "CF"
    assert frame.loc[0, "concept"] == "Revenues"
    assert frame.loc[0, "filing_date"] == pd.Timestamp("2026-05-01")


def test_parse_world_bank_monthly_urea(monkeypatch) -> None:
    workbook = pd.DataFrame(
        [
            ["World Bank commodity prices", None, None],
            ["Date", "Crude oil", "Urea"],
            ["2026M01", 70.0, 310.5],
            ["2026M02", 72.0, 320.0],
        ]
    )
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: workbook)

    frame = parse_monthly_urea(b"fake-workbook", retrieved_at=RETRIEVED_AT)

    assert list(frame["value"]) == [310.5, 320.0]
    assert frame.loc[0, "observation_date"] == pd.Timestamp("2026-01-01")
    assert frame.loc[0, "unit"] == "USD_per_metric_ton"


def test_parse_ers_crop_costs_returns() -> None:
    payload = (
        b'"Commodity","Category","Item","Units","Size","Region","Country","Year","Value","Survey base year"\n'
        b'"Corn","Net value","Value less total costs","dollars per planted acre",'
        b'"No specific size","U.S. total","United States",2025,-102.99,"Base survey of 2021"\n'
    )

    frame = parse_crop_costs_returns(payload, crop="corn", retrieved_at=RETRIEVED_AT)

    assert len(frame) == 1
    assert frame.loc[0, "commodity"] == "corn"
    assert frame.loc[0, "value"] == -102.99
    assert frame.loc[0, "available_time"] == pd.Timestamp("2026-05-01")


def test_normalize_nass_planted_acres() -> None:
    payload = {
        "data": [
            {
                "commodity_desc": "CORN",
                "statisticcat_desc": "AREA PLANTED",
                "short_desc": "CORN - ACRES PLANTED",
                "agg_level_desc": "NATIONAL",
                "state_name": "",
                "country_name": "UNITED STATES",
                "year": "2025",
                "reference_period_desc": "YEAR",
                "Value": "95,203,000",
                "unit_desc": "ACRES",
                "load_time": "2025-06-30 15:00:00",
            }
        ]
    }

    frame = normalize_quickstats(payload, retrieved_at=RETRIEVED_AT)

    assert frame.loc[0, "commodity"] == "corn"
    assert frame.loc[0, "value"] == 95_203_000
    assert frame.loc[0, "available_time"] == pd.Timestamp("2025-06-30 15:00:00")
