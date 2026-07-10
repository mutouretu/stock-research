from __future__ import annotations

from pathlib import Path
from typing import Iterator, Tuple

import pandas as pd

from market_pattern_labeler.utils.dates import to_trade_datetime

REQUIRED_PRICE_COLS = ["trade_date", "open", "high", "low", "close"]
OPTIONAL_COLS = ["vol", "amount", "ts_code", "symbol", "volume", "adj_close", "market"]


def _ensure_required_columns(df: pd.DataFrame, file_path: Path) -> bool:
    missing = [col for col in REQUIRED_PRICE_COLS if col not in df.columns]
    if missing:
        print(f"[warn] skip {file_path.name}: missing required columns {missing}")
        return False
    return True


def _infer_ts_code(df: pd.DataFrame, file_path: Path) -> str:
    if "ts_code" in df.columns:
        non_null = df["ts_code"].dropna()
        if not non_null.empty:
            ts_code = str(non_null.iloc[0])
            if "symbol" in df.columns:
                symbol = df["symbol"].dropna()
                if not symbol.empty and str(symbol.iloc[0]) != ts_code:
                    print(
                        f"[warn] {file_path.name}: ts_code={ts_code} "
                        f"differs from symbol={symbol.iloc[0]}"
                    )
            return ts_code
    if "symbol" in df.columns:
        non_null = df["symbol"].dropna()
        if not non_null.empty:
            return str(non_null.iloc[0])
    return file_path.stem


def _normalize_daily(df: pd.DataFrame, file_path: Path | None = None) -> pd.DataFrame:
    out = df.copy()
    if "vol" not in out.columns and "volume" in out.columns:
        out["vol"] = out["volume"]
    elif "vol" not in out.columns:
        out["vol"] = pd.NA
    if "ts_code" not in out.columns and "symbol" in out.columns:
        out["ts_code"] = out["symbol"]

    out["trade_date"] = to_trade_datetime(out["trade_date"])
    out = out.dropna(subset=["trade_date"])

    for col in ["open", "high", "low", "close", "vol", "amount", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    keep_cols = REQUIRED_PRICE_COLS + [col for col in OPTIONAL_COLS if col in out.columns]
    out = out.loc[:, list(dict.fromkeys(keep_cols))]
    duplicate_mask = out.duplicated("trade_date", keep=False)
    if duplicate_mask.any():
        name = file_path.name if file_path else "<dataframe>"
        print(f"[warn] {name}: duplicate trade_date rows={int(duplicate_mask.sum())}; keep last")
        out = out.drop_duplicates("trade_date", keep="last")
    out = out.sort_values("trade_date").reset_index(drop=True)
    return out


def iter_daily_frames(data_dir: str | Path) -> Iterator[Tuple[str, pd.DataFrame]]:
    """Yield `(ts_code, daily_df)` from parquet files in a directory."""
    base = Path(data_dir)
    if not base.exists():
        raise FileNotFoundError(f"daily data directory not found: {base}")

    files = sorted(base.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files found in {base}")

    for file_path in files:
        try:
            df = pd.read_parquet(file_path)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] skip {file_path.name}: read parquet failed ({exc})")
            continue

        if df.empty:
            continue
        if not _ensure_required_columns(df, file_path):
            continue

        normalized = _normalize_daily(df, file_path)
        if normalized.empty:
            continue

        ts_code = _infer_ts_code(df, file_path)
        if "ts_code" not in normalized.columns:
            normalized["ts_code"] = ts_code
        yield ts_code, normalized
