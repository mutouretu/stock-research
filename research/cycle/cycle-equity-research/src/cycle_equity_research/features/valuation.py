"""Placeholders for valuation features."""

import pandas as pd


def build_valuation_percentile_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Later calculate point-in-time valuation percentiles; currently preserve the frame."""
    return frame.copy()
