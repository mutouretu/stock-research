"""Compatibility wrapper for common review scoring helpers.

New code should import from ``src.reviewers.common.scoring``.
"""

from src.reviewers.common.scoring import sigmoid_boost_factor, sigmoid_decay_factor, sigmoid_rise_factor

__all__ = ["sigmoid_boost_factor", "sigmoid_decay_factor", "sigmoid_rise_factor"]
