"""Per-run state shared by the platform layer and the defenses.

Tracks the two provenances of a run:
  * instruction provenance: who authored text that reached the model as guidance;
  * the run label: the meet of the reader sets of all data the run has read.
It also records confirmations asked of the invoker and replay steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import re

from ..domain.labels import Label, meet
from ..domain.world import World

ConfirmPolicy = Literal["deny", "approve", "ask"]


@dataclass
class Segment:
    text: str
    kind: str                     # graph | skill | memory | tool_desc | tool_result | subagent | a2a_reply | user
    authors: frozenset[str]
    instruction: bool             # does it enter the model as guidance?


@dataclass
class Confirmation:
    what: str
    reason: str
    approved: bool


@dataclass
class Step:
    kind: str
    text: str
    label: Label                  # reader set of the data this step shows


@dataclass
class RunContext:
    run_id: str
    invoker: str
    world: World
    defense: "Defense"            # noqa: F821  (defenses.config.Defense; avoids an import cycle)
    confirm_policy: ConfirmPolicy = "deny"
    user_text: str = ""
    label: Label = None
    reads: list[frozenset[str]] = field(default_factory=list)  # reader set of each datum read
    instr_authors: set[str] = field(default_factory=set)
    segments: list[Segment] = field(default_factory=list)
    confirmations: list[Confirmation] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    pi_flags: list[str] = field(default_factory=list)
    approver: Callable[..., bool] | None = None   # simulated invoker for the "ask" policy
    gate_judge: Any = None                        # LLM asked at the effect gate (C2J, C2A)
    gate_log: list[str] = field(default_factory=list)   # what the gate judge answered, per effect

    def add_segment(self, seg: Segment) -> None:
        self.segments.append(seg)
        if seg.instruction:
            self.instr_authors |= set(seg.authors)

    def observe(self, readers: frozenset[str]) -> None:
        self.label = meet(self.label, readers)
        if readers not in self.reads:
            self.reads.append(readers)

    def step(self, kind: str, text: str, label: Label = None) -> None:
        self.steps.append(Step(kind, text, label))

    def confirm(self, what: str, reason: str) -> bool:
        if self.confirm_policy == "ask" and self.approver is not None:
            p = self.world.dir.principals.get(self.invoker) if self.world is not None else None
            shown_what, shown_reason = what, reason
            if getattr(self.defense, "neutral_reason", False):
                # control: same prompt points, but nothing about who wrote what
                shown_what = re.sub(r",? ?(published|edited) by [\w-]+:?|\s*\(added by [\w-]+\)", "", what)
                shown_reason = "the platform paused this action for confirmation"
            elif getattr(self.defense, "anonymous_author", False):
                # control: keep what the author cannot do, hide who the author is
                shown_what = re.sub(r",? ?(published|edited) by [\w-]+:?|\s*\(added by [\w-]+\)", "", what)
                shown_reason = re.sub(r"written by .+?, who cannot", "written by a co-author, who cannot", reason)
            ok = self.approver(getattr(p, "display", self.invoker), self.user_text, shown_what, shown_reason,
                               busy=getattr(self.defense, "busy_user", False))
        else:
            ok = self.confirm_policy == "approve"
        self.confirmations.append(Confirmation(what, reason, ok))
        return ok

    def endorsed(self, tokens: set[str]) -> bool:
        """Did the invoker's own turn name this destination?

        A bare name must match as a whole word ("ken" does not match "taken"); an address or
        path, which is specific, may match as a substring.
        """
        t = self.user_text.lower()
        words = set(re.findall(r"[a-z0-9_]+", t))
        for tok in tokens:
            if not tok:
                continue
            tok = tok.lower()
            if re.fullmatch(r"[a-z0-9_]+", tok):
                if tok in words:
                    return True
            elif tok in t:
                return True
        return False

    def endorses_principal(self, pid: str) -> bool:
        """Did the invoker's turn name this specific principal (by id, display or address)?"""
        if pid == self.invoker:
            return True
        names = set(self.world.dir.names_of(pid)) if self.world is not None else set()
        if pid.startswith("ext:"):          # an address outside the directory: the raw address
            names.add(pid[4:])
        return self.endorsed(names | {pid})
