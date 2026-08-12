# Builders — Practical Guide

This folder converts validated structured workflows into collider-tool
commands.

Builders are deterministic and never call an LLM.

## Current builders

### madgraph.py

Builds:

- model import;
- process generation;
- additional processes;
- intermediate resonances;
- exclusions;
- coupling orders;
- recursive decay chains;
- output command.

### madgraph_workflow.py

Adds:

- launch command;
- event count;
- random seed;
- beam energies;
- optional Pythia8;
- optional Delphes;
- final confirmation command.

It does not execute MadGraph.

## Current limitation

Total centre-of-mass energy is automatically divided equally only for
supported symmetric collider pairs such as:

- p and p;
- e- and e+;
- mu- and mu+;
- q and q~.

Unequal beam energies are not yet represented by schema version 1.

MadAnalysis is deliberately not enabled inside the MG5 launch block. When requested, it runs later as a separate validated post-processing stage.

Run all tests with:

    cd HEPLocalAgent
    PYTHONPATH=src python -m unittest discover -s tests -v

Never add unrestricted raw MadGraph commands as a shortcut.

## Noninteractive MadGraph runs

The workflow builder inserts:

    set automatic_html_opening False --no_save

before the MadGraph `launch` command.

This prevents MG5 from opening its generated HTML report in a browser
and blocking the agent until that browser window is closed.

The HTML report files are still generated inside the process output
folder and can be opened manually later.

The `--no_save` option prevents the agent from changing the user's
global MadGraph configuration.
