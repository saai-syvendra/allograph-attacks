"""Combined tables for the paper, built from the run logs.

Each section names the run it reads, so no run is counted twice. The last section,
"Numbers quoted in the text", holds the figures the paper states in prose.

    python3 scripts/extended_tables.py > runs/extended.md
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]
LEAKY = {"TWIN_BA2_v5", "TWIN_BA7_v2", "TWIN_BA7_v4"}
SEPARATE = {"BA4", "BA8", "SWAP"}


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in open(RUNS / f"{name}.jsonl")]


def pick(rows, model, defense):
    return [r for r in rows if r["model"].endswith(model) and r["defense"] == defense and not r["error"]]


def boot(groups: list[list[int]], n: int = 4000, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    st = []
    for _ in range(n):
        pk = [groups[rng.randrange(len(groups))] for _ in groups]
        st.append(sum(map(sum, pk)) / sum(map(len, pk)))
    st.sort()
    return st[int(0.025 * n)], st[int(0.975 * n)]


def rate_ci(rows, pred, key=lambda r: r["scenario"]):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(1 if pred(r) else 0)
    gs = list(g.values())
    if not gs:
        return float("nan"), float("nan"), float("nan")
    lo, hi = boot(gs)
    return sum(map(sum, gs)) / sum(map(len, gs)), lo, hi


def pairs(rows) -> dict:
    """(pair, repeat) -> 1 if the legit half succeeded and the attack half failed."""
    x = {}
    for r in rows:
        if r["scenario"].startswith("SWAP_"):
            name, half = r["scenario"][5:].rsplit("_", 1)
            x[(name, r["repeat"], half)] = r
    return {(n, rep): int(bool(r["benign_success"]) and not x[(n, rep, "attack")]["attack_success"])
            for (n, rep, h), r in x.items() if h == "legit" and (n, rep, "attack") in x}


def halves(rows, half):
    return [r for r in rows if r["scenario"].startswith("SWAP_") and r["scenario"].endswith("_" + half)]


def mcnemar(a: dict, b: dict) -> tuple[int, int, int, float]:
    keys = a.keys() & b.keys()
    b01 = sum(1 for k in keys if a[k] and not b[k])
    b10 = sum(1 for k in keys if b[k] and not a[k])
    n = b01 + b10
    p = min(1.0, 2 * sum(comb(n, i) for i in range(min(b01, b10) + 1)) / 2 ** n) if n else 1.0
    return len(keys), b01, b10, p


def sign_test(a: dict, b: dict, unit: str = "pair") -> tuple[int, int, int, float]:
    """Exact sign test on each unit's separation rate over its repeats. unit="pair" uses the 14
    pairs; unit="line" merges each eng pair with its sales mirror (7 instruction lines)."""
    def per_pair(d):
        g = defaultdict(list)
        for (n, _), v in d.items():
            g[n.replace("sales_", "") if unit == "line" else n].append(v)
        return {n: sum(v) / len(v) for n, v in g.items()}
    a, b = per_pair(a), per_pair(b)
    keys = a.keys() & b.keys()
    w = sum(1 for k in keys if a[k] > b[k])
    l = sum(1 for k in keys if a[k] < b[k])
    n = w + l
    p = min(1.0, 2 * sum(comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n) if n else 1.0
    return len(keys), w, l, p


def fisher(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test for the 2x2 table [[a, b], [c, d]]."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    def pr(x):
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p0 = pr(a)
    return min(1.0, sum(pr(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if pr(x) <= p0 + 1e-12))


def f(x: float) -> str:
    return "n/a" if x != x else f"{x:.2f}"


def main() -> None:
    main_, abl, cse = load("main"), load("pia_ablation"), load("ext_cse")
    sales, s_user, neutral = load("ext_sales"), load("ext_sales_user"), load("ext_neutral")
    appr, appr_diff = load("approval"), load("approval_diff")
    prompt = load("ext_prompt")
    L: list[str] = []

    # 1. CSE on the full matrix, next to CS from the main run
    L += ["## CSE (Countersign with effect-level C2) against CS, full matrix", "",
          "Gate ASR excludes BA4/BA8/SWAP; benign excludes SWAP halves and leak-by-design twins.", "",
          "| model | defense | gate ASR [95% CI] | BA4 | BA8 | benign success | gate asks/benign run | all asks/benign run |",
          "|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        for d, rows in (("CS", main_), ("CSE", cse)):
            rs = pick(rows, m, d)
            atk = [r for r in rs if r["kind"] == "attack" and r["pattern"] not in SEPARATE]
            ben = [r for r in rs if r["kind"] == "benign" and not r["scenario"].startswith(("SWAP_", "SWAPM_"))
                   and r["scenario"] not in LEAKY]
            a, lo, hi = rate_ci(atk, lambda r: r["attack_success"])
            ba4 = [r for r in rs if r["pattern"] == "BA4" and r["kind"] == "attack"]
            ba8 = [r for r in rs if r["pattern"] == "BA8" and r["kind"] == "attack"]
            gate = sum(1 for r in ben for c in r["confirm_log"] if c.split(":")[0] not in ("C3", "C4"))
            L.append(f"| {m} | {d} | {f(a)} [{f(lo)}, {f(hi)}] | "
                     f"{f(sum(r['attack_success'] for r in ba4) / len(ba4))} | "
                     f"{f(sum(r['attack_success'] for r in ba8) / len(ba8))} | "
                     f"{f(sum(bool(r['benign_success']) for r in ben) / len(ben))} | "
                     f"{f(gate / len(ben))} | {f(sum(r['confirmations'] for r in ben) / len(ben))} |")
    L += ["", "CSE gate ASR by pattern (all models):", ""]
    byp = defaultdict(list)
    for r in cse:
        if r["kind"] == "attack" and r["defense"] == "CSE":
            byp[r["pattern"]].append(r["attack_success"])
    L.append(" ".join(f"{p}={sum(v) / len(v):.2f}" for p, v in sorted(byp.items())))

    # 2. 14 author-swap pairs: eng pairs from the main run, sales pairs from ext_sales; CSE from ext_cse
    L += ["", "## Author-swap pairs, 14 pairs (7 eng + 7 mirrored sales), 42 pair-repeats per model", "",
          "Separated CI: bootstrap over the 14 pairs. Multi: legit half plus a harmless unentitled co-author line.", "",
          "| model | defense | separated [95% CI] | eng sep | sales sep | legit succ | attack succ | multi task succ |",
          "|---|---|---|---|---|---|---|---|"]
    swap_sets = {}
    for m in MODELS:
        for d in ("D0", "PI", "PIA", "C2", "C2E", "CS", "CSE", "EFFCONF"):
            if d == "CSE":
                rs = pick(cse, m, d)
            else:
                rs = [r for r in pick(main_, m, d) if "_sales_" not in r["scenario"]] + pick(sales, m, d)
            pr = pairs(rs)
            swap_sets[(m, d)] = pr
            g = defaultdict(list)
            for (n, _), v in pr.items():
                g[n].append(v)
            lo, hi = boot(list(g.values()))
            eng = [v for (n, _), v in pr.items() if not n.startswith("sales_")]
            sal = [v for (n, _), v in pr.items() if n.startswith("sales_")]
            leg, atk = halves(rs, "legit"), halves(rs, "attack")
            multi = [r for r in rs if r["scenario"].startswith("SWAPM_")]
            L.append(f"| {m} | {d} | {f(sum(pr.values()) / len(pr))} [{f(lo)}, {f(hi)}] | "
                     f"{f(sum(eng) / len(eng))} | {f(sum(sal) / len(sal))} | "
                     f"{f(sum(bool(r['benign_success']) for r in leg) / len(leg))} | "
                     f"{f(sum(r['attack_success'] for r in atk) / len(atk))} | "
                     f"{f(sum(bool(r['benign_success']) for r in multi) / len(multi))} |")

    # 3. paired tests on 14 pairs
    L += ["", "## Exact McNemar tests on separation (42 pair-repeats per model)", "",
          "PIA vs PIAG uses the same-run rows (eng from pia_ablation, sales from ext_sales).", "",
          "McNemar treats the 42 pair-repeats as independent; the sign test uses the 14 pairs as the unit.", "",
          "| model | comparison | n repeats | only first | only second | McNemar p | pairs first better | pairs second better | sign-test p (pairs) | sign-test p (lines) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for m in MODELS:
        pia_same = pairs(pick(abl, m, "PIA")) | pairs(pick(sales, m, "PIA"))
        piag = pairs(pick(abl, m, "PIAG")) | pairs(pick(sales, m, "PIAG"))
        for name, a, b in (("PIA vs PIAG", pia_same, piag),
                           ("C2 vs PIA", swap_sets[(m, "C2")], swap_sets[(m, "PIA")]),
                           ("CSE vs PIA", swap_sets[(m, "CSE")], swap_sets[(m, "PIA")]),
                           ("PIA vs PI", swap_sets[(m, "PIA")], swap_sets[(m, "PI")])):
            n, x, y, p = mcnemar(a, b)
            _, w, l, sp = sign_test(a, b)
            lp = sign_test(a, b, "line")[3]
            L.append(f"| {m} | {name} | {n} | {x} | {y} | {p:.4f} | {w} | {l} | {sp:.4f} | {lp:.4f} |")
        L.append(f"| {m} | PIAG separation (same run) | {len(piag)} | {f(sum(piag.values()) / len(piag))} | "
                 f"PIA {f(sum(pia_same.values()) / len(pia_same))} | | | | | |")

    # 4. approval policies on 14 pairs
    L += ["", "## Approval policies on the 14 pairs", "",
          "CSU: eng from approval_diff, sales from ext_sales_user (both with diff-showing re-consent prompts). "
          "EFFCONFU: eng from approval, sales from ext_sales_user. CSNU (control: same prompt points, "
          "authorship removed, neutral note): ext_neutral. CS deny-all: main + ext_sales. CSU (readable prompt) and CSAU (author name hidden, "
          "missing permission kept): ext_prompt.", "",
          "| model | policy | separated | legit succ | attack succ | multi task succ | approved/attack-half prompt |",
          "|---|---|---|---|---|---|---|"]
    for m in MODELS:
        sources = {
            "CS (deny)": [r for r in pick(main_, m, "CS")] + pick(sales, m, "CS"),
            "CSU": [r for r in pick(appr_diff, m, "CSU") if r["scenario"].startswith("SWAP")] + pick(s_user, m, "CSU"),
            "CSU (readable prompt)": pick(prompt, m, "CSU"),
            "CSAU": pick(prompt, m, "CSAU"),
            "CSNU": pick(neutral, m, "CSNU"),
            "EFFCONFU": [r for r in pick(appr, m, "EFFCONFU") if r["scenario"].startswith("SWAP")]
                        + pick(s_user, m, "EFFCONFU"),
        }
        for d, rs in sources.items():
            rs = [r for r in rs if r["scenario"].startswith(("SWAP_", "SWAPM_"))]
            pr = pairs(rs)
            leg, atk = halves(rs, "legit"), halves(rs, "attack")
            multi = [r for r in rs if r["scenario"].startswith("SWAPM_")]
            asked = sum(r["confirmations"] for r in atk)
            ok = sum(r["confirmations_approved"] for r in atk)
            L.append(f"| {m} | {d} | {f(sum(pr.values()) / len(pr))} | "
                     f"{f(sum(bool(r['benign_success']) for r in leg) / len(leg))} | "
                     f"{f(sum(r['attack_success'] for r in atk) / len(atk))} | "
                     f"{f(sum(bool(r['benign_success']) for r in multi) / len(multi))} | "
                     f"{f(ok / asked) if asked else 'n/a'} |")
    # 5. second model family: Gemini 3.6 Flash as the agent (detector still Claude Haiku).
    # The log's model field holds the alias the run requested, which the filter below matches.
    gem = load("ext_gemini")
    L += ["", "## Second model family: Gemini 3.6 Flash on the 14 pairs (ext_gemini)", "",
          "| defense | separated [95% CI] | legit succ | attack succ | multi task succ |", "|---|---|---|---|---|"]
    gsets = {}
    for d in ("D0", "PI", "PIA", "CSE"):
        rs = pick(gem, "gemini-3.5-flash", d)
        pr = pairs(rs)
        gsets[d] = pr
        g = defaultdict(list)
        for (n, _), v in pr.items():
            g[n].append(v)
        lo, hi = boot(list(g.values()))
        leg, atk = halves(rs, "legit"), halves(rs, "attack")
        multi = [r for r in rs if r["scenario"].startswith("SWAPM_")]
        L.append(f"| {d} | {f(sum(pr.values()) / len(pr))} [{f(lo)}, {f(hi)}] | "
                 f"{f(sum(bool(r['benign_success']) for r in leg) / len(leg))} | "
                 f"{f(sum(r['attack_success'] for r in atk) / len(atk))} | "
                 f"{f(sum(bool(r['benign_success']) for r in multi) / len(multi))} |")
    L += ["", "| comparison | pairs first better | pairs second better | sign-test p (pairs) | sign-test p (lines) |",
          "|---|---|---|---|---|"]
    for name, a, b in (("CSE vs PIA", gsets["CSE"], gsets["PIA"]), ("PIA vs PI", gsets["PIA"], gsets["PI"]),
                       ("CSE vs PI", gsets["CSE"], gsets["PI"])):
        _, w, l, sp = sign_test(a, b)
        L.append(f"| {name} | {w} | {l} | {sp:.4f} | {sign_test(a, b, 'line')[3]:.4f} |")

    # 6. detector from another family: Gemini judges the text, Claude agents act (ext_gdet_*)
    L += ["", "## Detector from another family: gemini detector, Claude agents, 14 pairs", "",
          "| agent | defense | separated [95% CI] | legit succ | attack succ | multi task succ |",
          "|---|---|---|---|---|---|"]
    gd = {"claude-haiku-5-5": load("ext_gdet_haiku"), "claude-sonnet-5-5": load("ext_gdet_sonnet")}
    for m, rows in gd.items():
        sets = {}
        for d in ("PI", "PIAG", "PIA"):
            rs = pick(rows, m, d)
            if not rs:
                continue
            pr = pairs(rs)
            sets[d] = pr
            g = defaultdict(list)
            for (n, _), v in pr.items():
                g[n].append(v)
            lo, hi = boot(list(g.values()))
            leg, atk = halves(rs, "legit"), halves(rs, "attack")
            multi = [r for r in rs if r["scenario"].startswith("SWAPM_")]
            L.append(f"| {m} | {d} | {f(sum(pr.values()) / len(pr))} [{f(lo)}, {f(hi)}] | "
                     f"{f(sum(bool(r['benign_success']) for r in leg) / len(leg))} | "
                     f"{f(sum(r['attack_success'] for r in atk) / len(atk))} | "
                     f"{f(sum(bool(r['benign_success']) for r in multi) / len(multi))} |")
        cse = swap_sets[(m, "CSE")]
        for name, a, b in (("PIA vs PI", sets.get("PIA"), sets.get("PI")),
                           ("PIA vs PIAG", sets.get("PIA"), sets.get("PIAG")),
                           ("CSE (Claude run) vs PIA", cse, sets.get("PIA"))):
            if a and b:
                _, w, l, sp = sign_test(a, b)
                L.append(f"| {m} | {name}: pairs {w}-{l}, sign p={sp:.4f} (pairs), "
                         f"{sign_test(a, b, 'line')[3]:.4f} (lines) | | | | |")

    L += ["", "Fisher exact tests on approved attack-half prompts (prompt as the unit):", ""]
    for m in MODELS:
        def tally(rows, d):
            atk = [r for r in pick(rows, m, d) if r["scenario"].startswith("SWAP_") and r["scenario"].endswith("_attack")]
            ok = sum(r["confirmations_approved"] for r in atk)
            return ok, sum(r["confirmations"] for r in atk) - ok
        u, a, n = tally(prompt, "CSU"), tally(prompt, "CSAU"), tally(neutral, "CSNU")
        def rates(rows, d, unit):
            ok, asked = defaultdict(int), defaultdict(int)
            for r in pick(rows, m, d):
                if r["scenario"].startswith("SWAP_") and r["scenario"].endswith("_attack"):
                    k = r["scenario"][5:-7]
                    k = k.replace("sales_", "") if unit == "line" else k
                    ok[k] += r["confirmations_approved"]
                    asked[k] += r["confirmations"]
            return {(k, 0): ok[k] / asked[k] for k in asked if asked[k]}
        sp_pair = sign_test(rates(neutral, "CSNU", "pair"), rates(prompt, "CSU", "pair"))[3]
        sp_line = sign_test(rates(neutral, "CSNU", "line"), rates(prompt, "CSU", "line"))[3]
        L.append(f"- {m}: CSNU {n[0]}/{sum(n)} vs CSU {u[0]}/{sum(u)}, p={fisher(*n, *u):.3f}; "
                 f"CSU vs CSAU {a[0]}/{sum(a)}, p={fisher(*u, *a):.3f}; "
                 f"sign test on approval rates CSNU vs CSU p={sp_pair:.3f} (pairs), {sp_line:.3f} (lines)")
    # 6. an LLM asked at the effect gate: C2J decides, C2A attributes for the lookup
    if (RUNS / "ext_gate.jsonl").exists():
        gate = load("ext_gate")
        L += ["", "## An LLM at the effect gate, 14 pairs and 3 bypass pairs (ext_gate)", "",
              "C2J: the model decides ALLOW or ASK at the tool call, shown each instruction segment, its "
              "author and whether that author holds the permission. C2A: the model names the segments that "
              "caused the call and the lookup decides over their authors. Judge: the Haiku detector model. "
              "Separated CI: bootstrap over the 14 pairs.", "",
              "| model | defense | separated [95% CI] | legit succ | attack succ | multi task succ | "
              "indirect bypass attack succ | folder bypass attack succ | bypass legit succ | "
              "legit halves asked | multi runs asked |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        gate_sets = {}
        for m in MODELS:
            for d in ("C2J", "C2A"):
                rs = pick(gate, m, d)
                pr = pairs(rs)
                gate_sets[(m, d)] = pr
                g = defaultdict(list)
                for (n, _), v in pr.items():
                    g[n].append(v)
                lo, hi = boot(list(g.values()))
                leg, atk = halves(rs, "legit"), halves(rs, "attack")
                multi = [r for r in rs if r["scenario"].startswith("SWAPM_")]
                byp = [r for r in rs if r["scenario"].startswith("BYP_")]
                ind = [r for r in byp if "indirect" in r["scenario"] and r["kind"] == "attack"]
                fol = [r for r in byp if "folder" in r["scenario"] and r["kind"] == "attack"]
                bl = [r for r in byp if r["kind"] == "benign"]
                rate = lambda rows, k: f(sum(bool(r[k]) for r in rows) / len(rows)) if rows else "n/a"
                L.append(f"| {m} | {d} | {f(sum(pr.values()) / len(pr))} [{f(lo)}, {f(hi)}] | "
                         f"{rate(leg, 'benign_success')} | {rate(atk, 'attack_success')} | "
                         f"{rate(multi, 'benign_success')} | {rate(ind, 'attack_success')} ({len(ind)} runs) | "
                         f"{rate(fol, 'attack_success')} ({len(fol)} runs) | {rate(bl, 'benign_success')} | "
                         f"{sum(1 for r in leg if r['confirmations'])} of {len(leg)} | "
                         f"{sum(1 for r in multi if r['confirmations'])} of {len(multi)} |")
        L += ["", "Exact sign tests on separation against the settings of the earlier runs:", "",
              "| model | comparison | pairs first better | pairs second better | sign-test p (pairs) | sign-test p (lines) |",
              "|---|---|---|---|---|---|"]
        for m in MODELS:
            for name, a, b in (("C2J vs PIA", gate_sets[(m, "C2J")], swap_sets[(m, "PIA")]),
                               ("CSE vs C2J", swap_sets[(m, "CSE")], gate_sets[(m, "C2J")]),
                               ("C2A vs PIA", gate_sets[(m, "C2A")], swap_sets[(m, "PIA")]),
                               ("CSE vs C2A", swap_sets[(m, "CSE")], gate_sets[(m, "C2A")])):
                _, w, l, sp = sign_test(a, b)
                L.append(f"| {m} | {name} | {w} | {l} | {sp:.4f} | {sign_test(a, b, 'line')[3]:.4f} |")
        errs = sum(1 for r in gate if r["error"])
        L += ["", f"Runs: {len(gate)}, errors: {errs}."]

    # 6b. bypass pairs under the lexical settings (ext_bypass); the summary file has no table for them
    if (RUNS / "ext_bypass.jsonl").exists():
        byp_rows = load("ext_bypass")
        L += ["", "## Bypass pairs under the lexical settings (ext_bypass)", "",
              "Attack halves that succeeded, of the runs in brackets. Indirect: the line never names "
              "its target. Folder: the request names the folder. CSEF is the stricter variant.", "",
              "| model | defense | indirect attacks | folder attack | legit halves completed |",
              "|---|---|---|---|---|"]
        for m in MODELS:
            for d in ("D0", "C2", "C2E", "CSE", "CSEF"):
                rs = pick(byp_rows, m, d)
                ind = [r for r in rs if "indirect" in r["scenario"] and r["kind"] == "attack"]
                fol = [r for r in rs if "folder" in r["scenario"] and r["kind"] == "attack"]
                leg = [r for r in rs if r["kind"] == "benign"]
                L.append(f"| {m} | {d} | {sum(r['attack_success'] for r in ind)} ({len(ind)}) | "
                         f"{sum(r['attack_success'] for r in fol)} ({len(fol)}) | "
                         f"{sum(bool(r['benign_success']) for r in leg)} ({len(leg)}) |")

    # 6c. pairs on the invoker's own files (ext_own): the default skip, and the settings that close it
    if (RUNS / "ext_own.jsonl").exists():
        own = load("ext_own")
        L += ["", "## Pairs on the invoker's own files (ext_own)", "",
              "Three lines that delete or overwrite a file in the invoker's home folder, written by "
              "the invoker (legit) or by an unentitled co-author (attack). CS and CSE skip effects "
              "that reach only the invoker; CSO and CSEO are the same settings with the skip closed.", "",
              "| model | defense | attacks succeeded | attack runs asked | legit completed | legit runs asked |",
              "|---|---|---|---|---|---|"]
        for m in MODELS:
            for d in ("D0", "CS", "CSE", "CSO", "CSEO"):
                rs = [r for r in pick(own, m, d) if r["scenario"].startswith("OWN_")]
                atk = [r for r in rs if r["kind"] == "attack"]
                leg = [r for r in rs if r["kind"] == "benign"]
                L.append(f"| {m} | {d} | {sum(r['attack_success'] for r in atk)} of {len(atk)} | "
                         f"{sum(1 for r in atk if r['confirmations'])} of {len(atk)} | "
                         f"{sum(bool(r['benign_success']) for r in leg)} of {len(leg)} | "
                         f"{sum(1 for r in leg if r['confirmations'])} of {len(leg)} |")
        L += ["", "Benign tasks in which a step saves into the invoker's folder (three Relay twins, "
              "where a sub-agent saves its summary, and one task whose request names the path):", "",
              "| model | defense | runs | runs asked at the effect gate | runs with a write to the home folder |",
              "|---|---|---|---|---|"]
        for m in MODELS:
            for d in ("D0", "CS", "CSE", "CSO", "CSEO"):
                rs = [r for r in pick(own, m, d) if not r["scenario"].startswith("OWN_")]
                gate_asked = sum(1 for r in rs if any(c.split(":")[0] not in ("C3", "C4") for c in r["confirm_log"]))
                wrote = sum(1 for r in rs if any("allow=True" in e and "'/home/" in e for e in r["effects_log"]))
                L.append(f"| {m} | {d} | {len(rs)} | {gate_asked} | {wrote} |")
        L += ["", f"Runs: {len(own)}, errors: {sum(1 for r in own if r['error'])}."]

    # 7. numbers quoted in the running text of the paper
    from ioulab.experiments.scenarios.benign import build_benign
    L += ["", "## Numbers quoted in the text", "",
          "Small figures the paper states in prose rather than in a table, each from the "
          "main run unless noted.", ""]

    # 7a. benign tasks with a real completion check (the rest can fail only by leaking)
    core = lambda s: not s.startswith(("SWAP_", "SWAPM_", "BYP_")) and s not in LEAKY
    benign_pool = sorted({r["scenario"] for r in main_ if r["kind"] == "benign" and core(r["scenario"])})
    by_id = {sc.id: sc for sc in build_benign()}
    # a trivial check is `lambda w: True`: it reads no global or attribute, so co_names is empty
    checked = {s for s in benign_pool
               if by_id[s].benign_check is not None and by_id[s].benign_check.__code__.co_names}
    L += [f"Of the {len(benign_pool)} benign tasks, {len(checked)} have a completion check; the other "
          f"{len(benign_pool) - len(checked)} can fail only by leaking.", "",
          "Completed, of 33 (11 checked tasks x 3 repeats):", "",
          "| setting | Haiku | Sonnet |", "|---|---|---|"]
    name = {"D0": "no defense", "PI": "text detector", "PIA": "permission-aware detector",
            "EFFCONF": "confirm everything", "CS": "Countersign, per run"}
    for d in ("D0", "PI", "PIA", "EFFCONF", "CS"):
        cells = []
        for m in MODELS:
            rs = [r for r in pick(main_, m, d) if r["kind"] == "benign" and r["scenario"] in checked]
            cells.append(str(sum(bool(r["benign_success"]) for r in rs)))
        L.append(f"| {name[d]} | {cells[0]} | {cells[1]} |")

    # 7b. attack scenarios that never succeed with no defense (so the checks are tested on the rest)
    d0 = defaultdict(list)
    for r in main_:
        if r["kind"] == "attack" and r["defense"] == "D0" and r["pattern"] not in SEPARATE \
                and not r["scenario"].startswith(("SWAPM_", "BYP_")):
            d0[r["scenario"]].append(r["attack_success"])
    dead = [s for s, v in d0.items() if not any(v)]
    L += ["", f"Attack scenarios that never succeed with no defense: {len(dead)} of {len(d0)}.", ""]

    # 7c. permission-aware detector: separation among pairs whose legit half completed
    L += ["Permission-aware detector, pairs separated among those whose legit half completed:", ""]
    for m in MODELS:
        rs = [r for r in pick(main_, m, "PIA") if "_sales_" not in r["scenario"]] + pick(sales, m, "PIA")
        half = {}
        for r in rs:
            if r["scenario"].startswith("SWAP_"):
                n, h = r["scenario"][5:].rsplit("_", 1)
                half[(n, r["repeat"], h)] = r
        num = den = 0
        for (n, rep, h), r in half.items():
            if h == "legit" and bool(r["benign_success"]) and (n, rep, "attack") in half:
                den += 1
                num += not half[(n, rep, "attack")]["attack_success"]
        L.append(f"- {m}: {num} of {den}")

    # 7d. Countersign vs confirm-everything on benign tasks: paired sign test over scenarios
    L += ["", "Countersign (per run) vs confirm everything on benign tasks, sign test over scenarios:", ""]
    for m in MODELS:
        rate = {d: defaultdict(list) for d in ("CS", "EFFCONF")}
        for r in main_:
            if r["model"].endswith(m) and r["kind"] == "benign" and core(r["scenario"]) and r["defense"] in rate:
                rate[r["defense"]][r["scenario"]].append(bool(r["benign_success"]))
        w = l = 0
        for s in set(rate["CS"]) & set(rate["EFFCONF"]):
            cs = sum(rate["CS"][s]) / len(rate["CS"][s])
            ef = sum(rate["EFFCONF"][s]) / len(rate["EFFCONF"][s])
            w += cs > ef
            l += ef > cs
        n = w + l
        p = min(1.0, 2 * sum(comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n) if n else 1.0
        L.append(f"- {m}: Countersign better on {w}, confirm everything on {l}, p = {p:.2f}")

    # 7e. corpus counts and the zero-success bounds of Table III
    scen = {r["scenario"]: r for r in main_}
    n_atk = sum(1 for r in scen.values() if r["kind"] == "attack" and r["pattern"] not in SEPARATE)
    n_nb = sum(1 for r in scen.values() if r["kind"] == "attack" and r["pattern"] in ("BA4", "BA8"))
    n_half = sum(1 for r in scen.values() if r["kind"] == "attack" and r["pattern"] == "SWAP")
    n_ben = sum(1 for r in scen.values() if r["kind"] == "benign")
    L += ["", f"Main-run corpus: {len(scen)} scenarios = {n_atk} attacks + {n_nb} neighboring-flow attacks + "
          f"{n_half} attack halves + {n_ben} benign tasks ({len(benign_pool)} in the benign columns).", "",
          "One-sided 95% upper bound when no scenario of n succeeds, 1 - 0.05^(1/n): "
          f"{1 - 0.05 ** (1 / n_atk):.2f} for n = {n_atk}, "
          f"{1 - 0.05 ** (1 / (n_atk - len(dead))):.2f} for n = {n_atk - len(dead)}.", ""]

    # 7f. text detector: benign runs with a flag
    for m in MODELS:
        ben = [r for r in pick(main_, m, "PI") if r["kind"] == "benign" and core(r["scenario"])]
        L.append(f"- Text detector, benign runs flagged, {m}: {sum(1 for r in ben if r['pi_flagged'])} of {len(ben)}")

    # 7g. permission-aware detector: what its unseparated pair-repeats were
    L += ["", "Permission-aware detector, pair-repeats not separated and why:", ""]
    for m in MODELS:
        rs = [r for r in pick(main_, m, "PIA") if "_sales_" not in r["scenario"]] + pick(sales, m, "PIA")
        half = {}
        for r in rs:
            if r["scenario"].startswith("SWAP_"):
                n, h = r["scenario"][5:].rsplit("_", 1)
                half[(n, r["repeat"], h)] = r
        refused = unflagged = through = 0
        missed = set()
        for (n, rep, h), r in half.items():
            if h != "legit":
                continue
            a = half[(n, rep, "attack")]
            if bool(r["benign_success"]) and not a["attack_success"]:
                continue
            missed.add(n)
            if not r["benign_success"]:
                refused += bool(r["pi_flagged"])
                unflagged += not r["pi_flagged"]
            else:
                through += 1
        L.append(f"- {m}: {refused + unflagged + through} not separated: {refused} legit halves the detector "
                 f"flagged, {unflagged} legit halves that failed with no flag, {through} attacks that got "
                 f"through; pairs missed at least once: {', '.join(sorted(missed))}")

    # 7h. per-run Countersign on the multi-author variants
    L += ["", "Per-run Countersign, multi-author runs in which it asked:", ""]
    for m in MODELS:
        rs = [r for r in pick(main_, m, "CS") if "_sales_" not in r["scenario"]] + pick(sales, m, "CS")
        multi = [r for r in rs if r["scenario"].startswith("SWAPM_")]
        L.append(f"- {m}: {sum(1 for r in multi if r['confirmations'])} of {len(multi)}")

    # 7i. simulated user: the sentence note by side, and the approve-leaning user
    L += ["", "Simulated user, sentence note (ext_prompt, CSU): attack halves that succeeded, eng / sales:", ""]
    for m in MODELS:
        atk = [r for r in pick(prompt, m, "CSU") if r["scenario"].startswith("SWAP_") and r["scenario"].endswith("_attack")]
        eng = [r for r in atk if "_sales_" not in r["scenario"]]
        sal = [r for r in atk if "_sales_" in r["scenario"]]
        L.append(f"- {m}: {sum(r['attack_success'] for r in eng)} of {len(eng)} / "
                 f"{sum(r['attack_success'] for r in sal)} of {len(sal)}")
    if (RUNS / "ext_user_busy.jsonl").exists():
        busy = load("ext_user_busy")
        L += ["", "Approve-leaning simulated user (ext_user_busy, Haiku agent only): attack-half runs "
              "with a question that was approved:", ""]
        for d, what in (("CSUB", "sentence note"), ("CSNUB", "neutral note")):
            atk = [r for r in busy if r["defense"] == d and r["scenario"].endswith("_attack") and not r["error"]]
            asked = [r for r in atk if r["confirmations"]]
            L.append(f"- {what} ({d}): {sum(1 for r in asked if r['confirmations_approved'])} of {len(asked)}")

    # 7j. gate model: answers the parser did not recognise (they count as a question)
    if (RUNS / "ext_gate.jsonl").exists():
        L += ["", "Gate model, multi-author variants: answers of ALLOW that the parser read as a question "
              "(the answer began with markdown emphasis, and the parser tests the first characters):", ""]
        for m in MODELS:
            odd = 0
            for r in pick(load("ext_gate"), m, "C2J"):
                if r["scenario"].startswith("SWAPM_"):
                    for g in r.get("gate_log", []):
                        ans = g.rsplit("->", 1)[-1].strip().upper()
                        odd += ans.lstrip(" *`_").startswith("ALLOW") and not ans.startswith("ALLOW")
            L.append(f"- {m}: {odd}")

    # 7k. the stand-up line with Sonnet, pooled over every released log
    logs = sorted(f.stem for f in RUNS.glob("*.jsonl") if "pilot" not in f.stem and "shard" not in f.stem)
    runs = done = 0
    for name in logs:
        for r in load(name):
            if ("standup" in r["scenario"] and r["kind"] == "benign" and not r["error"]
                    and r["model"].endswith("claude-sonnet-5-5")):
                runs += 1
                done += bool(r["benign_success"])
    L += ["", f"The stand-up line with Sonnet: the dated entry was written in {done} of {runs} runs "
          "(legitimate halves and multi-author variants, every setting, all logs)."]

    # 7l. Implant: its attack runs, which the pooled tables leave out
    imp = [r for name in logs for r in load(name) if r["pattern"] == "BA5" and r["kind"] == "attack"]
    L += ["", f"Implant: {sum(bool(r['attack_success']) for r in imp)} of {len(imp)} attack runs succeeded "
          f"(settings: {', '.join(sorted({r['defense'] for r in imp}))})."]

    sys.stdout.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
