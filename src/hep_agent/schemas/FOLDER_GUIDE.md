# Schemas — Practical Guide

This folder defines the structured language used between the local LLM and the deterministic collider tools.

The LLM should not directly write unrestricted MadGraph, Pythia, or Delphes files.

Instead, it should produce structured information describing:

- the selected physics model;
- incoming beams;
- the hard-scattering process;
- additional particles;
- particle decays;
- coupling-order restrictions;
- collider energy;
- event-generation settings;
- requested simulation stages;
- analysis requests.

The deterministic builders will convert this information into actual tool files.

## Why this structure is needed

A structure that is too restrictive would support only a few fixed processes.

A structure that is too unrestricted would allow the LLM to generate invalid MadGraph syntax.

The schema should therefore be:

- general enough for many collider processes;
- recursive enough for decay chains;
- strict enough to validate before execution;
- independent of one particular local model.

## Current status

This folder currently contains design documentation only.

There is nothing to execute yet.

To read the schema design:

    cd ~/Benchmark/HEPToolBench_GitHub/local_hep_agent
    cat src/hep_agent/schemas/SCHEMA_DESIGN.md
