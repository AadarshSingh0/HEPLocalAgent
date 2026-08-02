# Orchestration — Practical Guide

This folder controls the order in which the agent performs its work.

The first component is the approval controller.

It returns one of three decisions:

- auto_confirm
- explicit_confirmation_required
- blocked

A safe and fully validated workflow may automatically continue after a
five-second cancellation window.

The approval controller itself does not wait for five seconds. The web
interface will later display the countdown and allow the user to cancel
or edit the plan.

Explicit confirmation is required when:

- a validator produces a warning;
- the request remains ambiguous;
- a repair changes the physics;
- an output may be overwritten;
- a physics-critical value was inferred by the LLM.

Validation errors always block execution.

Run all tests with:

    cd ~/Benchmark/HEPLocalAgent
    PYTHONPATH=src python -m unittest discover -s tests -v

## Run records

The file:

    run_record.py

saves a JSON record for every agent run.

The record includes model timings, corrections, validation results,
repair attempts, fallback use, approval decisions, and generated MG5
commands.

The default location is:

    results/runs/

These records will later be used to compare Agent A, Agent B, and
Agent C.

The record is saved even when the model server or planner fails.

## Separate MadAnalysis stage

The file `analysis_stage.py` controls MA5 post-processing after event
generation has completed.

Current input priority:

1. Pythia8 HepMC in hadron mode;
2. parton-level LHE in parton mode.

Delphes ROOT is not selected yet because the current MA5 installation
has its optional Delphes reader disabled.

The stage distinguishes:

- no supported event input;
- missing MA5 executable;
- unsupported quick-look process;
- MA5 execution or report-validation failure.

When `pipeline.madanalysis` is false, the stage is skipped and does not
affect a successful MG5 run.

## Preparation and execution separation

The end-to-end controller now exposes two reusable stages:

### `prepare_end_to_end()`

Runs:

- local-model planning;
- deterministic grounding correction;
- bounded repair and optional fallback;
- MG5 artifact construction;
- deterministic validation;
- run-record creation.

It does not execute MadGraph or MadAnalysis.

### `execute_prepared()`

Executes the exact artifact produced by `prepare_end_to_end()`.

It does not call the planner or repair models again. This is required
for graphical interfaces: the workflow displayed for approval must be
the same workflow that is eventually executed.

The original `run_end_to_end()` remains available for the command-line
interface and internally combines the two stages.
