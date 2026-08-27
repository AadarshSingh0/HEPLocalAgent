# Paper B — Capability Supplement: Frozen Design

Status: **FROZEN before any live call** (2026-08-17).

This is a **small, later, reviewer-motivated supplementary coverage study**,
completely separate from the primary 20x3 experiment, the 50-request
reviewer extension, the 61-unit three-way baseline, and the containment
statistics. It exists only because the reviewer asked whether Paper B has
live evidence for three advertised capabilities — energy scans, MadAnalysis,
and user-UFO/BSM workflows — beyond the SM MG5/Pythia8/Delphes workflows that
dominated the large studies. It is **not** a prespecified primary
comparative experiment; no statistical generalization is claimed.

## 0. Release under evaluation

- HEPLocalAgent **v0.1.1** @ `feeccfb10fb424beaac3c6da4530128fc9cff585`.
- HEPToolBench @ `509205cd117136662d1ab82488f1ca280c838619` (not used by this
  supplement; no scorer changes).
- `git diff src/hep_agent/` must remain empty. No production patch is
  permitted. A capability that cannot be exercised from the released feature
  envelope is recorded as "not demonstrated by live supplementary evaluation".

## 1. Advertised-capability audit (from released source + tests)

### 1.1 Energy scans

| Question | Answer | Evidence |
|---|---|---|
| Implemented in v0.1.1? | **YES** | `src/hep_agent/scans/` (energy_scan.py, preparation.py, execution.py, text_parser.py, point_adapter.py) |
| Reachable from natural-language agent path? | **YES** | Released UI entry `prepare_energy_scan(prompt, client=OllamaClient(), profile=...)` (`web_app.py`); it parses the scan range deterministically, calls the ordinary planner once for the base workflow through `run_preexecution_loop`, then expands the grid deterministically. Same planner/grounding/validation/gate as the primary study. |
| Pre-existing positive test/fixture? | **YES** | `tests/test_energy_scan_preparation.py` (SCAN_REQUEST fixture), `tests/test_energy_scan*.py`, `tests/test_energy_scan_execution.py` |
| Scientifically valid request definable from pre-existing material? | **YES** | Use the frozen SCAN_REQUEST from `test_energy_scan_preparation.py` |
| Run without production modification? | **YES** | Released `prepare_energy_scan` / `execute_energy_scan` |
| Executable with the managed stack? | **YES** | `execute_energy_scan` with `ExistingPipelinePointExecutor` + `.hep-stack` manifest executables |

### 1.2 MadAnalysis

| Question | Answer | Evidence |
|---|---|---|
| Implemented in v0.1.1? | **YES** | `src/hep_agent/analysis/` (madanalysis.py builder, runner.py, runtime.py); `run_madanalysis_stage` in `orchestration/end_to_end.py` |
| Reachable from natural-language agent path? | **YES** | `pipeline.madanalysis=True` triggers the MA5 stage in `execute_prepared`; analysis-fact extraction routes rich MA5 requests to the full structured planner |
| Pre-existing positive test/fixture? | **YES** | `tests/test_end_to_end_madanalysis.py` (REQUEST fixture), `tests/test_structured_madanalysis.py`, `tests/test_madanalysis_builder.py` |
| Scientifically valid request definable from pre-existing material? | **YES** | Use the frozen REQUEST from `test_end_to_end_madanalysis.py` |
| Run without production modification? | **YES** | Released `prepare_end_to_end` / `run_end_to_end` |
| Executable with the managed stack? | **YES** | `.hep-stack/madanalysis5` launcher + manifest executable("madanalysis5") |

### 1.3 User-UFO / BSM workflows

| Question | Answer | Evidence |
|---|---|---|
| Implemented in v0.1.1? | **YES** (schema/validation/builder level) | `PhysicsModelSpec` with `ModelSource.USER_UFO`/`INSTALLED_UFO` + `model_path`; `validation/model_domain.py` statically parses UFO `particles.py`; builder emits `import model <path>` (`builders/madgraph.py:_render_model_import`) |
| Reachable from natural-language agent path? | **QUALIFIED** | The planner must emit `model.source=user_ufo` with a `model_path`; the request must supply a model path. Pre-existing positive tests: `test_genuine_user_ufo_with_path_is_untouched`, `test_ufo_domain_validation.py`. Whether the two models actually produce a valid user-UFO workflow live is exactly what this supplement measures. |
| Pre-existing positive test/fixture? | **YES** (domain/planner level) | `tests/test_ufo_domain_validation.py` (synthetic particles.py fixture), `tests/test_model_classification.py::test_genuine_user_ufo_with_path_is_untouched` |
| Scientifically valid request definable from pre-existing material? | **YES** | A request naming a real UFO model path from the managed stack with a BSM process. The managed stack ships the standard MG5 **MSSM_SLHA2** model (98 statically-parsed particle labels incl. `n1` neutralino, `x1+`/`x1-` charginos) — a real, MG5-usable UFO model. |
| Run without production modification? | **YES** | Released planner + builder + domain validation |
| Executable with the managed stack? | **QUALIFIED** | `MSSM_SLHA2` is a real MG5 model directory inside `.hep-stack/madgraph/models/`, so `import model <path>` is expected to work; the synthetic validation-only particles.py fixture is NOT used for runtime. |

## 2. Frozen request set (3 requests × 2 models = 6 live evaluations)

Two fixed, reliable models only:
- `qwen2.5-coder:7b` (profile `qwen25_7b`, 300 s timeout)
- `qwen3-coder-next:Q4_K_M` (profile `qwen3_next`, 180 s timeout)

Each request is sourced from pre-existing released tests/UI material and was
frozen before any live result. Expected outcomes are derived from the
pre-existing tests/specification, never from observed model output.

| request_id | capability | source | request text (verbatim) | expected outcome | expected intent |
|---|---|---|---|---|---|
| `cap_energy_scan` | Energy scan | `tests/test_energy_scan_preparation.py::SCAN_REQUEST` | "Simulate proton-proton collisions producing an electron and a positron. Do an energy scan from 1 TeV to 5 TeV in steps of 500 GeV. Generate 100 events per point." | execute_supported_workflow | e+ e-, scan 1–5 TeV step 500 GeV (9 points), 100 events/point, no Pythia8/Delphes/MA5 |
| `cap_madanalysis` | MadAnalysis | `tests/test_end_to_end_madanalysis.py::REQUEST` | "Simulate proton-proton collisions producing an electron and a positron at 13 TeV. Generate 10 events and create default plots." | execute_supported_workflow | e+ e-, 13 TeV, 10 events, madanalysis=True |
| `cap_user_ufo` | User-UFO/BSM | `tests/test_ufo_domain_validation.py` fixture semantics + real managed MSSM_SLHA2 model | "At a 13 TeV proton-proton collider, generate p p > x1+ x1- using the MSSM UFO model at <HEPLOCALAGENT_EVIDENCE_ROOT>/.hep-stack/madgraph/models/MSSM_SLHA2. Generate 100 events. Do not use Pythia8, Delphes, or MadAnalysis." | execute_supported_workflow | p p > x1+ x1-, model source=user_ufo with the given path, 13 TeV, 100 events, no Pythia8/Delphes/MA5 |

### 2.1 Execution paths per capability

- `cap_energy_scan` → released `prepare_energy_scan(prompt, client, profile)`.
  Success criterion (frozen): `PreparedEnergyScan.is_ready is True` (base
  workflow READY_FOR_APPROVAL + plan expanded), point count 9, 100
  events/point, base workflow intent e+ e- with no Pythia8/Delphes/MA5.
- `cap_madanalysis` → released `prepare_end_to_end(...)`. Success criterion
  (frozen): full status READY_FOR_APPROVAL, `pipeline.madanalysis=True`,
  intent preserved (e+ e-, 13 TeV, 10 events).
- `cap_user_ufo` → released `prepare_end_to_end(...)`. Success criterion
  (frozen): full status READY_FOR_APPROVAL, `model.source=user_ufo`,
  `model.model_path` set to the supplied path, process `p p > x1+ x1-`,
  13 TeV, 100 events, no Pythia8/Delphes/MA5.

### 2.2 Optional runtime confirmation (3A)

For each capability where **at least one model** produces a valid,
gate-approved artifact, attempt at most ONE representative runtime
confirmation using the existing managed `.hep-stack` and a modest resource
budget. Event counts defined BEFORE execution (small):

- Energy scan: execute a small scan (`execute_energy_scan` +
  `ExistingPipelinePointExecutor` with manifest executables), small
  events/point.
- MadAnalysis: execute the normal released MG5 → MA5 path with a small event
  sample (10 events as frozen).
- UFO: execute only because `MSSM_SLHA2` is a real MG5-usable model already
  present in the managed stack; small event sample. A validation-only
  synthetic particles.py fixture would NOT be sufficient, and none is used.

Preserve artifacts/logs/hashes. No event-count escalation. A failure is
data. If a capability cannot legitimately be runtime-tested from the
released envelope, document that and narrow the manuscript claim.

## 3. Infrastructure retry policy (inherited, frozen)

Same philosophy as the primary/extension: a transport/server/Ollama timeout
before a usable response is an infrastructure-invalid attempt, not a
semantic failure. Max 3 first-call attempts, unchanged per-profile timeouts.
No timeout increases. A genuine malformed/incorrect response is NOT retried.

## 4. Integrity

- No production-source changes (`git diff src/hep_agent/` empty).
- No scorer changes, no label changes after results, no merging into any
  existing denominator (primary 47, extension 50/160, matched 61,
  containment 96).
- All raw responses, WorkflowIntent, grounding/validation outcome,
  READY/non-READY, artifacts, intent-preservation, repair/fallback/call
  counts and provenance are preserved per unit.
- Files frozen: `DESIGN.md`, `requests.json`, `labels.json`, `source_map.json`
  (SHA-256 recorded in `hashes.sha256` BEFORE any live call).
