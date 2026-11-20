# Changelog

## 1.0.0 (2026-11-20)

First archived release, accompanying the AGENT 2027 submission.

## Harness versions behind the reported runs

Every row in `runs/*.jsonl` carries `code_version`, a hash of the outcome-relevant harness code
(analysis and the CLI are excluded, so a reporting fix never changes it). These are the versions
behind the paper's numbers, oldest first. The code in this repository is the latest version
that ran, `d666479310d4` (the last row).

| code_version | Runs | What changed from the previous version |
|---|---|---|
| `8ab3a597fd52` | `main` (6,264), `pia_ablation` (378) | Baseline for the paper: C1-C5, C2E, PI/PIA/PIAG, EFFCONF, 7 eng author-swap pairs, multi-author variants. |
| `ac54a27f95f8` | `approval` (2,268) | Simulated invoker (`informed_user`, defenses CSU and EFFCONFU) and approve-all CSA. Prompts are unchanged for every other defense. |
| `71d9aef95de1` | `approval_diff` (696) | C3 re-consent prompts list the added and removed instruction lines with their authors; the consent snapshot keeps each skill file's text. |
| `5220588498e3` | `ext_cse` (822), `ext_sales` (1,008), `ext_sales_user` (252), `ext_neutral` (252) | 7 mirrored author-swap pairs on the sales folder; CSE (Countersign with C2E); CSNU control (authorship removed from what the simulated invoker sees, real reason kept in the log). The general-assistant lines are authored by each graph's owner, which leaves the eng pairs unchanged. |
| `da6b4913a72b` | `ext_prompt` (504) | Readable C2 prompt ("this step comes from instructions written by Erin, who cannot delete /team/eng/roadmap.md themselves") replacing the terse string ("steered by ['erin'], who do not hold this write permission"); CSAU control (author name hidden, missing permission kept). |
| `b17032f4f63c` | `ext_gemini` (504) | Gemini support in the model factory (key from a file outside the repo, client-side rate limiter) and Google's rate-limit errors in the pause rules; C2 prompt says "this run includes" unless effect-level attribution traced the step (CSE asks with this wording in this run). Agent model Gemini 3.6 Flash at temperature 0; detector still claude-haiku-5-5. Run first as one repeat (168 runs), then completed to three with `--resume`; one run that hit a network error was rerun. All 43 CSE prompts in this run used the causal wording ("this step comes from"). The Gemini runs requested the alias `gemini-3.5-flash`, which the API served with `gemini-3.6-flash`; the `model` field of this log holds the alias, and rows from later runs also record the serving model in `served_models`. |
| `1b122cbfa6d4` | `ext_gdet_haiku` (378), `ext_gdet_sonnet` (252) | Gemini as the PI/PIA/PIAG detector with Claude agents. Rows record the detector model and its tokens separately from the agent's (`detector_model`, `detector_input_tokens`, `detector_output_tokens`) and the models the provider says served each call (`served_models`) (Gemini 3.6 Flash, requested under the alias named above). One Haiku PIAG run that hit a Google API error was rerun with `--resume`. |
| `49c57c0a1f9a` | `ext_neutral_pia` (252), `ext_bypass` (180), `ext_bypass_cost` (276), `ext_user_gemini` (504), `ext_user_busy` (252) | PIAN: the detector prompt without "deleting or changing things". CSEF / C2EF: deletes and overwrites (writes to a file present at the start of the run) use run-level attribution when a run has several authors, and are endorsed only by an exactly named path; BYP_* bypass pairs (indirection, folder prefix). CSUB / CSNUB: an approve-leaning ("busy") simulated user. `ext_user_gemini` uses Gemini 3.6 Flash as the simulated user. |
| `9ec42e804c6b` | `ext_gate` (576) | An LLM asked at the effect gate (`ioulab/defenses/gate_judge.py`). C2J: the model answers ALLOW or ASK at the tool call, shown each instruction segment with its author and whether each author holds the permission for this exact effect. C2A: the model names the segments that caused the call and the lookup decides over their authors; an answer that cannot be parsed charges every author. Judge model claude-haiku-5-5. Rows record the judge's answers in `gate_log`. Scenarios: the 14 author-swap pairs with their multi-author variants and the 3 bypass pairs. No change to any earlier setting. |
| `73e2d639112f` | none | Working remarks removed from comments and docstrings under `ioulab/`, and the reporting script `experiments/analysis.py` tidied (Implant kept out of the pooled summaries, "IOU" dropped from a heading); the run summaries in `runs/` were regenerated. No run behavior changed: with docstrings stripped, every syntax tree and every parsed YAML file is identical to `9ec42e804c6b`. |
| `d666479310d4` | `ext_own` (300) | A flag that closes the skip for effects reaching only the invoker's own files (`check_own`; settings CSO and CSEO, which are CS and CSE with the skip closed), and three pairs on the invoker's own files (`OWN_*`: the same line written by the invoker or by an unentitled co-author). Run on those pairs plus the benign tasks in which a step saves into the invoker's folder, under D0, CS, CSE, CSO and CSEO. No change to any earlier setting. Includes the comment cleanup of the previous row and a second one (the placeholder used when no API key is set was renamed, which is the only code change). The run was first made on build `723ba967a919` and repeated on this one so that the newest log matches the released code; every figure the paper reports from it came out the same, and only the repeat is kept. |

Implant (BA5) scenarios are in `approval.jsonl` but excluded from every reported table, as in `main`.
The combined tables in `runs/extended.md` are produced by `scripts/extended_tables.py`, which names
the run each cell comes from.

Early pilot runs that preceded `main` are not part of this release. No reported number comes
from them.
