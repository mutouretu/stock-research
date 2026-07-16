"""Configuration-driven research panel construction."""

from cycle_equity_research.panels.builder import (
    attach_quarterly_features,
    build_daily_panel,
    build_quarterly_panel,
)
from cycle_equity_research.panels.curation import (
    build_core_monthly_panel,
    build_core_quarterly_panel,
    build_tactical_context_panel,
)

__all__ = [
    "attach_quarterly_features",
    "build_core_monthly_panel",
    "build_core_quarterly_panel",
    "build_daily_panel",
    "build_quarterly_panel",
    "build_tactical_context_panel",
]
