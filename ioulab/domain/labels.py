"""Reader-set labels in the decentralized-label-model style.

A label is the set of principals allowed to read some data. `None` is top: nothing has
been read yet, so there is no restriction.
"""

from __future__ import annotations

Label = frozenset[str] | None


def meet(a: Label, b: frozenset[str]) -> frozenset[str]:
    """Greatest lower bound of two reader sets (intersection); None is top."""
    return b if a is None else a & b


def flows_to(audience: frozenset[str], label: Label) -> bool:
    """May data with `label` reach `audience`? (audience must be a subset of readers)."""
    return label is None or audience <= label
