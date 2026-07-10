from __future__ import annotations

from dataclasses import dataclass
from html import escape
import os
from pathlib import Path
import tempfile
from typing import Any

_MPL_CACHE_DIR = Path(tempfile.gettempdir()) / "market_pattern_labeler_mpl"
_MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CACHE_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(_MPL_CACHE_DIR))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from market_pattern_labeler.data.daily_loader import _normalize_daily
from market_pattern_labeler.utils.dates import to_trade_datetime


REVIEW_COLUMNS = [
    "rank",
    "ts_code",
    "asof_date",
    "pattern_stage",
    "candidate_score",
    "window",
    "chart_path",
    "chart_anchor_date",
    "miner_name",
    "prior_high_date",
    "prior_high_price",
    "base_low_date",
    "base_low_price",
    "base_high_price",
    "base_range_pct",
    "base_close_std_pct",
    "neckline_date",
    "breakout_date",
    "breakout_distance_pct",
    "breakout_recency_bars",
    "monthly_trend_months",
    "monthly_trend_return_pct",
    "monthly_trend_ma_slope_pct",
    "monthly_close_vs_ma_pct",
    "left_bottom_date",
    "middle_peak_date",
    "right_bottom_date",
    "neckline_price",
    "current_close",
    "prior_drawdown_pct",
    "middle_rebound_pct",
    "bottom_similarity_pct",
    "neckline_distance_pct",
    "volume_ratio_20",
    "manual_review",
    "review_note",
]


@dataclass
class PlotCandidatesSummary:
    candidates_loaded: int
    candidates_selected: int
    charts_generated: int
    skipped_candidates: int
    output_dir: Path
    review_csv: Path
    index_html: Path

    def summary_text(self) -> str:
        return "\n".join(
            [
                f"candidates_loaded={self.candidates_loaded}",
                f"candidates_selected={self.candidates_selected}",
                f"charts_generated={self.charts_generated}",
                f"skipped_candidates={self.skipped_candidates}",
                f"output_dir={self.output_dir}",
                f"review_csv={self.review_csv}",
                f"index_html={self.index_html}",
            ]
        )


def load_candidates(path: str | Path) -> pd.DataFrame:
    candidate_path = Path(path)
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidates CSV not found: {candidate_path}")
    return pd.read_csv(candidate_path)


def select_candidates(
    df: pd.DataFrame,
    stage: str | None = None,
    top_n: int = 100,
    sample: str = "top",
    score_column: str = "candidate_score",
    random_seed: int = 42,
) -> pd.DataFrame:
    out = df.copy()
    if stage:
        if "pattern_stage" not in out.columns:
            print("[warn] stage filter requested but pattern_stage column is missing")
            return out.iloc[0:0].copy()
        out = out[out["pattern_stage"].astype(str) == str(stage)].copy()

    if out.empty:
        return out.reset_index(drop=True)

    limit = max(0, int(top_n))
    if sample not in {"top", "random", "year_stratified"}:
        raise ValueError(f"unsupported sample mode: {sample}")

    if sample == "random":
        if limit == 0 or limit >= len(out):
            return out.sample(frac=1.0, random_state=int(random_seed)).reset_index(drop=True)
        return out.sample(n=limit, random_state=int(random_seed)).reset_index(drop=True)
    if sample == "year_stratified":
        return _select_year_stratified(out, limit=limit, score_column=score_column)

    if score_column not in out.columns:
        print(f"[warn] score column missing: {score_column}; keep original order")
        selected = out
    else:
        out[score_column] = pd.to_numeric(out[score_column], errors="coerce")
        selected = out.sort_values(score_column, ascending=False, na_position="last")
    if limit > 0:
        selected = selected.head(limit)
    return selected.reset_index(drop=True)


def _select_year_stratified(df: pd.DataFrame, *, limit: int, score_column: str) -> pd.DataFrame:
    if "asof_date" not in df.columns:
        print("[warn] year_stratified sample requested but asof_date column is missing; fallback to top")
        return select_candidates(df, top_n=limit, sample="top", score_column=score_column)

    out = df.copy()
    out["_sample_year"] = pd.to_datetime(out["asof_date"], errors="coerce").dt.year
    out = out.dropna(subset=["_sample_year"]).copy()
    if out.empty:
        return out.drop(columns=["_sample_year"], errors="ignore").reset_index(drop=True)

    if score_column in out.columns:
        out[score_column] = pd.to_numeric(out[score_column], errors="coerce")
        sort_cols = ["_sample_year", score_column]
        ascending = [True, False]
    else:
        print(f"[warn] score column missing: {score_column}; keep year order")
        sort_cols = ["_sample_year"]
        ascending = [True]

    grouped = {
        int(year): group.sort_values(sort_cols, ascending=ascending, na_position="last").reset_index(drop=True)
        for year, group in out.groupby("_sample_year", sort=True)
    }
    selected: list[pd.Series] = []
    target = len(out) if limit == 0 else min(limit, len(out))
    offset = 0
    years = sorted(grouped)
    while len(selected) < target:
        added = False
        for year in years:
            group = grouped[year]
            if offset < len(group):
                selected.append(group.iloc[offset])
                added = True
                if len(selected) >= target:
                    break
        if not added:
            break
        offset += 1

    if not selected:
        return out.iloc[0:0].drop(columns=["_sample_year"], errors="ignore").reset_index(drop=True)
    return pd.DataFrame(selected).drop(columns=["_sample_year"], errors="ignore").reset_index(drop=True)


def load_daily_for_symbol(data_dir: str | Path, ts_code: str) -> pd.DataFrame:
    base = Path(data_dir)
    if not base.exists():
        raise FileNotFoundError(f"daily data directory not found: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"daily data path is not a directory: {base}")

    path = base / f"{ts_code}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"daily parquet not found for {ts_code}: {path}")
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"read parquet failed for {ts_code}: {exc}") from exc
    if "trade_date" not in df.columns or "close" not in df.columns:
        raise ValueError(f"daily parquet missing trade_date/close for {ts_code}: {path}")
    normalized = _normalize_daily(df, path)
    if normalized.empty:
        raise ValueError(f"daily parquet has no valid rows for {ts_code}: {path}")
    return normalized


def plot_candidate(
    candidate: pd.Series,
    daily: pd.DataFrame,
    output_path: str | Path,
    pre_days: int = 1260,
    post_days: int = 90,
    anchor: str = "breakout",
) -> str:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prepared = daily.copy()
    prepared["trade_date"] = to_trade_datetime(prepared["trade_date"])
    prepared["close"] = pd.to_numeric(prepared["close"], errors="coerce")
    prepared = prepared.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
    if prepared.empty:
        raise ValueError("daily data has no valid trade_date/close rows")

    asof_ts = _candidate_date(candidate, "asof_date")
    asof_idx = _nearest_not_later_index(prepared["trade_date"], asof_ts)
    if asof_idx is None:
        raise ValueError(f"asof_date has no matching prior trade date: {asof_ts}")

    anchor_idx = _resolve_anchor_index(prepared, candidate, asof_idx, anchor)
    start_idx = max(0, anchor_idx - max(0, int(pre_days)))
    end_idx = min(len(prepared) - 1, anchor_idx + max(0, int(post_days)))
    window_df = prepared.iloc[start_idx : end_idx + 1].copy()

    fig, ax = plt.subplots(figsize=(12, 6), dpi=120)
    ax.plot(window_df["trade_date"], window_df["close"], linewidth=1.6, label="close")

    neckline = _float_value(candidate, "neckline_price")
    if neckline is not None:
        ax.axhline(neckline, linestyle="--", linewidth=1.0, label="neckline")

    _mark_first_available(ax, window_df, candidate, ["prior_high_date"], "prior_high", marker="^")
    _mark_first_available(ax, window_df, candidate, ["base_low_date", "left_bottom_date"], "base_low", marker="v")
    _mark_first_available(ax, window_df, candidate, ["neckline_date", "middle_peak_date"], "neckline_peak", marker="o")
    _mark_first_available(ax, window_df, candidate, ["right_bottom_date"], "right_bottom", marker="v")
    _mark_first_available(ax, window_df, candidate, ["breakout_date"], "breakout", marker="D")

    asof_date = prepared.loc[asof_idx, "trade_date"]
    asof_close = float(prepared.loc[asof_idx, "close"])
    if start_idx <= asof_idx <= end_idx:
        ax.axvline(asof_date, linestyle=":", linewidth=1.0, label="asof_date")
        ax.scatter([asof_date], [asof_close], marker="x", s=70, label="asof_close", zorder=5)

    anchor_date = prepared.loc[anchor_idx, "trade_date"]
    anchor_close = float(prepared.loc[anchor_idx, "close"])
    ax.axvline(anchor_date, linestyle="-.", linewidth=1.0, label="chart_anchor")
    ax.scatter([anchor_date], [anchor_close], marker="D", s=45, label="anchor_close", zorder=5)

    title = (
        f"{_str_value(candidate, 'ts_code')} | {_str_value(candidate, 'miner_name')} | "
        f"{_str_value(candidate, 'pattern_stage')} | "
        f"score={_float_text(candidate, 'candidate_score')} | window={_str_value(candidate, 'window')} | "
        f"asof={_str_value(candidate, 'asof_date')} | anchor={_date_str(anchor_date)}"
    )
    ax.set_title(title)
    ax.set_xlabel("trade_date")
    ax.set_ylabel("close")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return _date_str(anchor_date)


def plot_candidates_batch(
    *,
    candidates_path: str | Path = "outputs/w_bottom/candidates/us_w_bottom_candidates.csv",
    data_dir: str | Path = "../shared_data/us/raw/daily/parquet_by_symbol",
    output_dir: str | Path = "outputs/w_bottom/charts/candidate_charts",
    stage: str | None = None,
    top_n: int = 100,
    sample: str = "top",
    random_seed: int = 42,
    pre_days: int = 1260,
    post_days: int = 90,
    score_column: str = "candidate_score",
    image_format: str = "png",
    anchor: str = "breakout",
) -> PlotCandidatesSummary:
    candidates = load_candidates(candidates_path)
    if not Path(data_dir).exists():
        raise FileNotFoundError(f"daily data directory not found: {data_dir}")

    selected = select_candidates(
        candidates,
        stage=stage,
        top_n=top_n,
        sample=sample,
        score_column=score_column,
        random_seed=random_seed,
    )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    review_rows: list[dict[str, Any]] = []
    charts_generated = 0
    skipped = 0
    image_ext = _safe_extension(image_format)

    daily_cache: dict[str, pd.DataFrame] = {}
    for idx, candidate in selected.iterrows():
        rank = len(review_rows) + 1
        ts_code = _str_value(candidate, "ts_code")
        try:
            if not ts_code:
                raise ValueError("missing ts_code")
            if ts_code not in daily_cache:
                daily_cache[ts_code] = load_daily_for_symbol(data_dir, ts_code)

            file_name = _chart_file_name(rank, candidate, image_ext)
            chart_path = out_dir / file_name
            chart_anchor_date = plot_candidate(
                candidate,
                daily_cache[ts_code],
                chart_path,
                pre_days=pre_days,
                post_days=post_days,
                anchor=anchor,
            )
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            print(f"[warn] skip candidate {idx} {ts_code or '<missing>'}: {exc}")
            continue

        charts_generated += 1
        review_rows.append(_review_row(rank, candidate, file_name, chart_anchor_date))

    review_df = pd.DataFrame(review_rows, columns=REVIEW_COLUMNS)
    review_csv = out_dir / "review.csv"
    review_df.to_csv(review_csv, index=False)
    index_html = out_dir / "index.html"
    _write_index_html(review_df, index_html)

    return PlotCandidatesSummary(
        candidates_loaded=len(candidates),
        candidates_selected=len(selected),
        charts_generated=charts_generated,
        skipped_candidates=skipped,
        output_dir=out_dir,
        review_csv=review_csv,
        index_html=index_html,
    )


def _review_row(rank: int, candidate: pd.Series, chart_path: str, chart_anchor_date: str) -> dict[str, Any]:
    row = {col: candidate.get(col, pd.NA) for col in REVIEW_COLUMNS}
    row["rank"] = rank
    row["chart_path"] = chart_path
    row["chart_anchor_date"] = chart_anchor_date
    row["manual_review"] = ""
    row["review_note"] = ""
    return row


def _write_index_html(review_df: pd.DataFrame, output_path: Path) -> None:
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Candidate Review</title>",
        "<style>body{font-family:Arial,sans-serif;margin:24px;} img{max-width:1100px;width:100%;border:1px solid #ddd;} .item{margin-bottom:32px;} .meta{margin:8px 0;color:#333;}</style>",
        "</head><body><h1>Candidate Review</h1>",
    ]
    for _, row in review_df.iterrows():
        chart = escape(str(row.get("chart_path", "")))
        meta = (
            f"#{row.get('rank', '')} {row.get('ts_code', '')} "
            f"{row.get('pattern_stage', '')} score={row.get('candidate_score', '')} "
            f"asof={row.get('asof_date', '')} anchor={row.get('chart_anchor_date', '')}"
        )
        parts.append("<div class='item'>")
        parts.append(f"<div class='meta'>{escape(meta)}</div>")
        parts.append(f"<img src='{chart}' alt='{escape(meta)}'>")
        parts.append("</div>")
    parts.append("</body></html>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def _resolve_anchor_index(prepared: pd.DataFrame, candidate: pd.Series, asof_idx: int, anchor: str) -> int:
    if anchor == "asof":
        return asof_idx
    if anchor != "breakout":
        raise ValueError(f"unsupported chart anchor: {anchor}")

    breakout_date = _candidate_date(candidate, "breakout_date")
    if breakout_date is not None:
        breakout_idx = _nearest_not_later_index(prepared["trade_date"], breakout_date)
        if breakout_idx is not None:
            return breakout_idx

    neckline = _float_value(candidate, "neckline_price")
    right_bottom_date = _candidate_date(candidate, "right_bottom_date")
    if neckline is None or right_bottom_date is None:
        return asof_idx

    right_bottom_idx = _nearest_not_later_index(prepared["trade_date"], right_bottom_date)
    if right_bottom_idx is None:
        return asof_idx

    close = pd.to_numeric(prepared["close"], errors="coerce")
    for idx in range(max(0, right_bottom_idx), asof_idx + 1):
        value = close.iloc[idx]
        if pd.notna(value) and float(value) >= neckline:
            return int(idx)
    return asof_idx


def _mark_date(ax: Any, window_df: pd.DataFrame, candidate: pd.Series, column: str, label: str, marker: str) -> None:
    date_value = _candidate_date(candidate, column)
    if date_value is None:
        print(f"[warn] missing {column} for {_str_value(candidate, 'ts_code')}")
        return
    idx = _nearest_not_later_index(window_df["trade_date"], date_value)
    if idx is None:
        return
    trade_date = window_df.loc[idx, "trade_date"]
    close = float(window_df.loc[idx, "close"])
    ax.scatter([trade_date], [close], marker=marker, s=55, label=label, zorder=5)
    ax.annotate(label, (trade_date, close), textcoords="offset points", xytext=(4, 7), fontsize=8)


def _mark_first_available(
    ax: Any,
    window_df: pd.DataFrame,
    candidate: pd.Series,
    columns: list[str],
    label: str,
    marker: str,
) -> None:
    for column in columns:
        if column in candidate and pd.notna(candidate.get(column)):
            _mark_date(ax, window_df, candidate, column, label, marker)
            return


def _nearest_not_later_index(dates: pd.Series, target: pd.Timestamp | None) -> int | None:
    if target is None or pd.isna(target):
        return None
    normalized = to_trade_datetime(dates)
    eligible = normalized[normalized <= pd.Timestamp(target)]
    if eligible.empty:
        return None
    return int(eligible.index[-1])


def _candidate_date(candidate: pd.Series, column: str) -> pd.Timestamp | None:
    if column not in candidate or pd.isna(candidate.get(column)):
        return None
    value = pd.to_datetime(candidate.get(column), errors="coerce")
    if pd.isna(value):
        return None
    return pd.Timestamp(value)


def _date_str(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _chart_file_name(rank: int, candidate: pd.Series, image_ext: str) -> str:
    ts_code = _safe_token(_str_value(candidate, "ts_code") or "UNKNOWN")
    stage = _safe_token(_str_value(candidate, "pattern_stage") or "candidate")
    asof_date = _safe_token(_str_value(candidate, "asof_date") or "NA")
    score = _float_text(candidate, "candidate_score").replace(".", "p")
    return f"{rank:04d}_{ts_code}_{stage}_{asof_date}_score{score}.{image_ext}"


def _safe_token(value: str) -> str:
    allowed = []
    for char in str(value):
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed).strip("_") or "NA"


def _safe_extension(value: str) -> str:
    ext = _safe_token(value.lower().lstrip("."))
    return ext or "png"


def _str_value(candidate: pd.Series, column: str) -> str:
    if column not in candidate or pd.isna(candidate.get(column)):
        return ""
    return str(candidate.get(column))


def _float_value(candidate: pd.Series, column: str) -> float | None:
    if column not in candidate or pd.isna(candidate.get(column)):
        return None
    value = pd.to_numeric(pd.Series([candidate.get(column)]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _float_text(candidate: pd.Series, column: str) -> str:
    value = _float_value(candidate, column)
    if value is None:
        return "NA"
    return f"{value:.3f}"


__all__ = [
    "PlotCandidatesSummary",
    "load_candidates",
    "load_daily_for_symbol",
    "plot_candidate",
    "plot_candidates_batch",
    "select_candidates",
]
