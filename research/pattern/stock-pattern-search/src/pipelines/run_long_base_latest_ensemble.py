"""Compatibility wrapper for W-bottom latest ensemble scanning.

New code should import from ``src.pipelines.w_bottom.run_long_base_latest_ensemble``.
"""

from src.pipelines.w_bottom.run_long_base_latest_ensemble import *  # noqa: F401,F403


if __name__ == "__main__":
    from src.pipelines.w_bottom.run_long_base_latest_ensemble import main

    main()
