from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from market_pattern_labeler.data.daily_loader import iter_daily_frames
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_easy.downtrend_simple import (
    DowntrendSimpleConfig,
    DowntrendSimpleMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_easy.high_volatility_range import (
    HighVolatilityRangeConfig,
    HighVolatilityRangeMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_easy.weak_sideways import (
    WeakSidewaysConfig,
    WeakSidewaysMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_hard.downtrend_rebound import (
    DowntrendReboundConfig,
    DowntrendReboundMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_hard.fake_breakout import (
    FakeBreakoutConfig,
    FakeBreakoutMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_hard.late_stage_acceleration import (
    LateStageAccelerationConfig,
    LateStageAccelerationMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_hard.volume_only_spike import (
    VolumeOnlySpikeConfig,
    VolumeOnlySpikeMiner,
)
from market_pattern_labeler.miners.w_bottom.bottom_base_breakout import (
    BottomBaseBreakoutConfig,
    BottomBaseBreakoutMiner,
)
from market_pattern_labeler.miners.w_bottom.long_base_breakout import (
    LongBaseBreakoutConfig,
    LongBaseBreakoutMiner,
)
from market_pattern_labeler.miners.w_bottom.w_bottom import WBottomConfig, WBottomMiner
from market_pattern_labeler.miners.type_v.positive.bottom_rebound import (
    BottomReboundConfig,
    BottomReboundMiner,
)
from market_pattern_labeler.miners.type_v.positive.range_support_rebound import (
    RangeSupportReboundConfig,
    RangeSupportReboundMiner,
)
from market_pattern_labeler.miners.type_v.negative_easy.steady_downtrend import (
    SteadyDowntrendConfig,
    SteadyDowntrendMiner,
)
from market_pattern_labeler.miners.type_v.negative_easy.steady_uptrend import (
    SteadyUptrendConfig,
    SteadyUptrendMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.positive import TypeNConfig, TypeNMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS


def _load_yaml(path: str | Path) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"config not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _miner_cfg(cfg: dict[str, Any], miner_name: str) -> dict[str, Any]:
    miner_cfg = cfg.get(miner_name, cfg)
    return miner_cfg if isinstance(miner_cfg, dict) else {}


def _build_miner(miner_name: str, cfg: dict[str, Any]):
    if miner_name == "type_n":
        return TypeNMiner(TypeNConfig.from_dict(_miner_cfg(cfg, "type_n")))
    if miner_name == "w_bottom":
        return WBottomMiner(WBottomConfig.from_dict(_miner_cfg(cfg, "w_bottom")))
    if miner_name == "bottom_base_breakout":
        return BottomBaseBreakoutMiner(
            BottomBaseBreakoutConfig.from_dict(_miner_cfg(cfg, "bottom_base_breakout"))
        )
    if miner_name == "long_base_breakout":
        return LongBaseBreakoutMiner(
            LongBaseBreakoutConfig.from_dict(_miner_cfg(cfg, "long_base_breakout"))
        )
    if miner_name == "bottom_rebound":
        return BottomReboundMiner(BottomReboundConfig.from_dict(_miner_cfg(cfg, "bottom_rebound")))
    if miner_name == "range_support_rebound":
        return RangeSupportReboundMiner(
            RangeSupportReboundConfig.from_dict(_miner_cfg(cfg, "range_support_rebound"))
        )
    if miner_name == "steady_uptrend":
        return SteadyUptrendMiner(SteadyUptrendConfig.from_dict(_miner_cfg(cfg, "steady_uptrend")))
    if miner_name == "steady_downtrend":
        return SteadyDowntrendMiner(SteadyDowntrendConfig.from_dict(_miner_cfg(cfg, "steady_downtrend")))
    if miner_name == "downtrend_simple":
        return DowntrendSimpleMiner(DowntrendSimpleConfig.from_dict(_miner_cfg(cfg, "downtrend_simple")))
    if miner_name == "weak_sideways":
        return WeakSidewaysMiner(WeakSidewaysConfig.from_dict(_miner_cfg(cfg, "weak_sideways")))
    if miner_name == "high_volatility_range":
        return HighVolatilityRangeMiner(
            HighVolatilityRangeConfig.from_dict(_miner_cfg(cfg, "high_volatility_range"))
        )
    if miner_name == "fake_breakout":
        return FakeBreakoutMiner(FakeBreakoutConfig.from_dict(_miner_cfg(cfg, "fake_breakout")))
    if miner_name == "downtrend_rebound":
        return DowntrendReboundMiner(DowntrendReboundConfig.from_dict(_miner_cfg(cfg, "downtrend_rebound")))
    if miner_name == "late_stage_acceleration":
        return LateStageAccelerationMiner(
            LateStageAccelerationConfig.from_dict(_miner_cfg(cfg, "late_stage_acceleration"))
        )
    if miner_name == "volume_only_spike":
        return VolumeOnlySpikeMiner(VolumeOnlySpikeConfig.from_dict(_miner_cfg(cfg, "volume_only_spike")))
    raise ValueError(f"unsupported miner: {miner_name}")


def _max_candidates_total(miner: Any, cfg: dict[str, Any], miner_name: str) -> Any:
    miner_cfg = _miner_cfg(cfg, miner_name)
    if "max_candidates_total" in miner_cfg:
        return miner_cfg["max_candidates_total"]
    miner_config = getattr(miner, "config", None)
    return getattr(miner_config, "max_candidates_total", None)


def run_miner(
    *,
    data_dir: str,
    output_csv: str,
    miner_name: str,
    config_path: str | None = None,
    symbols: str | list[str] | None = None,
) -> pd.DataFrame:
    cfg = _load_yaml(config_path) if config_path else {}
    miner = _build_miner(miner_name, cfg)
    output_columns = getattr(miner, "output_columns", CANDIDATE_COLUMNS)

    symbol_count = 0
    failed_symbols = 0
    rows: list[pd.DataFrame] = []
    symbol_filter = _parse_symbols(symbols)

    for ts_code, daily_df in iter_daily_frames(data_dir):
        if symbol_filter is not None and ts_code not in symbol_filter:
            continue
        symbol_count += 1
        try:
            out = miner.scan_one(ts_code, daily_df)
        except Exception as exc:  # noqa: BLE001
            failed_symbols += 1
            print(f"[warn] scan failed for {ts_code}: {exc}")
            continue
        if not out.empty:
            rows.append(out)

    if rows:
        candidates = pd.concat(rows, ignore_index=True)
        candidates = candidates.sort_values(
            ["candidate_score", "asof_date"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)
    else:
        candidates = pd.DataFrame(columns=output_columns)

    for col in output_columns:
        if col not in candidates.columns:
            candidates[col] = pd.NA
    candidates = candidates[output_columns]

    max_candidates_total = _max_candidates_total(miner, cfg, miner_name)
    if max_candidates_total:
        candidates = candidates.head(int(max_candidates_total)).reset_index(drop=True)

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output_path, index=False)

    print(f"processed_symbols={symbol_count}")
    print(f"failed_symbols={failed_symbols}")
    print(f"generated_candidates={len(candidates)}")
    _print_candidate_distribution(candidates)
    print(f"output_csv={output_path}")

    return candidates


def _parse_symbols(symbols: str | list[str] | None) -> set[str] | None:
    if symbols is None:
        return None
    if isinstance(symbols, str):
        items = [item.strip() for item in symbols.split(",")]
    else:
        items = [str(item).strip() for item in symbols]
    parsed = {item for item in items if item}
    return parsed or None


def _print_candidate_distribution(candidates: pd.DataFrame) -> None:
    if candidates.empty:
        print("candidate_year_distribution={}")
        print("window_distribution={}")
        print("pattern_stage_distribution={}")
        return
    if "asof_date" in candidates.columns:
        years = pd.to_datetime(candidates["asof_date"], errors="coerce").dt.year.dropna().astype(int)
        print(f"candidate_year_distribution={years.value_counts().sort_index().to_dict()}")
    if "window" in candidates.columns:
        print(f"window_distribution={candidates['window'].value_counts().to_dict()}")
    if "pattern_stage" in candidates.columns:
        print(f"pattern_stage_distribution={candidates['pattern_stage'].value_counts().to_dict()}")
