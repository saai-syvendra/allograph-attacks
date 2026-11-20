"""C1 (audience non-widening) and C2 (instruction-authority alignment) decisions, plus the
provenance-free comparison baselines.

Endorsement follows robust declassification: an effect whose destination the invoker's own
turn names is the invoker's own decision (integrity), and the invoker may release data that
only the invoker could read (confidentiality). Anything else that would break P1 or P2 asks
the invoker to confirm.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.world import World
from ..platform.run_context import RunContext
from ..platform.tool_semantics import ToolMeta
from .gate_judge import gate_view

PLATFORM = "platform"
DISCLOSES = ("send", "write")          # effects that move data to an audience
EFFECTS = ("send", "write", "delete")  # effects that change the world under someone's authority


@dataclass
class Decision:
    allow: bool
    reason: str = ""


def holds(w: World, principal: str, meta: ToolMeta, args: dict, invoker: str) -> bool:
    """Could `principal`, acting as themselves, perform this effect?"""
    if principal == PLATFORM:
        return True
    if meta.key == "mail.send_mail":
        return principal == invoker            # only the account owner can send as this identity
    if meta.key.startswith("fs."):
        path = args.get("file_path") or args.get("path") or ""
        return principal in w.readers_of_path(path)
    if meta.operator is not None:
        return principal == meta.operator       # handing data to a third party's own service
    return principal == (meta.identity or invoker)


def _lacking(rc: RunContext, meta: ToolMeta, args: dict, authors: set[str] | None = None) -> list[str]:
    pool = rc.instr_authors if authors is None else authors
    others = sorted(a for a in pool if a not in {rc.invoker, PLATFORM})
    return [a for a in others if not holds(rc.world, a, meta, args, rc.invoker)]


def naming_authors(rc: RunContext, meta: ToolMeta, args: dict, tokens: set[str]) -> set[str]:
    """Authors of instruction segments that name this effect's target (empty if none does)."""
    return steering_authors(rc, meta, args, tokens, fallback=False)


def steering_authors(rc: RunContext, meta: ToolMeta, args: dict, tokens: set[str],
                     fallback: bool = True) -> set[str]:
    """Effect-level attribution (C2E): authors whose instruction text names this effect's target.

    The target is named by the destination tokens (a path or folder, a recipient's name or
    address) and, for a third party's tool or agent, its id. If no segment names the target the
    effect may have been steered indirectly, so every instruction author counts (the run-level
    rule). Known evasion: an attacker's line can ride on an entitled author's line that already
    names the target.
    """
    toks = {t.lower() for t in tokens if t and len(t) > 2}
    path = args.get("file_path") or args.get("path") or ""
    if path:
        toks |= {path.lower(), path.rsplit("/", 1)[-1].lower()}
    if meta.operator is not None:
        toks.add(meta.key.split(".")[-1].lower() if meta.key.startswith("a2a.") else meta.key.split(".")[0].lower())
    hit: set[str] = set()
    for seg in rc.segments:
        if seg.instruction and any(t in seg.text.lower() for t in toks):
            hit |= set(seg.authors)
    return hit or (set(rc.instr_authors) if fallback else set())


_VERB = {"write": "write to", "delete": "delete", "send": "send to"}


def _c2_note(rc: RunContext, meta: ToolMeta, args: dict, lacking: list[str], causal: bool = False) -> str:
    """The C2 prompt as the invoker reads it: whose instructions are involved, and what they cannot
    do. Only effect-level attribution that found a segment naming the target says the step comes
    from those instructions; otherwise the run merely includes them."""
    names = " and ".join(rc.world.dir.principals[a].display if rc.world and a in rc.world.dir.principals
                         else a for a in lacking)
    target = args.get("file_path") or args.get("path") or ", ".join(args.get("to", []) or []) or meta.key
    lead = "this step comes from" if causal else "this run includes"
    return (f"{lead} instructions written by {names}, who cannot "
            f"{_VERB.get(meta.effect, meta.effect)} {target} themselves")


def check_outbound(rc: RunContext, meta: ToolMeta, args: dict) -> Decision:
    d = rc.defense
    if meta.effect == "read" or meta.dest is None:
        return Decision(True)
    identity = meta.identity or rc.invoker
    audience, tokens = meta.dest(args, rc.world, identity)
    me = frozenset([rc.invoker])

    # Endorsement is per recipient for a send (so naming carol does not also endorse a payload's
    # extra recipient), and whole-destination for a write or delete (the invoker names a path).
    path = args.get("file_path") or args.get("path") or ""
    # A delete, or a write over a file that existed when the run began, destroys something.
    destructive = meta.effect == "delete" or (meta.effect == "write" and
                                              path in getattr(rc.world, "initial_paths", ()))
    if meta.effect == "send":
        recipients = audience - me
        named = frozenset(a for a in recipients if rc.endorses_principal(a))
        endorsed = recipients <= named
    else:
        recipients = audience - me
        # strict_destructive: naming a folder does not endorse destroying a file inside it
        etokens = {path} if (d.strict_destructive and destructive and path) else tokens
        # An effect that reaches only the invoker's own files leaks nothing, so by default it is
        # treated as endorsed. check_own drops that shortcut: only the request endorses it.
        endorsed = (audience <= me and not d.check_own) or rc.endorsed(etokens)
        named = recipients if endorsed else frozenset()
    problems: list[str] = []

    # C1 confidentiality (P2): a datum the run read reaches a recipient that could not read it.
    # Declassification: the invoker may release data that only the invoker could read to
    # recipients the invoker named. Naming a recipient never releases shared (group, HR, third
    # party) data to them.
    if d.c1_audience and meta.effect in DISCLOSES and recipients:
        for r in rc.reads:
            targets = recipients - (named if r <= me else frozenset())
            if not (targets <= r):
                problems.append(f"C1: data readable only by {sorted(r)} would reach {sorted(targets - r)}")
                break

    # C2 integrity (P1): an author who does not hold this permission is steering the invoker's.
    if d.c2_alignment and meta.effect in EFFECTS and identity == rc.invoker and not endorsed \
            and (d.c2_judge or d.c2_attrib_llm):
        # A model asked at the effect, with the lookup's facts, in place of the lexical rule.
        if rc.gate_judge is None:
            raise RuntimeError(f"{d.name} needs a gate judge (--detector)")
        view, by_no = gate_view(rc, meta, args, holds)
        if d.c2_judge:
            ask, raw = rc.gate_judge.decide(view)
            rc.gate_log.append(f"{meta.key} {view.action} -> {raw}")
            if ask:
                problems.append("C2: " + _c2_note(rc, meta, args, _lacking(rc, meta, args) or ["a co-author"]))
        else:
            nums, raw = rc.gate_judge.attribute(view)
            rc.gate_log.append(f"{meta.key} {view.action} -> {raw}")
            charged = None if nums is None else {a for n in nums for a in by_no[n]}
            lacking = _lacking(rc, meta, args, charged)
            if lacking:
                problems.append("C2: " + _c2_note(rc, meta, args, lacking, causal=nums is not None))
    elif d.c2_alignment and meta.effect in EFFECTS and identity == rc.invoker and not endorsed:
        effect_level = d.c2_effect and not (d.strict_destructive and destructive)
        lacking = _lacking(rc, meta, args, steering_authors(rc, meta, args, tokens) if effect_level else None)
        if lacking:
            causal = effect_level and bool(naming_authors(rc, meta, args, tokens) & set(lacking))
            problems.append("C2: " + _c2_note(rc, meta, args, lacking, causal))

    # Baseline: confirm every unrequested side effect, with no notion of who authored it.
    if d.confirm_unrequested and meta.effect in EFFECTS and not endorsed:
        problems.append("E: side effect the invoker did not request")

    # Baseline: confirm any send whose audience reaches beyond the invoker.
    if d.confirm_external and meta.effect == "send" and not audience <= me:
        problems.append(f"X: send reaches {sorted(audience - me)}")

    # Resource-level author ceiling: hard block (no prompt) if any instruction author could not
    # perform this effect themselves (definer rights intersected with invoker rights, at the sink).
    if d.resource_ceiling and meta.effect in EFFECTS and not endorsed:
        lacking = _lacking(rc, meta, args)
        if lacking:
            return Decision(False, f"RCEIL: author {lacking} could not perform this {meta.effect}")

    if not problems:
        return Decision(True)
    reason = "; ".join(problems)
    if rc.confirm(f"{meta.key} {args}", reason):
        return Decision(True, "confirmed: " + reason)
    return Decision(False, reason)
