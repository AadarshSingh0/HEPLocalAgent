# HEPLocalAgent

HEPLocalAgent is a standalone local multi-model collider agent. Its model
routing and validation design was informed by the HEPToolBench evaluation,
but the benchmark repository is not a runtime dependency.

The planned controlled comparison includes:

1. Llama 3 8B as the original agent baseline;
2. Qwen3-Coder-Next as the default planner and repair model;
3. a routed architecture using Qwen3-Coder-Next by default and
   Llama 3.3 70B as a fallback for repeated validation failures.

The repository includes:

- agent source code;
- model-routing configuration;
- prompt templates;
- whitelisted tools;
- self-contained deterministic validation under `src/hep_agent/validation`;
- bounded repair logic;
- held-out agent evaluation scenarios;
- execution logs and aggregate results.

No API keys, model weights, personal paths, or private environment files
should be committed.

## Repository documentation

See [`docs/REPOSITORY_GUIDE.md`](docs/REPOSITORY_GUIDE.md) for the
current architecture, directory responsibilities, complete source-file
inventory, common commands, and stability boundaries. The guide is generated
from the repository by `scripts/generate_repository_guide.py`.


## Beginner installation

For a guided Linux or macOS installation, see
[`docs/INSTALL_FOR_EVERYONE.md`](docs/INSTALL_FOR_EVERYONE.md).

After downloading the repository, run:

    chmod +x install.sh run_agent.sh uninstall.sh scripts/*.sh
    ./install.sh
    ./run_agent.sh

Remove the project-managed environment and HEP tools with:

    ./uninstall.sh

## Installation self-test

To verify that the physics toolchain is installed and working end to end,
without involving any model, run the deterministic self-test:

    python -m hep_agent.selftest --events 1000

It runs a fixed trial process (`p p > e+ e-`) with Pythia8, Delphes, and
MadAnalysis, detects which of those tools the selected MadGraph actually
provides, and reports each one as `OK` (ran and produced output), `MISS` (not
installed), or `FAIL` (installed but did not produce output). It reads the
MadGraph log and explains common failures (for example a Python/library
version mismatch). Point it at your tools with `--mg5` and `--ma5`, or create
`configs/local_paths.json`:

    {
      "mg5_executable": "/path/to/MG5_aMC/bin/mg5_aMC",
      "madanalysis5_executable": "/path/to/madanalysis5/bin/ma5"
    }

The same check is available in the web interface under **System doctor →
Run installation self-test**.

## Environment requirements

The agent is a Python package that orchestrates an existing MadGraph install;
MadGraph in turn provides Pythia8, Delphes, and MadAnalysis under its
`HEPTools` directory. A common pitfall is a **Python version mismatch**: if
MadGraph's Pythia8/LHAPDF were compiled against one Python version but the
agent is run under a different one, MadGraph's shower probe can crash silently
and fall back to `shower = OFF`, so Pythia8 produces no output. Run the agent
in the same Python environment the HEP tools were compiled against (or rebuild
LHAPDF/Pythia8 for your current Python). The installation self-test detects and
reports this condition explicitly.

## AI-assisted development

This software was developed with extensive assistance from large language models, including ChatGPT, for implementation, debugging, documentation, architecture, and interface design.

The project author defined the scientific goals, evaluated the workflows, ran the tests, inspected the generated artifacts, and remains responsible for the software and its scientific claims.

See [`AI_ASSISTED_DEVELOPMENT.md`](AI_ASSISTED_DEVELOPMENT.md) for the full disclosure.

## Internal compatibility names

The public project and command are named `HEPLocalAgent` and
`hep-local-agent`. A small number of internal maintenance-script filenames
still contain `local_hep_agent`, including
`scripts/bootstrap_local_hep_agent.sh` and
`scripts/uninstall_local_hep_agent.sh`. These filenames are retained in the
initial release to preserve the already validated Linux and macOS installation
paths. They do not change the public package name or Python module name.
