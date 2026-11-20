"""Mutable state for one run: documents, mail, HR rows, a virtual filesystem, logs.

The virtual filesystem holds team folders, memory files (AGENTS.md per tier) and skills
(SKILL.md per scope). Each mount has an audience scope; each file remembers who wrote it.
Every private item carries a unique canary string so leaks can be detected exactly.
A fresh World is built from the fixture for every run.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .principals import SPACE, Directory


@dataclass
class Doc:
    id: str
    owner: str
    title: str
    body: str
    readers: frozenset[str]


@dataclass
class Mail:
    id: str
    sender: str
    to: list[str]
    subject: str
    body: str

    def readers(self) -> frozenset[str]:
        return frozenset([self.sender, *self.to])


@dataclass
class HRRow:
    user: str
    salary: str
    rating: str
    notes: str


@dataclass
class Mount:
    prefix: str                 # e.g. "/team/eng/"
    audience: frozenset[str]    # scope, unexpanded (e.g. {"grp:eng"})
    label: str = ""             # human-readable name the invoker would use ("eng folder")


@dataclass
class VFile:
    content: str
    author: str


@dataclass
class Effect:
    seq: int
    tool: str
    identity: str        # whose credentials executed it
    args: dict
    audience: frozenset[str]
    allowed: bool = True
    reason: str = ""


@dataclass
class SinkRecord:
    """Anything that left the run and who can now read it (for the oracle)."""
    sink: str
    content: str
    audience: frozenset[str]


class World:
    def __init__(self, directory: Directory) -> None:
        self.dir = directory
        self.docs: dict[str, Doc] = {}
        self.mail: dict[str, Mail] = {}
        self.hr: dict[str, HRRow] = {}
        self.hr_readers_extra: frozenset[str] = frozenset()  # e.g. the HR group can read all rows
        self.mounts: list[Mount] = []
        self.files: dict[str, VFile] = {}
        self.effects: list[Effect] = []
        self.sinks: list[SinkRecord] = []
        self.remote_logs: dict[str, list[str]] = {}      # operator-owned servers/agents -> payloads
        self.canaries: dict[str, frozenset[str]] = {}    # canary string -> reader set
        self.invoker: str = ""                           # the run's invoker (set before scoring)
        self.endorsed_readers: frozenset[str] = frozenset()  # principals the invoker named this run
        self._ids = itertools.count(1)

    # ---- ids and canaries ---------------------------------------------
    def nid(self, prefix: str) -> str:
        return f"{prefix}{next(self._ids)}"

    def register_canary(self, canary: str, readers: frozenset[str]) -> str:
        self.canaries[canary] = readers
        return canary

    # ---- virtual filesystem -------------------------------------------
    def add_mount(self, prefix: str, audience: set[str] | frozenset[str], label: str = "") -> Mount:
        m = Mount(prefix if prefix.endswith("/") else prefix + "/", frozenset(audience), label)
        self.mounts.append(m)
        self.mounts.sort(key=lambda x: len(x.prefix), reverse=True)
        return m

    def mount_of(self, path: str) -> Mount | None:
        return next((m for m in self.mounts if path.startswith(m.prefix)), None)

    def readers_of_path(self, path: str) -> frozenset[str]:
        m = self.mount_of(path)
        return self.dir.expand(m.audience) if m else frozenset()

    def put_file(self, path: str, content: str, author: str) -> None:
        self.files[path] = VFile(content, author)

    # ---- other readers ------------------------------------------------
    def hr_row_readers(self, uid: str) -> frozenset[str]:
        return frozenset([uid]) | self.hr_readers_extra

    def space_readers(self) -> frozenset[str]:
        return self.dir.expand([SPACE])

    # ---- logs ---------------------------------------------------------
    def record_sink(self, sink: str, content: str, audience: frozenset[str]) -> None:
        self.sinks.append(SinkRecord(sink, content, audience))

    def record_effect(self, tool: str, identity: str, args: dict, audience: frozenset[str],
                      allowed: bool = True, reason: str = "") -> Effect:
        e = Effect(len(self.effects) + 1, tool, identity, args, audience, allowed, reason)
        self.effects.append(e)
        return e
