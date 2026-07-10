"""Placeholders for agricultural demand features."""

import pandas as pd


def build_crop_demand_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Later combine configured crop and acreage signals; currently preserve the frame."""
    return frame.copy()
