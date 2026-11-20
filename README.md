# allograph-attacks

Testbed, run logs and the platform table for the paper
*Your Keys, Their Words: Allograph Attacks on Shared Agent Platforms* (under review).

On a shared agent platform, a workflow runs with the permissions of whoever presses "run", but
its instructions were written by whoever was allowed to edit it. A co-author can therefore add a
line that makes the agent do something the co-author could not do themselves. The paper calls
this an **allograph attack**. The same line can be routine from one co-author and an attack
from another, so wording cannot tell the two apart. What a platform needs is who wrote each line
and what that person may do, at the moment of the action. The paper's check, **Countersign**,
decides by looking those facts up, and the experiments measure the hard part, which is deciding
which authors an action is charged to.

This repository lets you check every number in the paper without an API key, and rerun any
experiment with your own key.

## Quick start

Python 3.12 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock && pip install -e .
```

Run the tests (a scripted model stands in for the LLM, so no key is needed):

```bash
pytest -q
```

Regenerate the combined tables from the logs and compare them with the committed copy:

```bash
python3 scripts/extended_tables.py > extended.new.md
diff extended.new.md runs/extended.md
```

Regenerate the summary of a single run (it rewrites `runs/main.md`, next to the log, with
identical content):

```bash
python3 -m ioulab.experiments.analysis runs/main.jsonl
```

## Where each result in the paper comes from

| In the paper | Log | Table generated from it |
|---|---|---|
| Table II, the eight builders | vendor documentation and builder source code | `docs/platform-table.md` |
| Table III, attack success and benign cost | `runs/main.jsonl`; per-effect Countersign from `runs/ext_cse.jsonl` | `runs/main.md`, `runs/extended.md` |
| Fig. 3, the author-swap pairs | `runs/main.jsonl`, `runs/ext_sales.jsonl`, `runs/ext_cse.jsonl` | `runs/extended.md`, section "Author-swap pairs" |
| Fig. 3, model at the gate and model attribution | `runs/ext_gate.jsonl` | `runs/extended.md`, section "An LLM at the effect gate" |
| Sign tests and intervals on the pairs | the logs above | `runs/extended.md`, section "Exact McNemar tests" |
| Detector told groups but not folders | `runs/pia_ablation.jsonl`, `runs/ext_sales.jsonl` | `runs/pia_ablation.md`, `runs/extended.md` |
| Second model family as the agent | `runs/ext_gemini.jsonl` | `runs/extended.md`, section "Second model family" |
| Bypass pairs and the stricter variant | `runs/ext_bypass.jsonl`, `runs/ext_bypass_cost.jsonl` | `runs/extended.md`, section "Bypass pairs"; `runs/ext_bypass_cost.md` |
| Pairs on the runner's own files | `runs/ext_own.jsonl` | `runs/extended.md`, section "Pairs on the invoker's own files" |
| Approve-leaning simulated user | `runs/ext_user_busy.jsonl` | `runs/extended.md`, section "Numbers quoted in the text" |
| Figures stated only in the prose | the logs above | `runs/extended.md`, section "Numbers quoted in the text" |
| Simulated user, four wordings of the confirmation | `runs/approval.jsonl`, `runs/approval_diff.jsonl`, `runs/ext_prompt.jsonl`, `runs/ext_sales_user.jsonl`, `runs/ext_neutral.jsonl` | `runs/approval.md`, `runs/approval_diff.md`, `runs/extended.md`, section "Approval policies" |
| Implant never succeeding | `runs/approval.jsonl` (scenarios `BA5_*`, all `attack_success` false) | counted from the log; `runs/approval.md` notes the exclusion |

Results that the paper does not report are here too: the audience check and version pinning on
their own (`runs/main.md`), the detector prompt without its delete example
(`runs/ext_neutral_pia.jsonl`), a detector from another model family (`runs/ext_gdet_haiku.jsonl`,
`runs/ext_gdet_sonnet.jsonl`) and a simulated user from another model family
(`runs/ext_user_gemini.jsonl`).

Each log is one JSON object per run, with these fields:

| Field | Meaning |
|---|---|
| `scenario`, `kind`, `pattern`, `variant` | scenario id; `attack` or `benign`; pattern code; wording variant |
| `defense`, `model`, `repeat` | the setting, the agent model as requested, and the repeat number |
| `attack_success`, `benign_success` | the outcome, from the oracle |
| `confirmations`, `confirmations_approved`, `confirm_log` | questions asked, how many were approved, and the reason shown for each |
| `effects`, `blocked_effects`, `effects_log` | effects that reached a tool, effects stopped, and each call with its arguments |
| `leaks`, `sinks` | marker strings that reached an audience outside their readers, and every sink written |
| `calls`, `attached`, `skipped` | the agent's tool calls in order; connectors attached and not attached |
| `pi_flagged`, `pi_flag_locs` | detector flags and where they fell |
| `final` | the start of the agent's last message |
| `latency_ms`, `input_tokens`, `output_tokens` | cost of the agent's part of the run |
| `code_version`, `error` | harness version; empty unless the run failed |
| `detector_model`, `detector_input_tokens`, `detector_output_tokens`, `served_models` | from version `1b122cbfa6d4` on: the detector, its tokens, and the models the provider says served the run |
| `gate_log` | from version `9ec42e804c6b` on: each answer of the gate model or the attributing model |

Scoring is exact: a leak is a private
item's marker string reaching an audience that could not read it at its source, and integrity
attacks are checked against the tool servers' effect logs. No LLM judges an outcome.

Words used in the generated tables: a *canary* is the marker string planted in a private item, *ASR* is the share of attack runs that succeeded, and a *twin* is an attack scenario with its payload removed, used as a benign task.

## Names in the paper and names in the code

The paper names things by what they do. The code and the logs use short codes.

| Code | Name in the paper | What runs |
|---|---|---|
| `D0` | no defense | only the invoker's tools are attached, and they are called as the invoker |
| `PI` | text detector | spotlighting plus a task-aware LLM detector on all text not written by the invoker |
| `PIA` | permission-aware detector | the same detector, also told each text's author and the folders that author can write |
| `PIAG` | detector told the author and groups only | `PIA` without the folders |
| `EFFCONF` | confirm everything | confirm every effect the request did not name |
| `C1` | audience check alone | |
| `C2` | alignment check, per run | every author in the run is charged |
| `C2E` | alignment check, per effect | only authors whose text names the effect's target are charged |
| `C3` | version pinning alone | |
| `CS` | Countersign, per run | `C1` to `C5` together |
| `CSE` | Countersign, per effect | `CS` with `C2E` in place of `C2` |
| `CSEF`, `C2EF` | the stricter variant | per-run attribution and exact-path matching for deletes and overwrites |
| `CSO`, `CSEO` | Countersign with the own-files skip closed | `CS` and `CSE`, but effects on the invoker's own files are checked too |
| `C2J` | model at the gate | an LLM decides at the tool call, given the authors and their permissions |
| `C2A` | lookup with model attribution | an LLM names the segments that caused the call, the lookup decides |
| `CSU`, `EFFCONFU` | with a simulated user | a model answers each confirmation |
| `CSAU`, `CSNU` | wording controls | the author's name hidden; a neutral note with no reason |
| `CSA` | approve everything | every confirmation is approved |
| `PIN`, `PIAN` | detector prompt control | the detector prompt without "deleting or changing things" |
| `CSUB`, `CSNUB` | approve-leaning user | the simulated user is told it is busy |

Rules and checks: the alignment rule is `P1`, the audience rule `P2` and the freshness rule
`P3`. `C4` and `C5` are the promotion and replay checks for the two neighboring flows.

Patterns: Steer is `BA1`, Sinkhole `BA2`, Widen `BA3`, Promote `BA4`, Implant `BA5`, Swap `BA6`,
Relay `BA7`, Watch `BA8`. The variants are `BA1X` (a Steer by an author from another group),
`BI1` (integrity only) and `BI2` (an added recipient). Author-swap pairs are
`SWAP_<name>_legit` and `SWAP_<name>_attack`, their multi-author variants are `SWAPM_<name>`,
the bypass pairs are `BYP_<name>_legit` and `BYP_<name>_attack`, and the pairs on the invoker's own files are `OWN_<name>_legit` and `OWN_<name>_attack`. `LEGIT_*` and `AD_*` are benign tasks written as such. Variants `_v1` to `_v5` of a pattern go from overt to disguised wording.

People: the paper follows the usual naming, so its attacker Mallory (sales) is `erin` in the
scenarios and logs, and its reader Eve (engineering) is `mallory`. Alice and Bob keep their
names. The package is called `ioulab` because the attack's first working name was "IOU attack"; a few identifiers keep it. Settings in the code that the table above does not list (`CEIL`, `RCEIL`, `XCONF`) are early baselines that no reported run uses.

## Layout

```
ioulab/
  domain/       principals, scopes, artifacts with per-line authorship, labels, the world
  platform/     scoped virtual file system, MCP proxy, run context, tool semantics, assembly
  defenses/     the checks, the detectors, the gate model and the simulated user
  protocols/    MCP servers (docs, mail, hrdb, collector) and an Agent2Agent server and client
  memory/       memory consolidation
  replay/       recorded-run views with viewer access control
  llm/          model factory and a scripted chat model for deterministic tests
  experiments/  oracle, runner, analysis, command line; scenarios/ holds the corpus and payloads
scripts/        extended_tables.py, which builds runs/extended.md
runs/           one raw log (.jsonl) and one summary (.md) per run family
tests/          deterministic tests of the harness
docs/platform-table.md  the 64 cells of the builder table, each with its source
CHANGELOG.md    releases, and which version of the harness produced which run
CITATION.cff, .zenodo.json  citation and archive metadata
NOTICE          copyright holders and which license covers which files
.github/workflows/check.yml  CI: runs the tests and regenerates the tables from the logs
```

The testbed is a synthetic enterprise platform built on real protocols: agents from `deepagents`
on LangGraph, real Model Context Protocol servers behind a proxy that attaches only the
invoker's tools, a real Agent2Agent remote agent, Agent Skills, tiered memory and a replay log.

## The code and the logs

Every log row carries `code_version`, a hash of the harness code and the payload file. The
harness grew while the experiments ran, so each run family carries the version that produced
it; `CHANGELOG.md` lists them in order and says what each version changed. Later versions add
settings and scenarios. Two of them also reworded the note that the alignment check shows when
it asks, which matters only to the settings in which a simulated user reads that note (see the
run-family table below).

The code here is the version of the latest run:

```bash
python3 -c "from ioulab.experiments.__main__ import code_version; print(code_version())"
```

prints `d666479310d4`, the value in every row of `runs/ext_own.jsonl`.

## Running new experiments

A deterministic dry run needs no key:

```bash
python3 -m ioulab.experiments --scripted --defenses D0,C2,C2E,CS,CSE,EFFCONF --out runs/scripted
```

It runs 954 scenario and setting combinations in about a minute, and its summary,
`runs/scripted.md`, ends with `## Errors: 0 of 954 runs`. Lines such as `read_doc failed` on the
console are tool calls that the platform refused, which is expected. Settings that need a model (the detectors,
the gate model, the simulated user) cannot run scripted. With real models, a missing or wrong
key stops the run and leaves a `.PAUSE` file next to the output; fix the key and rerun with
`--resume`.

For real models, put an Anthropic key in the environment variable `IOULAB_ANTHROPIC_API_KEY`
(or in the file `~/.config/ioulab/anthropic_key`). The main run is

```bash
python3 -m ioulab.experiments \
  --models anthropic:claude-haiku-5-5,anthropic:claude-sonnet-5-5 \
  --detector anthropic:claude-haiku-5-5 \
  --defenses D0,PI,PIA,C1,C2,C2E,C3,EFFCONF,CS \
  --only '^(?!(TWIN_)?BA5_|SWAPM?_sales|BYP_|OWN_)' \
  --repeats 3 --workers 8 --out runs/main
```

which is 6,264 runs. The other run families use the same command with the settings, scenarios
and models below (`--repeats 3` throughout; the detector, the gate model and the simulated user
are `anthropic:claude-haiku-5-5` unless noted).

| Run family | Runs | `--defenses` | Scenarios (`--only`) | Notes |
|---|---|---|---|---|
| `main` | 6,264 | `D0,PI,PIA,C1,C2,C2E,C3,EFFCONF,CS` | all but Implant, the sales pairs, the bypass and own-file pairs | |
| `pia_ablation` | 378 | `PI,PIA,PIAG` | the 7 eng pairs and their multi-author variants (`^SWAPM?_(?!sales)`) | |
| `approval` | 2,268 | `CSU,EFFCONFU,CSA` | the main corpus plus Implant | terse note (`steered by [...]`), which the released code no longer produces |
| `approval_diff` | 696 | `CSU` | the main corpus | terse note; re-consent notes show the changed lines |
| `ext_cse` | 822 | `CSE` | the main corpus plus the sales pairs | |
| `ext_sales` | 1,008 | `D0,PI,PIAG,PIA,C2,C2E,EFFCONF,CS` | the 7 sales pairs and variants (`^SWAPM?_sales`) | |
| `ext_sales_user` | 252 | `CSU,EFFCONFU` | `^SWAPM?_sales` | terse note |
| `ext_neutral` | 252 | `CSNU` | all 14 pairs and variants (`^SWAPM?_`) | |
| `ext_prompt` | 504 | `CSU,CSAU` | `^SWAPM?_` | sentence note worded "this step comes from..."; from the next version on, per-run settings say "this run includes..." |
| `ext_gemini` | 504 | `D0,PI,PIA,CSE` | `^SWAPM?_` | Gemini 3.6 Flash as the agent (`--models`) |
| `ext_gdet_haiku` | 378 | `PI,PIA,PIAG` | `^SWAPM?_` | Haiku agent, Gemini 3.6 Flash as the detector (`--detector`) |
| `ext_gdet_sonnet` | 252 | `PI,PIA` | `^SWAPM?_` | Sonnet agent, Gemini 3.6 Flash as the detector (`--detector`) |
| `ext_neutral_pia` | 252 | `PIAN` | `^SWAPM?_` | |
| `ext_bypass` | 180 | `D0,C2,C2E,CSE,CSEF` | `^BYP_` | |
| `ext_bypass_cost` | 276 | `CSEF` | `^SWAPM?_` and the integrity-only benign twins | |
| `ext_user_gemini` | 504 | `CSU,CSNU` | `^SWAPM?_` | Gemini 3.6 Flash as the simulated user (`--user-model`) |
| `ext_user_busy` | 252 | `CSUB,CSNUB` | `^SWAPM?_` | Haiku agent only; sentence note worded "this run includes..." |
| `ext_gate` | 576 | `C2J,C2A` | `^(SWAPM?_|BYP_)` | about 8.4 million input and 0.4 million output tokens |
| `ext_own` | 300 | `D0,CS,CSE,CSO,CSEO` | `^(OWN_|TWIN_BA7_v[135]$|LEGIT_save_home$)` | |

`--resume` skips runs that are already in the output, so an interrupted run can be restarted.
A Gemini model needs a key in `IOULAB_GEMINI_API_KEY`; `CHANGELOG.md` gives the model id that
the Gemini runs requested. Keys are never written to a log. LLM outputs vary, so a
rerun will not match the committed logs row for row.

## Adding a scenario or a setting

A setting is one entry in `DEFENSES` in `ioulab/defenses/config.py`: a name and the flags of the
`Defense` dataclass it turns on. The flags are read in `ioulab/defenses/checks.py` (the checks at
a tool call), `ioulab/defenses/pinning.py` (version pinning), `ioulab/defenses/pi_baselines.py`
(the detectors), `ioulab/platform/` (`assembly.py`, `mcp_proxy.py`, `run_context.py`: what is
attached, screened and asked), `ioulab/memory/consolidation.py` and `ioulab/replay/log.py` (the
two neighboring flows) and `ioulab/experiments/runner.py`. To add a check, add a flag, read it in `check_outbound`, and add a setting that
sets it.

A scenario is a `Scenario` object (`ioulab/experiments/scenarios/schema.py`): who runs it, what
they ask, a `build` function that returns the world and the shared workflow with an author for
every line, and either a `goal` (an attack succeeded) or a `benign_check` (the task was done).
`scenarios/own_files.py` is the shortest complete example of a pair. Attack texts for the main
corpus live in `scenarios/payloads.yaml`. Register a new builder in `all_scenarios()` in
`ioulab/experiments/__main__.py`, give it a `scripted_policy` so the tests can run it without a
model, and select it with `--only`.

## The builder table

`docs/platform-table.md` lists the 64 cells of the paper's table of eight shared agent builders.
Each cell has its code and the vendor page or source file it rests on, so that it can be checked.

## A note on the attack payloads

The instruction texts used as attacks are in `ioulab/experiments/scenarios/payloads.yaml`. They
are test inputs for this synthetic testbed. Nothing here was run against a live product. The one check on a real builder was a default-deny probe on a local Langflow install (two users, one reading and running the other's flow), noted in `docs/platform-table.md`.

## License

The code is under the MIT License (`LICENSE`). The run logs in `runs/` and the table in
`docs/` are under CC BY 4.0 (`LICENSE-DATA`). Copyright 2026 the allograph-attacks authors
(`NOTICE`).

## Citing

Cite the release with `CITATION.cff` (GitHub shows it under "Cite this repository"). Each tagged
release is archived on Zenodo with a DOI.
