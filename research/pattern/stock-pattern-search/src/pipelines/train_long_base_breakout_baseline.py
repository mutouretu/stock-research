"""Compatibility wrapper for W-bottom long-base baseline training.

New code should import from ``src.pipelines.w_bottom.train_long_base_breakout_baseline``.
"""

from src.pipelines.w_bottom.train_long_base_breakout_baseline import *  # noqa: F401,F403


if __name__ == "__main__":
    from src.pipelines.w_bottom.train_long_base_breakout_baseline import main

    main()
