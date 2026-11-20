"""Shareable artifacts: authors per piece, scope, runs-as mode and version.

Instruction-bearing artifacts (graphs, skills, subagent specs, memory files) are made of
pieces, each with its own author, so instruction provenance is exact even when several
people edit the same artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .principals import Directory


class RunsAs(str, Enum):
    INVOKER = "invoker"    # on-behalf-of the user who pressed run
    OWNER = "owner"        # the artifact owner's own credentials (maker credentials, remote agents)
    PLATFORM = "platform"  # first-party platform service, not a principal


class ArtifactKind(str, Enum):
    GRAPH = "graph"
    SKILL = "skill"
    CONNECTOR = "connector"  # an MCP server registered on the platform
    AGENT = "agent"          # a remote A2A agent
    SUBAGENT = "subagent"    # a shared subagent spec


@dataclass(frozen=True)
class Piece:
    text: str
    author: str


@dataclass
class Revision:
    version: int
    editor: str
    content: dict
    note: str = ""


@dataclass
class Artifact:
    id: str
    kind: ArtifactKind
    owner: str
    scope: frozenset[str]              # who may use or attach it
    runs_as: RunsAs = RunsAs.INVOKER
    revisions: list[Revision] = field(default_factory=list)

    @property
    def current(self) -> Revision:
        return self.revisions[-1]

    @property
    def version(self) -> int:
        return self.current.version

    def at(self, version: int | None) -> Revision:
        if version is None:
            return self.current
        return next(r for r in self.revisions if r.version == version)

    def edit(self, editor: str, content: dict, note: str = "") -> Revision:
        rev = Revision(self.version + 1 if self.revisions else 1, editor, content, note)
        self.revisions.append(rev)
        return rev

    def authors(self, version: int | None = None) -> frozenset[str]:
        """Authors of the pieces present in a revision, plus the owner."""
        content = self.at(version).content
        found = {self.owner}
        for v in content.values():
            for item in v if isinstance(v, list) else [v]:
                if isinstance(item, Piece):
                    found.add(item.author)
        return frozenset(found)


class Registry:
    def __init__(self, directory: Directory) -> None:
        self.dir = directory
        self.items: dict[str, Artifact] = {}

    def add(self, art: Artifact) -> Artifact:
        self.items[art.id] = art
        return art

    def get(self, aid: str) -> Artifact:
        return self.items[aid]

    def can_use(self, uid: str, aid: str) -> bool:
        return uid in self.dir.expand(self.items[aid].scope)
