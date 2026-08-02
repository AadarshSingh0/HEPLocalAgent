# Analysis — Practical Guide

This folder builds and later executes deterministic post-processing
analyses.

MadAnalysis is deliberately separate from MadGraph execution:

    event generation
    -> optional Pythia8
    -> optional Delphes
    -> MadAnalysis post-processing

This means an analysis can be rerun without regenerating events.

## madanalysis.py

The current quick-look builder:

- imports one existing event sample;
- uses a restricted plot-command allowlist;
- creates process-aware plots from supported final-state particles;
- adds missing transverse momentum;
- submits one MA5 job;
- exits cleanly.

For an electron-positron final state, it builds:

- positron transverse momentum;
- electron transverse momentum;
- positron pseudorapidity;
- electron pseudorapidity;
- dilepton invariant mass;
- missing transverse momentum.

The LLM does not write unrestricted MA5 scripts.

Current supported particle labels:

    e+ e- mu+ mu- ta+ ta- a

More labels and process classes will be added after they have been
tested against real MA5 samples.

The MA5 runner must not trust process return code alone. A valid run
will later require:

- return code zero;
- no MA5-ERROR log messages;
- an HTML report;
- a PDF report;
- the expected number of plot images.

## runner.py

The MadAnalysis runner executes a previously validated MA5 artifact.

It:

- writes the deterministic script to `analysis.ma5`;
- invokes MA5 without `shell=True`;
- uses the correct parton, hadron, or reconstructed mode flag;
- applies a timeout;
- saves stdout and stderr separately;
- searches for internal `MA5-ERROR` messages;
- requires HTML and PDF reports;
- requires the exact expected number of plots.

A zero operating-system return code does not automatically mean that
MadAnalysis succeeded. MA5 can report script errors and still return
zero, so both logs and generated artifacts are validated.
