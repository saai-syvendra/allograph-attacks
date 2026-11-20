"""Defense configurations compared in the experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Defense:
    name: str
    c1_audience: bool = False     # P2 at sinks
    c2_alignment: bool = False    # P1 at effectors
    c2_effect: bool = False       # C2 over the authors whose text names the effect's target
    c3_pin: bool = False          # P3 version pinning
    c4_promotion: bool = False    # P2 for memory promotion
    c5_replay: bool = False       # P2 for replay viewers
    author_ceiling: bool = False  # attach only tools every author can also use
    resource_ceiling: bool = False  # hard-block a sink an instruction author could not use
    confirm_unrequested: bool = False  # provenance-free baseline: confirm any unrequested effect
    confirm_external: bool = False     # provenance-free baseline: confirm any send beyond the invoker
    pi_spotlight: bool = False    # baseline: delimit tool output as data
    pi_detector: bool = False     # baseline: classifier over non-invoker text
    pi_provenance: bool = False   # the detector is also told who wrote the text and what they may do
    pi_prov_folders: bool = True  # include the author's writable shared folders (off = ablation PIAG)
    approve_all: bool = False     # sensitivity: the invoker approves every confirmation
    informed_user: bool = False   # a simulated invoker reads each prompt and decides
    neutral_reason: bool = False  # control: the prompt omits every authorship cue and gives a neutral note
    anonymous_author: bool = False  # control: the prompt keeps the missing permission but hides who
    pi_neutral_prompt: bool = False  # control: the judge prompt without "deleting or changing things"
    busy_user: bool = False       # the simulated invoker leans towards approving
    strict_destructive: bool = False  # deletes and overwrites: run-level C2 when several authors, exact-path endorsement
    c2_judge: bool = False        # C2 decided by an LLM at the effect, given authors and their permissions
    c2_attrib_llm: bool = False   # C2 by lookup, over the authors an LLM says caused the effect
    check_own: bool = False       # C2 also covers effects that reach only the invoker's own files


DEFENSES: dict[str, Defense] = {
    "D0": Defense("D0"),
    "PI": Defense("PI", pi_spotlight=True, pi_detector=True),
    "PIA": Defense("PIA", pi_spotlight=True, pi_detector=True, pi_provenance=True),
    "PIAG": Defense("PIAG", pi_spotlight=True, pi_detector=True, pi_provenance=True, pi_prov_folders=False),
    "C1": Defense("C1", c1_audience=True),
    "C2": Defense("C2", c2_alignment=True),
    "C2E": Defense("C2E", c2_alignment=True, c2_effect=True),
    "C3": Defense("C3", c3_pin=True),
    "CS": Defense("CS", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True),
    "CSA": Defense("CSA", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True,
                   approve_all=True),
    "CSU": Defense("CSU", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True,
                   informed_user=True),
    "CSE": Defense("CSE", c1_audience=True, c2_alignment=True, c2_effect=True, c3_pin=True, c4_promotion=True,
                   c5_replay=True),
    "CSNU": Defense("CSNU", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True,
                    informed_user=True, neutral_reason=True),
    "PIN": Defense("PIN", pi_spotlight=True, pi_detector=True, pi_neutral_prompt=True),
    "PIAN": Defense("PIAN", pi_spotlight=True, pi_detector=True, pi_provenance=True, pi_neutral_prompt=True),
    "CSEF": Defense("CSEF", c1_audience=True, c2_alignment=True, c2_effect=True, c3_pin=True, c4_promotion=True,
                    c5_replay=True, strict_destructive=True),
    "C2EF": Defense("C2EF", c2_alignment=True, c2_effect=True, strict_destructive=True),
    "CSUB": Defense("CSUB", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True,
                    informed_user=True, busy_user=True),
    "CSNUB": Defense("CSNUB", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True,
                     informed_user=True, neutral_reason=True, busy_user=True),
    "CSAU": Defense("CSAU", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True,
                    informed_user=True, anonymous_author=True),
    "EFFCONFU": Defense("EFFCONFU", confirm_unrequested=True, informed_user=True),
    "CSO": Defense("CSO", c1_audience=True, c2_alignment=True, c3_pin=True, c4_promotion=True, c5_replay=True,
                   check_own=True),
    "CSEO": Defense("CSEO", c1_audience=True, c2_alignment=True, c2_effect=True, c3_pin=True, c4_promotion=True,
                    c5_replay=True, check_own=True),
    "C2J": Defense("C2J", c2_alignment=True, c2_judge=True),
    "C2A": Defense("C2A", c2_alignment=True, c2_attrib_llm=True),
    "CEIL": Defense("CEIL", author_ceiling=True),
    "RCEIL": Defense("RCEIL", resource_ceiling=True),
    "EFFCONF": Defense("EFFCONF", confirm_unrequested=True),
    "XCONF": Defense("XCONF", confirm_external=True),
}
