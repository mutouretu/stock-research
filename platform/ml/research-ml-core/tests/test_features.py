import pandas as pd
import pytest

from research_ml_core.features import add_lag_features, add_return_features, add_rolling_features


def test_rolling_lag_and_return_features() -> None:
    frame = pd.DataFrame({"close": [10.0, 11.0, 12.0, 15.0]})
    result = add_return_features(frame, periods=(1,))
    result = add_lag_features(result, columns=("close",), lags=(1,))
    result = add_rolling_features(result, column="close", windows=(2,))

    assert result.loc[1, "close_return_1"] == pytest.approx(0.1)
    assert result.loc[2, "close_lag_1"] == 11.0
    assert result.loc[3, "close_rolling_mean_2"] == 13.5


def test_return_fill_and_rolling_warmup_are_configurable() -> None:
    frame = pd.DataFrame({"close": [10.0, None, 12.0]})
    returns = add_return_features(frame, periods=(1,), fill_method="pad")
    rolling = add_rolling_features(frame, column="close", windows=(2,), min_periods=1)

    assert returns["close_return_1"].iloc[1] == pytest.approx(0.0)
    assert returns["close_return_1"].iloc[2] == pytest.approx(0.2)
    assert rolling["close_rolling_mean_2"].tolist() == pytest.approx([10.0, 10.0, 12.0])
