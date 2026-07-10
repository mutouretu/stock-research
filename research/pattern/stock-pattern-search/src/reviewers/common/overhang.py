from __future__ import annotations

import math
from typing import Tuple

import numpy as np
import pandas as pd


def build_volume_weighted_price_histogram(
    df: pd.DataFrame,
    *,
    lookback: int = 150,
    n_bins: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a close-price histogram weighted by volume over the latest lookback rows."""
    if "close" not in df.columns or "vol" not in df.columns:
        raise ValueError("Overhang histogram requires columns: close, vol")

    window = df.tail(int(lookback)).copy()
    prices = pd.to_numeric(window["close"], errors="coerce")
    volumes = pd.to_numeric(window["vol"], errors="coerce").fillna(0.0).clip(lower=0.0)
    valid = prices.notna() & volumes.notna()
    prices = prices[valid]
    volumes = volumes[valid]

    if prices.empty:
        return np.zeros(int(n_bins), dtype=float), np.linspace(0.0, 1.0, int(n_bins) + 1)

    min_price = float(prices.min())
    max_price = float(prices.max())
    if not math.isfinite(min_price) or not math.isfinite(max_price) or min_price == max_price:
        pad = max(abs(min_price) * 0.001, 0.01)
        min_price -= pad
        max_price += pad

    hist, bin_edges = np.histogram(prices.to_numpy(), bins=int(n_bins), range=(min_price, max_price), weights=volumes.to_numpy())
    return hist.astype(float), bin_edges.astype(float)


def compute_overhang_ratio(hist: np.ndarray, bin_edges: np.ndarray, current_price: float) -> float:
    """Return the weighted volume share in price bins above current_price."""
    total_volume = float(np.nansum(hist))
    if total_volume <= 0 or not math.isfinite(total_volume):
        return 0.0
    if pd.isna(current_price):
        return 0.0

    price = float(current_price)
    bin_index = int(np.searchsorted(bin_edges, price, side="right") - 1)
    bin_index = max(0, min(bin_index, len(hist) - 1))
    volume_above_current = float(np.nansum(hist[bin_index + 1 :]))
    return max(0.0, min(volume_above_current / total_volume, 1.0))


def compute_overhang_factor(
    overhang_ratio: float,
    *,
    threshold: float = 0.35,
    sharpness: float = 12.0,
    min_factor: float = 0.4,
    max_factor: float = 1.0,
) -> float:
    """Map overhang_ratio to a decay factor in [min_factor, max_factor]."""
    if pd.isna(overhang_ratio):
        return max_factor
    exponent = max(min(float(sharpness) * (float(overhang_ratio) - float(threshold)), 60.0), -60.0)
    decay = 1.0 / (1.0 + math.exp(exponent))
    return float(min_factor) + (float(max_factor) - float(min_factor)) * decay


__all__ = [
    "build_volume_weighted_price_histogram",
    "compute_overhang_factor",
    "compute_overhang_ratio",
]
