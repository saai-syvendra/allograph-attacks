"""C4: memory promotion keeps audiences from widening.

A consolidated memory note inherits the meet of its sources' reader sets; it may be written
into a tier only if every reader of that tier could read all of its sources.
"""

from __future__ import annotations

from ..domain.labels import flows_to


def promotion_allowed(tier_readers: frozenset[str], source_label: frozenset[str] | None) -> bool:
    return flows_to(tier_readers, source_label)
