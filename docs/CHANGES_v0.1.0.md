# HEPLocalAgent v0.1.0 — Architecture and Change Record

This document is the release-candidate record for HEPLocalAgent v0.1.0.
It replaces the earlier increment log, which stopped at an intermediate
353-test state.

**Standalone baseline:** `878b69b` (`Make HEPLocalAgent fully standalone`)

**Verified public base:** `baa88d6` (`Merge pull request #1 from
AadarshSingh0/agent/workflow-grounding-20260809`)

**History represented by that public base:** 19 commits reachable after the
standalone baseline, including topic, consolidation, and merge commits.

**Test history:** 295 at the standalone baseline, 370 at `baa88d6`, and
**379 in the final release-readiness change set**. The full unit suite is
model-free and does not call Ollama or execute HEP software.

Verified with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```

Latest result:

```text
Ran 379 tests
OK
```

---

## 1. Design principle

HEPLocalAgent separates model-assisted interpretation from deterministic
containment.

- **Interpretation:** a selected Ollama model translates ordinary language
  into either a compact semantic process proposal or a full typed workflow
  proposal.
- **Containment:** ordinary Python code checks supported request facts,
  selected-model particle names, schema consistency, the constructed artifact,
  approval policy, and execution provenance.

A more capable model can improve what the agent understands. It does not gain
permission to bypass validation, approval, or the deterministic artifact
builder.

---

## 2. Current request flow

1. The web or terminal interface checks that the request contains a collider or
   incoming state, a physics target, an energy, and an event count.
2. The agent selects one planning route:
   - the **thin semantic LLM route** for ordinary process language; or
   - the **full structured LLM route** for richer workflow requirements.
3. Exact MadGraph-style process syntax supplied by the user is parsed
   deterministically and treated as authoritative.
4. Deterministic grounding checks supported explicit facts against the proposed
   workflow.
5. Particle and multiparticle tokens are checked against the selected Standard
   Model or a statically parseable UFO model.
6. Eligible grounding or model-domain errors may enter a bounded repair path.
   Every repair is revalidated. Unsupported or unresolved cases are blocked.
7. The deterministic builder constructs the complete MG5 command artifact.
8. Final artifact validation checks the built commands and pipeline
   consistency.
9. Approval policy returns one of:
   - `AUTO_CONFIRM`: cancellable five-second countdown;
   - `EXPLICIT_CONFIRMATION`: no countdown and a required user action; or
   - `BLOCKED`: execution is unavailable.
10. The exact approved artifact is executed without another planner call.
11. MadGraph manages requested Pythia8 and Delphes stages. MadAnalysis is a
    separate post-processing stage when usable event output exists.
12. Commands, decisions, corrections, outputs, timings, and failures are
    recorded for inspection.

The two planners are alternatives. Their outputs are not generated and compared
against each other.

---

## 3. Major changes since the standalone baseline

### 3.1 Model-relative particle-domain validation

- Standard Model particle names and MadGraph default multiparticles are checked
  before execution.
- Invalid glued tokens such as `tt~` are caught inside the agent.
- Parseable UFO `particles.py` files are inspected statically with Python's AST;
  the model file is not imported or executed.
- Missing or unparseable UFO namespaces fall back to permissive domain
  validation to avoid false claims about an unknown model.

### 3.2 Built-in model classification

Standard Model and `loop_sm` spellings are canonicalized across case, spaces,
underscores, and hyphens. A built-in model incorrectly labelled as a user UFO is
corrected, while genuine UFO names remain user models.

### 3.3 Model-led pipeline interpretation

The thin semantic planner returns a restricted object containing a process
expression plus Pythia8 and Delphes intent. This supports phrasings such as
"turn on showering" while deterministic anchors preserve explicit on/off
instructions.

The model does not freely write a complete executable MG5 launch script. The
full artifact remains deterministic.

### 3.4 Repairable containment

Eligible request-grounding and model-domain failures may be sent to the bounded
repair model with deterministic feedback. Repairs that cannot be justified or
validated are rejected. Builder, final-artifact, and runtime failures do not
enter an unrestricted LLM retry loop.

### 3.5 Exact-process authority

When the user supplies syntax such as:

```text
generate p p > z > e+ e-
```

the explicit process is authoritative. Planner additions that change incoming
particles, final particles, required intermediates, exclusions, or coupling
orders are removed or rejected according to the implemented rules.

At amplitude level, both `QED=2` and `QED<=2` are represented as maximum-order
restrictions and emitted as `QED<=2`. Unsupported internal claims of exact or
minimum amplitude-level coupling order are rejected.

### 3.6 Request recognition and grounding

The minimum request gate recognizes named physics targets such as top-pair,
Drell--Yan, and Higgs production while rejecting generic phrases such as
"event production" as a final-state specification.

Natural-language particle grounding now preserves mixed multiparticle clauses.
For example, a stated `mu- mu+ e- e+` final state is no longer truncated to the
first recognized particle--antiparticle pair. Overlapping phrases such as
`positive muon` and `anti-top` are counted once rather than as two tokens.

This deterministic vocabulary remains intentionally conservative; arbitrary
natural-language particle descriptions still rely on model interpretation or
exact MadGraph syntax.

### 3.7 Installed-model selection and routing profiles

The web interface queries the configured Ollama host at `/api/tags`,
deduplicates and sorts installed models, and lets the user choose the actual
primary model independently of the routing profile.

- **Ollama model:** model used for the new request.
- **Routing profile:** timeout, retry budget, and optional fallback behavior.

If discovery fails, configured models remain available with a warning. A
selected primary model is not redundantly reused as its own fallback. The
starter installer and `starter_local` profile both use
`qwen2.5-coder:7b`.

### 3.8 Approval enforcement across interfaces

The core and terminal interfaces already distinguished automatic, explicit,
and blocked decisions. The web interface now enforces the same distinction for
both ordinary workflows and complete energy scans.

An expired countdown can start execution only for `AUTO_CONFIRM`. A workflow
marked `EXPLICIT_CONFIRMATION` has no deadline and requires a button click. A
blocked or missing approval decision cannot start external software.

### 3.9 Installation self-test and diagnosis

The deterministic self-test is available through:

```bash
python -m hep_agent.selftest
hep-local-agent-selftest
```

It builds a fixed `p p > e+ e-` workflow without an LLM and reports MadGraph,
Pythia8, Delphes, and MadAnalysis separately. It distinguishes missing tools
from installed tools that failed and diagnoses recognized Python-version,
LHAPDF/Pythia8, segmentation-fault, core-dump, shower-disable, and interface
loading patterns.

Delphes is discovered in both common layouts:

```text
MG5_ROOT/Delphes
MG5_ROOT/HEPTools/Delphes
```

### 3.10 Web interface and failure reporting

The web interface separates Chat, workflow building, installation testing, and
run history. It exposes the interpreted workflow, generated artifact,
corrections, model calls, repair count, fallback use, and provenance.

Failure details now combine request-grounding and artifact/model-domain issues,
including stage, error code, message, and schema path. Clearing the browser
conversation does not delete persistent run records or scientific outputs.

### 3.11 Acceptance and regression testing

The repository includes replayable acceptance scenarios for both planning
routes, natural-language paraphrases, and negative cases that must repair or
block. `scripts/record_acceptance.py` can record outputs from an actual Ollama
model without committing machine-specific recordings.

Installer tests are hermetic: they do not inherit the developer's
`OLLAMA_HOST`, and simulated macOS tests do not reuse an unrelated local virtual
environment.

### 3.12 Repository and installer hardening

- Python requirement: 3.10 or newer.
- Console entry points: `hep-local-agent`, `hep-local-agent-web`,
  `hep-local-agent-doctor`, and `hep-local-agent-selftest`.
- Supported installer targets: Ubuntu/Debian-family x86-64 and macOS on Intel or
  Apple Silicon, with the documented remote-Ollama path for unsupported local
  Ollama configurations.
- `--dry-run` previews installation and uninstallation plans.
- Full-stack installer validation uses a fixed 10-event trial.
- Uninstallation is guarded and does not implicitly remove unrelated Ollama
  models, the Ollama application, Homebrew, Apple command-line tools, Linux
  system packages, or scientific results unless the corresponding explicit
  option is selected.
- Temporary patch scripts, patch files, generated package metadata, and
  machine-specific acceptance recordings are excluded from releases.

---

## 4. Trust contracts and boundaries

1. **Model output is a proposal.** The LLM interprets language and may emit a
   constrained process expression or typed workflow proposal; it does not have
   unrestricted authority over the complete executable artifact.
2. **Artifact construction is deterministic.** The complete MG5 workflow and
   supported MA5 commands are built by fixed code.
3. **Exact user syntax is authoritative.** Explicit process syntax is preserved
   within the supported schema and coupling-order semantics.
4. **Validation is evidence-bounded.** Particle-domain validation is
   authoritative only when the selected model namespace is known. Unknown UFO
   namespaces are reported as permissive rather than falsely certified.
5. **Repair is bounded and revalidated.** No repair is accepted merely because
   an LLM proposed it.
6. **Approval is policy-controlled.** Physics-changing repair, unresolved
   ambiguity, warnings, overwrite risk, unsupported features, or
   physics-critical model inference require explicit confirmation.
7. **Execution uses the approved artifact.** The planner is not called again
   after approval.
8. **Subprocess use is constrained.** External tools are invoked without shell
   interpolation and under timeouts. This is not an operating-system sandbox.
9. **Provenance is recorded.** Run records include the request, profile, model
   calls, prompt hashes, approval, artifact, corrections, and observed results.
10. **Deployment may be local or configured remote.** Ollama defaults to a
    local host, but a user-configured remote Ollama host receives the model
    request; the software does not claim that data always remains on one
    physical machine.

---

## 5. Current limitations

- Passing agent validation does not prove that MadGraph has viable diagrams,
  that the cross section is nonzero, or that the requested analysis is
  scientifically useful.
- The natural-language particle vocabulary used for deterministic grounding is
  deliberately limited. Exact MadGraph syntax is the most authoritative path
  for uncommon particles or complex final states.
- Schema version 1 supports only limited required-intermediate structure.
- Unparseable UFO namespaces use permissive domain validation.
- Exact and minimum amplitude-level coupling-order comparisons are
  intentionally unsupported; maximum restrictions are supported.
- External HEP tools can still fail because of installation, compilation,
  environment, physics, or runtime problems.
- Non-shell subprocess execution and timeouts reduce command risk but do not
  provide OS-level sandboxing.

---

## 6. Release verification

- [x] Public base `baa88d6` independently verified at 370 tests.
- [x] Mixed natural-language multiparticle grounding fixed and regression
      tested.
- [x] Web explicit-confirmation behavior fixed for workflows and scans.
- [x] Unit suite increased to 379 and passes without Ollama or HEP tools.
- [x] This change record updated to the current architecture and limitations.
- [x] Installer and `starter_local` model naming aligned to
      `qwen2.5-coder:7b`.
- [ ] Record and replay the optional live-model acceptance suite on the release
      machine.
- [ ] Run the deterministic installation self-test on the final release
      toolchain.
- [ ] Push the release-readiness branch and merge it into `main`.
- [ ] Create the `v0.1.0` tag after the final host checks.

The unchecked host-dependent items are release operations, not missing unit
implementation. They require the actual Ollama and HEP installations that will
be used for the release.
