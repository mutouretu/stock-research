from research_ml_core.split import walk_forward_split


def test_walk_forward_split_is_ordered_and_expanding() -> None:
    splits = walk_forward_split(10, train_size=4, test_size=2, step=2)

    assert len(splits) == 3
    assert splits[0].train.tolist() == [0, 1, 2, 3]
    assert splits[0].test.tolist() == [4, 5]
    assert splits[-1].train.tolist() == list(range(8))
    assert splits[-1].test.tolist() == [8, 9]
