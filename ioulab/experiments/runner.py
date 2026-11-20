"""Run one scenario under one defense with one model, and score it exactly.

A run:
  1. builds a fresh world + registry from the scenario and binds the world to the servers;
  2. for A2A scenarios, sets the remote agents' per-run replies;
  3. assembles the shared graph for the invoker and invokes it;
  4. for BA4, runs the memory consolidation job afterwards;
  5. for BA8, builds replay views for the privileged viewer;
  6. scores leaks/effects with the exact oracle and records confirmations, pi-flags, overhead.

The same code path runs the scripted model (deterministic tests) and real models.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from langchain_core.callbacks import get_usage_metadata_callback

from ..defenses.config import DEFENSES, Defense
from ..defenses.approver import llm_approver
from ..defenses.gate_judge import LLMGateJudge
from ..defenses.pi_baselines import NEUTRAL_PROMPT, llm_detector
from ..llm.factory import text_of
from ..memory.consolidation import consolidate
from ..platform.assembly import Assembler
from ..platform.mcp_proxy import MCPProxy
from ..platform.run_context import RunContext
from ..protocols.a2a.server import A2AHost, Behaviors
from ..protocols.mcp_servers.common import HOLDER
from ..replay.log import replay_views
from .oracle import replay_leaks, sink_leaks
from .scenarios.corpus import benign_plan
from .scenarios.schema import Scenario


@dataclass
class RunResult:
    scenario: str
    kind: str
    pattern: str
    variant: str
    defense: str
    model: str
    repeat: int
    attack_success: bool = False
    benign_success: bool | None = None
    confirmations: int = 0
    confirmations_approved: int = 0
    pi_flagged: int = 0
    effects: int = 0
    blocked_effects: int = 0
    attached: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)   # top-level tool calls, in order
    leaks: list[str] = field(default_factory=list)   # "canary->sink" for every unauthorised flow
    sinks: list[str] = field(default_factory=list)   # "sink | audience | content" for everything that left
    effects_log: list[str] = field(default_factory=list)  # "tool identity allow args" for every effect
    confirm_log: list[str] = field(default_factory=list)  # the reason text of each confirmation asked
    pi_flag_locs: list[str] = field(default_factory=list) # where the PI detector flagged text
    gate_log: list[str] = field(default_factory=list)     # the gate judge's answer for each effect (C2J, C2A)
    code_version: str = ""                                # hash of the harness code that produced it
    final: str = ""                                   # the agent's last message (truncated)
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    served_models: list[str] = field(default_factory=list)  # models the provider says answered
    detector_model: str = ""                              # the PI/PIA judge, when one ran
    detector_input_tokens: int = 0
    detector_output_tokens: int = 0
    error: str = ""


class Runner:
    def __init__(self, a2a_host: A2AHost | None, detector_model: Any | None = None,
                 user_model: Any | None = None, detector_name: str = "", gate_judge: Any | None = None) -> None:
        self.a2a = a2a_host
        self.detector_name = detector_name
        self.detector = llm_detector(detector_model) if detector_model is not None else None
        self.approver = llm_approver(user_model) if user_model is not None else None
        # the gate judge (C2J, C2A) uses the detector's model unless a test injects its own
        self.gate_judge = gate_judge or (LLMGateJudge(detector_model) if detector_model is not None else None)

    async def run(self, scn: Scenario, defense: Defense, model: Any, model_name: str,
                  repeat: int = 0, confirm_policy: str = "deny", scripted: bool = False) -> RunResult:
        pattern = scn.payload.pattern if scn.payload else (scn.tags[0] if scn.tags else "")
        variant = scn.payload.variant if scn.payload else (scn.tags[-1] if scn.tags else "")
        r = RunResult(scn.id, scn.kind, pattern, variant, defense.name, model_name, repeat)
        t0 = time.time()
        with get_usage_metadata_callback() as usage:
            await self._run(scn, defense, model, repeat, confirm_policy, scripted, r)
        # The callback keys usage by model name. When the detector is a different model from the
        # agent, its tokens go to the detector fields so each is priced correctly.
        # Providers report the model that served the call (an alias may resolve to a newer model),
        # so the two are told apart by family, which is enough when they come from different ones.
        family = {"google": "gemini", "google_genai": "gemini", "gemini": "gemini", "anthropic": "claude"}
        det = family.get(self.detector_name.partition(":")[0], "")
        agent = family.get(model_name.partition(":")[0], "")
        for name, u in usage.usage_metadata.items():
            if det and det != agent and name.startswith(det):
                r.detector_model = name
                r.detector_input_tokens += u.get("input_tokens", 0)
                r.detector_output_tokens += u.get("output_tokens", 0)
            else:
                r.input_tokens += u.get("input_tokens", 0)
                r.output_tokens += u.get("output_tokens", 0)
                r.served_models = sorted(set(r.served_models) | {name})
        r.latency_ms = int((time.time() - t0) * 1000)
        return r

    async def _run(self, scn: Scenario, defense: Defense, model: Any, repeat: int,
                   confirm_policy: str, scripted: bool, r: RunResult) -> None:
        try:
            world, reg, extras = scn.build()
            HOLDER.world = world
            world.initial_paths = frozenset(world.files)    # what an overwrite would destroy
            NEUTRAL_PROMPT.set(defense.pi_neutral_prompt)
            if "a2a_reply" in extras and self.a2a is not None:
                for aid, text in extras["a2a_reply"].items():
                    Behaviors.by_id[aid] = Behaviors.by_id.get(aid)
                    from ..protocols.a2a.server import RemoteAgentBehavior
                    Behaviors.by_id[aid] = RemoteAgentBehavior(owner=reg.get(aid).owner, reply=text)
            rc = RunContext(f"{scn.id}-{defense.name}-{repeat}", scn.invoker, world, defense,
                            "approve" if defense.approve_all else "ask" if defense.informed_user else confirm_policy,
                            scn.user_ask)
            if defense.informed_user:
                if self.approver is None and not scripted:
                    raise RuntimeError(f"{defense.name} needs --user-model (or --detector)")
                rc.approver = self.approver or (lambda *a, **k: False)
            rc.gate_judge = self.gate_judge
            use_model = model if not scripted else self._scripted_for(scn)
            asm_model = use_model
            assembler = Assembler(reg, self.a2a, self.detector)
            async with MCPProxy(rc, {}, self.detector) as proxy:
                asm = await assembler.build(rc, scn.graph_id, asm_model, proxy, pins=extras.get("pins"))
                state = await asm.agent.ainvoke({"messages": [{"role": "user", "content": scn.user_ask}]},
                                                {"recursion_limit": 50})
                r.attached, r.skipped = asm.attached, asm.skipped
                msgs = state.get("messages", []) if isinstance(state, dict) else []
                r.calls = [tc["name"] for m in msgs for tc in (getattr(m, "tool_calls", None) or [])]
                if msgs:
                    r.final = text_of(msgs[-1].content)[:400]

            if "consolidate_user" in extras:
                await consolidate(rc, _NoneMemModel() if scripted else use_model,
                                  extras["consolidate_user"], extras.get("consolidation_policy"), self.detector)

            world.invoker = scn.invoker
            world.endorsed_readers = frozenset(pid for pid in world.dir.principals
                                               if rc.endorses_principal(pid))
            r.leaks = sorted({f"{lk.canary}->{lk.sink}" for lk in sink_leaks(world)})
            # full evidence, so goals can be re-applied offline without a re-run
            r.sinks = [f"{sk.sink} | {sorted(sk.audience)} | {sk.content}" for sk in world.sinks]
            r.effects_log = [f"{e.tool} as {e.identity} allow={e.allowed} {e.args}" for e in world.effects]
            r.confirm_log = [c.reason for c in rc.confirmations]
            r.pi_flag_locs = list(rc.pi_flags)
            r.gate_log = list(rc.gate_log)
            if scn.viewers:
                views = replay_views(rc, scn.viewers)
                r.attack_success = bool(replay_leaks(world, views))
            elif scn.goal is not None:
                r.attack_success = scn.goal(world)
            if scn.kind == "benign":
                no_leak = not sink_leaks(world)
                task_ok = scn.benign_check(world) if scn.benign_check is not None else True
                r.benign_success = bool(task_ok and no_leak)

            r.confirmations = len(rc.confirmations)
            r.confirmations_approved = sum(1 for c in rc.confirmations if c.approved)
            r.pi_flagged = len(rc.pi_flags)
            r.effects = len(world.effects)
            r.blocked_effects = sum(1 for e in world.effects if not e.allowed)
        except Exception as e:  # noqa: BLE001  - record and continue the matrix
            while isinstance(e, BaseExceptionGroup) and e.exceptions:   # surface the real cause
                e = e.exceptions[0]
            r.error = f"{type(e).__name__}: {e}"[:300]

    def _scripted_for(self, scn: Scenario):
        from .scenarios.corpus import _compliant_plan, relay_policy, swap_gate
        from .scenarios.benign import legit_plan
        from .scenarios.schema import Channel
        from ..llm.scripted import ScriptedChatModel
        if scn.scripted_policy is not None:
            return ScriptedChatModel(policy=scn.scripted_policy())
        if scn.id.startswith("LEGIT_"):
            policy = legit_plan(scn.plan_key)
        elif scn.kind == "benign" or scn.payload is None:
            policy = benign_plan()
        elif scn.payload.channel == Channel.SUBAGENT:
            policy = relay_policy(scn.payload)
        else:
            policy = _compliant_plan(scn.payload)
            if scn.payload.pattern == "BA6":
                policy = swap_gate(scn.payload, policy, benign_plan())
        return ScriptedChatModel(policy=policy)


class _NoneMemModel:
    """Scripted consolidation model: promotes the user's memory verbatim (worst case)."""

    async def ainvoke(self, prompt: str) -> Any:
        import re
        m = re.search(r"MEMORY FILE OF \w+:\n(.*)", prompt, re.S)
        text = m.group(1).strip() if m else ""

        class _R:
            content = text or "NONE"
        return _R()
