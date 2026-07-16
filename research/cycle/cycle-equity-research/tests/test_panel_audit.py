import pandas as pd

from cycle_equity_research.quality.audit import (
    audit_annual_reconciliation,
    audit_asof_values,
    audit_determinism,
    audit_period_means,
    stable_frame_hash,
)


def test_stable_frame_hash_changes_with_content() -> None:
    first = pd.DataFrame({"date": pd.to_datetime(["2025-01-01"]), "value": [1.0]})
    same = first.copy()
    changed = first.assign(value=2.0)

    assert stable_frame_hash(first) == stable_frame_hash(same)
    assert stable_frame_hash(first) != stable_frame_hash(changed)
    assert audit_determinism("same", first, same)["status"] == "PASS"


def test_asof_audit_rejects_value_published_after_panel_date() -> None:
    panel = pd.DataFrame({"date": pd.to_datetime(["2025-05-01"]), "price": [900.0]})
    source = pd.DataFrame(
        {
            "available_time": pd.to_datetime(["2025-04-01", "2025-05-02"]),
            "value": [300.0, 900.0],
        }
    )

    result = audit_asof_values(
        panel,
        source,
        name="asof",
        panel_time_col="date",
        source_available_col="available_time",
        source_value_col="value",
        panel_value_col="price",
        sample_count=1,
    )

    assert result["status"] == "FAIL"
    assert result["evidence"][0]["expected"] == 300.0


def test_period_mean_audit_applies_availability_cutoff() -> None:
    panel = pd.DataFrame(
        {
            "period_end": pd.to_datetime(["2025-03-31"]),
            "panel_available_time": pd.to_datetime(["2025-05-01"]),
            "quarter_mean": [300.0],
        }
    )
    source = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2025-01-31", "2025-03-31"]),
            "available_time": pd.to_datetime(["2025-02-10", "2025-05-10"]),
            "value": [300.0, 900.0],
        }
    )

    result = audit_period_means(
        panel,
        source,
        name="quarter mean",
        period_end_col="period_end",
        panel_available_col="panel_available_time",
        source_time_col="observation_date",
        source_available_col="available_time",
        source_value_col="value",
        panel_value_col="quarter_mean",
        sample_count=1,
    )

    assert result["status"] == "PASS"
    assert result["evidence"][0]["source_rows"] == 1


def test_annual_reconciliation_requires_four_quarters_to_equal_annual() -> None:
    quarterly = pd.DataFrame(
        {
            "period_end": pd.to_datetime(
                ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
            ),
            "revenue": [100.0, 120.0, 130.0, 150.0],
        }
    )
    annual = pd.DataFrame({"year": [2025], "value": [500.0]})

    result = audit_annual_reconciliation(
        quarterly,
        annual,
        name="annual revenue",
        quarterly_value_col="revenue",
        annual_year_col="year",
        annual_value_col="value",
    )

    assert result["status"] == "PASS"
    assert result["evidence"][0]["difference"] == 0.0
