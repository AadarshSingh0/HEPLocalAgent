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

## Package structure

- `src/hep_agent/`: installable agent, validation, orchestration, execution,
  model-routing, command-line, and web-interface source;
- `configs/` and `prompts/`: portable example configuration, profiles, and
  planner/repair prompt templates;
- `tests/` and `evaluation/`: model-free regression/acceptance tests and
  compact evaluation scenarios;
- `scripts/`, `install.sh`, `run_agent.sh`, and `uninstall.sh`: installation,
  launch, validation, maintenance, and removal commands;
- `docs/`: installation, architecture, schema, manifest, and release
  documentation;
- `legacy_baseline/`: retained original baseline implementation used for the
  controlled comparison.

## Repository documentation

See [`docs/REPOSITORY_GUIDE.md`](docs/REPOSITORY_GUIDE.md) for the
current architecture, directory responsibilities, complete source-file
inventory, common commands, and stability boundaries. The guide is generated
from the repository by `scripts/generate_repository_guide.py`.

## CPC sample input and output

The replayable acceptance suite in
[`tests/acceptance/scenarios.json`](tests/acceptance/scenarios.json) contains
paired sample inputs and outputs for comprehensive model-free pipeline tests.
Each scenario records the natural-language sample input in `request`, the
corresponding representative raw planner output in `model_outputs`, and the
verified pipeline result in `expect`. For example,
`full_explicit_top_pair` covers a complete 13 TeV top-pair request, its
structured planner response, and the expected validated MadGraph command and
run settings.

Run the complete replay suite without Ollama or HEP software with:

    PYTHONPATH=src python -m unittest tests.test_acceptance -v

The harness passes those recorded outputs through the real validation and
workflow-construction pipeline. These compact JSON fixtures are program test
data and expected outputs; generated event files are intentionally excluded.


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

To verify the clone-owned physics toolchain end to end without involving any
model, run:

    .venv/bin/python -m hep_agent.selftest --events 1000

The self-test reads this clone's `.hep-stack/manifest.json` and uses the same
controlled environment builder as normal CLI and web/UI execution. It runs
MadGraph, Pythia8, Delphes, and MadAnalysis and fails closed if an executable,
XML-data directory, ROOT runtime, or native dependency escapes `.hep-stack`.
External-tool overrides are not part of the publication-default workflow.

## Environment requirements

Each clone owns its Python environment in `.venv` and its complete native HEP
stack in `.hep-stack`. Linux installs ROOT directly under the stack. macOS
installs a private Miniforge bootstrap and ROOT runtime under the same stack,
then builds MG5, Pythia8, HepMC2, Delphes, MA5, and the MG5–Pythia interface
against it with Apple Clang. User Conda, Homebrew, Snap, system HEP packages,
old clones, and shared HEPLocalAgent tools are never selected by normal
installation or execution.

## AI-assisted development

This software was developed with extensive assistance from large language models, including ChatGPT, for implementation, debugging, documentation, architecture, and interface design.

The project author defined the scientific goals, evaluated the workflows, ran the tests, inspected the generated artifacts, and remains responsible for the software and its scientific claims.

See [`AI_ASSISTED_DEVELOPMENT.md`](AI_ASSISTED_DEVELOPMENT.md) for the full disclosure.

## Internal compatibility names

The public project and command are named `HEPLocalAgent` and
`hep-local-agent`. A small number of internal maintenance-script filenames
still contain `local_hep_agent`, including
`scripts/bootstrap_local_hep_agent.sh` and
`scripts/uninstall_local_hep_agent.sh`. They are retained only as explicitly
unsupported compatibility paths and are not called by the publication-default
installer. They do not change the public package name, Python module name, or
clone-owned stack contract.
