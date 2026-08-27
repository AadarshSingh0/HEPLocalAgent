# Capability Supplement Results — Paper B

**Status:** COMPLETE (2026-08-17). Small supplementary coverage check, reviewer-motivated,
separate from the prespecified primary comparative experiment.

## Scope and position

- This is a **separate supplementary capability-coverage study**, NOT part of:
  the primary 47-semantic-unit denominator, the 50-request extension,
  the 61 matched A/B/C baseline denominator, or the containment statistics.
- Target: at most **one frozen valid request per capability** (energy scan,
  MadAnalysis, user-UFO/BSM) x **two reliable existing models**
  (qwen2.5-coder:7b, qwen3-coder-next:Q4_K_M) = **6 live agent evaluations**.
- Motivation: the reviewer asked for coverage of supported energy scans,
  MadAnalysis, and BSM/UFO workflows, which the large live study mostly did not
  demonstrate as valid live successes.
- **No statistical generalization is claimed** — exact N is small (6 units).

## Capability audit (released v0.1.1, commit feeccfb10fb424beaac3c6da4530128fc9cff585)

| Capability | Implemented in v0.1.1? | Reachable from NL agent path? | Pre-existing positive test/fixture? | Run without production change? |
|---|---|---|---|---|
| Energy scans | Yes (`src/hep_agent/scans/`, `prepare_energy_scan`, `execute_energy_scan`, `ExistingPipelinePointExecutor`) | Yes (semantic route via `prepare_energy_scan`) | Yes (`tests/test_energy_scan*`, parser fixtures) | Yes |
| MadAnalysis | Yes (`src/hep_agent/analysis/`, structured MA5 schema, MG5->MA5 runtime stage) | Qualified — only when the request text makes the MA5 intent detectable (fact extraction is trigger-based) | Yes (`tests/test_structured_madanalysis.py`, `tests/test_end_to_end_madanalysis.py`) | Yes |
| User-UFO/BSM | Yes (`PhysicsModelSpec`, model reference via `import model <path>`) | Yes (full-structured route with explicit model fact) | Yes (`tests/test_ufo_domain_validation.py`; real shipped UFOs in managed stack: `MSSM_SLHA2`, `taudecay_UFO`) | Yes |

Frozen design: `evaluation/paper_b_capability_supplement/DESIGN.md`, `requests.json`,
`labels.json`, `source_map.json`, `hashes.sha256` (frozen BEFORE live calls;
model-free tests in `evaluation/paper_b_capability_supplement/tests/` pass).

## Live results (6 units)

| Request | Class | Expected | qwen2.5-coder:7b | qwen3-coder-next:Q4_K_M |
|---|---|---|---|---|
| cap_energy_scan | valid_supported_variant | execute_supported_workflow | correct acceptance, intent preserved | correct acceptance, intent preserved |
| cap_madanalysis | valid_supported_variant | execute_supported_workflow | false rejection (MA5 stage silently dropped, reached READY without it) | false rejection (same) |
| cap_user_ufo | valid_supported_variant | execute_supported_workflow | correct acceptance, intent preserved | correct acceptance, intent preserved |

- LLM calls: exactly 1 per unit (6 total). Repair: 0. Fallback: 0.
  Infrastructure attempts: 1 per unit. No re-planning, no repair.
- All units reached READY_FOR_APPROVAL; both MadAnalysis units reached READY
  but with `pipeline.madanalysis=False` — the frozen label requires the MA5
  stage, so they are classified false rejection (intent not preserved).

## Optional runtime confirmation (3A)

Per the frozen rule, runtime confirmation is attempted only for capabilities
with a valid gate-approved artifact:

1. **Energy scan — RUNTIME CONFIRMED (qwen3-coder-next:Q4_K_M, cap_energy_scan).**
   Re-ran `prepare_energy_scan` with the saved first planner response (ReplayClient,
   zero new model calls) and executed via `execute_energy_scan` +
   `ExistingPipelinePointExecutor` on the managed `.hep-stack`:
   **9 points x 100 events, energies 1-5 TeV in 500 GeV steps; per-point LHE
   verified (beam energies scale correctly: 500+500 GeV at 1 TeV ... 2500+2500 GeV
   at 5 TeV); 48.0 s wall.**
2. **User-UFO — RUNTIME CONFIRMED (qwen3-coder-next:Q4_K_M, cap_user_ufo).**
   Reconstructed the exact saved full-agent artifact from the persisted run record
   (`20260817T065601_1f61cbb5.json`, `build_madgraph_workflow_artifact`, artifact
   commands SHA-256 `6b33ea54...`) and executed through the released
   `execute_prepared` path on the managed stack with the real `MSSM_SLHA2` model:
   **`import model <MSSM_SLHA2>`, `generate p p > x1+ x1-`, 100 events,
   iseed 1, ebeam 6500; LHE verified, cross-section 0.4823 +/- 0.002625 pb;
   8.1 s wall.** Genuine MG5 3.5.13 run (Feynman diagrams generated for
   u u~ > x1+ x1-, c c~ > x1+ x1-, d d~ > x1+ x1-, s s~ > x1+ x1-).
3. **MadAnalysis — NOT runtime-confirmed.** Neither model produced a valid
   gate-approved artifact with `pipeline.madanalysis=True` (both silently dropped
   the MA5 stage), so per 3A there is no valid artifact to confirm at runtime.
   This is documented honestly; no runtime was faked.

## Answers to the paper-truthfulness questions

- **Can Paper B truthfully claim live evidence for valid energy-scan handling?
  YES.** Live correct acceptance + intent preservation for both models, and a
  real 9-point runtime execution on the managed stack.
- **Can Paper B truthfully claim live evidence for valid MadAnalysis handling?
  NO (not from live evaluation).** Both models silently dropped the requested
  MA5 stage (reached READY without it). The capability exists in v0.1.1 with
  pre-existing tests, but live valid-MA5 handling was NOT demonstrated.
  Supported wording: "MadAnalysis construction is implemented in v0.1.1 with
  model-free tests, but the live evaluation did not produce a valid
  MadAnalysis-including workflow; requests phrased around generic 'plots'
  routed to the semantic planner, which cannot represent the MA5 stage."
- **Can Paper B truthfully claim live evidence for valid user-UFO handling?
  YES.** Live correct acceptance + intent preservation for both models, and a
  real MSSM_SLHA2 chargino-pair runtime execution on the managed stack.

## Exact N and denominators

- 6 live units (3 requests x 2 models); not merged into any other denominator.
- 4/6 correct acceptance with intent preservation (scan 2/2, UFO 2/2).
- 2/6 false rejection (MadAnalysis 2/2; both models).
- 0/6 false acceptance, 0 infrastructure-unavailable, 0 repair, 0 fallback.
- 2/3 capabilities runtime-confirmed on the managed stack.

## Files

- `evaluation/paper_b_capability_supplement/` — frozen design, requests, labels,
  source_map, hashes, runner, model-free tests, raw results (6 units), runtime
  confirmations.
- `paper_outputs/capability_supplement_results.csv` — machine-readable 6-row table.
- `manuscript_ready/capability_supplement.tex` — manuscript-ready prose.
