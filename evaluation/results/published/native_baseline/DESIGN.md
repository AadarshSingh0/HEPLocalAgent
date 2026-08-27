# NATIVE_BASELINE_DESIGN — Baseline A: LLM → native HEP commands

**Status: FROZEN before any live call** (2026-08-16). Part of the
reviewer-extension (evaluation/paper_b_reviewer_extension/DESIGN.md §6).

## Purpose

The reviewer asks for a meaningful baseline comparison. The primary paper-B
design already provides:

- **Baseline B** (LLM → structured intent → deterministic builder): the
  planner-only branch of the paired design (no grounding/validation/repair).
- **Condition C** (full HEPLocalAgent guarded pipeline): the full-agent branch.

**Baseline A** (LLM → native HEP commands directly) is the missing condition:
the model is asked, in one call, to produce the native MadGraph artifact
(MG5 proc card or MG5 command script) directly, without the agent's
structured intermediate representation, grounding, validation, or repair.

## Design (frozen)

- **Requests:** the SAME frozen 20 original valid requests
  (evaluation/paper_b_end_to_end/requests.json) — verbatim request text.
- **Models:** the SAME final four-model set
  (MODEL_SELECTION.md): qwen2.5-coder:7b, qwen3-coder-next:Q4_K_M,
  qwen2.5-coder:14b, qwen3.5:27b.
- **Matrix:** 20 requests × 4 models = **80 direct-native evaluations**.
- **Prompt template:** frozen (`native_baseline_prompt.txt`). One call per
  unit; the prompt asks for the native artifact directly, mirroring the
  benchmark prompt style WITHOUT leaking the expected answer (no output-name
  leakage beyond what the frozen primary requests already state; the primary
  request text is used verbatim).
- **Generation settings:** same frozen settings as the primary evaluation
  (temperature 0.0; planner-style num_predict; 300 s timeout; infra retry
  policy: ≤3 first-call attempts for transport failures only).
- **Scoring:** original unmodified HEPToolBench deterministic scorers via the
  same frozen scoring adapter (physics-preserving normalized strict-pass
  PRIMARY; raw strict-pass SECONDARY). The frozen primary normalization
  transforms apply ONLY to the already-justified non-physics representation
  differences (output-name, define-p insertion, bare launch, madspin=OFF).
  Never normalized: process, particles, energies, event count, model, stages.
- **Preserved per unit:** raw model output, adapted artifact, scorer JSON
  (raw + normalized), generation metadata, infra attempts.
- **Reported metric:** task/pass-critical success (per DESIGN.md §21 — the
  primary `passed` semantics of the frozen scorer), not a manuscript-facing
  "strict pass" where HEPToolBench uses `strict_passed` differently.

## Baseline A scoring adapter (frozen)

The model's raw output is wrapped exactly like a benchmark submission (the
same file-name convention used by the primary harness:
`proc_card.dat` for families 1–3, `mg5_script.txt` for ttbar_workflow) and
scored by the frozen scorer via `runners/evaluate_submission.py`. The same
`normalize_artifact` transforms from the frozen primary adapter are applied
for the PRIMARY normalized view; raw artifact is always preserved and scored
separately. No new normalization rules are introduced.

## What is NOT done

- No agent machinery (no structured intent, no grounding, no validation, no
  repair, no approval gate) is applied to Baseline A.
- No second model call per unit except legitimate infrastructure retries.
- The model is not given the expected answer; the request text is the frozen
  primary request text.

## Three-way matched comparison (frozen)

For the 20 valid requests × 4 models:

- A = native baseline task-pass rate (this design);
- B = planner-only task-pass rate (from the primary matrix for the fixed
  models, and from the reviewer-extension paired runs for the new models);
- C = full guarded-agent success (same sources).

Report per model and overall: A, B, C rates; A→B, B→C, A→C changes (pp);
paired transitions; continuous scores; model-call counts. B→C is the
guarded-pipeline improvement (deterministic grounding + validation + gating),
NEVER "repair lift". Human approval quality is not isolated (automatic
approval used) — stated as a limitation.
