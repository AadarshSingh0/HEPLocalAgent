# HEPLocalAgent — Practical Folder Guide

This folder contains the standalone HEPLocalAgent collider-agent project.

The goal is to build a useful local agent that can:

- understand collider-physics requests;
- construct MadGraph workflows safely;
- validate files before execution;
- run MadGraph, Pythia, Delphes, or MadAnalysis when requested;
- repair invalid outputs using validator feedback;
- use faster and slower local models only when necessary.

## Main folders

### legacy_baseline

This is a clean copy of the original working MicroMadAgent source code.

Keep this folder unchanged. It preserves the original Llama 3 agent for comparison and reproducibility.

### src/hep_agent

This contains the new production agent.

The planner, model routing, workflow schema, builders, execution controller, and user interface will be developed here.

### src/hep_agent/validation

This contains the self-contained checks performed before execution.

HEPToolBench scorers are not a runtime dependency of this repository. Keep
agent validation behavior explicit and cover any intentional comparison with
benchmark scoring in tests.

### evaluation

This contains fixed scenario definitions, offline evaluation runners, and two
distinct result areas:

- `evaluation/results/`: generated offline-evaluation output, ignored by default;
- `evaluation/results/published/`: intentionally curated, version-controlled
  evaluation evidence with provenance and checksums.

### results

Root `results/` contains ordinary runtime agent run records and logs generated
locally. It remains ignored and should not contain source code or curated
evaluation evidence.

## Useful terminal commands

Show the folder structure:

    cd HEPLocalAgent
    tree -a -L 4

Show source and documentation files:

    find . -type f ! -path './results/*' ! -path './evaluation/results/*' ! -path '*/__pycache__/*' | sort

Check the frozen original baseline:

    tree -a -L 4 legacy_baseline

## Important rules

1. Keep legacy_baseline unchanged.
2. Do not edit benchmark tasks or scorers unless a genuine bug is found.
3. Validate generated artifacts before execution.
4. Do not classify Ollama, MadGraph, or timeout failures as model failures.
5. Save enough information to reproduce every evaluated run.
6. Do not commit temporary outputs or large generated files.
