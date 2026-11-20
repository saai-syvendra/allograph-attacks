"""Run the experiment matrix and write results.

Usage:
  python3 -m ioulab.experiments --scripted                 # deterministic dry run, no API key
  python3 -m ioulab.experiments --models anthropic:claude-haiku-5-5
  python3 -m ioulab.experiments --models anthropic:claude-haiku-5-5,anthropic:claude-sonnet-5-5 \
      --detector anthropic:claude-haiku-5-5 --defenses D0,PI,PIA,C2,CS --repeats 3 --out runs/main

Writes <out>.jsonl (one row per run), <out>.csv and <out>.md (summary tables).

`--workers N` splits the matrix over N processes (the platform keeps per-process state, so
runs inside one process stay sequential) and merges their rows. `--resume` skips runs already
in the output, so a long matrix can be restarted after an interruption.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from ..llm.factory import make_model
from .analysis import rows_to_csv, summary_markdown
from .defenses_list import ALL_DEFENSES
from .runner import Runner, RunResult
from .scenarios.benign import build_benign
from .scenarios.bypass import build_bypass
from .scenarios.own_files import build_own
from .scenarios.corpus import build_attacks, build_ba8


def all_scenarios():
    return build_attacks() + build_ba8() + build_benign() + build_bypass() + build_own()


def _key(model: str, defense: str, scenario: str, repeat: int) -> tuple:
    return (model, defense, scenario, repeat)


# Errors that mean the key or account cannot continue: pause the whole matrix instead of
# churning through the remaining jobs. Rate limits back off and retry first; three failed runs in
# a row also pause.
FATAL = ("AuthenticationError", "PermissionDeniedError", "credit balance", "billing",
         "invalid x-api-key", "Error code: 401", "Error code: 403", "API_KEY_INVALID", "PERMISSION_DENIED")
RATE = ("RateLimitError", "Error code: 429", "overloaded", "Error code: 529",
        "RESOURCE_EXHAUSTED", "ResourceExhausted", "429 ", "503 UNAVAILABLE", "UNAVAILABLE")
BACKOFF = (60, 120, 240, 480)    # seconds to wait before retrying a rate-limited run
PAUSE_EXIT = 3


def code_version() -> str:
    """A hash of the harness code and payloads, stamped on every row; resume only reuses rows
    produced by the same code, so a fix between pause and resume cannot mix versions."""
    import hashlib
    root = Path(__file__).resolve().parent.parent
    # only code that changes what a run does or how it is scored; reporting and CLI code
    # (analysis.py, __main__.py) is excluded so a reporting fix does not change the hash of
    # runs that are already recorded
    skip = {"experiments/analysis.py", "experiments/__main__.py"}
    h = hashlib.sha256()
    for f in sorted(list(root.rglob("*.py")) + list(root.rglob("*.yaml"))):
        rel = f.relative_to(root).as_posix()
        if "__pycache__" in f.parts or rel in skip:
            continue
        h.update(rel.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def pause_file(out: Path) -> Path:
    env = os.environ.get("IOULAB_PAUSE_FILE")
    return Path(env) if env else out.with_suffix(".PAUSE")


def _shard_base(out: Path) -> Path:
    m = re.match(r"(.*)-shard\d+$", out.name)
    return out.with_name(m.group(1)) if m else out


def _all_rows(out: Path) -> list[RunResult]:
    """Rows from this output and every sibling shard file, so a resume reuses finished work even
    if the job list or worker count changed."""
    base = _shard_base(out)
    paths = {out.with_suffix(".jsonl"), base.with_suffix(".jsonl"),
             *base.parent.glob(f"{base.name}-shard*.jsonl")}
    return [r for p in paths for r in load_rows(p)]


def load_rows(path: Path) -> list[RunResult]:
    if not path.exists():
        return []
    return [RunResult(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def write_outputs(rows: list[RunResult], out: Path) -> None:
    out.with_suffix(".jsonl").write_text("".join(json.dumps(asdict(r)) + "\n" for r in rows))
    out.with_suffix(".csv").write_text(rows_to_csv(rows))
    out.with_suffix(".md").write_text(summary_markdown(rows))
    print(f"\nWrote {out.with_suffix('.jsonl')}, .csv, .md  ({len(rows)} rows)")


async def run_matrix(models: list[str], defenses: list[str], repeats: int, scripted: bool,
                     detector_spec: str | None, out: Path, shard: tuple[int, int] = (0, 1),
                     resume: bool = False, only: str | None = None,
                     user_spec: str | None = None) -> list[RunResult]:
    from ..protocols.a2a.server import A2AHost
    from .defenses_list import by_name

    scns = all_scenarios()
    if only:                          # e.g. --only '^(SWAP|BI1)' for a targeted check
        scns = [x for x in scns if re.search(only, x.id)]
    names = ["scripted"] if scripted else models
    jobs = [(m, d, s, rep) for m in names for d in defenses for s in scns for rep in range(repeats)]
    jobs = jobs[shard[0]::shard[1]]
    path = out.with_suffix(".jsonl")
    ver = code_version()
    usable = lambda r: not r.error and r.code_version == ver      # noqa: E731
    prior = load_rows(path) if resume else []
    stale = sum(1 for r in prior if not r.error and r.code_version != ver)
    if stale:
        print(f"  [shard {shard[0]}/{shard[1]}] ignoring {stale} rows from a different code version", flush=True)
    rows = [r for r in prior if usable(r)]                          # failed or stale runs are redone
    have = {_key(r.model, r.defense, r.scenario, r.repeat) for r in (_all_rows(out) if resume else [])
            if usable(r)}
    jobs = [j for j in jobs if _key(j[0], j[1], j[2].id, j[3]) not in have]
    pause = pause_file(out)

    host = A2AHost({"enricher": "A partner enrichment agent."}).start()
    for noisy in ("httpx", "a2a"):   # libraries may reset levels on import; set again here
        logging.getLogger(noisy).setLevel(logging.WARNING)
    detector_model = make_model(detector_spec) if detector_spec else None
    user_spec = user_spec or detector_spec
    user_model = make_model(user_spec) if user_spec and not scripted else None
    runner = Runner(host, detector_model, user_model, detector_spec or "")
    model_objs = {m: (None if scripted else make_model(m)) for m in names}

    out.parent.mkdir(parents=True, exist_ok=True)
    jsonl = path.open("w")
    for r in rows:
        jsonl.write(json.dumps(asdict(r)) + "\n")
    t0 = time.time()
    streak = 0
    paused = False
    for i, (mname, dname, scn, rep) in enumerate(jobs, 1):
        if pause.exists():
            print(f"  [shard {shard[0]}/{shard[1]}] pause file found; stopping at {i-1}/{len(jobs)}", flush=True)
            paused = True
            break
        r = await runner.run(scn, by_name(dname), model_objs[mname], mname, rep, scripted=scripted)
        for wait in BACKOFF:            # a rate limit that outlasted the SDK's retries: back off
            if not (r.error and any(x in r.error for x in RATE)) or pause.exists():
                break
            print(f"  [shard {shard[0]}/{shard[1]}] rate limited; retrying in {wait}s", flush=True)
            time.sleep(wait)
            r = await runner.run(scn, by_name(dname), model_objs[mname], mname, rep, scripted=scripted)
        r.code_version = ver
        streak = streak + 1 if r.error else 0
        fatal = r.error and any(f in r.error for f in FATAL + RATE)   # RATE here = still limited after backoff
        if fatal or streak >= 3:
            reason = r.error if fatal else f"3 failed runs in a row; last: {r.error}"
            pause.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} shard {shard[0]}: {reason[:300]}\n")
            print(f"  [shard {shard[0]}/{shard[1]}] PAUSING: {reason[:200]}", flush=True)
            paused = True
            break                       # the failed row is not kept; resume retries it
        rows.append(r)
        jsonl.write(json.dumps(asdict(r)) + "\n")
        jsonl.flush()
        if i % 20 == 0 or i == len(jobs):
            print(f"  [shard {shard[0]}/{shard[1]}] {i}/{len(jobs)}  ({(time.time()-t0):.0f}s)", flush=True)
    jsonl.close()
    host.stop()
    if paused:
        raise SystemExit(PAUSE_EXIT)
    return rows


def run_workers(argv: list[str], workers: int, out: Path) -> None:
    """Run the matrix in `workers` processes, one shard each, then merge their rows."""
    out.parent.mkdir(parents=True, exist_ok=True)
    pause = out.with_suffix(".PAUSE")
    if pause.exists():
        print(f"Removing old pause file: {pause.read_text().strip()}")
        pause.unlink()
    env = dict(os.environ, IOULAB_PAUSE_FILE=str(pause))
    procs = []
    for k in range(workers):
        part = out.with_name(f"{out.name}-shard{k}")
        cmd = [sys.executable, "-m", "ioulab.experiments", *argv, "--shard", f"{k}/{workers}",
               "--out", str(part)]
        log = part.with_suffix(".log").open("a")
        procs.append(subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env))
    codes = [p.wait() for p in procs]
    # merge, keeping one row per run (a successful row beats a failed one)
    best: dict[tuple, RunResult] = {}
    ver = code_version()
    for r in _all_rows(out.with_name(f"{out.name}-shard0")):
        if r.code_version and r.code_version != ver:
            continue                    # rows from older code are not merged
        k = _key(r.model, r.defense, r.scenario, r.repeat)
        if k not in best or (best[k].error and not r.error):
            best[k] = r
    rows = sorted(best.values(), key=lambda r: (r.model, r.defense, r.scenario, r.repeat))
    if pause.exists():
        print(f"PAUSED: {pause.read_text().strip()}")
        done = sum(1 for r in rows if not r.error)
        print(f"{done} completed runs saved. Fix the key or wait, then rerun the same command with --resume.")
        raise SystemExit(PAUSE_EXIT)
    write_outputs(rows, out)
    errors = sum(1 for r in rows if r.error)
    print(f"worker exit codes {codes}; {errors} rows with errors")
    print("\n" + summary_markdown(rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="anthropic:claude-haiku-5-5")
    ap.add_argument("--defenses", default=",".join(ALL_DEFENSES))
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--scripted", action="store_true", help="use the deterministic scripted model (no API key)")
    ap.add_argument("--detector", default=None, help="model spec for the detector, the gate model and the simulated user (e.g. anthropic:claude-haiku-5-5)")
    ap.add_argument("--out", default="runs/run")
    ap.add_argument("--workers", type=int, default=1, help="split the matrix over N processes")
    ap.add_argument("--shard", default="0/1", help=argparse.SUPPRESS)
    ap.add_argument("--resume", action="store_true", help="skip runs already in the output")
    ap.add_argument("--only", default=None, help="regex: run only scenarios whose id matches")
    ap.add_argument("--user-model", default=None, help="model spec for the simulated user (CSU, CSAU, CSNU, CSUB, EFFCONFU); defaults to --detector")
    a = ap.parse_args()
    for noisy in ("httpx", "a2a"):   # one INFO line per HTTP call drowns the progress lines
        logging.getLogger(noisy).setLevel(logging.WARNING)
    out = Path(a.out)
    if a.workers > 1:
        # each worker gets its own --out shard file and no --workers flag
        drop = {"--out", "--workers"}
        argv, skip = [], False
        for x in sys.argv[1:]:
            if skip:
                skip = False
            elif x in drop:
                skip = True
            elif x.split("=")[0] not in drop:
                argv.append(x)
        run_workers(argv, a.workers, out)
        return
    k, n = (int(x) for x in a.shard.split("/"))
    rows = asyncio.run(run_matrix(a.models.split(","), a.defenses.split(","), a.repeats, a.scripted,
                                  a.detector, out, (k, n), a.resume, a.only, a.user_model))
    if n == 1:
        write_outputs(rows, out)
        print("\n" + summary_markdown(rows))


if __name__ == "__main__":
    main()
