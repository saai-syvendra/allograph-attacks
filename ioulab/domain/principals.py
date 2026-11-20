"""Principals, scopes and reader sets.

A Scope is a set of principal ids (users, groups, the space, external parties); a reader set
is that scope expanded to concrete principals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

SPACE = "space:main"


class Kind(str, Enum):
    USER = "user"
    GROUP = "group"
    SPACE = "space"
    EXTERNAL = "external"


@dataclass(frozen=True)
class Principal:
    id: str
    kind: Kind
    display: str = ""
    email: str = ""


class Directory:
    """Users, groups and the space. Resolves scopes to reader sets."""

    def __init__(self) -> None:
        self.principals: dict[str, Principal] = {}
        self.members: dict[str, set[str]] = {}  # group/space id -> user ids
        self.org_admin: str | None = None
        self.space_manager: str | None = None

    def add_user(self, uid: str, display: str = "", email: str = "") -> None:
        self.principals[uid] = Principal(uid, Kind.USER, display or uid, email or f"{uid}@acme.example")
        self.members.setdefault(SPACE, set()).add(uid)
        self.principals.setdefault(SPACE, Principal(SPACE, Kind.SPACE, "Acme space"))

    def add_group(self, gid: str, users: Iterable[str], display: str = "") -> None:
        self.principals[gid] = Principal(gid, Kind.GROUP, display or gid)
        self.members[gid] = set(users)

    def add_external(self, xid: str, display: str = "", email: str = "") -> None:
        self.principals[xid] = Principal(xid, Kind.EXTERNAL, display or xid, email)

    @property
    def users(self) -> list[str]:
        return [p.id for p in self.principals.values() if p.kind == Kind.USER]

    def expand(self, scope: Iterable[str]) -> frozenset[str]:
        """Expand a scope to the concrete principals (users or externals) who can read."""
        out: set[str] = set()
        for pid in scope:
            if pid in self.members:
                out |= self.members[pid]
            else:
                out.add(pid)
        return frozenset(out)

    def groups_of(self, uid: str) -> list[str]:
        return [g for g, m in self.members.items() if uid in m and g != SPACE]

    def resolve_address(self, addr: str) -> str:
        """Map an e-mail address or name to a principal id; unknown addresses become externals."""
        a = addr.strip().lower()
        for p in self.principals.values():
            if a in {p.id.lower(), p.email.lower(), p.display.lower()}:
                return p.id
        return f"ext:{a}"

    def names_of(self, pid: str) -> set[str]:
        p = self.principals.get(pid)
        if not p:
            return {pid.lower()}
        return {s.lower() for s in (p.id, p.display, p.email) if s}
