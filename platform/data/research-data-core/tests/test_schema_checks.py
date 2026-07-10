import pandas as pd
import pytest

from research_data_core.schema import check_no_duplicate_keys, normalize_columns, require_columns


def test_schema_checks_and_normalization() -> None:
    frame = pd.DataFrame({"key": [1, 1], "source_value": [2, 3]})
    with pytest.raises(ValueError, match="Missing required columns"):
        require_columns(frame, ["missing"])
    with pytest.raises(ValueError, match="duplicate keys"):
        check_no_duplicate_keys(frame, ["key"])
    result = normalize_columns(frame, {"source_value": "value"})
    assert "value" in result
