"""Shared chart utilities.

Currently centralizes legend label formatting to ensure consistent
presentation across manual XML updates, pptx builder seeding, and
dynamic chart updates.
"""

from __future__ import annotations

from typing import Iterable

from app.utils.formatting import format_label


def make_unique_labels(labels: Iterable[str]) -> list[str]:
    """Ensure labels are unique after formatting by appending counters.

    Example: ['Net Income', 'Net_Income'] -> ['Net Income', 'Net Income (2)']
    """
    seen: dict[str, int] = {}
    result: list[str] = []
    for raw in labels:
        base = raw
        # format_label(raw, fallback="Series")
        count = seen.get(base, 0) + 1
        seen[base] = count
        if count == 1:
            result.append(base)
        else:
            result.append(f"{base} ({count})")
    return result
