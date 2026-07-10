"""Placeholders for nitrogen-economics feature construction."""

import pandas as pd


def build_nitrogen_spread_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Later derive configurable product-versus-input spreads; currently preserve the frame."""
    return frame.copy()


def build_gas_cost_proxy(frame: pd.DataFrame) -> pd.DataFrame:
    """Later derive a configurable natural-gas cost proxy; currently preserve the frame."""
    return frame.copy()
