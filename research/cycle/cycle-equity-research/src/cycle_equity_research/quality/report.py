"""Data quality reporting for the CF Milestone 1 source inventory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    check: str
    message: str


@dataclass
class DatasetQuality:
    dataset_id: str
    path: str
    status: str = "PASS"
    rows: int = 0
    first_observation: str | None = None
    last_observation: str | None = None
    missing_rate: dict[str, float] = field(default_factory=dict)
    issues: list[QualityIssue] = field(default_factory=list)

    def add(self, severity: str, check: str, message: str) -> None:
        self.issues.append(QualityIssue(severity, check, message))
        if severity == "ERROR":
            self.status = "ERROR"
        elif severity == "WARNING" and self.status == "PASS":
            self.status = "WARNING"


@dataclass(frozen=True)
class DataQualityReport:
    subject: str
    milestone: int
    as_of: str
    datasets: tuple[DatasetQuality, ...]
    pending_p0_sources: tuple[str, ...]

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "ERROR" for item in self.datasets for issue in item.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "WARNING" for item in self.datasets for issue in item.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "milestone": self.milestone,
            "as_of": self.as_of,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "pending_p0_sources": list(self.pending_p0_sources),
            "datasets": [asdict(item) for item in self.datasets],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        lines = [
            f"# {self.subject} Milestone {self.milestone} 数据质量报告",
            "",
            f"- 数据审计日期：{self.as_of}",
            f"- ERROR：{self.error_count}",
            f"- WARNING：{self.warning_count}",
            f"- 尚未接入的 P0 来源：{', '.join(self.pending_p0_sources) or '无'}",
            "",
            "| Dataset | 状态 | 行数 | 起始日期 | 最新日期 |",
            "|---|---:|---:|---:|---:|",
        ]
        for item in self.datasets:
            lines.append(
                f"| `{item.dataset_id}` | {item.status} | {item.rows} | "
                f"{item.first_observation or '-'} | {item.last_observation or '-'} |"
            )
        for item in self.datasets:
            lines.extend(["", f"## {item.dataset_id}", "", f"路径：`{item.path}`", ""])
            if item.missing_rate:
                lines.extend(["关键字段缺失率：", ""])
                for column, rate in item.missing_rate.items():
                    lines.append(f"- `{column}`：{rate:.2%}")
                lines.append("")
            if item.issues:
                for issue in item.issues:
                    lines.append(f"- **{issue.severity}** `{issue.check}`：{issue.message}")
            else:
                lines.append("- 未发现质量问题。")
        return "\n".join(lines) + "\n"


def build_data_quality_report(
    config_path: str | Path,
    *,
    root: str | Path | None = None,
    as_of: date | None = None,
) -> DataQualityReport:
    config_path = Path(config_path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Quality config must contain a YAML mapping: {config_path}")
    workspace = Path(root).resolve() if root else _find_workspace_root(config_path)
    audit_date = as_of or date.today()
    datasets = tuple(
        _inspect_dataset(spec, workspace=workspace, as_of=audit_date)
        for spec in config.get("datasets", [])
    )
    return DataQualityReport(
        subject=str(config["subject"]),
        milestone=int(config["milestone"]),
        as_of=audit_date.isoformat(),
        datasets=datasets,
        pending_p0_sources=tuple(str(value) for value in config.get("pending_p0_sources", [])),
    )


def write_data_quality_report(
    report: DataQualityReport,
    *,
    markdown_path: str | Path,
    json_path: str | Path,
) -> None:
    markdown = Path(markdown_path)
    json_output = Path(json_path)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(report.to_markdown(), encoding="utf-8")
    json_output.write_text(report.to_json() + "\n", encoding="utf-8")


def _inspect_dataset(spec: dict[str, Any], *, workspace: Path, as_of: date) -> DatasetQuality:
    path = Path(str(spec["path"]))
    resolved = path if path.is_absolute() else workspace / path
    result = DatasetQuality(dataset_id=str(spec["dataset_id"]), path=str(path))
    if not resolved.is_file():
        result.add("ERROR", "file_exists", f"数据文件不存在：{resolved}")
        return result
    try:
        frame = pd.read_parquet(resolved)
    except Exception as exc:
        result.add("ERROR", "readable", f"无法读取 Parquet：{exc}")
        return result

    result.rows = len(frame)
    required = [str(value) for value in spec.get("required_columns", [])]
    missing_columns = [column for column in required if column not in frame]
    if missing_columns:
        result.add("ERROR", "required_columns", f"缺少字段：{missing_columns}")
    present_required = [column for column in required if column in frame]
    result.missing_rate = {
        column: float(frame[column].isna().mean()) for column in present_required
    }
    for column, rate in result.missing_rate.items():
        if rate > 0.05:
            result.add("WARNING", "missing_rate", f"{column} 缺失率为 {rate:.2%}")

    minimum_rows = int(spec.get("min_rows", 1))
    if len(frame) < minimum_rows:
        result.add("ERROR", "minimum_rows", f"行数 {len(frame)} 低于要求 {minimum_rows}")

    key_columns = [str(value) for value in spec.get("key_columns", [])]
    if key_columns and all(column in frame for column in key_columns):
        duplicates = int(frame.duplicated(key_columns).sum())
        if duplicates:
            result.add("ERROR", "unique_key", f"唯一键重复 {duplicates} 行：{key_columns}")

    date_column = str(spec["date_col"])
    dates = pd.to_datetime(frame[date_column], errors="coerce") if date_column in frame else None
    if dates is None:
        result.add("ERROR", "date_column", f"日期字段不存在：{date_column}")
    else:
        valid_dates = dates.dropna()
        if valid_dates.empty:
            result.add("ERROR", "date_values", f"日期字段无法解析：{date_column}")
        else:
            result.first_observation = valid_dates.min().date().isoformat()
            result.last_observation = valid_dates.max().date().isoformat()
            target_start = spec.get("target_start")
            start_tolerance = int(spec.get("start_tolerance_days", 7))
            target_start_date = pd.Timestamp(target_start).date() if target_start else None
            if (
                target_start_date
                and (valid_dates.min().date() - target_start_date).days > start_tolerance
            ):
                result.add(
                    "WARNING",
                    "history_coverage",
                    f"最早日期 {result.first_observation} 晚于目标 {target_start}",
                )
            max_staleness = spec.get("max_staleness_days")
            if max_staleness is not None:
                stale_days = (as_of - valid_dates.max().date()).days
                if stale_days > int(max_staleness):
                    result.add(
                        "WARNING",
                        "staleness",
                        f"最新数据距审计日 {stale_days} 天，阈值为 {max_staleness} 天",
                    )

    available_column = spec.get("available_time_col")
    if available_column:
        if available_column not in frame:
            result.add("ERROR", "available_time", f"缺少 available time：{available_column}")
        elif dates is not None:
            available = pd.to_datetime(frame[available_column], errors="coerce")
            invalid = int((available < dates).fillna(False).sum())
            if invalid:
                result.add("ERROR", "available_time_order", f"available time 早于观察日 {invalid} 行")

    expected_units = {str(value) for value in spec.get("expected_units", [])}
    if expected_units and "unit" in frame:
        actual_units = set(frame["unit"].dropna().astype(str).unique())
        unexpected = sorted(actual_units - expected_units)
        if unexpected:
            result.add("ERROR", "units", f"发现未声明单位：{unexpected}")

    if "value" in frame and not bool(spec.get("allow_non_positive", False)):
        numeric = pd.to_numeric(frame["value"], errors="coerce")
        non_positive = int((numeric <= 0).fillna(False).sum())
        if non_positive:
            result.add("WARNING", "non_positive_values", f"value 非正数 {non_positive} 行")
    price_columns = {"price_low", "price_high", "price_average"}
    if price_columns.issubset(frame.columns):
        low = pd.to_numeric(frame["price_low"], errors="coerce")
        high = pd.to_numeric(frame["price_high"], errors="coerce")
        average = pd.to_numeric(frame["price_average"], errors="coerce")
        invalid_range = int(((low > high) | (average < low) | (average > high)).fillna(False).sum())
        if invalid_range:
            result.add("ERROR", "price_ranges", f"均价不在高低区间内 {invalid_range} 行")
        non_positive_prices = int(((low <= 0) | (high <= 0) | (average <= 0)).fillna(False).sum())
        if non_positive_prices:
            result.add("ERROR", "positive_prices", f"价格非正数 {non_positive_prices} 行")
    return result


def _find_workspace_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "platform").is_dir() and (
            candidate / "research"
        ).is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate stock-research root from {start}")
