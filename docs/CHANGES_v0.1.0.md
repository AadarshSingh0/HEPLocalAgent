# HEPLocalAgent — Architecture Change Summary

**Baseline:** commit `878b69b` ("Make HEPLocalAgent fully standalone") — the
version described in the current Paper B manuscript.
**This change set:** 11 focused commits on top of the baseline.
**Tests:** 295 (baseline) → **353**, all passing and model-free (no Ollama or
HEP tools required to run the suite).

This document explains, for each change: what the old agent did, what the new
agent does, and why. It then lists new/modified files, states the agent's trust
guarantees as explicit contracts, maps each change to the Paper B sections that
need editing, and gives a `v0.1.0` release checklist.

---

## 1. The guiding principle

Every change follows one rule that separates two kinds of deterministic logic:

- **Interpretation** — *what did the user mean?* (Pythia on or off; is 13 TeV
  total or per-beam; what is the final state?). This should become **more
  flexible** as the local model grows more capable.
- **Containment** — *is the proposed thing real and safe to execute?* (Is `tt~`
  a particle the loaded model defines; is the command shell-safe; will it run
  the exact approved artifact?). This must **always hold**, regardless of model
  capability, because the failure mode of every model — small or large — is
  being confident and wrong.

Short form: **relax interpretation as capability grows; never relax
containment.** A bigger model buys freedom in what it is allowed to *mean*, not
freedom to run unreal or unsafe commands.

---

## 2. The three original problems (found in real macOS testing) — now fixed

| # | Symptom (old behaviour) | Root cause | New behaviour |
|---|---|---|---|
| 1 | `p p > tt~` (a glued, non-existent token) passed validation and reached MadGraph, which then rejected it. | The particle validator only checked *characters* (`^[A-Za-z0-9_+\-~]+$`); it never checked whether the token exists in the selected model. | The token is caught inside the agent, with a suggested fix (`Did you mean 't', 't~'?`), and — since increment 4 — automatically repaired. |
| 2 | An exact request using the Standard Model failed with *"A user UFO model requires model_path"* before MadGraph ever ran. | The model emitted `{"name":"StandardModel","source":"user_ufo"}`; the built-in-model rescue list did not contain `standardmodel` (no space), so Pydantic rejected the workflow at construction. | Any Standard Model / loop_sm spelling (`StandardModel`, `Standard Model`, `standard_model`, `SM`, …) is normalised to the canonical built-in name; a built-in mislabelled as a UFO is corrected. Genuine UFO names are untouched. |
| 3 | "turn on Pythia" was silently ignored (Pythia stayed off), while "with Pythia8" worked. | On the natural-language route the LLM emitted only the process line; Pythia/Delphes were decided by a rigid regex that recognised only `with/use/enable/run` + the literal word "pythia". | The model now interprets stage intent. "turn on Pythia", "enable showering", "parton level only", "detector simulation", etc. are understood by the model, with explicit deterministic anchors kept as a high-confidence override. **Validated on real `qwen2.5-coder:7b`.** |

---

## 3. Change-by-change summary

### Increment 1 — Model-relative particle-domain validation (`15bbb80`)
- **Old:** particle tokens were only checked for safe characters.
- **New:** every particle/multiparticle token is validated against the
  namespace of the *selected model*. For the built-in Standard Model this is the
  SM particle set plus MadGraph's default multiparticles (`p`, `j`, `l+`, …).
  When the namespace cannot be determined, validation is **permissive** (no
  false blocks). Rejections carry split/stem suggestions for later repair.
- **Why it matters:** this is the containment layer. It is model-relative, so a
  richer model is not constrained to the Standard Model — the check only ever
  fires when a token genuinely is not in the loaded model.

### Increment 2 — Built-in model misclassification fix (`aa9370e`)
- **Old:** only a hard-coded 4-entry allowlist of exact spellings was rescued.
- **New:** a spelling-tolerant canonicaliser (case, spaces, underscores, hyphens
  all ignored) maps Standard Model / loop_sm spellings to the canonical name and
  repairs a built-in mislabelled as a UFO. Real UFO names are left alone.

### Increment 3 — Model-led pipeline interpretation (`d1221b4`)
- **Old:** on the natural-language route, the LLM emitted only a `generate` line;
  Pythia/Delphes came 100% from regex; a miss silently defaulted to off and was
  even tagged `validated_default` so approval did not flag it.
- **New:** the semantic planner returns a small structured object
  (`{process, pythia8, delphes}` with `on`/`off`/`unspecified`). The model
  interprets stage intent from natural language; explicit deterministic anchors
  still take precedence when present. Backward-compatible (a bare `generate`
  line still parses). Provenance is recorded in `field_sources`.

### Increment 4 — Repairable containment (`b531788`)
- **Old:** a domain violation (e.g. `tt~`) surfaced only at the final artifact
  check and *blocked* — the model never got a chance to fix it.
- **New:** the repair loop now acts on grounding mismatches **and** model-domain
  violations, so an invalid particle is fed back to the repair model with its
  suggested correction. If repair cannot fix it, the final artifact validation
  still blocks execution — containment is preserved. Applies to the primary and
  fallback repair paths.

### Increment 5 — Model-aware validation for UFO/BSM models (`5815e36`)
- **Old:** domain validation was authoritative only for the Standard Model;
  custom models were always permissive (unchecked).
- **New:** a UFO model's `particles.py` is statically parsed (via `ast`, **never
  executed**) to extract its particle set, and tokens are validated against
  *that* model plus MadGraph's default multiparticles. Containment now covers
  custom/BSM models; the namespace expands to whatever the loaded model defines.
  Unparseable or missing models remain permissive.

### Increment 6 — Data-driven acceptance harness with real-model recording (`c1b7c4c`)
- **Old:** the 295 unit tests mocked the model and never exercised the semantic
  route — they were blind to live-model language variation, which is exactly why
  real macOS testing found bugs the suite missed.
- **New:** a paraphrase battery (many phrasings → same workflow) and a negative
  battery (invalid tokens repaired or blocked, never executed) run through the
  real pipeline via replayed model outputs, covering both routes. Scenarios are
  data (`tests/acceptance/scenarios.json`). `scripts/record_acceptance.py`
  captures real local-model outputs so actual model behaviour can be validated
  in CI (via `HEP_ACCEPTANCE_SCENARIOS`).

### Increment 7 — Deterministic installation self-test (`4b37a32`)
- **New capability:** a no-LLM cross-check that runs a fixed trial process
  (`p p > e+ e-`) with Pythia8 + Delphes + MadAnalysis all enabled, through the
  real deterministic execution/analysis stages, and reports per-tool health.
  Exposed as `python -m hep_agent.selftest` (and a `hep-local-agent-selftest`
  entry point) and as a button in the web app's **System doctor** section.
  Verifies the toolchain is installed and working end to end, with no planner or
  model involved.

### Increment 8 — Test-suite hardening (`2e35712`)
- **Bootstrap tests made hermetic:** they no longer inherit `OLLAMA_HOST` from
  the developer's shell. The bootstrap script changes its install decisions
  based on `OLLAMA_HOST`, so a configured remote Ollama could previously make
  the macOS-rejection tests fail spuriously.
- **Acceptance scenarios made robust:** the two injected-invalid scenarios are
  marked `synthetic` so the recorder never overwrites them with a real model's
  (valid) output, and the detector-simulation expectation requires only Delphes
  (enabling showering for detector simulation is reasonable model behaviour).

---

## 4. What the agent can do now that it could not before

- **Catch non-existent particles before execution** — for the Standard Model and
  for any parseable UFO/BSM model, an invalid or glued particle token is stopped
  inside the agent instead of failing in MadGraph.
- **Auto-correct invalid particles** — a bad token is fed back to the model with
  a concrete suggestion and repaired within budget.
- **Understand pipeline intent in natural language** — Pythia/Delphes are decided
  by model interpretation, not a fixed phrase list; "magic phrase" rigidity is
  gone.
- **Validate against custom physics models** — load your own UFO model and the
  containment guarantee expands to that model's particle set.
- **Verify its own installation** — one command (or button) runs the full
  toolchain on a fixed process and reports per-tool health, no model involved.
- **Stay correct under refactoring and across models** — a data-driven acceptance
  suite plus a real-model recording workflow guard against regressions and
  live-model drift.

---

## 5. Trust guarantees (state these as contracts in the paper and README)

1. **The model never writes an executable script or launch commands.** It
   proposes a typed intent (and, on the natural-language route, a single process
   line plus stage intent). All MadGraph/Pythia/Delphes/MadAnalysis command-file
   construction is deterministic.
2. **Every particle is validated against the loaded model.** A token that the
   selected model does not define cannot reach MadGraph.
3. **Invalid never executes.** If validation fails and repair cannot fix it, the
   workflow is blocked, not run.
4. **Execution is sandboxed by construction.** Commands run as non-shell
   subprocess argument lists (`shell=True` is never used) under explicit
   timeouts; the exact approved artifact is executed with no further model call.
5. **Every run is reproducible.** A JSON provenance record captures prompt
   hashes, model, profile, and artifact.
6. **Everything is local.** Any Ollama-served model works; no data leaves the
   machine.

> Note for accuracy: the earlier manuscript phrasing "the LLM performs exactly
> one job / never writes MadGraph syntax" should be replaced by contract (1)
> above, which is precise about what the model does and does not produce.

---

## 6. Files

### New files (12)
| File | Purpose |
|---|---|
| `src/hep_agent/validation/model_domain.py` | Model-relative particle-domain validation; SM namespace; UFO `particles.py` parser; canonical built-in names. |
| `src/hep_agent/selftest.py` | Deterministic installation self-test (function + `python -m hep_agent.selftest` CLI). |
| `scripts/record_acceptance.py` | Records real local-model outputs for the acceptance scenarios. |
| `tests/acceptance/scenarios.json` | Acceptance scenarios (representative outputs; CI-green). |
| `tests/acceptance/scenarios.template.json` | Recording template (recordable scenarios have no outputs; synthetic keep theirs). |
| `tests/test_acceptance.py` | Data-driven acceptance harness (both routes). |
| `tests/test_model_domain_validation.py` | Tests for SM domain validation. |
| `tests/test_model_classification.py` | Tests for tolerant built-in model classification. |
| `tests/test_semantic_pipeline_intent.py` | Tests for model-led pipeline interpretation. |
| `tests/test_domain_repair.py` | Tests that invalid particles are repaired, not just blocked. |
| `tests/test_ufo_domain_validation.py` | Tests for UFO/BSM domain validation. |
| `tests/test_selftest.py` | Tests for the installation self-test reporting logic. |

### Modified files (8)
| File | Change |
|---|---|
| `src/hep_agent/validation/core.py` | Wire model-domain validation into `validate_workflow`. |
| `src/hep_agent/validation/__init__.py` | Export the new domain validators. |
| `src/hep_agent/models/planner.py` | Spelling-tolerant built-in model canonicalisation. |
| `src/hep_agent/models/semantic_process.py` | Structured semantic output (`process` + `pythia8` + `delphes`); precedence logic. |
| `src/hep_agent/orchestration/preexecution.py` | Fold domain violations into the repair loop. |
| `src/hep_agent/ui/web_app.py` | Installation self-test button in the System doctor section. |
| `pyproject.toml` | `hep-local-agent-selftest` entry point. |
| `tests/test_bootstrap_scripts.py` | Hermetic subprocess environment (strip `OLLAMA_HOST`). |

---

## 7. Paper B — sections to update

- **Abstract / architecture overview and Figure 1.** Replace "the LLM performs
  exactly one job / never writes MadGraph syntax" with trust contract (1). The
  validation box now includes **model-aware domain validation** (particles
  checked against the loaded model, including UFO/BSM); the repair loop now also
  repairs **domain violations**.
- **Planner / interpretation section.** Describe model-led pipeline
  interpretation on the natural-language route (structured `process` + stage
  intent), with deterministic anchors as a high-confidence override — replacing
  the previous regex-only pipeline description.
- **Validation section.** Add the model-relative domain validator and the UFO
  `particles.py` parsing (static, non-executing).
- **Repair section.** State that invalid particles are fed back with suggestions
  and repaired within budget; unresolved cases are blocked.
- **Test count.** Update "273 tests" (or "295") to **346**, and describe the
  acceptance harness and real-model recording as a distinct validation layer.
- **Installation / features.** Add the deterministic installation self-test
  (CLI + web button).
- **Limitations.** The "magic phrase" rigidity is resolved; note remaining items
  (e.g. the deterministic anchor regex can still over-trigger on unusual
  phrasings; UFO models whose particles are not declared via `Particle(...)` in
  `particles.py` fall back to permissive validation).

---

## 8. How to verify on your system

```bash
# 1. Full suite (model-free). Should print: Ran 346 tests ... OK
python -m unittest discover -s tests -p 'test_*.py'

# 2. Real-model acceptance (records your local model, then replays it)
python scripts/record_acceptance.py \
    --in tests/acceptance/scenarios.template.json \
    --out tests/acceptance/scenarios.qwen7b.json \
    --model qwen2.5-coder:7b            # add --ollama-host http://HOST:11434 if remote
HEP_ACCEPTANCE_SCENARIOS=tests/acceptance/scenarios.qwen7b.json \
    python -m unittest tests.test_acceptance -v

# 3. Installation self-test (runs the full toolchain; no model involved)
python -m hep_agent.selftest \
    --mg5 /path/to/MG5_aMC/bin/mg5_aMC \
    --ma5 /path/to/madanalysis5/bin/ma5 \
    --events 1000
# or create configs/local_paths.json and run:  python -m hep_agent.selftest

# 4. Web button: launch the web app -> System doctor -> "Run installation self-test"
```

If you use a remote Ollama, set a full URL: `export OLLAMA_HOST=http://HOST:11434`
(scheme and port are required).

---

## 9. `v0.1.0` release checklist

- [ ] Apply all 8 increments; `python -m unittest discover -s tests` → **346 OK**.
- [ ] Run the real-model acceptance suite against `qwen2.5-coder:7b` and confirm
      green (or record any model-specific expectation adjustments).
- [ ] Run the installation self-test on the release machine and confirm all four
      tools pass.
- [ ] Update Paper B per section 7 above.
- [ ] Update the README trust guarantees per section 5.
- [ ] Reconcile model naming across paper, installer, `configs/agent_profiles.json`,
      and the UI (installer default `qwen2.5-coder:7b` vs `starter_local` profile
      model — see note below).
- [ ] Confirm `pyproject.toml` version and the git tag agree, then tag `v0.1.0`.

> **Known naming inconsistency to resolve before tagging:** the bootstrap
> installer's default starter model is `qwen2.5-coder:7b`, but the
> `starter_local` profile in `configs/agent_profiles.json` currently points at a
> different model. Align these (and the paper's starter/primary/fallback
> terminology) so a clean default install and the default profile use the same
> model.
