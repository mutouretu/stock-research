"""Leakage-aware index splits for ordered observations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TimeSplit:
    train: np.ndarray
    test: np.ndarray


def walk_forward_split(
    n_samples: int,
    *,
    train_size: int,
    test_size: int,
    step: int | None = None,
    expanding: bool = True,
) -> list[TimeSplit]:
    if min(n_samples, train_size, test_size) <= 0:
        raise ValueError("n_samples, train_size, and test_size must be positive")
    stride = int(test_size if step is None else step)
    if stride <= 0:
        raise ValueError("step must be positive")

    splits: list[TimeSplit] = []
    test_start = int(train_size)
    while test_start + test_size <= n_samples:
        train_start = 0 if expanding else test_start - train_size
        splits.append(
            TimeSplit(
                train=np.arange(train_start, test_start, dtype=int),
                test=np.arange(test_start, test_start + test_size, dtype=int),
            )
        )
        test_start += stride
    return splits


def rolling_window_split(n_samples: int, *, train_size: int, test_size: int, step: int | None = None) -> list[TimeSplit]:
    return walk_forward_split(
        n_samples,
        train_size=train_size,
        test_size=test_size,
        step=step,
        expanding=False,
    )


def expanding_window_split(n_samples: int, *, min_train_size: int, test_size: int, step: int | None = None) -> list[TimeSplit]:
    return walk_forward_split(
        n_samples,
        train_size=min_train_size,
        test_size=test_size,
        step=step,
        expanding=True,
    )
