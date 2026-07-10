import pandas as pd

from research_data_core.alignment import merge_asof_by_entity


def test_merge_asof_with_and_without_entity() -> None:
    left = pd.DataFrame({"group": ["b", "a", "a"], "when": [3, 2, 4]})
    right = pd.DataFrame(
        {"group": ["a", "b", "a"], "when": [1, 2, 3], "value": [10, 20, 30]}
    )
    grouped = merge_asof_by_entity(left, right, on="when", by="group")
    assert grouped["value"].tolist() == [10, 20, 30]

    plain = merge_asof_by_entity(left[["when"]], right[["when", "value"]], on="when")
    assert plain["value"].tolist() == [20, 30, 30]
