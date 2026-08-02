# General Collider-Workflow Schema Design

## Purpose

The schema is the structured intermediate language connecting:

user request
→ local LLM planner
→ structured collider workflow
→ deterministic builders and validators

It should support much more than a few example processes.

It should eventually represent:

- proton-proton collisions;
- lepton colliders;
- parton-level initial states;
- simple final states;
- additional jets or photons;
- nested particle decays;
- Standard Model and UFO models;
- MadGraph-only runs;
- MadGraph plus Pythia;
- MadGraph plus Pythia and Delphes;
- analysis and parameter-scan workflows.

## 1. Task type

The workflow records what the user wants the agent to do.

Examples:

- generate_process
- run_simulation
- repair_failed_run
- analyse_existing_output
- patch_parameter_card
- plan_parameter_scan

## 2. Physics model

The workflow records the requested model.

Examples:

- sm
- MSSM
- loop_sm
- a user-provided UFO model

The selected model determines which particles and parameters are valid.

## 3. Collider and beams

The two incoming beams must be stored separately.

Examples:

- p and p
- e- and e+
- mu- and mu+
- q and q~

The workflow must also distinguish between:

- energy per beam;
- total centre-of-mass energy.

This avoids confusing 6.5 TeV per beam with 6.5 TeV total.

## 4. Hard process

The hard-process section stores the main production process.

Example:

initial particles: p, p
final particles: t, t~

It may also contain:

- excluded particles;
- required intermediate particles;
- coupling-order restrictions;
- additional merged processes;
- extra jets or photons.

## 5. Decay tree

Particle decays should be stored recursively.

Example:

p p produces t and t~

t decays to W+ and b
W+ decays to mu+ and muon neutrino

t~ decays to W- and b~
W- decays to jets

The LLM describes the parent-child relationships.

The deterministic builder decides the exact MadGraph parentheses, commas, and syntax.

## 6. Run settings

The workflow stores settings such as:

- number of events;
- random seed;
- beam energy;
- PDF choice;
- basic cuts;
- output name;
- timeout.

Values not supplied by the user must be marked as defaults.

The agent must distinguish between:

- a user-provided value;
- a validated default;
- an LLM guess.

An LLM guess about the physics must not be silently executed.

## 7. Simulation pipeline

The workflow records which stages are requested:

- MadGraph matrix-element generation;
- Pythia8 showering;
- Delphes detector simulation;
- MadAnalysis analysis.

Each stage should be independently enabled or disabled.

## 8. Approval information

The workflow records whether it may automatically continue.

Possible decisions:

- safe_auto_confirm
- explicit_confirmation_required
- blocked

A validated low-risk request may execute after the five-second cancellation window.

An ambiguous request or physics-changing repair must wait for explicit approval.

## 9. Provenance and agent state

Every run should record:

- original user request;
- planner model;
- fallback model, when used;
- raw model response;
- validated structured workflow;
- defaults that were applied;
- repair attempts;
- validator feedback;
- execution status;
- timings;
- failure category.

## Main design principle

The LLM decides the intended physics workflow.

The deterministic system decides how to write and validate the tool syntax.

A complicated process should not be allowed to bypass the structured representation.
