"""Replay of recorded runs, with viewer access rules.

Platforms commonly let graph owners, editors, space managers and the org admin play back
other users' runs. Without redaction every step is visible to them (the Watch pattern).
With C5 a viewer sees a step only if they could read the data it shows; the rest is
redacted, and break-glass viewing is a separate, logged path not modelled here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..platform.run_context import RunContext, Step


@dataclass
class View:
    viewer: str
    role: str
    visible: list[Step]
    redacted: int


def visible_to(step: Step, viewer: str, redact: bool) -> bool:
    return (not redact) or step.label is None or viewer in step.label


def replay_views(rc: RunContext, viewers: dict[str, str]) -> list[View]:
    """`viewers` maps viewer id -> role (graph_owner, editor, space_manager, org_admin)."""
    redact = rc.defense.c5_replay
    views = []
    for v, role in viewers.items():
        shown = [s for s in rc.steps if visible_to(s, v, redact)]
        views.append(View(v, role, shown, len(rc.steps) - len(shown)))
    return views
