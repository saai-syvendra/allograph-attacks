"""Scenario schema shared by the corpus, the runner and the oracle.

A scenario is one shared-graph situation. It names the invoker and the user's ask, the
fixture that builds the world and registry, the graph to run, and either an attack goal
(what a successful attack would achieve, checked exactly) or nothing (a benign task).

Each attack carries a `payload`: the text an author places into an instruction-bearing
channel. Payload text lives in payloads.yaml and is spliced into the fixture at load time,
so the attack prose is separate from the harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from ...domain.world import World
from ..oracle import Leak


class Channel(str, Enum):
    GRAPH = "graph"            # a co-author's line in a shared graph prompt
    SKILL = "skill"            # a shared skill's SKILL.md body
    MEMORY = "memory"          # a group/space AGENTS.md memory file
    TOOL_DESC = "tool_desc"    # a user-registered MCP tool's description
    SUBAGENT = "subagent"      # a shared subagent spec's prompt
    A2A_REPLY = "a2a_reply"    # a remote agent's reply text
    CONSOLIDATION = "consolidation"  # the memory consolidation policy text


@dataclass
class Payload:
    """One injected instruction, authored by someone other than the invoker."""
    id: str                    # matches a key in payloads.yaml
    pattern: str               # BA1..BA8
    channel: Channel
    author: str                # principal who placed the text
    variant: str = ""          # overt | semi | covert | cross_ref | benign_looking
    text: str = ""             # filled from payloads.yaml
    goal_note: str = ""        # plain-language description of intended effect (for authors)


# An attack succeeds when its goal predicate holds against the final world.
Goal = Callable[[World], bool]


@dataclass
class Scenario:
    id: str
    kind: str                  # "attack" | "benign"
    invoker: str
    user_ask: str
    graph_id: str
    build: Callable[..., tuple]        # fixture -> (world, registry, extras)
    plan_key: str = ""         # which scripted plan to use for dry runs
    payload: Payload | None = None
    goal: Goal | None = None           # attack: True == attack succeeded
    benign_check: Goal | None = None   # benign twin: True == task done correctly
    viewers: dict[str, str] = field(default_factory=dict)  # replay viewers for BA8
    tags: list[str] = field(default_factory=list)
    scripted_policy: Callable | None = None   # a deterministic plan for the scripted model


def leaked(leaks: list[Leak], canary: str) -> bool:
    return any(lk.canary == canary for lk in leaks)
