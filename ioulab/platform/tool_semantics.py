"""What the platform knows about each tool: its effect and where its output goes.

Countersign needs, for every outbound call, the audience that will be able to read what
leaves the run and the words an invoker would use to name that destination (to tell an
invoker-endorsed disclosure from one steered by someone else).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..domain.world import World

DestFn = Callable[[dict, World, str], tuple[frozenset[str], set[str]]]


@dataclass(frozen=True)
class ToolMeta:
    key: str                         # e.g. "mail.send_mail", "fs.write_file", "a2a.planner"
    effect: str                      # read | write | send | delete
    dest: DestFn | None = None       # (audience, naming tokens) for outbound calls
    identity: str = ""               # whose credentials execute it (filled at attach time)
    operator: str | None = None      # third party who receives the arguments, if any


def mail_dest(args: dict, w: World, caller: str):
    tokens: set[str] = set()
    rcpt = []
    for a in args.get("to", []) or []:
        r = w.dir.resolve_address(a)
        rcpt.append(r)
        tokens |= w.dir.names_of(r) | {a.lower()}
    return frozenset([caller, *rcpt]), tokens


def path_dest(args: dict, w: World, caller: str):
    path = args.get("file_path") or args.get("path") or ""
    m = w.mount_of(path)
    tokens = {path.lower()}
    if m is not None:
        tokens |= {m.prefix.lower().rstrip("/"), m.label.lower()} - {""}
    return w.readers_of_path(path), tokens


def operator_dest(operator: str, label: str) -> DestFn:
    def _dest(args: dict, w: World, caller: str):
        return frozenset([operator]), {label.lower()} | w.dir.names_of(operator)
    return _dest


MCP_SEMANTICS: dict[str, tuple[str, DestFn | None]] = {
    "docs.search_docs": ("read", None),
    "docs.read_doc": ("read", None),
    "mail.list_inbox": ("read", None),
    "mail.read_mail": ("read", None),
    "mail.send_mail": ("send", mail_dest),
    "hrdb.get_employee": ("read", None),
}

# deepagents built-in filesystem tools, backed by the platform VFS
FS_SEMANTICS: dict[str, ToolMeta] = {
    "ls": ToolMeta("fs.ls", "read"),
    "read_file": ToolMeta("fs.read_file", "read"),
    "glob": ToolMeta("fs.glob", "read"),
    "grep": ToolMeta("fs.grep", "read"),
    "write_file": ToolMeta("fs.write_file", "write", path_dest),
    "edit_file": ToolMeta("fs.edit_file", "write", path_dest),
    "delete": ToolMeta("fs.delete", "delete", path_dest),
}
