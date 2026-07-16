"""Enhanced, deterministic audits for research panels."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def stable_frame_hash(frame: pd.DataFrame) -> str:
    """Return a content hash that also covers column names and dtypes."""
    digest = hashlib.sha256()
    schema = "\n".join(f"{column}:{frame[column].dtype}" for column in frame.columns)
    digest.update(schema.encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return digest.hexdigest()


def audit_asof_values(
    panel: pd.DataFrame,
    source: pd.DataFrame,
    *,
    name: str,
    panel_time_col: str,
    source_available_col: str,
    source_value_col: str,
    panel_value_col: str,
    sample_count: int = 10,
    tolerance: float = 1e-9,
) -> dict:
    """Check fixed panel samples against the latest source value available at that time."""
    candidates = panel.dropna(subset=[panel_time_col, panel_value_col]).sort_values(panel_time_col)
    samples = candidates.iloc[_sample_positions(len(candidates), sample_count)]
    observations = source.dropna(subset=[source_available_col, source_value_col]).copy()
    observations[source_available_col] = pd.to_datetime(
        observations[source_available_col], errors="coerce"
    )
    observations = observations.sort_values(source_available_col)
    failures: list[dict] = []
    evidence: list[dict] = []
    for row in samples.itertuples(index=False):
        panel_time = pd.Timestamp(getattr(row, panel_time_col))
        actual = float(getattr(row, panel_value_col))
        eligible = observations[observations[source_available_col] <= panel_time]
        expected = float(eligible.iloc[-1][source_value_col]) if not eligible.empty else float("nan")
        matched_time = eligible.iloc[-1][source_available_col] if not eligible.empty else pd.NaT
        passed = not pd.isna(expected) and abs(actual - expected) <= tolerance
        item = {
            "panel_time": panel_time.isoformat(),
            "source_available_time": _iso(matched_time),
            "expected": expected,
            "actual": actual,
            "passed": passed,
        }
        evidence.append(item)
        if not passed:
            failures.append(item)
    return _result(name, len(evidence), failures, evidence)


def audit_exact_values(
    panel: pd.DataFrame,
    source: pd.DataFrame,
    *,
    name: str,
    panel_time_col: str,
    source_time_col: str,
    source_value_col: str,
    panel_value_col: str,
    sample_count: int = 10,
    tolerance: float = 1e-9,
) -> dict:
    """Check fixed panel samples against source rows with the same observation period."""
    candidates = panel.dropna(subset=[panel_time_col, panel_value_col]).sort_values(panel_time_col)
    samples = candidates.iloc[_sample_positions(len(candidates), sample_count)]
    observations = source.copy()
    observations[source_time_col] = pd.to_datetime(observations[source_time_col], errors="coerce")
    failures: list[dict] = []
    evidence: list[dict] = []
    for row in samples.itertuples(index=False):
        panel_time = pd.Timestamp(getattr(row, panel_time_col))
        actual = float(getattr(row, panel_value_col))
        matched = observations[observations[source_time_col] == panel_time]
        expected = float(matched.iloc[-1][source_value_col]) if not matched.empty else float("nan")
        passed = not pd.isna(expected) and abs(actual - expected) <= tolerance
        item = {
            "panel_time": panel_time.isoformat(),
            "expected": expected,
            "actual": actual,
            "passed": passed,
        }
        evidence.append(item)
        if not passed:
            failures.append(item)
    return _result(name, len(evidence), failures, evidence)


def audit_period_means(
    panel: pd.DataFrame,
    source: pd.DataFrame,
    *,
    name: str,
    period_end_col: str,
    panel_available_col: str,
    source_time_col: str,
    source_available_col: str,
    source_value_col: str,
    panel_value_col: str,
    sample_count: int = 10,
    tolerance: float = 1e-9,
) -> dict:
    """Recompute fixed quarterly means using period and availability cutoffs."""
    candidates = panel.dropna(subset=[period_end_col, panel_value_col]).sort_values(period_end_col)
    samples = candidates.iloc[_sample_positions(len(candidates), sample_count)]
    observations = source.copy()
    observations[source_time_col] = pd.to_datetime(observations[source_time_col], errors="coerce")
    observations[source_available_col] = pd.to_datetime(
        observations[source_available_col], errors="coerce"
    )
    failures: list[dict] = []
    evidence: list[dict] = []
    for row in samples.itertuples(index=False):
        period_end = pd.Timestamp(getattr(row, period_end_col))
        cutoff = pd.Timestamp(getattr(row, panel_available_col))
        period_start = period_end.to_period("Q").start_time
        eligible = observations[
            observations[source_time_col].between(period_start, period_end)
            & (observations[source_available_col] <= cutoff)
        ]
        expected = float(eligible[source_value_col].mean()) if not eligible.empty else float("nan")
        actual = float(getattr(row, panel_value_col))
        passed = not pd.isna(expected) and abs(actual - expected) <= tolerance
        item = {
            "period_end": period_end.isoformat(),
            "cutoff": cutoff.isoformat(),
            "source_rows": len(eligible),
            "expected": expected,
            "actual": actual,
            "passed": passed,
        }
        evidence.append(item)
        if not passed:
            failures.append(item)
    return _result(name, len(evidence), failures, evidence)


def audit_determinism(name: str, first: pd.DataFrame, second: pd.DataFrame) -> dict:
    first_hash = stable_frame_hash(first)
    second_hash = stable_frame_hash(second)
    passed = first_hash == second_hash
    evidence = [{"first_hash": first_hash, "second_hash": second_hash, "passed": passed}]
    return _result(name, 1, [] if passed else evidence, evidence)


def audit_annual_reconciliation(
    quarterly: pd.DataFrame,
    annual: pd.DataFrame,
    *,
    name: str,
    quarterly_value_col: str,
    annual_year_col: str,
    annual_value_col: str,
    tolerance: float = 1.0,
) -> dict:
    """Reconcile four derived quarters to independently selected annual source facts."""
    working = quarterly[["period_end", quarterly_value_col]].dropna().copy()
    working["year"] = pd.to_datetime(working["period_end"]).dt.year
    sums = working.groupby("year")[quarterly_value_col].agg(["sum", "count"])
    source = annual.set_index(annual_year_col)[annual_value_col]
    evidence: list[dict] = []
    failures: list[dict] = []
    for year in sorted(set(sums.index) & set(source.index)):
        if int(sums.loc[year, "count"]) != 4:
            continue
        quarterly_sum = float(sums.loc[year, "sum"])
        annual_value = float(source.loc[year])
        passed = abs(quarterly_sum - annual_value) <= tolerance
        item = {
            "year": int(year),
            "quarterly_sum": quarterly_sum,
            "annual_value": annual_value,
            "difference": quarterly_sum - annual_value,
            "passed": passed,
        }
        evidence.append(item)
        if not passed:
            failures.append(item)
    if not evidence:
        failures.append({"message": "no complete years available for reconciliation"})
    return _result(name, len(evidence), failures, evidence)


def write_audit_report(results: list[dict], markdown_path: Path, json_path: Path) -> None:
    failures = sum(result["status"] == "FAIL" for result in results)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CF M1/M2 增强审计报告",
        "",
        f"- 检查项：{len(results)}",
        f"- FAIL：{failures}",
        "",
        "| 检查 | 状态 | 样本数 | 失败数 |",
        "|---|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| `{result['name']}` | {result['status']} | {result['sample_count']} | "
            f"{result['failure_count']} |"
        )
    lines.extend(["", "固定样本明细保存在同目录 JSON 报告中。", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps({"failure_count": failures, "checks": results}, indent=2) + "\n",
        encoding="utf-8",
    )


def _sample_positions(length: int, count: int) -> list[int]:
    if length <= 0:
        raise ValueError("Cannot sample an empty frame")
    if count <= 0:
        raise ValueError("sample_count must be positive")
    if length <= count:
        return list(range(length))
    return sorted({round(index * (length - 1) / (count - 1)) for index in range(count)})


def _result(name: str, sample_count: int, failures: list[dict], evidence: list[dict]) -> dict:
    return {
        "name": name,
        "status": "FAIL" if failures else "PASS",
        "sample_count": sample_count,
        "failure_count": len(failures),
        "failures": failures,
        "evidence": evidence,
    }


def _iso(value) -> str | None:
    return None if pd.isna(value) else pd.Timestamp(value).isoformat()
