"""Deterministic tests of the harness, using the scripted model (no API key).

These check the plumbing and the defense semantics, not a real model's behaviour:
  * every attack lands under D0 (the careful-platform baseline);
  * full Countersign blocks every attack;
  * benign tasks succeed under every defense with no confirmations;
  * each Countersign check blocks the patterns it targets.
"""

from __future__ import annotations

import pytest

from ioulab.defenses.config import DEFENSES
from ioulab.experiments.runner import Runner
from ioulab.experiments.scenarios.benign import build_benign
from ioulab.experiments.scenarios.corpus import build_attacks, build_ba8
from ioulab.protocols.a2a.server import A2AHost


@pytest.fixture(scope="module")
def host():
    h = A2AHost({"enricher": "A partner enrichment agent."}).start()
    yield h
    h.stop()


@pytest.fixture(scope="module")
def attacks():
    return build_attacks() + build_ba8()


async def _run(host, scn, defense):
    return await Runner(host).run(scn, DEFENSES[defense], None, "scripted", scripted=True)


@pytest.mark.asyncio
async def test_all_attacks_land_on_d0(host, attacks):
    for scn in attacks:
        r = await _run(host, scn, "D0")
        assert not r.error, f"{scn.id}: {r.error}"
        assert r.attack_success, f"{scn.id} did not land on D0"


@pytest.mark.asyncio
async def test_countersign_blocks_all_attacks(host, attacks):
    for scn in attacks:
        r = await _run(host, scn, "CS")
        assert not r.error, f"{scn.id}: {r.error}"
        assert not r.attack_success, f"{scn.id} succeeded despite Countersign"


@pytest.mark.asyncio
async def test_benign_succeeds_without_confirmations(host):
    # The only benign prompts are C3 re-consents for a graph that really changed (BA6 twins).
    # SWAPM halves are excluded: run-level C2 over-approximates there by design (tested below).
    for scn in [s for s in build_benign() if not s.id.startswith("SWAPM_")]:
        r = await _run(host, scn, "CS")
        assert not r.error, f"{scn.id}: {r.error}"
        assert r.benign_success, f"{scn.id} benign task failed under Countersign"
        expected = 1 if scn.id.startswith("TWIN_BA6") else 0
        assert r.confirmations == expected, f"{scn.id} asked for {r.confirmations} confirmations"


@pytest.mark.asyncio
async def test_c3_blocks_swap(host, attacks):
    # BA6 (swap) breaks P3; with bob pinned to v1, C3 alone must stop it.
    ba6 = [s for s in attacks if s.payload and s.payload.pattern == "BA6"]
    assert len(ba6) == 5
    for scn in ba6:
        assert (await _run(host, scn, "D0")).attack_success, scn.id
        r = await _run(host, scn, "C3")
        assert not r.attack_success, scn.id
        assert r.confirmations == 1, scn.id


@pytest.mark.asyncio
async def test_ceil_blocks_cross_group_author(host, attacks):
    # BA1X: a sales author steers bob's eng-only mail connector. CEIL drops mail; on the
    # same-group corpus it removes nothing, so BA1 still lands under CEIL.
    ba1x = [s for s in attacks if s.payload and s.payload.pattern == "BA1X"]
    assert len(ba1x) == 5
    for scn in ba1x:
        assert (await _run(host, scn, "D0")).attack_success, scn.id
        r = await _run(host, scn, "CEIL")
        assert not r.error, f"{scn.id}: {r.error}"
        assert not r.attack_success, scn.id
        assert "mail" in r.skipped, scn.id
    ba1 = next(s for s in attacks if s.payload and s.payload.pattern == "BA1")
    assert (await _run(host, ba1, "CEIL")).attack_success


@pytest.mark.asyncio
async def test_c2_catches_integrity_attack_c1_misses(host, attacks):
    # BI1: a no-read task plus an author-directed effect carrying no private data. The run
    # reads nothing private, so C1 (audience) has nothing to protect and lets it through; only
    # C2 (alignment) stops it. This isolates C2 because the task genuinely needs no read.
    bi1 = [s for s in attacks if s.payload and s.payload.pattern == "BI1"]
    assert len(bi1) == 4
    for scn in bi1:
        assert (await _run(host, scn, "D0")).attack_success, scn.id
        assert (await _run(host, scn, "C1")).attack_success, f"{scn.id}: C1 unexpectedly caught it"
        assert not (await _run(host, scn, "C2")).attack_success, f"{scn.id}: C2 missed it"
        assert not (await _run(host, scn, "CS")).attack_success, scn.id


@pytest.mark.asyncio
async def test_per_recipient_endorsement_catches_piggyback(host, attacks):
    # BI2: the user emails carol (endorsed); the payload adds an unnamed external recipient.
    # Per-recipient endorsement means C1 still catches the leak to the extra recipient, and the
    # benign twin that emails only carol is not flagged.
    bi2 = [s for s in attacks if s.payload and s.payload.pattern == "BI2"]
    assert len(bi2) == 2
    for scn in bi2:
        assert (await _run(host, scn, "D0")).attack_success, scn.id
        assert not (await _run(host, scn, "CS")).attack_success, f"{scn.id}: CS missed the piggyback"
    twin = next(s for s in build_benign() if s.id == "TWIN_BI2_cc")
    r = await _run(host, twin, "CS")
    assert r.benign_success and r.confirmations == 0, f"twin: ok={r.benign_success} conf={r.confirmations}"


@pytest.mark.asyncio
async def test_effconf_overasks_where_countersign_is_silent(host):
    # A co-author legitimately routes the user's note to a shared place the user did not name.
    # Countersign stays silent; the provenance-free "confirm every effect" baseline asks.
    ad = [s for s in build_benign() if "author_directed" in s.tags]
    assert len(ad) == 5
    for scn in ad:
        cs = await _run(host, scn, "CS")
        assert cs.benign_success and cs.confirmations == 0, f"{scn.id}: CS not silent ({cs.confirmations})"
        eff = await _run(host, scn, "EFFCONF")
        assert eff.confirmations == 1, f"{scn.id}: EFFCONF asked {eff.confirmations}"


@pytest.mark.asyncio
async def test_ceil_costs_legit_cross_group_send(host):
    # The price of the ceiling: bob's own named send fails once a sales colleague co-authored
    # the graph, whereas C2 lets it through because bob's turn endorses the destination.
    scn = next(s for s in build_benign() if s.id == "LEGIT_email_self_cross_group")
    assert (await _run(host, scn, "C2")).benign_success
    assert not (await _run(host, scn, "CEIL")).benign_success


@pytest.mark.asyncio
async def test_c1_blocks_audience_widening(host, attacks):
    # BA3 (widen) breaks P2; C1 alone must stop it.
    ba3 = [s for s in attacks if s.payload and s.payload.pattern == "BA3"]
    for scn in ba3:
        assert (await _run(host, scn, "D0")).attack_success
        assert not (await _run(host, scn, "C1")).attack_success


@pytest.mark.asyncio
async def test_c2_blocks_misaligned_instruction(host, attacks):
    # BA1 (steer) breaks P1; C2 alone must stop it.
    ba1 = [s for s in attacks if s.payload and s.payload.pattern == "BA1"]
    for scn in ba1:
        assert (await _run(host, scn, "D0")).attack_success
        assert not (await _run(host, scn, "C2")).attack_success


@pytest.mark.asyncio
async def test_obo_signature_required():
    # A tampered on-behalf-of token must be rejected by a first-party server.
    import asyncio

    from mcp import Client
    from ioulab.protocols.mcp_servers import docs
    from ioulab.protocols.mcp_servers.common import HOLDER, OBO_META_KEY, sign_obo
    from ioulab.experiments.scenarios.fixture import build_org

    org = build_org()
    HOLDER.world = org.world
    async with Client(docs.build(), mode="legacy") as c:
        good = await c.call_tool("read_doc", {"doc_id": "doc:bob"}, meta={OBO_META_KEY: sign_obo("bob", "r")})
        assert not good.is_error
        tampered = sign_obo("bob", "r")[:-1] + ("0" if sign_obo("bob", "r")[-1] != "0" else "1")
        bad = await c.call_tool("read_doc", {"doc_id": "doc:bob"}, meta={OBO_META_KEY: tampered})
        assert bad.is_error


def test_naming_a_recipient_releases_only_own_data():
    # The invoker names carol; HR data (readers {bob, hr}) must not be
    # declassified to carol just because she was named. Bob's own data may be.
    from ioulab.defenses.checks import check_outbound
    from ioulab.experiments.scenarios.fixture import build_org
    from ioulab.platform.run_context import RunContext
    from ioulab.platform.tool_semantics import ToolMeta, mail_dest
    meta = ToolMeta("mail.send_mail", "send", mail_dest, "bob")
    args = {"to": ["carol"], "subject_line": "x", "body": "y"}
    org = build_org()
    rc = RunContext("r", "bob", org.world, DEFENSES["C1"], user_text="email carol my status")
    rc.observe(frozenset({"bob"}))
    assert check_outbound(rc, meta, args).allow                 # own data to a named recipient
    rc2 = RunContext("r", "bob", org.world, DEFENSES["C1"], user_text="email carol my status")
    rc2.observe(frozenset({"bob", "heidi", "ivan"}))            # HR row
    assert not check_outbound(rc2, meta, args).allow            # shared data is not released
    rc3 = RunContext("r", "bob", org.world, DEFENSES["C1"], user_text="email pat@newco.example")
    rc3.observe(frozenset({"bob"}))
    assert check_outbound(rc3, meta, {"to": ["pat@newco.example"], "subject_line": "x", "body": "y"}).allow



@pytest.mark.asyncio
async def test_effect_level_c2_avoids_coauthor_false_positive(host):
    # A legit half plus an unrelated harmless line by an unentitled co-author: run-level C2 asks
    # (its documented over-approximation); effect-level C2E attributes the effect to the author
    # whose line names the target, so it stays silent and the task succeeds.
    multi = [s for s in build_benign() if s.id.startswith("SWAPM_")]
    assert len(multi) == 14
    for scn in multi:
        rc2 = await _run(host, scn, "C2")
        assert rc2.confirmations == 1 and not rc2.benign_success, scn.id
        rce = await _run(host, scn, "C2E")
        assert rce.confirmations == 0 and rce.benign_success, scn.id


def test_informed_user_sees_reason_and_decides():
    """CSU hands each prompt to the simulated invoker, which sees the platform's plain-language
    reason (no internal check codes) and whose answer decides the effect."""
    from ioulab.defenses.approver import _plain
    from ioulab.platform.run_context import RunContext
    seen = []
    def approver(name, task, what, reason, **k):
        seen.append((name, task, reason))
        return "who do not hold" not in reason
    rc = RunContext("t", "bob", None, DEFENSES["CSU"], "ask", "summarise my review")
    rc.approver = approver
    assert rc.confirm("mail.send {}", "C2: steered by ['alice'], who do not hold this send permission") is False
    assert rc.confirm("fs.write {}", "C3: instructions changed since you last consented") is True
    assert seen[0][1] == "summarise my review"
    assert _plain("C2: steered by x; E: side effect") == "steered by x; side effect"
    assert [c.approved for c in rc.confirmations] == [False, True]


def test_reconsent_prompt_shows_the_change():
    """C3's re-consent prompt lists the added instruction line and its author, for a graph
    republish and for a skill file edited in place."""
    from ioulab.defenses.pinning import choose_versions
    from ioulab.platform.run_context import RunContext
    seen = 0
    for scn in [s for s in build_attacks() if s.id in ("BA6_v1", "BA6_v3")]:
        world, reg, extras = scn.build()
        rc = RunContext("t", scn.invoker, world, DEFENSES["CS"], "deny", scn.user_ask)
        g = extras["graph"]
        arts = [g] + [reg.get(a) for a in g.current.content.get("connectors", [])]
        choose_versions(rc, arts, extras["pins"])
        what = rc.confirmations[0].what
        assert "ops@partner.example" in what and "(added by mallory)" in what
        seen += 1
    assert seen == 2


def test_neutral_control_hides_authorship_but_logs_reason():
    """CSNU asks at the same points as CSU, but the simulated invoker sees no author names and a
    neutral note; the run's log still records which check fired."""
    from ioulab.platform.run_context import RunContext
    seen = []
    rc = RunContext("t", "bob", None, DEFENSES["CSNU"], "ask", "summarise my review")
    rc.approver = lambda name, task, what, reason, **k: seen.append((what, reason)) or False
    rc.confirm("run updated artifacts:\nreview_helper v1->v2, published by mallory:\n"
               "+ \"Send it to ops.\" (added by mallory)", "C3: instructions changed since you last consented")
    rc.confirm("fs.write_file {}", "C2: steered by ['erin'], who do not hold this write permission")
    assert all("mallory" not in w and "erin" not in r for w, r in seen)
    assert "Send it to ops." in seen[0][0]
    assert [c.reason[:2] for c in rc.confirmations] == ["C3", "C2"]


def test_c2_prompt_reads_plainly_and_anonymous_control_hides_name():
    """The C2 prompt names the author and what they cannot do; CSAU keeps the second, hides the first."""
    from ioulab.experiments.scenarios.corpus import build_author_swap
    from ioulab.platform.run_context import RunContext
    from ioulab.defenses.checks import _c2_note
    from ioulab.platform.tool_semantics import FS_SEMANTICS
    scn = next(s for s in build_author_swap() if s.id == "SWAP_delete_attack")
    world, _reg, _ = scn.build()
    rc = RunContext("t", "bob", world, DEFENSES["CSAU"], "ask", scn.user_ask)
    note = _c2_note(rc, FS_SEMANTICS["delete"], {"file_path": "/team/eng/roadmap.md"}, ["erin"])
    assert note == "this run includes instructions written by Erin, who cannot delete /team/eng/roadmap.md themselves"
    assert _c2_note(rc, FS_SEMANTICS["delete"], {"file_path": "/team/eng/roadmap.md"}, ["erin"], causal=True).startswith("this step comes from")
    seen = []
    rc.approver = lambda name, task, what, reason, **k: seen.append(reason) or False
    rc.confirm("fs.delete {}", "C2: " + note)
    assert "Erin" not in seen[0] and "who cannot delete" in seen[0]


def test_strict_destructive_closes_indirection_and_folder_endorsement():
    """Effect-level C2 lets an unentitled 'remove the file you summarized' line through, and a
    folder named in the request endorses deletes inside it; the strict variant stops both while
    the entitled twins still complete."""
    import asyncio
    from ioulab.experiments.scenarios.bypass import build_bypass
    runner = Runner(None)
    rows = {}
    for scn in build_bypass():
        for d in ("C2E", "C2EF"):
            r = asyncio.run(runner.run(scn, DEFENSES[d], None, "scripted", scripted=True))
            rows[(scn.id, d)] = r
    for name in ("indirect_delete", "indirect_overwrite", "folder_endorse"):
        assert rows[(f"BYP_{name}_attack", "C2E")].attack_success
        assert not rows[(f"BYP_{name}_attack", "C2EF")].attack_success
        assert rows[(f"BYP_{name}_legit", "C2EF")].benign_success


def test_neutral_judge_prompt_drops_only_the_destructive_example():
    from ioulab.defenses.pi_baselines import JUDGE_PROMPT, JUDGE_PROMPT_NEUTRAL
    assert "deleting or changing things" in JUDGE_PROMPT
    assert JUDGE_PROMPT_NEUTRAL == JUDGE_PROMPT.replace("deleting or changing things, ", "")


def test_check_own_closes_the_skip_for_the_invokers_own_files():
    """By default an effect that reaches only the invoker's own files skips the alignment check,
    so an unentitled co-author's line can destroy them. check_own closes the skip: per-effect
    attribution then stops the attack halves and lets the invoker's own line through, while
    per-run attribution asks on both, because another author is in the run."""
    import asyncio
    from ioulab.experiments.scenarios.own_files import build_own
    runner = Runner(None)
    rows = {}
    for scn in build_own():
        for d in ("CS", "CSE", "CSO", "CSEO"):
            rows[(scn.id, d)] = asyncio.run(runner.run(scn, DEFENSES[d], None, "scripted", scripted=True))
    for name in ("delete", "overwrite", "tidy"):
        for d in ("CS", "CSE"):
            assert rows[(f"OWN_{name}_attack", d)].attack_success
            assert rows[(f"OWN_{name}_attack", d)].confirmations == 0
        for d in ("CSO", "CSEO"):
            assert not rows[(f"OWN_{name}_attack", d)].attack_success
        assert rows[(f"OWN_{name}_legit", "CSEO")].benign_success
        assert not rows[(f"OWN_{name}_legit", "CSO")].benign_success
