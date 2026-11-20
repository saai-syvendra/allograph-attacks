"""C3: instruction freshness through version pinning.

The invoker consented to particular versions of the instruction-bearing artifacts a graph
uses: the graph, its connectors and subagents (by registry version) and the skill files in
the folders it links (by content hash, since a skill can be edited in place without the graph
changing). If any of them changed since, the run asks for re-consent. If that is declined,
registry artifacts run at their consented versions and a changed skill file is withheld
(the file store keeps no history to roll back to).

Memory files are not pinned: memory is meant to change between runs, and steering through
memory is C2's job.
"""

from __future__ import annotations

import hashlib

from ..domain.artifacts import Artifact, Piece, Registry, Revision
from ..domain.world import World
from ..platform.run_context import RunContext

FILE = "file:"
TEXT = "text:"     # the skill file's text at consent time, so a re-consent prompt can show the change


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def skill_files(world: World, sources: list[str]) -> list[str]:
    return sorted(path for path in world.files for src in sources
                  if path.startswith(src) and path.endswith("SKILL.md"))


def consent_snapshot(reg: Registry, world: World, graph_id: str) -> dict[str, int | str]:
    """What the invoker approved: registry versions plus a hash of each linked skill file."""
    graph = reg.get(graph_id)
    content = graph.current.content
    pins: dict[str, int | str] = {graph.id: graph.version}
    for aid in content.get("connectors", []) + content.get("subagents", []):
        pins[aid] = reg.get(aid).version
    for path in skill_files(world, content.get("skill_sources", [])):
        pins[FILE + path] = _digest(world.files[path].content)
        pins[TEXT + path] = world.files[path].content
    return pins


def _lines(rev: Revision) -> dict[str, str]:
    """Instruction lines of a revision, each with its author (a piece's author, else the editor)."""
    out: dict[str, str] = {}
    def walk(v):
        if isinstance(v, Piece):
            for ln in v.text.splitlines():
                out.setdefault(ln.strip(), v.author)
        elif isinstance(v, str):
            for ln in v.splitlines():
                out.setdefault(ln.strip(), rev.editor)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k in ("connectors", "subagents", "agents"):     # ids, not instruction text
                    for aid in x:
                        out.setdefault(f"uses {k[:-1]} {aid}", rev.editor)
                else:
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(rev.content)
    out.pop("", None)
    return out


def _show(old: dict[str, str], new: dict[str, str]) -> list[str]:
    def clip(t):
        return t if len(t) <= 240 else t[:237] + "..."
    shown = [f'+ "{clip(t)}" (added by {a})' for t, a in new.items() if t not in old]
    shown += [f'- "{clip(t)}" (removed)' for t in old if t not in new]
    return shown


def choose_versions(rc: RunContext, artifacts: list[Artifact], pins: dict[str, int]) -> dict[str, int | None]:
    """Return the version to run for each artifact id (None = current)."""
    chosen: dict[str, int | None] = {a.id: None for a in artifacts}
    if not rc.defense.c3_pin:
        return chosen
    changed = [a for a in artifacts if a.id in pins and a.version != pins[a.id]]
    files = rc.world.files
    changed_files = [k[len(FILE):] for k, h in pins.items() if k.startswith(FILE)
                     and (k[len(FILE):] not in files or _digest(files[k[len(FILE):]].content) != h)]
    if not changed and not changed_files:
        return chosen
    diff = []
    for a in changed:
        diff.append(f"{a.id} v{pins[a.id]}->v{a.version}, published by {a.current.editor}:")
        diff += _show(_lines(a.at(pins[a.id])), _lines(a.current))
    for path in changed_files:
        if path not in files:
            diff.append(f"{path} was deleted")
            continue
        diff.append(f"{path} edited by {files[path].author}:")
        def split(text, who):
            return {ln.strip(): who for ln in text.splitlines() if ln.strip()}
        diff += _show(split(str(pins.get(TEXT + path, "")), ""), split(files[path].content, files[path].author))
    if rc.confirm("run updated artifacts:\n" + "\n".join(diff), "C3: instructions changed since you last consented"):
        return chosen
    for a in changed:
        chosen[a.id] = pins[a.id]
    for path in changed_files:
        files.pop(path, None)
    return chosen
