# Validation — Practical Guide

This folder contains deterministic checks performed before execution.

The validator does not call an LLM.

It checks:

- required pipeline stages;
- unsafe particle, model, and output names;
- unsupported schema features;
- unusually large event requests;
- whether the builder accepts the workflow;
- whether the artifact exactly matches deterministic builder output;
- whether generated commands contain unsafe content.

Run all tests with:

    cd ~/Benchmark/HEPToolBench_GitHub/local_hep_agent
    PYTHONPATH=src python -m unittest discover -s tests -v

Warnings do not automatically make a workflow invalid.

Errors block execution.

The later approval controller will use warnings to decide whether the
five-second automatic confirmation is allowed.
