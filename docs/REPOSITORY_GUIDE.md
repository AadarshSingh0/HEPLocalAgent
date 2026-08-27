# HEP Agent Repository Guide

> This file is generated from the eligible repository working tree.
> The two generated inventory files are excluded to avoid self-reference.
> Do not edit the generated inventory manually. Update source files
> or module docstrings and rerun `scripts/generate_repository_guide.py`.

## Repository snapshot

- Generated: `2026-08-27T09:11:32.088528+00:00`
- Git branch: `publish-evaluation-results`
- Base/source commit at generation time: `feeccfb10fb424beaac3c6da4530128fc9cff585`
- Documented files: `267`

## Runtime architecture

The production design separates model interpretation from deterministic
workflow construction, validation, execution, and provenance.

1. **User interface:** Accepts Chat or Build-workflow requests and presents concise results with diagnostics available on demand. Relevant files: `src/hep_agent/ui/web_app.py`, `src/hep_agent/ui/cli.py`
2. **Request interpretation:** Routes explicit syntax and natural-language requests to the appropriate planning path. Relevant files: `src/hep_agent/models/semantic_process.py`, `src/hep_agent/models/planner.py`, `src/hep_agent/models/routing.py`
3. **Grounding and validation:** Preserves explicit user facts and rejects unsupported or ambiguous requests. Relevant files: `src/hep_agent/validation/grounding.py`, `src/hep_agent/validation/process_request.py`, `src/hep_agent/validation/analysis_request.py`
4. **Pre-execution orchestration:** Coordinates planning, bounded repair, validation, and approval. Relevant files: `src/hep_agent/orchestration/preexecution.py`, `src/hep_agent/orchestration/grounding_repair.py`, `src/hep_agent/orchestration/approval.py`
5. **Deterministic artifact construction:** Compiles the validated internal workflow into exact HEP-tool commands. Relevant files: `src/hep_agent/builders/madgraph.py`, `src/hep_agent/builders/madgraph_workflow.py`
6. **Execution and output verification:** Runs approved artifacts and verifies that required scientific outputs were actually produced. Relevant files: `src/hep_agent/orchestration/end_to_end.py`, `src/hep_agent/execution/result_parser.py`
7. **Run records and provenance:** Stores workflow, commands, model calls, validation results, execution status, timing, and output locations. Relevant files: `src/hep_agent/orchestration/run_record.py`

## Stability boundaries

- **Production runtime:** `src/hep_agent/`, `configs/`, and `prompts/`.
- **Regression protection:** `tests/`.
- **Offline experiments and measurements:** `evaluation/`.
- **Generated outputs:** root `results/`, ordinary `evaluation/results/` runs, and logs are intentionally omitted. The curated `evaluation/results/published/` evidence is included.
- **Maintenance utilities:** `scripts/`.

## Directory map

| Directory | Files | Purpose |
|---|---:|---|
| `.` | 11 | Repository root containing project metadata, documentation, configuration, source code, tests, and evaluation utilities. |
| `.streamlit` | 1 | Repository directory containing the files listed below. |
| `configs` | 2 | Runtime configuration, including agent profiles and local HEP-tool paths. |
| `docs` | 3 | Human-readable and machine-readable repository documentation. |
| `evaluation` | 7 | Offline evaluation scenarios and runners. These files measure agent behavior but are not required by the production runtime. |
| `evaluation/results` | 1 | Offline evaluation outputs; only the README and curated published evidence are version controlled. |
| `evaluation/results/published` | 6 | Curated Paper B evaluation evidence, provenance, and checksums. |
| `evaluation/results/published/capability_supplement` | 10 | Repository directory containing the files listed below. |
| `evaluation/results/published/native_baseline` | 9 | Repository directory containing the files listed below. |
| `evaluation/results/published/primary_end_to_end` | 11 | Repository directory containing the files listed below. |
| `evaluation/results/published/reviewer_extension` | 16 | Repository directory containing the files listed below. |
| `legacy_baseline` | 7 | Repository directory containing the files listed below. |
| `legacy_baseline/core` | 9 | Repository directory containing the files listed below. |
| `legacy_baseline/core/agents` | 1 | Repository directory containing the files listed below. |
| `prompts` | 3 | Version-controlled system prompts used by planners and repair models. |
| `scripts` | 16 | Repository maintenance, documentation, and developer utility scripts. |
| `src/hep_agent` | 3 | Main HEP-agent package. |
| `src/hep_agent/analysis` | 5 | Structured analysis planning, compilation, and result handling. |
| `src/hep_agent/builders` | 4 | Deterministic builders that compile validated workflows into MadGraph or related tool artifacts. |
| `src/hep_agent/doctor` | 6 | Repository directory containing the files listed below. |
| `src/hep_agent/evaluation` | 2 | Repository directory containing the files listed below. |
| `src/hep_agent/execution` | 5 | External-tool execution, output discovery, and execution-result handling. |
| `src/hep_agent/models` | 8 | Model clients, structured planners, semantic planning, repair, routing, and model-response normalization. |
| `src/hep_agent/orchestration` | 10 | Pre-execution, approval, repair, execution, end-to-end coordination, and run-record orchestration. |
| `src/hep_agent/runtime` | 4 | Repository directory containing the files listed below. |
| `src/hep_agent/scans` | 7 | Parameter-scan preparation, execution, and aggregation support. |
| `src/hep_agent/schemas` | 6 | Pydantic models defining the internal validated workflow language. |
| `src/hep_agent/ui` | 6 | Command-line and Streamlit web interfaces. |
| `src/hep_agent/validation` | 9 | Request grounding, capability checks, workflow validation, artifact validation, and safety checks. |
| `tests` | 77 | Unit and regression tests for production behavior. |
| `tests/acceptance` | 2 | Repository directory containing the files listed below. |

## File inventory

### `.`

Repository root containing project metadata, documentation, configuration, source code, tests, and evaluation utilities.

| File | Category | Purpose |
|---|---|---|
| `.gitignore` | project support | # Python caches |
| `AI_ASSISTED_DEVELOPMENT.md` | project support | Markdown documentation: AI-Assisted Development Disclosure. |
| `FOLDER_GUIDE.md` | project support | Markdown documentation: HEPLocalAgent — Practical Folder Guide. |
| `install.sh` | project support | Shell utility script. |
| `LICENSE` | project support | MIT License |
| `pyproject.toml` | package metadata | TOML project or tool configuration. |
| `README.md` | project support | Markdown documentation: HEPLocalAgent. |
| `requirements-web.txt` | project support | -r requirements.txt |
| `requirements.txt` | package metadata | pydantic>=2.7,<3 |
| `run_agent.sh` | project support | Shell utility script. |
| `uninstall.sh` | project support | Shell utility script. |

### `.streamlit`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `.streamlit/config.toml` | project support | TOML project or tool configuration. |

### `configs`

Runtime configuration, including agent profiles and local HEP-tool paths.

| File | Category | Purpose |
|---|---|---|
| `configs/agent_profiles.json` | configuration | JSON object with top-level keys: legacy_llama3, qwen_primary, qwen_cascade, starter_local. |
| `configs/local_paths.example.json` | configuration | JSON object with top-level keys: mg5_executable, madanalysis5_executable, madanalysis5_native_executable, root_config, root_path. |

### `docs`

Human-readable and machine-readable repository documentation.

| File | Category | Purpose |
|---|---|---|
| `docs/CHANGES_v0.1.0.md` | documentation | Markdown documentation: HEPLocalAgent v0.1.0 — Architecture and Change Record. |
| `docs/INSTALL_FOR_EVERYONE.md` | documentation | Markdown documentation: Independent HEPLocalAgent installation. |
| `docs/MACOS_VALIDATION_HANDOFF.md` | documentation | Markdown documentation: Apple Silicon fresh-stack validation handoff. |

### `evaluation`

Offline evaluation scenarios and runners. These files measure agent behavior but are not required by the production runtime.

| File | Category | Purpose |
|---|---|---|
| `evaluation/preexecution_scenarios_v1.json` | evaluation | Evaluation scenario definition containing 10 scenarios. |
| `evaluation/process_generalization_v1.json` | evaluation | Evaluation scenario definition containing 24 scenarios. |
| `evaluation/run_model_structure_comparison.py` | evaluation | Compare raw planner ability with final structured-agent output. |
| `evaluation/run_preexecution_eval.py` | evaluation | Run the frozen pre-execution generalization evaluation. |
| `evaluation/run_process_generalization_v1.py` | evaluation | Run the frozen process-generalization suite without HEP execution. |
| `evaluation/run_process_semantic_comparison.py` | evaluation | Test pure natural-language-to-MadGraph process interpretation. |
| `evaluation/run_semantic_agent_eval.py` | evaluation | Evaluate the thin semantic planner plus deterministic compiler. |

### `evaluation/results`

Offline evaluation outputs; only the README and curated published evidence are version controlled.

| File | Category | Purpose |
|---|---|---|
| `evaluation/results/README.md` | evaluation | Markdown documentation: Evaluation results. |

### `evaluation/results/published`

Curated Paper B evaluation evidence, provenance, and checksums.

| File | Category | Purpose |
|---|---|---|
| `evaluation/results/published/CHECKSUMS.sha256` | evaluation | 9d5d39d92d10fad6121be052b1cb9e43638e15f07f5fb934c9392072a54dad17 README.md |
| `evaluation/results/published/privacy_scan_report.txt` | evaluation | PRIVACY SCAN STATUS: PASS |
| `evaluation/results/published/publication_manifest.csv` | evaluation | suite,published_file,source_file,source_sha256,published_sha256,transformation,bytes |
| `evaluation/results/published/README.md` | evaluation | Markdown documentation: HEPLocalAgent curated evaluation-results review package. |
| `evaluation/results/published/source_inventory.csv` | evaluation | candidate_path,suite,run_timestamp,runner_commit,scenario_hash,models_profiles,number_of_trials,completeness,paper_relevance,privacy_findings,authority_decision |
| `evaluation/results/published/validation_report.txt` | evaluation | VALIDATION STATUS: PASS |

### `evaluation/results/published/capability_supplement`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `evaluation/results/published/capability_supplement/DESIGN.md` | evaluation | Markdown documentation: Paper B — Capability Supplement: Frozen Design. |
| `evaluation/results/published/capability_supplement/labels.json` | evaluation | JSON object with top-level keys: evaluation_version, frozen_on, note, outcome_classes, expected_accept, expected_non_execution. |
| `evaluation/results/published/capability_supplement/README.md` | evaluation | Markdown documentation: Capability supplement. |
| `evaluation/results/published/capability_supplement/requests.json` | evaluation | JSON object with top-level keys: evaluation_version, frozen_on, scope_note, requests. |
| `evaluation/results/published/capability_supplement/results.csv` | evaluation | model,request_id,request_class,expected_outcome,outcome_class,correct_outcome,full_ready,intent_preserved,intent_differences,planner_route,llm_call_count,repair_attempts,infrastructure_attempts,runtime_status,runtime_verified,runtime_detail |
| `evaluation/results/published/capability_supplement/rows.jsonl` | evaluation | {"approval_decision": "explicit_confirmation_required", "case_dir": "evaluation/paper_b_capability_supplement/results/20260817T071500Z/cases/qwen2.5-coder_7b/cap_energy_scan", "correct_outcome": true, "corrections_count": 0, "evaluation_ver |
| `evaluation/results/published/capability_supplement/runtime_summary.json` | evaluation | JSON list containing 1 entries. |
| `evaluation/results/published/capability_supplement/source_hashes.sha256` | evaluation | 72d30440ae5d363e5db01db6bc4bb98baa9c8259f59b7b3cd25f4ed885f8059b evaluation/paper_b_capability_supplement/DESIGN.md |
| `evaluation/results/published/capability_supplement/source_map.json` | evaluation | JSON object with top-level keys: evaluation_version, frozen_on, note, requests. |
| `evaluation/results/published/capability_supplement/summary.md` | evaluation | Markdown documentation: Capability Supplement Results — Paper B. |

### `evaluation/results/published/native_baseline`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `evaluation/results/published/native_baseline/DESIGN.md` | evaluation | Markdown documentation: NATIVE_BASELINE_DESIGN — Baseline A: LLM → native HEP commands. |
| `evaluation/results/published/native_baseline/infrastructure_attempts.jsonl` | evaluation | {"attempt": 1, "error": "OllamaClientError: The Ollama request timed out.", "model": "qwen3-coder-next:Q4_K_M", "outcome": "timeout", "raw_path": "<HEPLOCALAGENT_EVIDENCE_ROOT>/evaluation/paper_b_reviewer_extension/results/20260816T080835Z/ |
| `evaluation/results/published/native_baseline/manifest.json` | evaluation | JSON object with top-level keys: design_sha256, evaluation_version, heplocalagent_git_sha, models, ollama_host, primary_requests_sha256, …. |
| `evaluation/results/published/native_baseline/prompt.txt` | evaluation | You are an expert in MadGraph5_aMC@NLO. Write the complete native MadGraph |
| `evaluation/results/published/native_baseline/README.md` | evaluation | Markdown documentation: Native baseline. |
| `evaluation/results/published/native_baseline/rows.csv` | evaluation | evaluation_version,timestamp,model,ollama_host,request_id,workflow_family,benchmark_task_id,request_text,row_kind,infrastructure_attempts,first_call_error,raw_output_path,task_pass,task_pass_raw,normalized_score,raw_score,normalized_artifac |
| `evaluation/results/published/native_baseline/rows.jsonl` | evaluation | {"benchmark_task_id": "mg_basic_001", "evaluation_version": "paper_b_reviewer_extension_native_baseline_v1.0", "first_call_error": null, "infrastructure_attempts": 1, "model": "qwen2.5-coder:7b", "normalized_artifact_path": "<HEPLOCALAGENT_ |
| `evaluation/results/published/native_baseline/three_way_results.csv` | evaluation | model,matched_n,A_native_pass,B_builder_pass,C_full_pass,A_pass_rate,B_pass_rate,C_pass_rate,A_to_B_improve,B_to_C_improve,A_to_C_improve,A_pass_C_fail,B_pass_C_fail,A_fail_B_fail_C_pass,fail_fail_fail |
| `evaluation/results/published/native_baseline/three_way_summary.md` | evaluation | Markdown documentation: Three-way baseline comparison (Paper B). |

### `evaluation/results/published/primary_end_to_end`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `evaluation/results/published/primary_end_to_end/DESIGN.md` | evaluation | Markdown documentation: Paper B — End-to-End Guarded-Agent Evaluation: Frozen Design. |
| `evaluation/results/published/primary_end_to_end/infrastructure_attempts.jsonl` | evaluation | {"attempt": 1, "case_root": "<HEPLOCALAGENT_EVIDENCE_ROOT>/evaluation/paper_b_end_to_end/results/20260815T110701Z/cases", "error": "OllamaClientError: The Ollama request timed out.", "model": "qwen3-coder-next:Q4_K_M", "outcome": "timeout", |
| `evaluation/results/published/primary_end_to_end/manifest.json` | evaluation | JSON object with top-level keys: evaluation_version, fallback_model, generation_settings, heplocalagent_git_dirty, heplocalagent_git_sha, heptoolbench_git_dirty, …. |
| `evaluation/results/published/primary_end_to_end/profiles.json` | evaluation | JSON object with top-level keys: qwen25_7b, qwen3_next, llama33_70b. |
| `evaluation/results/published/primary_end_to_end/README.md` | evaluation | Markdown documentation: Primary end-to-end evaluation. |
| `evaluation/results/published/primary_end_to_end/requests.json` | evaluation | JSON object with top-level keys: evaluation_version, frozen_on, scope_note, requests. |
| `evaluation/results/published/primary_end_to_end/results_summary.json` | evaluation | JSON object with top-level keys: n_infrastructure_unavailable, n_legacy_infrastructure_invalid, n_rows, n_semantic, operational, overall, …. |
| `evaluation/results/published/primary_end_to_end/results_summary.md` | evaluation | Markdown documentation: Paper B end-to-end results summary. |
| `evaluation/results/published/primary_end_to_end/rows.csv` | evaluation | evaluation_version,timestamp,heplocalagent_git_sha,heptoolbench_git_sha,model,ollama_host,model_metadata_path,request_id,workflow_family,paraphrase_index,request_text,benchmark_task_id,scorer_path,planner_route,initial_model_raw_path,initia |
| `evaluation/results/published/primary_end_to_end/rows.jsonl` | evaluation | {"evaluation_version": "paper_b_end_to_end_v1.0", "timestamp": "20260815T110756Z", "heplocalagent_git_sha": "feeccfb10fb424beaac3c6da4530128fc9cff585", "heptoolbench_git_sha": "509205cd117136662d1ab82488f1ca280c838619", "model": "qwen2.5-co |
| `evaluation/results/published/primary_end_to_end/task_map.json` | evaluation | JSON object with top-level keys: description, families. |

### `evaluation/results/published/reviewer_extension`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `evaluation/results/published/reviewer_extension/by_class.csv` | evaluation | request_class,n_units,n_semantic,n_infra_unavailable,n_valid,n_non_exec,correct_outcome,false_acceptance,false_rejection,intent_preserved |
| `evaluation/results/published/reviewer_extension/by_model.csv` | evaluation | model,n_units,n_semantic,n_infra_unavailable,n_valid,n_non_exec,correct_accept,false_reject,accepted_valid,intent_preserved,correct_reject,false_accept,repair_used,corrections_used,fallback_used |
| `evaluation/results/published/reviewer_extension/DESIGN.md` | evaluation | Markdown documentation: Paper B — Reviewer-Extension (50-request containment + baseline) Frozen Design. |
| `evaluation/results/published/reviewer_extension/infrastructure_attempts.jsonl` | evaluation | {"attempt": 1, "error": "OllamaClientError: The Ollama request timed out.", "model": "granite4:32b-a9b-h", "outcome": "timeout", "raw_path": "<HEPLOCALAGENT_EVIDENCE_ROOT>/evaluation/paper_b_reviewer_extension/results/20260816T075420Z/cases |
| `evaluation/results/published/reviewer_extension/LABEL_PROVENANCE.md` | evaluation | Markdown documentation: LABEL_PROVENANCE — Reviewer-Extension Requests and Labels. |
| `evaluation/results/published/reviewer_extension/labels.json` | evaluation | JSON object with top-level keys: evaluation_version, frozen_on, note, outcome_classes, expected_accept, expected_non_execution. |
| `evaluation/results/published/reviewer_extension/manifest.json` | evaluation | JSON object with top-level keys: design_sha256, evaluation_version, extension_requests_sha256, heplocalagent_git_sha, labels_sha256, model_profiles, …. |
| `evaluation/results/published/reviewer_extension/MODEL_SELECTION.md` | evaluation | Markdown documentation: MODEL_SELECTION — Reviewer-Extension Model Set (frozen 2026-08-16). |
| `evaluation/results/published/reviewer_extension/profiles.json` | evaluation | JSON object with top-level keys: qwen25_7b, qwen3_next, qwen25_14b, granite4_32b. |
| `evaluation/results/published/reviewer_extension/README.md` | evaluation | Markdown documentation: Reviewer extension. |
| `evaluation/results/published/reviewer_extension/requests.json` | evaluation | JSON object with top-level keys: evaluation_version, frozen_on, scope_note, requests. |
| `evaluation/results/published/reviewer_extension/results.csv` | evaluation | model,request_id,request_class,expected_outcome,is_extension,row_kind,full_status,full_ready,correct_outcome,false_acceptance,false_rejection,intent_preserved,repair_attempts,corrections_count,fallback_used,llm_call_count,infrastructure_att |
| `evaluation/results/published/reviewer_extension/rows.csv` | evaluation | approval_decision,correct_outcome,corrections_count,evaluation_version,expected_outcome,failure_category,fallback_used,false_acceptance,false_rejection,first_call_error,first_response_attempt,full_ready,full_status,infrastructure_attempts,i |
| `evaluation/results/published/reviewer_extension/rows.jsonl` | evaluation | {"approval_decision": "auto_confirm", "correct_outcome": true, "corrections_count": 2, "evaluation_version": "paper_b_reviewer_extension_v1.0", "expected_outcome": "execute_supported_workflow", "failure_category": null, "fallback_used": fal |
| `evaluation/results/published/reviewer_extension/source_map.json` | evaluation | JSON object with top-level keys: evaluation_version, frozen_on, note, requests. |
| `evaluation/results/published/reviewer_extension/summary.md` | evaluation | Markdown documentation: Reviewer-extension results (Paper-B reviewer response). |

### `legacy_baseline`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `legacy_baseline/app.py` | project support | Python package or support module. |
| `legacy_baseline/config.py` | project support | Portable runtime configuration for the retained legacy baseline. |
| `legacy_baseline/main.py` | project support | MadGraph5 File Generator ======================== Usage: python main.py "p p > e- e+" python main.py "p p > t t~ at 14 TeV with 50000 events, run pythia8" python main.py --backend openai --base-url http://localhost:8000/v1 "p p > h at 13 TeV" |
| `legacy_baseline/README_legacy.md` | project support | Markdown documentation: MadGraph5 File Generator. |
| `legacy_baseline/requirements.txt` | project support | requests |
| `legacy_baseline/test_plots.py` | project support | Python package or support module. |
| `legacy_baseline/tests.py` | project support | Tests for the MadGraph tree builder. Run with: python -m pytest tests.py -v |

### `legacy_baseline/core`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `legacy_baseline/core/__init__.py` | project support | Python package or support module. |
| `legacy_baseline/core/analyser.py` | project support | Python module exposing: run_post_analysis. |
| `legacy_baseline/core/bootstrap.py` | project support | Python module exposing: heal_environment. |
| `legacy_baseline/core/constants.py` | project support | Python package or support module. |
| `legacy_baseline/core/extractor.py` | project support | Parameter Extractor =================== Sends user input to a local Llama3 8B (via Ollama) or any OpenAI-compatible endpoint and extracts ONLY structured JSON — never MadGraph syntax. |
| `legacy_baseline/core/result_parser.py` | project support | Python module exposing: parse_cross_section. |
| `legacy_baseline/core/runner.py` | project support | Python module exposing: run_mg5_script. |
| `legacy_baseline/core/tree_builder.py` | project support | MadGraph5 Tree Builder ====================== Deterministic syntax assembler. Takes structured JSON from the LLM and walks a decision tree to produce correct MadGraph5 files. |
| `legacy_baseline/core/validator.py` | project support | Python module exposing: normalize_particle, normalize_model, safe_name, make_unique_name, validate_and_normalize. |

### `legacy_baseline/core/agents`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `legacy_baseline/core/agents/confirmation.py` | project support | Python module exposing: get_confirmation_summary. |

### `prompts`

Version-controlled system prompts used by planners and repair models.

| File | Category | Purpose |
|---|---|---|
| `prompts/FOLDER_GUIDE.md` | prompt | Markdown documentation: Prompts — Practical Guide. |
| `prompts/planner_system.txt` | prompt | You are the structured planning component of a local collider-physics agent. |
| `prompts/repair_system.txt` | prompt | You repair a structured collider workflow that failed deterministic validation. |

### `scripts`

Repository maintenance, documentation, and developer utility scripts.

| File | Category | Purpose |
|---|---|---|
| `scripts/audit_managed_stack.py` | maintenance | Audit manifest ownership and native HEP linkage without external discovery. |
| `scripts/bootstrap_independent_hep_agent.sh` | maintenance | Shell utility script. |
| `scripts/bootstrap_local_hep_agent.sh` | maintenance | Shell utility script. |
| `scripts/configure_madanalysis_runtime.py` | maintenance | Pin an existing MadAnalysis 5 installation to managed dependencies. |
| `scripts/finalize_managed_stack.py` | maintenance | Configure, smoke-test, audit, and record one clone-owned HEP stack. |
| `scripts/generate_repository_guide.py` | maintenance | Generate an accurate repository guide and machine-readable manifest. |
| `scripts/install_managed_hep_stack.sh` | maintenance | Shell utility script. |
| `scripts/install_managed_hep_stack_macos.sh` | maintenance | Shell utility script. |
| `scripts/managed_stack_launcher.py` | maintenance | Clone-local launcher that cannot inherit or discover external HEP tools. |
| `scripts/managed_stack_ownership.sh` | maintenance | Shell utility script. |
| `scripts/record_acceptance.py` | maintenance | Record real local-model outputs for the acceptance scenarios. |
| `scripts/run_managed_agent.sh` | maintenance | Shell utility script. |
| `scripts/uninstall_independent_hep_agent.sh` | maintenance | Shell utility script. |
| `scripts/validate_full_stack.py` | maintenance | Validate MadGraph, Pythia8, Delphes, and MadAnalysis without Ollama. |
| `scripts/validate_macos_root_package.py` | maintenance | Fail-closed validation of the exact ROOT package selected by Conda. |
| `scripts/validate_madanalysis_runtime.py` | maintenance | Noninteractive startup smoke test for one configured MA5 runtime. |

### `src/hep_agent`

Main HEP-agent package.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/__init__.py` | production | Local HEP agent package. |
| `src/hep_agent/conversation.py` | production | Conversational routing for the local HEP agent. |
| `src/hep_agent/selftest.py` | production | Deterministic, tool-aware installation self-test. |

### `src/hep_agent/analysis`

Structured analysis planning, compilation, and result handling.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/analysis/__init__.py` | production | Deterministic post-processing analysis tools. |
| `src/hep_agent/analysis/FOLDER_GUIDE.md` | production | Markdown documentation: Analysis — Practical Guide. |
| `src/hep_agent/analysis/madanalysis.py` | production | Deterministic MadAnalysis 5 script construction. |
| `src/hep_agent/analysis/runner.py` | production | Safe subprocess execution for deterministic MadAnalysis artifacts. |
| `src/hep_agent/analysis/runtime.py` | production | Runtime isolation for managed MadAnalysis 5 executions. |

### `src/hep_agent/builders`

Deterministic builders that compile validated workflows into MadGraph or related tool artifacts.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/builders/__init__.py` | production | Public imports for deterministic artifact builders. |
| `src/hep_agent/builders/FOLDER_GUIDE.md` | production | Markdown documentation: Builders — Practical Guide. |
| `src/hep_agent/builders/madgraph.py` | production | Deterministic MadGraph process builder. |
| `src/hep_agent/builders/madgraph_workflow.py` | production | Deterministic MadGraph launch-workflow builder. |

### `src/hep_agent/doctor`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/doctor/__init__.py` | production | HEP-agent environment doctor. |
| `src/hep_agent/doctor/checks.py` | production | Environment and installation checks for the HEP agent. |
| `src/hep_agent/doctor/cli.py` | production | Command-line interface for the HEP-agent doctor. |
| `src/hep_agent/doctor/managed_stack.py` | production | Doctor checks for the authoritative clone-owned HEP stack. |
| `src/hep_agent/doctor/models.py` | production | Data models for HEP-agent environment diagnostics. |
| `src/hep_agent/doctor/render.py` | production | Text rendering for doctor reports. |

### `src/hep_agent/evaluation`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/evaluation/__init__.py` | production | Evaluation helpers for the local HEP agent. |
| `src/hep_agent/evaluation/preexecution.py` | production | Deterministic checks for frozen pre-execution evaluation scenarios. |

### `src/hep_agent/execution`

External-tool execution, output discovery, and execution-result handling.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/execution/__init__.py` | production | Public imports for external execution and result parsing. |
| `src/hep_agent/execution/FOLDER_GUIDE.md` | production | Markdown documentation: Execution — Practical Guide. |
| `src/hep_agent/execution/madgraph_runner.py` | production | Safe subprocess runner for validated MadGraph workflows. |
| `src/hep_agent/execution/outcome.py` | production | Validation of externally executed HEP workflow outcomes. |
| `src/hep_agent/execution/result_parser.py` | production | Deterministic parsing of completed MadGraph executions. |

### `src/hep_agent/models`

Model clients, structured planners, semantic planning, repair, routing, and model-response normalization.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/models/__init__.py` | production | Public imports for model clients, planners, repair, and routing. |
| `src/hep_agent/models/FOLDER_GUIDE.md` | production | Markdown documentation: Models — Practical Guide. |
| `src/hep_agent/models/ollama.py` | production | Small Ollama client used by the local HEP agent. |
| `src/hep_agent/models/planner.py` | production | Structured local-LLM planner for collider workflows. |
| `src/hep_agent/models/repair.py` | production | Validator-guided repair of structured collider workflows. |
| `src/hep_agent/models/routing.py` | production | Configuration models for local-agent routing profiles. |
| `src/hep_agent/models/semantic_process.py` | production | Thin semantic planning for collider-process requests. |
| `src/hep_agent/models/workflow_payload.py` | production | Safe structural normalization of model-produced workflow JSON. |

### `src/hep_agent/orchestration`

Pre-execution, approval, repair, execution, end-to-end coordination, and run-record orchestration.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/orchestration/__init__.py` | production | Public imports for agent orchestration. |
| `src/hep_agent/orchestration/analysis_stage.py` | production | Orchestration for separate MadAnalysis post-processing. |
| `src/hep_agent/orchestration/approval.py` | production | Approval policy for validated collider workflows. |
| `src/hep_agent/orchestration/end_to_end.py` | production | Complete local-agent preparation and external execution. |
| `src/hep_agent/orchestration/FOLDER_GUIDE.md` | production | Markdown documentation: Orchestration — Practical Guide. |
| `src/hep_agent/orchestration/grounding_repair.py` | production | Safe deterministic corrections based on explicit user statements. |
| `src/hep_agent/orchestration/preexecution.py` | production | Central pre-execution loop for the local collider agent. |
| `src/hep_agent/orchestration/process_reconciliation.py` | production | Deterministic reconciliation of inclusive and partonic processes. |
| `src/hep_agent/orchestration/run_record.py` | production | Save reproducible records of local-agent pre-execution runs. |
| `src/hep_agent/orchestration/terminal_approval.py` | production | Terminal approval interface for collider-agent execution. |

### `src/hep_agent/runtime`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/runtime/__init__.py` | production | Authoritative managed HEP stack manifest and process environment. |
| `src/hep_agent/runtime/audit.py` | production | Live native-linkage audit derived only from a validated stack manifest. |
| `src/hep_agent/runtime/linkage.py` | production | Platform-neutral native linkage inspection for the managed HEP stack. |
| `src/hep_agent/runtime/stack.py` | production | One clone-owned contract for every HEP subprocess. |

### `src/hep_agent/scans`

Parameter-scan preparation, execution, and aggregation support.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/scans/__init__.py` | production | Deterministic multi-run scan planning and execution. |
| `src/hep_agent/scans/energy_scan.py` | production | Deterministic collider-energy scan planning. |
| `src/hep_agent/scans/execution.py` | production | Sequential execution and deterministic analysis of energy scans. |
| `src/hep_agent/scans/FOLDER_GUIDE.md` | production | Markdown documentation: Scans — Practical Guide. |
| `src/hep_agent/scans/point_adapter.py` | production | Adapter from deterministic scan points to the existing HEP pipeline. |
| `src/hep_agent/scans/preparation.py` | production | Prepare natural-language energy scans without executing HEP tools. |
| `src/hep_agent/scans/text_parser.py` | production | Deterministic natural-language parsing for energy-scan ranges. |

### `src/hep_agent/schemas`

Pydantic models defining the internal validated workflow language.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/schemas/__init__.py` | production | Public imports for the collider-workflow schema. |
| `src/hep_agent/schemas/analysis.py` | production | Restricted structured language for MadAnalysis 5 requests. |
| `src/hep_agent/schemas/FOLDER_GUIDE.md` | production | Markdown documentation: Schemas — Practical Guide. |
| `src/hep_agent/schemas/PROCESS_SCHEMA_V1.md` | production | Markdown documentation: Process Schema Version 1. |
| `src/hep_agent/schemas/SCHEMA_DESIGN.md` | production | Markdown documentation: General Collider-Workflow Schema Design. |
| `src/hep_agent/schemas/workflow.py` | production | Structured collider-workflow schema. |

### `src/hep_agent/ui`

Command-line and Streamlit web interfaces.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/ui/__init__.py` | production | User interfaces for the local HEP agent. |
| `src/hep_agent/ui/cli.py` | production | Command-line interface for the local HEP agent. |
| `src/hep_agent/ui/FOLDER_GUIDE.md` | production | Markdown documentation: User Interfaces — Practical Guide. |
| `src/hep_agent/ui/web_app.py` | production | Streamlit research console for the local HEP agent. |
| `src/hep_agent/ui/web_launcher.py` | production | Console launcher for the Streamlit HEP-agent interface. |
| `src/hep_agent/ui/web_support.py` | production | Non-visual support functions for the local Streamlit interface. |

### `src/hep_agent/validation`

Request grounding, capability checks, workflow validation, artifact validation, and safety checks.

| File | Category | Purpose |
|---|---|---|
| `src/hep_agent/validation/__init__.py` | production | Public imports for deterministic validation. |
| `src/hep_agent/validation/analysis_request.py` | production | Ground MadAnalysis intent in explicit user instructions. |
| `src/hep_agent/validation/core.py` | production | Deterministic validation for collider workflows and artifacts. |
| `src/hep_agent/validation/FOLDER_GUIDE.md` | production | Markdown documentation: Validation — Practical Guide. |
| `src/hep_agent/validation/grounding.py` | production | Ground structured workflows in explicit facts from the user request. |
| `src/hep_agent/validation/madgraph_workflow.py` | production | Validation of complete deterministic MG5 workflows. |
| `src/hep_agent/validation/model_domain.py` | production | Model-relative domain validation for collider workflows. |
| `src/hep_agent/validation/process_request.py` | production | Parse explicit MadGraph-style process syntax from user requests. |
| `src/hep_agent/validation/workflow_request.py` | production | Conservative validation of user-supplied workflow requirements. |

### `tests`

Unit and regression tests for production behavior.

| File | Category | Purpose |
|---|---|---|
| `tests/FOLDER_GUIDE.md` | test | Markdown documentation: Tests — Practical Guide. |
| `tests/test_acceptance.py` | test | Data-driven acceptance harness. |
| `tests/test_agentic_repair_loop.py` | test | Tests for bounded repair retries and larger-model escalation. |
| `tests/test_analysis_request_grounding.py` | test | Tests for deterministic analysis-request grounding. |
| `tests/test_analysis_stage.py` | test | Tests for separate MadAnalysis post-processing orchestration. |
| `tests/test_approval.py` | test | Tests for the approval and five-second auto-confirm policy. |
| `tests/test_bootstrap_scripts.py` | test | Static tests for beginner installation shell scripts. |
| `tests/test_cli.py` | test | Tests for the local HEP-agent command parser. |
| `tests/test_configure_madanalysis_runtime.py` | test | Tests for persistent MadAnalysis runtime configuration. |
| `tests/test_conversation.py` | test | Tests for conversational versus workflow routing. |
| `tests/test_doctor.py` | test | Tests for doctor report models and rendering. |
| `tests/test_doctor_integrated_tools.py` | test | Doctor checks for integrated HEP-tool installations. |
| `tests/test_domain_repair.py` | test | Tests that model-domain violations are repairable, not just blocking. |
| `tests/test_end_to_end.py` | test | Tests for the full agent through external execution. |
| `tests/test_end_to_end_madanalysis.py` | test | End-to-end tests including separate MA5 post-processing. |
| `tests/test_energy_scan.py` | test | Tests for deterministic collider-energy scan planning. |
| `tests/test_energy_scan_execution.py` | test | Tests for sequential scan execution and aggregation. |
| `tests/test_energy_scan_point_adapter.py` | test | Tests for the existing-pipeline scan-point adapter. |
| `tests/test_energy_scan_preparation.py` | test | Tests for energy-scan preparation through the existing planner. |
| `tests/test_energy_scan_progress.py` | test | Tests for energy-scan progress callbacks. |
| `tests/test_energy_scan_range.py` | test | Tests for unit-safe deterministic energy-scan ranges. |
| `tests/test_energy_scan_text_parser.py` | test | Tests for deterministic natural-language energy-scan parsing. |
| `tests/test_event_output_levels.py` | test | Tests for LHE, HepMC, and Delphes ROOT discovery. |
| `tests/test_execution_outcome.py` | test | Tests for validated external-execution outcomes. |
| `tests/test_explicit_process_authority.py` | test | Explicit MadGraph-style syntax must be authoritative. |
| `tests/test_full_stack_validation_script.py` | test | Tests for the model-free installed-tool validation utility. |
| `tests/test_grounding.py` | test | Tests for grounding planner output in explicit user facts. |
| `tests/test_grounding_repair.py` | test | Tests for safe deterministic grounding corrections. |
| `tests/test_legacy_config.py` | test | Regression tests for portable legacy-baseline runtime configuration. |
| `tests/test_macos_managed_stack.py` | test | Hermetic Darwin coverage for the clone-owned managed HEP stack. |
| `tests/test_madanalysis_builder.py` | test | Tests for deterministic MadAnalysis script construction. |
| `tests/test_madanalysis_negation.py` | test | Regression tests for explicit MadAnalysis negation. |
| `tests/test_madanalysis_pipeline_separation.py` | test | Tests that MA5 runs separately from the MG5 launch interface. |
| `tests/test_madanalysis_preview.py` | test | Tests for deterministic MA5 command previews. |
| `tests/test_madanalysis_runner.py` | test | Tests for the safe MadAnalysis subprocess runner. |
| `tests/test_madanalysis_runtime.py` | test | Tests for deterministic MadAnalysis runtime isolation. |
| `tests/test_madgraph_builder.py` | test | Tests for deterministic MadGraph process construction. |
| `tests/test_madgraph_runner.py` | test | Tests for the safe MadGraph subprocess runner. |
| `tests/test_madgraph_workflow.py` | test | Tests for full deterministic MG5 launch workflows. |
| `tests/test_model_classification.py` | test | Tests for tolerant built-in model classification in the planner parser. |
| `tests/test_model_domain_validation.py` | test | Tests for model-relative particle-domain validation. |
| `tests/test_models.py` | test | Tests for Ollama communication and model profiles. |
| `tests/test_noninteractive_madgraph.py` | test | Tests for noninteractive MadGraph execution settings. |
| `tests/test_planner.py` | test | Tests for the structured collider planner. |
| `tests/test_planner_analysis.py` | test | Tests for structured-analysis planner integration. |
| `tests/test_planner_builtin_models.py` | test | Regression tests for recognised built-in model normalisation. |
| `tests/test_planner_payload_sanitization.py` | test | Regression tests for planner payload sanitization. |
| `tests/test_planner_retry_loop.py` | test | Tests for initial planner retries and accounting. |
| `tests/test_preexecution.py` | test | Tests for the complete pre-execution agent loop. |
| `tests/test_preexecution_evaluation.py` | test | Tests for deterministic pre-execution evaluation checks. |
| `tests/test_prepared_end_to_end.py` | test | Tests for separately preparing and executing one workflow. |
| `tests/test_process_constraint_grounding.py` | test | Tests for inclusive process grounding. |
| `tests/test_process_reconciliation.py` | test | Tests for inclusive-process reconciliation. |
| `tests/test_repair.py` | test | Tests for validator-guided structured repair. |
| `tests/test_repair_prompt_contract.py` | test | Tests for the structured repair-prompt contract. |
| `tests/test_repository_guide.py` | test | Regression tests for portable, fresh generated repository documentation. |
| `tests/test_request_normalization.py` | test | Tests for harmless user-request whitespace normalization. |
| `tests/test_result_parser.py` | test | Tests for deterministic MadGraph result parsing. |
| `tests/test_run_record.py` | test | Tests for reproducible pre-execution run records. |
| `tests/test_selftest.py` | test | Tests for the tool-aware installation self-test. |
| `tests/test_semantic_pipeline_intent.py` | test | Tests for model-led pipeline-stage interpretation on the semantic route. |
| `tests/test_semantic_process.py` | test | Tests for the thin semantic process compiler. |
| `tests/test_semantic_process_routing.py` | test | Tests for explicit-versus-semantic production routing. |
| `tests/test_stack_runtime.py` | test | Hermetic tests for the authoritative clone-owned HEP stack contract. |
| `tests/test_structured_madanalysis.py` | test | Tests for structured deterministic MA5 compilation. |
| `tests/test_terminal_approval.py` | test | Tests for the terminal approval interface. |
| `tests/test_ufo_domain_validation.py` | test | Tests for model-aware domain validation of UFO/BSM models. |
| `tests/test_validate_madanalysis_runtime.py` | test | Tests for the installer MA5 smoke-test command. |
| `tests/test_validation.py` | test | Tests for deterministic workflow and artifact validation. |
| `tests/test_web_approval_countdown.py` | test | Tests for automatic web-approval countdown calculations. |
| `tests/test_web_failure_issues.py` | test | Tests for failed-request validation details in the web interface. |
| `tests/test_web_request_state.py` | test | Tests for Streamlit request-input state decisions. |
| `tests/test_web_support.py` | test | Tests for persistent web-interface history helpers. |
| `tests/test_web_tool_status.py` | test | Tests for web-interface HEP tool health detection. |
| `tests/test_workflow_payload_normalization.py` | test | Tests for safe pre-validation workflow JSON normalization. |
| `tests/test_workflow_request.py` | test | Tests for minimum executable workflow requirements. |
| `tests/test_workflow_schema.py` | test | Tests for the general collider-workflow schema. |

### `tests/acceptance`

Repository directory containing the files listed below.

| File | Category | Purpose |
|---|---|---|
| `tests/acceptance/scenarios.json` | test | JSON list containing 9 entries. |
| `tests/acceptance/scenarios.template.json` | test | JSON list containing 9 entries. |

## Common commands

Run these commands from the `HEPLocalAgent/` repository root.

### Install

```bash
python -m pip install -e ".[web]"
```

### Run all tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

### Launch the web interface

```bash
OLLAMA_HOST=http://HOST:11434 \
PYTHONPATH=src \
python -m streamlit run src/hep_agent/ui/web_app.py
```

### Regenerate this guide

```bash
PYTHONPATH=src python scripts/generate_repository_guide.py
```

### Run explicit-process generalization evaluation

```bash
OLLAMA_HOST=http://HOST:11434 \
PYTHONPATH=src \
python evaluation/run_process_generalization_v1.py \
  --profile qwen_primary \
  --groups core \
  --run-label documented_core_run
```

### Run semantic-process evaluation

```bash
OLLAMA_HOST=http://HOST:11434 \
PYTHONPATH=src \
python evaluation/run_semantic_agent_eval.py \
  --model qwen3-coder-next:Q4_K_M \
  --run-label documented_semantic_run
```

## Documentation-maintenance rule

Regenerate this guide after:

- adding, removing, or renaming a source file;
- changing the responsibility of a module;
- adding a new evaluation suite;
- adding the doctor or another major subsystem;
- changing standard launch or test commands.

The accompanying `docs/REPOSITORY_MANIFEST.json` provides the same
inventory in machine-readable form for future doctor checks. Its
`source_git_commit` is the base commit visible when generation ran;
it cannot be the SHA of the later commit containing the generated
file. Both generated inventory files exclude themselves.
