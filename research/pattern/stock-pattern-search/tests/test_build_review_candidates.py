from pathlib import Path

import pandas as pd
import yaml

from src.pipelines.build_review_candidates import build_review_candidates


def test_build_review_candidates_merges_specialist_passes(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    runup_path = pred_dir / "runup.csv"
    output_path = pred_dir / "review.csv"

    pd.DataFrame(
        [
            {"sample_id": "a_2026-03-27", "ts_code": "a", "asof_date": "2026-03-27", "score_mean": 0.9},
            {"sample_id": "b_2026-03-27", "ts_code": "b", "asof_date": "2026-03-27", "score_mean": 0.8},
            {"sample_id": "c_2026-03-27", "ts_code": "c", "asof_date": "2026-03-27", "score_mean": 0.7},
        ]
    ).to_csv(baseline_path, index=False)
    pd.DataFrame(
        [
            {"sample_id": "b_2026-03-27", "ts_code": "b", "asof_date": "2026-03-27", "score_mean": 0.95},
            {"sample_id": "c_2026-03-27", "ts_code": "c", "asof_date": "2026-03-27", "score_mean": 0.85},
        ]
    ).to_csv(runup_path, index=False)

    config_path = tmp_path / "review.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": "2026-03-27",
                "output_path": str(output_path),
                "baseline": {
                    "name": "baseline_type_n",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 3,
                },
                "specialists": [
                    {
                        "name": "runup",
                        "path": str(runup_path),
                        "score_col": "score_mean",
                        "top_n": 2,
                        "pass_rank": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert out.loc[0, "ts_code"] == "b"
    assert out.loc[0, "pass_runup"]
    assert out.loc[0, "pass_count"] == 1
    assert not out[out["ts_code"] == "a"].iloc[0]["pass_runup"]
    assert {"review_rank", "baseline_rank", "runup_rank", "runup_score"}.issubset(out.columns)


def test_build_review_candidates_can_apply_runup_post_penalty(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    raw_dir = tmp_path / "raw"
    pred_dir.mkdir()
    raw_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    output_path = pred_dir / "review_penalty.csv"

    asof_date = "2026-03-27"
    pd.DataFrame(
        [
            {"sample_id": f"low_{asof_date}", "ts_code": "low", "asof_date": asof_date, "score_mean": 0.8},
            {"sample_id": f"high_{asof_date}", "ts_code": "high", "asof_date": asof_date, "score_mean": 0.9},
        ]
    ).to_csv(baseline_path, index=False)

    dates = pd.date_range(end=asof_date, periods=5, freq="D")
    pd.DataFrame({"trade_date": dates, "close": [10, 10, 10, 10, 11]}).to_parquet(raw_dir / "low.parquet")
    pd.DataFrame({"trade_date": dates, "close": [10, 10, 10, 10, 16]}).to_parquet(raw_dir / "high.parquet")

    config_path = tmp_path / "review_penalty.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": asof_date,
                "output_path": str(output_path),
                "primary_score_col": "adjusted_score",
                "baseline": {
                    "name": "baseline_type_n",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 2,
                },
                "post_penalties": {
                    "runup": {
                        "enabled": True,
                        "raw_data_dir": str(raw_dir),
                        "window": 5,
                        "threshold": 0.35,
                        "sharpness": 20,
                        "score_col": "baseline_score",
                        "output_score_col": "adjusted_score",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert {"runup_5", "runup_penalty_factor", "adjusted_score"}.issubset(out.columns)
    low = out[out["ts_code"] == "low"].iloc[0]
    high = out[out["ts_code"] == "high"].iloc[0]
    assert low["runup_penalty_factor"] > high["runup_penalty_factor"]
    assert low["adjusted_score"] > high["adjusted_score"]
    assert out.iloc[0]["ts_code"] == "low"


def test_build_review_candidates_can_apply_volume_post_penalty(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    raw_dir = tmp_path / "raw"
    pred_dir.mkdir()
    raw_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    output_path = pred_dir / "review_volume.csv"

    asof_date = "2026-03-27"
    pd.DataFrame(
        [
            {"sample_id": f"fresh_{asof_date}", "ts_code": "fresh", "asof_date": asof_date, "score_mean": 0.8},
            {"sample_id": f"late_{asof_date}", "ts_code": "late", "asof_date": asof_date, "score_mean": 0.8},
        ]
    ).to_csv(baseline_path, index=False)

    dates = pd.date_range(end=asof_date, periods=30, freq="D")
    fresh_vol = [100.0] * 27 + [220.0, 230.0, 240.0]
    late_vol = [100.0] * 20 + [600.0] * 10
    pd.DataFrame({"trade_date": dates, "vol": fresh_vol}).to_parquet(raw_dir / "fresh.parquet")
    pd.DataFrame({"trade_date": dates, "vol": late_vol}).to_parquet(raw_dir / "late.parquet")

    config_path = tmp_path / "review_volume.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": asof_date,
                "output_path": str(output_path),
                "primary_score_col": "adjusted_score",
                "baseline": {
                    "name": "baseline_type_n",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 2,
                },
                "post_penalties": {
                    "volume": {
                        "enabled": True,
                        "raw_data_dir": str(raw_dir),
                        "ma_window": 20,
                        "short_window": 3,
                        "score_col": "baseline_score",
                        "output_score_col": "adjusted_score",
                        "strength": {"threshold": 1.8, "sharpness": 3, "max_boost": 0.15},
                        "streak": {"spike_ratio": 1.8, "threshold": 3, "sharpness": 1.5},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert {"volume_ratio_3d_20", "volume_spike_streak", "volume_penalty_factor", "adjusted_score"}.issubset(
        out.columns
    )
    fresh = out[out["ts_code"] == "fresh"].iloc[0]
    late = out[out["ts_code"] == "late"].iloc[0]
    assert fresh["volume_spike_streak"] < late["volume_spike_streak"]
    assert fresh["volume_penalty_factor"] > late["volume_penalty_factor"]
    assert fresh["adjusted_score"] > late["adjusted_score"]


def test_build_review_candidates_can_apply_base_stability_post_penalty(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    raw_dir = tmp_path / "raw"
    pred_dir.mkdir()
    raw_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    output_path = pred_dir / "review_base.csv"

    asof_date = "2026-03-27"
    pd.DataFrame(
        [
            {"sample_id": f"flat_{asof_date}", "ts_code": "flat", "asof_date": asof_date, "score_mean": 0.8},
            {"sample_id": f"trend_{asof_date}", "ts_code": "trend", "asof_date": asof_date, "score_mean": 0.8},
        ]
    ).to_csv(baseline_path, index=False)

    dates = pd.date_range(end=asof_date, periods=140, freq="D")
    flat = pd.DataFrame(
        {
            "trade_date": dates,
            "ma_bfq_20": [10.0] * 140,
            "ma_bfq_60": [10.0] * 140,
        }
    )
    trend = pd.DataFrame(
        {
            "trade_date": dates,
            "ma_bfq_20": [10.0 + i * 0.08 for i in range(140)],
            "ma_bfq_60": [10.0 + i * 0.02 for i in range(140)],
        }
    )
    flat.to_parquet(raw_dir / "flat.parquet")
    trend.to_parquet(raw_dir / "trend.parquet")

    config_path = tmp_path / "review_base.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": asof_date,
                "output_path": str(output_path),
                "primary_score_col": "adjusted_score",
                "baseline": {
                    "name": "baseline_type_n",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 2,
                },
                "post_penalties": {
                    "base_stability": {
                        "enabled": True,
                        "raw_data_dir": str(raw_dir),
                        "window": 20,
                        "score_col": "baseline_score",
                        "output_score_col": "adjusted_score",
                        "ma_gap": {"threshold": 0.04, "sharpness": 80},
                        "ma_trend": {
                            "prior_lag": 40,
                            "recent_weight": 0.7,
                            "prior_weight": 0.3,
                            "threshold": 0.08,
                            "sharpness": 30,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert {"base_ma_gap_l2", "base_ma60_trend_abs", "base_stability_factor", "adjusted_score"}.issubset(
        out.columns
    )
    flat_row = out[out["ts_code"] == "flat"].iloc[0]
    trend_row = out[out["ts_code"] == "trend"].iloc[0]
    assert flat_row["base_stability_factor"] > trend_row["base_stability_factor"]
    assert flat_row["adjusted_score"] > trend_row["adjusted_score"]


def test_build_review_candidates_can_apply_box_breakout_post_penalty(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    raw_dir = tmp_path / "raw"
    pred_dir.mkdir()
    raw_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    output_path = pred_dir / "review_breakout.csv"

    asof_date = "2026-03-27"
    pd.DataFrame(
        [
            {"sample_id": f"near_{asof_date}", "ts_code": "near", "asof_date": asof_date, "score_mean": 0.8},
            {"sample_id": f"far_{asof_date}", "ts_code": "far", "asof_date": asof_date, "score_mean": 0.8},
        ]
    ).to_csv(baseline_path, index=False)

    dates = pd.date_range(end=asof_date, periods=70, freq="D")
    pd.DataFrame(
        {
            "trade_date": dates,
            "high": [10.0] * 69 + [10.2],
            "close": [9.8] * 69 + [10.05],
        }
    ).to_parquet(raw_dir / "near.parquet")
    pd.DataFrame(
        {
            "trade_date": dates,
            "high": [10.0] * 69 + [9.3],
            "close": [9.0] * 69 + [9.2],
        }
    ).to_parquet(raw_dir / "far.parquet")

    config_path = tmp_path / "review_breakout.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": asof_date,
                "output_path": str(output_path),
                "primary_score_col": "adjusted_score",
                "baseline": {
                    "name": "baseline_type_n",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 2,
                },
                "post_penalties": {
                    "box_breakout": {
                        "enabled": True,
                        "raw_data_dir": str(raw_dir),
                        "window": 60,
                        "score_col": "baseline_score",
                        "output_score_col": "adjusted_score",
                        "min_factor": 0.3,
                        "max_factor": 1.2,
                        "strength": {"threshold": -0.01, "sharpness": 80},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert {"box_high", "box_breakout_pct", "box_breakout_factor", "adjusted_score"}.issubset(out.columns)
    near = out[out["ts_code"] == "near"].iloc[0]
    far = out[out["ts_code"] == "far"].iloc[0]
    assert near["box_breakout_pct"] > far["box_breakout_pct"]
    assert near["box_breakout_factor"] > far["box_breakout_factor"]
    assert near["adjusted_score"] > far["adjusted_score"]


def test_build_review_candidates_can_apply_overhang_post_penalty(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    raw_dir = tmp_path / "raw"
    pred_dir.mkdir()
    raw_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    output_path = pred_dir / "review_overhang.csv"

    asof_date = "2026-03-27"
    pd.DataFrame(
        [
            {"sample_id": f"clear_{asof_date}", "ts_code": "clear", "asof_date": asof_date, "score_mean": 0.8},
            {"sample_id": f"heavy_{asof_date}", "ts_code": "heavy", "asof_date": asof_date, "score_mean": 0.8},
        ]
    ).to_csv(baseline_path, index=False)

    dates = pd.date_range(end=asof_date, periods=160, freq="D")
    pd.DataFrame(
        {
            "trade_date": dates,
            "close": [10.0] * 159 + [20.0],
            "vol": [100.0] * 160,
        }
    ).to_parquet(raw_dir / "clear.parquet")
    pd.DataFrame(
        {
            "trade_date": dates,
            "close": [20.0] * 159 + [10.0],
            "vol": [100.0] * 160,
        }
    ).to_parquet(raw_dir / "heavy.parquet")

    config_path = tmp_path / "review_overhang.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": asof_date,
                "output_path": str(output_path),
                "primary_score_col": "adjusted_score",
                "baseline": {
                    "name": "baseline_type_n",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 2,
                },
                "post_penalties": {
                    "overhang": {
                        "enabled": True,
                        "raw_data_dir": str(raw_dir),
                        "lookback": 150,
                        "n_bins": 50,
                        "threshold": 0.35,
                        "sharpness": 12,
                        "min_factor": 0.4,
                        "max_factor": 1.0,
                        "score_col": "baseline_score",
                        "output_score_col": "adjusted_score",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert {"overhang_ratio", "overhang_factor", "adjusted_score"}.issubset(out.columns)
    clear = out[out["ts_code"] == "clear"].iloc[0]
    heavy = out[out["ts_code"] == "heavy"].iloc[0]
    assert clear["overhang_ratio"] < heavy["overhang_ratio"]
    assert clear["overhang_factor"] > heavy["overhang_factor"]
    assert clear["adjusted_score"] > heavy["adjusted_score"]


def test_build_review_candidates_can_attach_chip_structure_fields_without_rescoring(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    raw_dir = tmp_path / "raw"
    pred_dir.mkdir()
    raw_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    output_path = pred_dir / "review_chip.csv"

    asof_date = "2026-03-27"
    anchor_date = "2026-03-24"
    pd.DataFrame(
        [
            {
                "sample_id": f"chip_{asof_date}",
                "ts_code": "chip",
                "anchor_date": anchor_date,
                "asof_date": asof_date,
                "score_mean": 0.8,
            }
        ]
    ).to_csv(baseline_path, index=False)

    dates = pd.date_range(end=asof_date, periods=8, freq="D")
    pd.DataFrame(
        {
            "trade_date": dates,
            "close": [10.0, 10.1, 10.2, 10.3, 10.8, 10.6, 10.5, 10.7],
            "cost_5pct": [8.0] * 8,
            "cost_15pct": [9.0] * 8,
            "cost_50pct": [10.0, 10.0, 10.1, 10.1, 10.3, 10.4, 10.4, 10.5],
            "cost_85pct": [11.0] * 8,
            "cost_95pct": [12.0] * 8,
            "weight_avg": [10.0, 10.0, 10.0, 10.0, 10.3, 10.4, 10.5, 10.6],
            "winner_rate": [0.45, 0.46, 0.48, 0.50, 0.72, 0.66, 0.61, 0.64],
        }
    ).to_parquet(raw_dir / "chip.parquet")

    config_path = tmp_path / "review_chip.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": asof_date,
                "output_path": str(output_path),
                "primary_score_col": "baseline_score",
                "baseline": {
                    "name": "phase2_tracking",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 1,
                },
                "post_penalties": {
                    "chip_structure": {
                        "enabled": True,
                        "raw_data_dir": str(raw_dir),
                        "pre_window": 3,
                        "near_pct": 0.03,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert {
        "anchor_date",
        "chip_price_vs_cost_50",
        "chip_price_vs_weight_avg",
        "chip_cost_band_width_15_85",
        "chip_center_shift",
        "chip_winner_rate_change",
    }.issubset(out.columns)
    row = out.iloc[0]
    assert row["anchor_date"] == anchor_date
    assert row["baseline_score"] == 0.8
    assert row["chip_price_vs_cost_50"] > 0
    assert row["chip_center_shift"] > 0


def test_build_review_candidates_can_apply_midlong_trend_soft_pruning(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    raw_dir = tmp_path / "raw"
    pred_dir.mkdir()
    raw_dir.mkdir()
    baseline_path = pred_dir / "baseline.csv"
    output_path = pred_dir / "review_trend.csv"

    asof_date = "2026-03-27"
    pd.DataFrame(
        [
            {"sample_id": f"up_{asof_date}", "ts_code": "up", "asof_date": asof_date, "score_mean": 0.8},
            {"sample_id": f"down_{asof_date}", "ts_code": "down", "asof_date": asof_date, "score_mean": 0.8},
        ]
    ).to_csv(baseline_path, index=False)

    dates = pd.date_range(end=asof_date, periods=150, freq="D")
    up_close = [10.0 + i * 0.05 for i in range(150)]
    down_close = [18.0 - i * 0.04 for i in range(150)]
    pd.DataFrame(
        {
            "trade_date": dates,
            "high": [v * 1.02 for v in up_close],
            "low": [v * 0.98 for v in up_close],
            "close": up_close,
        }
    ).to_parquet(raw_dir / "up.parquet")
    pd.DataFrame(
        {
            "trade_date": dates,
            "high": [v * 1.02 for v in down_close],
            "low": [v * 0.98 for v in down_close],
            "close": down_close,
        }
    ).to_parquet(raw_dir / "down.parquet")

    config_path = tmp_path / "review_trend.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "asof_date": asof_date,
                "output_path": str(output_path),
                "primary_score_col": "adjusted_score",
                "baseline": {
                    "name": "phase2_tracking",
                    "path": str(baseline_path),
                    "score_col": "score_mean",
                    "top_n": 2,
                },
                "post_penalties": {
                    "midlong_trend": {
                        "enabled": True,
                        "raw_data_dir": str(raw_dir),
                        "short_window": 20,
                        "mid_window": 60,
                        "long_window": 120,
                        "slope_lag": 20,
                        "return_window": 120,
                        "position_window": 120,
                        "min_return": 0.0,
                        "min_mid_ma_slope": 0.0,
                        "min_position": 0.45,
                        "threshold": 0.0,
                        "sharpness": 80,
                        "min_factor": 0.25,
                        "max_factor": 1.35,
                        "score_col": "baseline_score",
                        "output_score_col": "adjusted_score",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    out = build_review_candidates(config_path)

    assert output_path.exists()
    assert {
        "trend_price_vs_mid_ma",
        "trend_mid_ma_slope",
        "trend_return",
        "trend_position",
        "trend_midlong_score",
        "trend_midlong_pass",
        "trend_ma_factor",
        "adjusted_score",
    }.issubset(out.columns)
    up = out[out["ts_code"] == "up"].iloc[0]
    down = out[out["ts_code"] == "down"].iloc[0]
    assert up["baseline_score"] == 0.8
    assert bool(up["trend_midlong_pass"])
    assert not bool(down["trend_midlong_pass"])
    assert up["trend_midlong_score"] > down["trend_midlong_score"]
    assert up["trend_ma_factor"] > down["trend_ma_factor"]
    assert up["adjusted_score"] > down["adjusted_score"]
