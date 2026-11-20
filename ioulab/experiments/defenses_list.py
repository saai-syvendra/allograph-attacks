"""Ordered defense list for the experiment matrix."""

from __future__ import annotations

from ..defenses.config import DEFENSES, Defense

ALL_DEFENSES = ["D0", "PI", "C1", "C2", "C3", "CEIL", "RCEIL", "EFFCONF", "XCONF", "CS", "CSA"]


def by_name(name: str) -> Defense:
    return DEFENSES[name]
