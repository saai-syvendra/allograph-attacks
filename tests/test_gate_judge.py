"""The effect-time judge settings (C2J, C2A) with a deterministic stand-in for the model.

C2J lets a judge decide at the effect, given the instruction segments, their authors and whether
each author holds the permission. C2A lets the judge pick the segments that caused the effect
and leaves the decision to the lookup. These tests check the wiring and the fail-closed paths.
"""

from __future__ import annotations

import pytest

from ioulab.defenses.config import DEFENSES
from ioulab.defenses.gate_judge import GateView
from ioulab.experiments.runner import Runner
from ioulab.experiments.scenarios.corpus import build_author_swap
from ioulab.protocols.a2a.server import A2AHost


@pytest.fixture(scope="module")
def host():
    h = A2AHost({"enricher": "A partner enrichment agent."}).start()
    yield h
    h.stop()


class RuleJudge:
    """Applies the alignment rule to what it is shown: ASK when any listed author lacks it."""

    def __init__(self, pick="all"):
        self.pick, self.views = pick, []

    def decide(self, view: GateView):
        self.views.append(view)
        return any(not ok for _, ok in view.facts), "rule"

    def attribute(self, view: GateView):
        self.views.append(view)
        if self.pick == "all":
            return {n for n, _, _ in view.segments}, "all"
        if self.pick == "none":
            return set(), "NONE"
        return None, "???"          # an answer that cannot be parsed


def _pair(name="del_roadmap"):
    scns = {s.id: s for s in build_author_swap()}
    names = sorted({s.tags[-1] for s in scns.values()})
    n = name if name in names else names[0]
    return scns[f"SWAP_{n}_legit"], scns[f"SWAP_{n}_attack"]


async def _run(host, scn, defense, judge):
    return await Runner(host, gate_judge=judge).run(scn, DEFENSES[defense], None, "scripted", scripted=True)


@pytest.mark.asyncio
async def test_judge_at_the_gate_separates_a_pair(host):
    legit, attack = _pair()
    judge = RuleJudge()
    ra = await _run(host, attack, "C2J", judge)
    assert not ra.error, ra.error
    assert not ra.attack_success and ra.confirmations >= 1
    rl = await _run(host, legit, "C2J", judge)
    assert not rl.error, rl.error
    assert rl.benign_success and rl.confirmations == 0
    # the judge saw the author's line, the concrete action and a yes/no fact for each author
    view = judge.views[0]
    assert view.segments and view.action and len(view.facts) >= 2
    assert ra.gate_log and rl.gate_log


@pytest.mark.asyncio
async def test_llm_attribution_feeds_the_lookup(host):
    legit, attack = _pair()
    # every segment charged: the same decision as run-level C2
    ra = await _run(host, attack, "C2A", RuleJudge("all"))
    assert not ra.error, ra.error
    assert not ra.attack_success and ra.confirmations >= 1
    rl = await _run(host, legit, "C2A", RuleJudge("all"))
    assert rl.benign_success and rl.confirmations == 0
    # no segment charged: the lookup has nobody to object to, so the attack goes through
    rn = await _run(host, attack, "C2A", RuleJudge("none"))
    assert rn.attack_success and rn.confirmations == 0
    # an unparseable answer fails closed to every author
    rx = await _run(host, attack, "C2A", RuleJudge("garbled"))
    assert not rx.attack_success and rx.confirmations >= 1


@pytest.mark.asyncio
async def test_gate_settings_need_a_judge(host):
    _, attack = _pair()
    r = await Runner(host).run(attack, DEFENSES["C2J"], None, "scripted", scripted=True)
    assert "needs a gate judge" in r.error
