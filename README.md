# HEPLocalAgent

This directory contains the local multi-model agent developed using the
results of the HEPToolBench local-model evaluation.

The planned controlled comparison includes:

1. Llama 3 8B as the original agent baseline;
2. Qwen3-Coder-Next as the default planner and repair model;
3. a routed architecture using Qwen3-Coder-Next by default and
   Llama 3.3 70B as a fallback for repeated validation failures.

The agent will reuse the deterministic task validators distributed under:

    ../local_llm_benchmark/

The final release will include:

- agent source code;
- model-routing configuration;
- prompt templates;
- whitelisted tools;
- deterministic validation;
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
