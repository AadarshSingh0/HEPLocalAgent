# Paper B — End-to-End Guarded-Agent Evaluation: Frozen Design

Status: **FROZEN for the live run** (version 1.1, 2026-08-15).

Revision 1.1 (2026-08-15, pre-live): per the evaluation owner's instruction,
the scoring policy is corrected BEFORE any live model result: the
**physics-preserving normalized strict-pass is now the PRIMARY metric**, and
the zero-normalization/raw-artifact strict-pass is the labelled SECONDARY
sensitivity. Normalization rules are unchanged (frozen, deterministic,
physics-preserving, identical for both branches); the unmodified HEPToolBench
scorers remain the only scorers; raw artifacts and raw scorer JSON are always
preserved.

This document is the frozen experimental specification for the controlled
evaluation that measures what HEPLocalAgent's deterministic grounding,
validation, approval gate, and bounded repair add over the model's initial
single-turn proposal. It is written **before any live model result exists**.
Nothing in this document may be changed after live model results are
collected; disagreements are recorded and analysed, not silently resolved.

---

## A. Scientific question

**Primary question**

> How often does HEPLocalAgent convert an in-scope natural-language request
> into a correct workflow that reaches the approval gate, and how much does
> the complete guarded agent improve over its initial single-turn model
> proposal?

The primary two-condition comparison measures the effect of the **whole
guarded layer applied after the first model proposal**:

    deterministic grounding + validation + bounded repair + approval gating

It does **not** isolate repair alone. The primary difference is therefore
named the **guarded-agent lift** (equivalently: full-agent lift,
validation-and-repair lift). It is **never** called "pure repair lift": no
no-repair validation condition is evaluated in the primary matrix (see §G for
the optional third ablation that would make that claim possible).

Three distinct notions are kept strictly separate throughout (Section 16 of
the commissioning brief):

1. **model initial correctness** — does the model's first proposal express the
   right physics (external benchmark scorer on the compiled baseline artifact);
2. **agent gate-level correctness** — does the full agent reach
   `READY_FOR_APPROVAL` with an artifact that satisfies the external benchmark
   scorer;
3. **external HEP runtime success** — did MadGraph/Pythia/Delphes run and
   produce files. Runtime success is **not** evidence of physics correctness
   and is measured only under the optional `--execute` mode (§6).

---

## B. Evaluation unit

One evaluation unit is

    one model × one fixed natural-language request

where the request belongs to one of the four in-scope workflow families
derived from HEPToolBench (§D). There are 20 requests and 3 target models, so
the primary matrix is **20 × 3 = 60 paired evaluations**.

---

## C. Models

Target model labels (must match the installed Ollama labels exactly; no
silent substitution):

| Model label                | Eval profile | Profile settings                              |
|----------------------------|--------------|-----------------------------------------------|
| `qwen2.5-coder:7b`         | `qwen25_7b`  | primary, no fallback, max_repairs=2, max_planner_attempts=2 |
| `qwen3-coder-next:Q4_K_M`  | `qwen3_next` | primary, no fallback, max_repairs=2, max_planner_attempts=2 |
| `llama3.3:70b`             | `llama33_70b`| primary, no fallback, max_repairs=2, max_planner_attempts=2 |

- Profiles are evaluation-only (`profiles.json` in this directory). They do
  not modify `configs/agent_profiles.json`. Fallback is intentionally disabled
  so each row isolates that model's planner+repair behaviour; `fallback_used`
  is therefore expected to be 0 and is reported as such (the production
  cascade profile `qwen_cascade` is not part of this ablation).
- Before the live run, the exact installed labels are verified with
  `ollama list`; `ollama show <model>` metadata is saved per model into the
  run manifest. If a target label is absent, the run is refused (no
  substitution).
- `OLLAMA_HOST` is honoured by the harness exactly as by HEPLocalAgent
  (`OllamaClient`), so the evaluation can target the same local/remote server.
  The resolved host is recorded in the manifest.

## Generation settings

Recorded from the actual source (not invented): the structured planner uses
`temperature=0.0`, `num_predict=4096`; the semantic planner uses
`temperature=0.0`, `num_predict=300`; repair uses the profile
`primary_timeout_seconds` (180 s). HEPLocalAgent does **not** set a random
seed for Ollama; this is stated explicitly in the manifest.

---

## D. Request set (frozen)

**Scope decision (frozen):** HEPToolBench family 4 (`mg_runcard_004`,
Drell-Yan run-card lepton cuts) is **excluded**. Audit finding: the
`WorkflowIntent` schema (`RunSettings`) has no cut fields, so `ptl`/`etal`
cannot be represented; the deterministic builder emits `set ...` launch
syntax that the frozen scorer explicitly rejects; and adapting the artifact
to include the cuts would fabricate physics the agent never produced. The
commissioning brief requires every request's physics to be within current
HEPLocalAgent scope (§10) and forbids adding physics requirements (§3D).
Including family 4 would violate both. The exclusion and its reason are part
of the frozen record.

The frozen request set is 4 families × 5 paraphrases = **20 requests**
(`requests.json`). Every paraphrase preserves the pass-critical physics of its
source benchmark task, mirrors the information content of the benchmark
prompt (no extra physics requirements, no expected-answer leakage beyond the
benchmark prompt), and is worded to stay on the agent's **full structured
route** (each request contains the explicit MadGraph process expression and
avoids the words `via`, `through`, and `decay*`, which would force the thin
semantic route even with explicit syntax).

| Family | Source task | Pass-critical physics (from the frozen scorer) |
|---|---|---|
| `drell_yan` (proc card) | `mg_basic_001` | `generate p p > e+ e-`; ebeam1=ebeam2=6500; no hard failures |
| `top_pair` (proc card) | `mg_basic_002` | `generate p p > t t~`; **`output TTbar`**; ebeam1=ebeam2=6500; no hard failures |
| `higgs_jet` (proc card) | `mg_basic_003` | `generate p p > h j`; **`output HJ`**; ebeam1=ebeam2=6500; no hard failures |
| `ttbar_workflow` (MG5 script) | `mg_workflow_005` | `import model sm`; exact `define p = ...`; `generate p p > t t~`; **`output TTbar_P8_Delphes`**; **bare `launch`**; `shower=Pythia8`; `detector=Delphes`; `analysis=OFF`; **`madspin=OFF`**; `done`; `set nevents 10000`; `set iseed 42`; ebeam1=ebeam2=6500; no hard failures |

Output-directory leakage rule (frozen): a paraphrase may state the output
directory only where the original benchmark prompt states it — yes for
`higgs_jet` (`Use HJ as the output directory`) and `ttbar_workflow`
(`output directory: TTbar_P8_Delphes`); **no** for `drell_yan` and `top_pair`
(the benchmark prompts do not state them, even though the scorers require
`DY_ee`/`TTbar` — a benchmark-internal prompt/scorer inconsistency that is
recorded, not repaired).

Energy phrasing rule (frozen): each request contains exactly one collider
energy expression ("13 TeV" total or "6500 GeV per beam"/"each beam"), because
the deterministic fact extractor takes the first energy match; a request with
two energy expressions would make the extracted ground-truth fact ambiguous.

Per-request ground truth (frozen in `requests.json`):

    request_id, workflow_family, paraphrase_index, request_text,
    source_benchmark_task, scorer_path (relative to HEPToolBench root),
    expected_process, model/ufo ("sm"), collision_energy_gev (13000),
    beam_energy_gev (6500), energy_meaning (total_center_of_mass or per_beam),
    event_count (None for families 1–3 — not in the benchmark prompt;
    10000 for ttbar_workflow), pythia8_state, delphes_state,
    madanalysis_state (False), expected_output_name (per the leakage rule),
    run_card/cut requirements (iseed 42 and madspin off for ttbar_workflow),
    expected_agent_route (asserted "full_structured" for all 20),
    notes.

Once frozen, `requests.json` is not edited after model results are seen.
Its SHA-256 is recorded in every run manifest.

---

## E. Conditions

### PRIMARY CONDITION 1 — Initial / planner-only

Measures the model's first proposal **without validator-guided rescue**:

1. exactly **one** initial planning model response (real Ollama call),
   recorded verbatim;
2. deterministic representation-to-artifact compilation only:
   `parse_planner_content` → `build_madgraph_workflow_artifact`
   (full route), or the semantic parse → `compile_semantic_process_workflow`
   → builder (semantic route). This compilation never repairs physics and
   applies no grounding corrections, no reconciliation, no validation, no
   repair;
3. if the first response cannot be parsed or compiled, the baseline is a
   failure — no rescue;
4. the compiled baseline artifact is scored with the family's frozen
   HEPToolBench scorer (raw and normalized forms, §Scoring).

Recorded: raw first response; parse success; compile success; compiled
artifact; parse/compile failure reason; benchmark score; strict-pass.

### PRIMARY CONDITION 2 — Full guarded agent

The same request runs through the actual released preparation path
(`prepare_end_to_end` → `run_preexecution_and_record` → `run_preexecution_loop`):

    planner (replayed first response) → deterministic grounding correction →
    reconciliation → grounding+model-domain validation → bounded repair
    (primary model) → optional fallback (not configured in this ablation) →
    deterministic builder → artifact validation → approval decision

Recorded: final status; final workflow; final artifact; benchmark score and
pass (raw and normalized); corrections; validation issue codes; repair
attempts; fallback use; model-call count; approval decision; failure
category; run-record path.

---

## F. Paired-sample requirement (frozen)

The two conditions consume the **identical first planner response**:

1. **Recording**: one real planner call is made through an evaluation-only
   `RecordingClient` (subclass of `OllamaClient`, so production routing
   `isinstance(client, OllamaClient)` is preserved) that saves the raw
   response and request transcript to disk;
2. **Baseline**: derived from that recorded response alone (Condition 1);
3. **Full agent**: `prepare_end_to_end` runs with an evaluation-only
   `ReplayClient` whose first planner call returns the recorded response
   verbatim (matched by SHA-256 of `(model, messages, response_schema)`);
   all subsequent calls (repairs, planner retries) go to the real server.

This makes the comparison genuinely paired: stochastic variation in the first
planner call cannot masquerade as validator/repair lift. Production planning
behavior is unchanged (no edits to `src/hep_agent`). The model-free harness
tests prove that replay actually substitutes the identical first response
(§11-A). If exact replay were ever proven impossible without changing
production semantics, the run would stop and this would be reported — the
harness never silently falls back to independent sampling.

---

## G. Optional third ablation (not run by default)

The harness supports a future third condition — grounding/validation enabled
but model repair disabled — which would isolate deterministic validation from
model repair. It is **not run** unless the user explicitly approves the
additional compute or a reviewer comment requires pure-repair isolation. Its
presence does not affect the primary two-condition comparison.

---

## 4. Scoring adapter (frozen)

The unmodified HEPToolBench deterministic scorers are the only scorers.
They are invoked as subprocesses through their documented CLI
(`runners/evaluate_submission.py --task <id> --submission <file>`), which
itself calls the original `tests/score.py`; no scorer logic is copied or
modified, and no scorer file is edited.

Three quantities are computed per artifact (initial and full):

1. **normalized strict-pass** (PRIMARY): the artifact after the frozen,
   physics-preserving format transforms below, scored by the same unmodified
   scorer. This is the primary experiment quantity: it measures whether the
   model/agent preserved the requested physics and workflow, not whether the
   released agent emits exactly the same incidental file formatting expected
   from a raw benchmark submission.
2. **raw strict-pass** (SECONDARY sensitivity, clearly labelled): the agent
   artifact exactly as produced, scored by the frozen scorer → `passed`
   boolean + continuous `score` + full `checks` + `failure_modes` JSON. This
   remains an important audit quantity and is always preserved.
3. **physics-content** (diagnostic): derived from the **raw** scorer JSON —
   the artifact's physics-bearing checks pass, regardless of format. Per
   family the physics-bearing checks are the scorer's own check keys:
   - `drell_yan`: `imports_sm`, `correct_process`, `ebeam1_6500`, `ebeam2_6500`;
   - `top_pair`: `imports_sm`, `correct_process`, `ebeam1_6500`, `ebeam2_6500`;
   - `higgs_jet`: `imports_sm`, `correct_process`, `ebeam1_6500`, `ebeam2_6500`;
   - `ttbar_workflow`: `imports_sm`, `correct_process`, `ebeam1_6500`,
     `ebeam2_6500`, `shower_pythia8`, `detector_delphes`, `analysis_off`,
     `madspin_off`, `nevents_10000`, `iseed_42`.

**Normalization transforms (frozen; applied deterministically, identically to
both conditions; never touch process lines, energies, event counts, seeds,
shower/detector/analysis choices, or model import):**

| Family | Transform (only the listed ones) |
|---|---|
| `drell_yan` | none |
| `top_pair` | `output <name>` → `output TTbar` (first occurrence) |
| `higgs_jet` | `output <name>` → `output HJ` (first occurrence) |
| `ttbar_workflow` | insert `define p = g u c d s u~ c~ d~ s~` after the `import model sm` line if absent; `launch <name>` → `launch`; insert `madspin=OFF` after the `analysis=OFF` line if absent; `output <name>` → `output TTbar_P8_Delphes` |

Rationale (frozen): the agent's deterministic builder emits `output <name>`
(a directory label), `launch <name>`, and omits `define p` and `madspin=OFF`.
These are artifact-format properties, not physics; the inserted `define p` is
the standard MG5 proton alias (MG5 already predefines `p`), and `madspin=OFF`
matches an explicit statement in the `ttbar_workflow` request. Because these
differences can impose strict-pass ceilings on families 2/3/5 even when the
requested physics is correct, the PRIMARY experiment measures the
physics-preserving normalized strict-pass; the raw artifact is preserved and
its strict-pass is reported as the secondary sensitivity. The raw artifact is
always preserved alongside the normalized one. If a required line is absent
(e.g., no `output` line at all), the transform is a no-op for that line — no
content the agent did not produce is invented, except the two documented
MG5-standard insertions above.

Every transform is unit-tested, and the request-set tests prove that each
canonical known-correct artifact passes the intended scorer while each
intentionally wrong artifact fails it (§10), so the scorer+adapter is proven
to measure the intended physics distinction before any model is run.

---## 5. Metrics (frozen before results)

Denominators: all denominators are the 20 in-scope requests (per model),
unless stated. `x/y` style counts are always reported together with
percentages.

**The publication-facing primary metrics P1–P8 use the physics-preserving
normalized strict-pass. The same P1–P8 computed from raw artifacts are
reported as the labelled secondary sensitivity analysis.**

- **P1. Planner-only strict-pass rate** (primary, normalized): `# initial_pass / 20`.
- **P2. Full guarded-agent success at the approval gate** (PRIMARY):
  a request succeeds iff `full status == READY_FOR_APPROVAL` **and** the
  final artifact normalized-passes the frozen scorer. Reported `x/20` + %.
- **P3. Guarded-agent lift**: `P2 − P1` in percentage points (not a vague
  percentage increase). Paired request-level transition counts are retained:
  `fail→fail`, `fail→pass`, `pass→pass`, `pass→fail` (normalized pass).
- **P4. Recovery rate**: among requests whose **initial** proposal
  normalized-fails, the fraction whose full-agent artifact normalized-passes.
  Numerator/denominator reported.
- **P5. Gate leakage (invalid-passed)**: among requests with
  `READY_FOR_APPROVAL`, the fraction whose final artifact normalized-fails.
  Reported as `invalid_ready / all_ready` and raw count. Not assumed zero.
- **P6. False rejection** (narrow, validator-facing): initial candidate
  normalized-passes the external scorer but the full agent does **not** reach
  `READY_FOR_APPROVAL`. Reported `x/y` (y = # initial-pass) and separately the
  **valid-request non-ready rate** `#not_ready / 20` (every request is
  intentionally valid and in-scope). Model planning failure is never
  conflated with validator false rejection.
- **P7. Repair usage**: mean repair attempts per request; `# requests with
  ≥1 repair`; fallback use (expected 0 — not configured); success after
  repair (`full_pass` among requests with ≥1 repair).
- **P8. Continuous score**: HEPToolBench continuous score retained as
  secondary information only; it never replaces strict pass.

**Secondary sensitivity (raw)**: metrics P1′–P8′ with identical definitions
on the raw artifact, clearly labelled as the audit/sensitivity view.

**Diagnostic**: physics-content pass (initial/full) per §4-3, reported as an
analysis column.

Wilson 95% confidence intervals are computed for proportions. Because the 20
paraphrases derive from only 4 physics workflows, they are not treated as 20
independent scientific tasks; per-family breakdowns are reported and no
hypothesis test is manufactured.

---

## 5b. Infrastructure-failure handling (frozen pre-analysis protocol
clarification)

The original §5 denominators (“all 20 in-scope requests per model”) did not
explicitly specify the treatment of first-call transport/server timeouts.
This clarification is frozen BEFORE any further live run and is a
pre-analysis protocol clarification: a paired semantic comparison requires
an actual first response, so a transport failure cannot be scored as an
incorrect semantic proposal.

A (model, request) unit becomes a **valid semantic measurement** only when a
usable first planner response is obtained. A transport/server/Ollama timeout
or equivalent infrastructure error occurring before any first planner
response is obtained is an **`infrastructure_invalid_attempt`**, NOT a
semantic planner failure. Such attempts:

- remain preserved verbatim (per-attempt `initial_attempt_<n>.json` in the
  case dir plus the run-level `infrastructure_attempts.jsonl` attempt-level
  provenance);
- never enter the planner-only or full-agent correctness denominators;
- are eligible for retry using the EXACT SAME model, request, `OLLAMA_HOST`,
  300 s timeout, generation settings, profile, scorer, normalization, and
  frozen request set — the 300 s threshold is NOT increased;
- at most **3 total first-call infrastructure attempts** per unit (the
  original plus up to 2 additional);
- are retried ONLY when no usable first response was obtained because of a
  transport/server/Ollama timeout or equivalent infrastructure failure
  (`OllamaClientError`). Retry is NEVER triggered by bad physics, scorer
  failure, parsing failure after a real response, validation blocks, or low
  quality — those remain genuine measured outcomes;
- once one usable first response is obtained, it is frozen and the normal
  paired design applies (planner-only derived from it, replayed into the
  full agent).

If all 3 attempts fail, the unit is marked **`infrastructure_unavailable`**,
kept outside the primary semantic denominator, and reported explicitly. A
secondary operational metric, **first-attempt completion rate** (units with
`first_response_attempt == 1` over evaluated units), is reported so the paper
can distinguish semantic correctness from operational model-server/time-limit
reliability.

The 9 first-call-timeout rows committed before this policy are preserved:
legacy rows remain in the append-only `rows.jsonl` history, and each is
additionally backfilled (idempotently) into `infrastructure_attempts.jsonl`
with the original row embedded verbatim under `preserved_row`, so no history
is silently replaced. On resume, legacy `infrastructure_invalid` rows are
NOT treated as completed: they are retried (attempts continue from the
recorded count), and the new canonical row supersedes the legacy row in the
CSV view.

Rule is model-independent; timeout threshold frozen at 300 s; no observed
semantic result caused any scorer/agent/design change.

---

## 6. Optional runtime end-to-end check (`--execute`)

OFF by default. When enabled, for a full-agent `READY_FOR_APPROVAL` result
the exact prepared artifact is executed with HEPLocalAgent's own
`execute_prepared()` using the managed `.hep-stack` path (no re-planning).
Recorded: execution status; LHE verification; HepMC verification (if Pythia8
requested); ROOT verification (if Delphes requested); cross section; event
count; runtime; output paths. An optional runtime end-to-end success metric is
defined as `READY_FOR_APPROVAL AND scorer strict pass AND requested outputs
verified`, kept separate from the pre-execution ablation because HEP runtime
failure can occur for reasons unrelated to planner correctness. No execution
is performed during harness development or the model-free tests.

---

## 8. Raw result format

One immutable row per `model × request`, both conditions in the same row, in
CSV (analysis-friendly) and JSONL (complete provenance). Fields:

    evaluation_version, timestamp, heplocalagent_git_sha, heptoolbench_git_sha,
    model, ollama_host, model_metadata_path, request_id, workflow_family,
    paraphrase_index, request_text, benchmark_task_id, scorer_path,
    planner_route,
    initial_model_raw_path, initial_parse_success, initial_compile_success,
    initial_artifact_path, initial_score, initial_pass,
    initial_score_raw, initial_pass_raw, initial_physics_ok,
    full_status, full_ready, full_artifact_path, full_score, full_pass,
    full_score_raw, full_pass_raw, full_physics_ok,
    approval_decision, corrections_count, repair_attempts, fallback_used,
    llm_call_count, failure_category, row_kind, infrastructure_attempts,
    first_response_attempt, first_call_error, infrastructure_attempts_path,
    validation_issue_codes, run_record_path,
    replay_provenance_path, replay_first_was_replayed,
    replay_delegated_call_count,
    invalid_passed, false_rejection, recovered_initial_failure,
    invalid_passed_raw, false_rejection_raw, recovered_initial_failure_raw
    (the unsuffixed pass/score/flag columns are the PRIMARY physics-preserving
    normalized strict-pass; the *_raw columns are the labelled SECONDARY
    raw-artifact strict-pass sensitivity)

and, under `--execute`:
    execution_status, execution_success, lhe_verified, hepmc_verified,
    root_verified, analysis_success, cross_section, generated_events,
    runtime_seconds.

Raw model responses, exact artifacts (raw and normalized), scorer JSON, and
HEPLocalAgent run records are preserved under the run directory. Generated
HEP event files are never committed.

---

## 9. Reproducibility manifest

`run_agent_eval.py` writes `results/<run_label>/manifest.json` per live run:
HEPLocalAgent SHA, HEPToolBench SHA, harness SHA, date/time, OS/platform,
Python version, `OLLAMA_HOST`, exact model labels, `ollama show` output (or
saved equivalent), eval profile configuration, retry/repair limits, fallback
model, timeout values, model-generation parameters (as actually used,
including the explicit statement that no Ollama seed is set), request-set
SHA-256, and scorer-file SHA-256 values.

---

## 10. Request-set validation (model-free, runs before any live model)

`tests/test_requests.py` proves: 20 unique request IDs; every request maps to
exactly one benchmark task; all scorer paths exist; all requested physics is
within current HEPLocalAgent scope (capability check passes, route is
`full_structured`, extracted facts match ground truth); no paraphrase changes
the intended physics (extracted energy/nevents/stages equal ground truth);
all four families are represented equally (5 each); source task IDs are
correct; ground-truth fields are internally consistent; and the leakage rule
(§D) holds.

`tests/test_scoring_adapter.py` additionally proves, per family, that (a) the
hand-authored canonical known-correct artifact (the HEPToolBench `expected/`
artifact) raw-passes the unmodified scorer, and (b) one intentionally wrong
artifact (a physics mistake: wrong process, wrong beam energy, or wrong
stage) is rejected by the scorer in both raw and normalized forms — so the
adapter is proven to measure the intended distinction before any model runs.

---

## 11. Model-free harness tests (before any Ollama contact)

`tests/` cover, with controlled mock responses:

- A. initial correct → full correct (and full must not corrupt it);
- B. initial wrong → repair makes correct;
- C. initial wrong → repair stays wrong → blocked;
- D. initial correct → full agent must not corrupt it;
- E. malformed first model response;
- F. full agent READY with benchmark-invalid artifact → flagged `invalid_passed`;
- G. scorer-valid initial candidate blocked by full agent → flagged `false_rejection`;
- H. fallback repair path (exercised with a mock fallback profile);
- I. thin (semantic) planner path;
- J. full (structured) planner path.

The tests prove paired replay substitutes the identical first response in
both branches (byte-identical raw content). No live experiment runs until
these pass.

---

## 12. Live run procedure

After user approval: (1) **smoke run** — one request × one target model;
inspect raw initial response, baseline artifact, full artifact, scorer JSON,
run record, and replay provenance; (2) only if correct, run the full
20 × 3 matrix with resume-after-interruption; completed rows are never
overwritten. Expected model calls ≥ 60 (one recorded planner call per unit,
plus full-agent repair calls); the harness counts and reports actual calls.

---

## 13. Analysis

Per model and overall: the §5 metric table with counts + percentages + Wilson
95% intervals, per-family breakdowns, paired transition counts, and a single
paired comparison figure (initial vs full success per model) using the
PRIMARY normalized pass; the raw sensitivity is carried in the same plot-data
CSV. Publication numbers are generated only from the saved raw result files —
never typed into plotting scripts.

---

## 15/16. Interpretation rules (frozen)

- The desired result is **not assumed**. Small lift, rare repair, blocked
  valid candidates, and invalid artifacts reaching the gate are all reported.
- If the external scorer disagrees with the agent's own validator, the scorer
  is **not** altered after results exist; the disagreement is recorded and
  analysed (genuine validator gap vs. scorer/artifact mismatch) before any
  change.
- The scorer adapter decisions above are frozen before the complete live run.

---

## Audit appendix (from source, v0.1.1 / HEPToolBench v1.2)

- HEPLocalAgent HEAD: `feeccfb10fb424beaac3c6da4530128fc9cff585` (tag v0.1.1).
- HEPToolBench HEAD: `509205cd117136662d1ab82488f1ca280c838619`.
- Both trees clean at audit time; no tags/releases are created or moved; no
  pushes.
- Reused production entry points (unchanged): `prepare_end_to_end`,
  `run_preexecution_and_record`, `run_preexecution_loop`, `plan_workflow`,
  `plan_semantic_process`, `parse_planner_content`,
  `build_madgraph_workflow_artifact`, `apply_safe_grounding_corrections`,
  `validate_request_grounding`, `decide_approval`, `OllamaClient`,
  `PreExecutionRunRecord`.
- Documentation-vs-source discrepancy (recorded): some repository prose
  predates the current thin/full routing; the current source and tests are
  treated as authoritative.
- Artifact-format gaps vs. the frozen scorers (from source, pre-live):
  documented in §4 — `output <name>` naming (families 2/3/5), missing
  `define p` (family 5), `launch <name>` (family 5), missing `madspin=OFF`
  (family 5). Family 1 has no pass-critical format gap. Family 4 excluded
  (§D). Per revision 1.1, these gaps are handled by the PRIMARY
  physics-preserving normalized strict-pass; the raw strict-pass (which
  carries the format ceilings) is the secondary sensitivity.
