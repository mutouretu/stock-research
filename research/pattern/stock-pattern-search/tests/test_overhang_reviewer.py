import pandas as pd

from src.review.overhang import (
    build_volume_weighted_price_histogram,
    compute_overhang_factor,
    compute_overhang_ratio,
)


def test_overhang_ratio_uses_volume_above_current_price() -> None:
    df = pd.DataFrame(
        {
            "close": [10.0, 10.0, 20.0, 20.0],
            "vol": [1.0, 1.0, 4.0, 4.0],
        }
    )

    hist, bin_edges = build_volume_weighted_price_histogram(df, lookback=4, n_bins=2)
    ratio = compute_overhang_ratio(hist, bin_edges, current_price=10.0)

    assert ratio == 0.8


def test_overhang_factor_decays_as_ratio_increases() -> None:
    low = compute_overhang_factor(0.1)
    high = compute_overhang_factor(0.8)

    assert 0.4 <= high < low <= 1.0
