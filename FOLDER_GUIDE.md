# Local HEP Agent — Practical Folder Guide

This folder contains the local collider-agent project connected to HEPToolBench.

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

### validators

This contains checks performed before execution.

Whenever possible, these validators should reuse the deterministic validators in:

../local_llm_benchmark/

Do not maintain silently different copies of benchmark scorers.

### evaluation

This will contain fixed scenarios and evaluation scripts for:

- Agent A: Llama 3 8B baseline
- Agent B: Qwen3-Coder-Next
- Agent C: Qwen3-Coder-Next with Llama 3.3 70B fallback

### results

This contains run records, logs, and evaluation summaries.

It should not contain source code.

## Useful terminal commands

Show the folder structure:

    cd ~/Benchmark/HEPToolBench_GitHub/local_hep_agent
    tree -a -L 4

Show source and documentation files:

    find . -type f ! -path './results/*' ! -path '*/__pycache__/*' | sort

Check the frozen original baseline:

    tree -a -L 4 legacy_baseline

## Important rules

1. Keep legacy_baseline unchanged.
2. Do not edit benchmark tasks or scorers unless a genuine bug is found.
3. Validate generated artifacts before execution.
4. Do not classify Ollama, MadGraph, or timeout failures as model failures.
5. Save enough information to reproduce every evaluated run.
6. Do not commit temporary outputs or large generated files.
