"""Compatibility wrapper for Type-N phase tracking helpers.

New code should import from ``src.pipelines.type_n.phase_tracking``.
"""

from src.pipelines.type_n.phase_tracking import *  # noqa: F401,F403


if __name__ == "__main__":
    import argparse

    from src.pipelines.type_n.phase_tracking import main

    parser = argparse.ArgumentParser(description="Build a deduplicated Phase1 pool and score it with Phase2 models.")
    parser.add_argument("--config", default="configs/phase_tracking.yaml", help="Path to phase tracking config yaml")
    args = parser.parse_args()
    main(config_path=args.config)
