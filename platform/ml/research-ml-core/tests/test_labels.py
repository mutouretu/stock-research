import pandas as pd
import pytest

from research_ml_core.labels import binary_classification_label, forward_return


def test_forward_return_and_binary_label() -> None:
    prices = pd.Series([10.0, 12.0, 9.0])
    target = forward_return(prices)
    labels = binary_classification_label(prices)

    assert target.iloc[0] == pytest.approx(0.2)
    assert target.iloc[1] == -0.25
    assert labels.iloc[:2].tolist() == [1, 0]
    assert pd.isna(labels.iloc[2])
