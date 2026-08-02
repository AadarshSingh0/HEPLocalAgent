# User Interfaces — Practical Guide

This folder exposes the tested agent core to users.

## cli.py

The command-line interface provides:

    hep-agent run "natural-language request"

It:

1. loads the selected agent profile;
2. reads the machine-local MadGraph path;
3. sends the request to the structured planner;
4. shows the interpreted and validated workflow;
5. displays deterministic corrections;
6. applies the approval policy;
7. executes MadGraph;
8. parses the physics result;
9. prints and saves the final record.

Physics interpretation, validation, building, execution, and parsing
remain in their dedicated modules. The CLI does not duplicate those
rules.

The future web interface should call the same orchestration layer.

## Streamlit web interface

The web interface consists of:

- `web_app.py`: the visual research console;
- `web_launcher.py`: the `hep-agent-web` command;
- `web_support.py`: tested run-history and path helpers.

The interface deliberately separates preparation and execution:

1. The user submits a natural-language request.
2. The planner and deterministic validators prepare one artifact.
3. The exact MG5 commands are displayed.
4. The user explicitly executes or cancels that artifact.
5. Execution does not call the planner again.

### History policy

Persistent history comes from JSON records under `results/runs/`.

The current browser session also displays chat-style messages, but
previous requests are not silently inserted into later model prompts.
This keeps separate runs independently reproducible.

### Result display

The interface displays:

- workflow interpretation;
- deterministic corrections;
- exact MG5 commands;
- execution and physics metrics;
- LHE, HepMC, and ROOT paths;
- MadAnalysis reports and plots;
- log tails;
- downloadable JSON, PDF, and command files.

## External-tool health display

The Streamlit sidebar checks the complete supported toolchain:

- MadGraph executable;
- Pythia8 installation or `pythia8-config`;
- Delphes executable and detector-card directory;
- MadAnalysis 5 executable.

Pythia8 and Delphes paths may be explicitly configured or inferred
from the configured MadGraph installation.

Standalone Delphes availability does not imply that the optional
MadAnalysis Delphes reader is enabled. These capabilities are shown
and handled separately.
