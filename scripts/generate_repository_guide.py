#!/usr/bin/env python3
"""Generate an accurate repository guide and machine-readable manifest."""

from __future__ import annotations

import ast
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIRECTORY = ROOT / "docs"
GUIDE_PATH = DOCS_DIRECTORY / "REPOSITORY_GUIDE.md"
MANIFEST_PATH = DOCS_DIRECTORY / "REPOSITORY_MANIFEST.json"

INCLUDED_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".sh",
}

INCLUDED_NAMES = {
    "README",
    "README.md",
    "LICENSE",
    "LICENSE.md",
    "Makefile",
}

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
}

IGNORED_PREFIXES = (
    "evaluation/results/",
    "results/",
    "logs/",
)

OUTPUT_PATHS = {
    GUIDE_PATH.relative_to(ROOT).as_posix(),
    MANIFEST_PATH.relative_to(ROOT).as_posix(),
}


DIRECTORY_DESCRIPTIONS = {
    ".": (
        "Repository root containing project metadata, documentation, "
        "configuration, source code, tests, and evaluation utilities."
    ),
    "configs": (
        "Runtime configuration, including agent profiles and local "
        "HEP-tool paths."
    ),
    "docs": (
        "Human-readable and machine-readable repository documentation."
    ),
    "evaluation": (
        "Offline evaluation scenarios and runners. These files measure "
        "agent behavior but are not required by the production runtime."
    ),
    "examples": (
        "Example requests, workflows, or usage demonstrations."
    ),
    "prompts": (
        "Version-controlled system prompts used by planners and repair models."
    ),
    "scripts": (
        "Repository maintenance, documentation, and developer utility scripts."
    ),
    "src": (
        "Installable Python source tree."
    ),
    "src/hep_agent": (
        "Main HEP-agent package."
    ),
    "src/hep_agent/analysis": (
        "Structured analysis planning, compilation, and result handling."
    ),
    "src/hep_agent/builders": (
        "Deterministic builders that compile validated workflows into "
        "MadGraph or related tool artifacts."
    ),
    "src/hep_agent/execution": (
        "External-tool execution, output discovery, and execution-result handling."
    ),
    "src/hep_agent/models": (
        "Model clients, structured planners, semantic planning, repair, "
        "routing, and model-response normalization."
    ),
    "src/hep_agent/orchestration": (
        "Pre-execution, approval, repair, execution, end-to-end coordination, "
        "and run-record orchestration."
    ),
    "src/hep_agent/scans": (
        "Parameter-scan preparation, execution, and aggregation support."
    ),
    "src/hep_agent/schemas": (
        "Pydantic models defining the internal validated workflow language."
    ),
    "src/hep_agent/tools": (
        "HEP-tool adapters and tool-specific helper functions."
    ),
    "src/hep_agent/ui": (
        "Command-line and Streamlit web interfaces."
    ),
    "src/hep_agent/validation": (
        "Request grounding, capability checks, workflow validation, "
        "artifact validation, and safety checks."
    ),
    "tests": (
        "Unit and regression tests for production behavior."
    ),
}


def run_git(*arguments: str) -> str | None:
    """Run a read-only Git command, returning None outside a Git repository."""

    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    value = completed.stdout.strip()
    return value or None


def relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_ignored(path: Path) -> bool:
    relative = relative_path(path)

    if any(
        relative == prefix.rstrip("/")
        or relative.startswith(prefix)
        for prefix in IGNORED_PREFIXES
    ):
        return True

    return any(
        part in IGNORED_DIRECTORY_NAMES
        or part.endswith(".egg-info")
        for part in path.relative_to(ROOT).parts
    )


def iter_project_files() -> list[Path]:
    """Return documentation-relevant files from the current repository."""

    files: list[Path] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        if is_ignored(path):
            continue

        relative = relative_path(path)

        if relative in OUTPUT_PATHS:
            continue

        if (
            path.suffix.lower() not in INCLUDED_SUFFIXES
            and path.name not in INCLUDED_NAMES
        ):
            continue

        files.append(path)

    return sorted(
        files,
        key=lambda item: relative_path(item).lower(),
    )


def first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()

        if stripped:
            return stripped

    return None


def first_markdown_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()

    return None


def clean_description(value: str) -> str:
    return " ".join(value.strip().split())


def python_description(path: Path) -> str:
    try:
        source = path.read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return "Python module; automatic description unavailable."

    module_docstring = ast.get_docstring(tree)

    if module_docstring:
        first_paragraph = module_docstring.split("\n\n", 1)[0]
        return clean_description(first_paragraph)

    public_classes = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and not node.name.startswith("_")
    ]

    public_functions = [
        node.name
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and not node.name.startswith("_")
    ]

    names = public_classes + public_functions

    if names:
        preview = ", ".join(names[:6])

        if len(names) > 6:
            preview += ", …"

        return f"Python module exposing: {preview}."

    return "Python package or support module."


def json_description(path: Path) -> str:
    try:
        payload: Any = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "JSON data or configuration file."

    if isinstance(payload, dict):
        if isinstance(payload.get("scenarios"), list):
            return (
                "Evaluation scenario definition containing "
                f"{len(payload['scenarios'])} scenarios."
            )

        keys = list(payload.keys())

        if keys:
            preview = ", ".join(
                str(key)
                for key in keys[:6]
            )

            if len(keys) > 6:
                preview += ", …"

            return f"JSON object with top-level keys: {preview}."

        return "Empty JSON object."

    if isinstance(payload, list):
        return f"JSON list containing {len(payload)} entries."

    return "JSON scalar value."


def file_description(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".py":
        return python_description(path)

    if suffix == ".json":
        return json_description(path)

    try:
        text = path.read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeDecodeError):
        return "Project file."

    if suffix == ".md":
        heading = first_markdown_heading(text)

        if heading:
            return f"Markdown documentation: {heading}."

        return "Markdown documentation."

    if suffix == ".toml":
        return "TOML project or tool configuration."

    if suffix in {
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
    }:
        return "Project configuration file."

    if suffix == ".sh":
        first = first_nonempty_line(text)

        if first and not first.startswith("#!"):
            return f"Shell utility: {clean_description(first)}"

        return "Shell utility script."

    first = first_nonempty_line(text)

    if first:
        return clean_description(first)[:240]

    return "Empty text file."


def category_for(relative: str) -> str:
    if relative.startswith("src/hep_agent/"):
        return "production"

    if relative.startswith("tests/"):
        return "test"

    if relative.startswith("evaluation/"):
        return "evaluation"

    if relative.startswith("prompts/"):
        return "prompt"

    if relative.startswith("configs/"):
        return "configuration"

    if relative.startswith("docs/"):
        return "documentation"

    if relative.startswith("scripts/"):
        return "maintenance"

    if relative in {
        "pyproject.toml",
        "requirements.txt",
    }:
        return "package metadata"

    return "project support"


def directory_description(directory: str) -> str:
    if directory in DIRECTORY_DESCRIPTIONS:
        return DIRECTORY_DESCRIPTIONS[directory]

    path = ROOT / directory

    if path.name.startswith("test"):
        return "Test-support directory."

    return "Repository directory containing the files listed below."


def escape_table_text(value: str) -> str:
    return value.replace("|", "\\|")


def existing_architecture_stage(
    label: str,
    candidates: tuple[str, ...],
    explanation: str,
) -> str | None:
    existing = [
        candidate
        for candidate in candidates
        if (ROOT / candidate).exists()
    ]

    if not existing:
        return None

    references = ", ".join(
        f"`{item}`"
        for item in existing
    )

    return f"1. **{label}:** {explanation} Relevant files: {references}"


def build_manifest(files: list[Path]) -> dict[str, Any]:
    entries = []

    for path in files:
        relative = relative_path(path)

        entries.append(
            {
                "path": relative,
                "directory": (
                    Path(relative).parent.as_posix()
                    if Path(relative).parent.as_posix() != "."
                    else "."
                ),
                "category": category_for(relative),
                "description": file_description(path),
                "size_bytes": path.stat().st_size,
            }
        )

    return {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "repository_root": str(ROOT),
        "git_branch": run_git(
            "branch",
            "--show-current",
        ),
        "git_commit": run_git(
            "rev-parse",
            "HEAD",
        ),
        "file_count": len(entries),
        "files": entries,
    }


def build_guide(manifest: dict[str, Any]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for entry in manifest["files"]:
        grouped[entry["directory"]].append(entry)

    lines = [
        "# HEP Agent Repository Guide",
        "",
        "> This file is generated from the current repository filesystem.",
        "> Do not edit the generated inventory manually. Update source files",
        "> or module docstrings and rerun `scripts/generate_repository_guide.py`.",
        "",
        "## Repository snapshot",
        "",
        f"- Generated: `{manifest['generated_at_utc']}`",
        f"- Git branch: `{manifest['git_branch'] or 'unavailable'}`",
        f"- Git commit: `{manifest['git_commit'] or 'unavailable'}`",
        f"- Documented files: `{manifest['file_count']}`",
        "",
        "## Runtime architecture",
        "",
        "The production design separates model interpretation from deterministic",
        "workflow construction, validation, execution, and provenance.",
        "",
    ]

    architecture_stages = [
        existing_architecture_stage(
            "User interface",
            (
                "src/hep_agent/ui/web_app.py",
                "src/hep_agent/ui/cli.py",
            ),
            "Accepts Chat or Build-workflow requests and presents concise "
            "results with diagnostics available on demand.",
        ),
        existing_architecture_stage(
            "Request interpretation",
            (
                "src/hep_agent/models/semantic_process.py",
                "src/hep_agent/models/planner.py",
                "src/hep_agent/models/routing.py",
            ),
            "Routes explicit syntax and natural-language requests to the "
            "appropriate planning path.",
        ),
        existing_architecture_stage(
            "Grounding and validation",
            (
                "src/hep_agent/validation/grounding.py",
                "src/hep_agent/validation/process_request.py",
                "src/hep_agent/validation/analysis_request.py",
            ),
            "Preserves explicit user facts and rejects unsupported or "
            "ambiguous requests.",
        ),
        existing_architecture_stage(
            "Pre-execution orchestration",
            (
                "src/hep_agent/orchestration/preexecution.py",
                "src/hep_agent/orchestration/grounding_repair.py",
                "src/hep_agent/orchestration/approval.py",
            ),
            "Coordinates planning, bounded repair, validation, and approval.",
        ),
        existing_architecture_stage(
            "Deterministic artifact construction",
            (
                "src/hep_agent/builders/madgraph.py",
                "src/hep_agent/builders/madgraph_workflow.py",
            ),
            "Compiles the validated internal workflow into exact HEP-tool commands.",
        ),
        existing_architecture_stage(
            "Execution and output verification",
            (
                "src/hep_agent/orchestration/end_to_end.py",
                "src/hep_agent/execution/runner.py",
                "src/hep_agent/execution/result_parser.py",
            ),
            "Runs approved artifacts and verifies that required scientific "
            "outputs were actually produced.",
        ),
        existing_architecture_stage(
            "Run records and provenance",
            (
                "src/hep_agent/orchestration/run_record.py",
            ),
            "Stores workflow, commands, model calls, validation results, "
            "execution status, timing, and output locations.",
        ),
    ]

    stage_number = 1

    for stage in architecture_stages:
        if stage is None:
            continue

        lines.append(
            stage.replace(
                "1.",
                f"{stage_number}.",
                1,
            )
        )
        stage_number += 1

    lines.extend(
        [
            "",
            "## Stability boundaries",
            "",
            "- **Production runtime:** `src/hep_agent/`, `configs/`, and `prompts/`.",
            "- **Regression protection:** `tests/`.",
            "- **Offline experiments and measurements:** `evaluation/`.",
            "- **Generated outputs:** `results/`, `evaluation/results/`, and logs. "
            "These are not source code and are intentionally omitted from the "
            "file-by-file inventory.",
            "- **Maintenance utilities:** `scripts/`.",
            "",
            "## Directory map",
            "",
            "| Directory | Files | Purpose |",
            "|---|---:|---|",
        ]
    )

    directories = sorted(
        grouped,
        key=lambda item: (
            item != ".",
            item.lower(),
        ),
    )

    for directory in directories:
        lines.append(
            "| "
            f"`{directory}` | "
            f"{len(grouped[directory])} | "
            f"{escape_table_text(directory_description(directory))} |"
        )

    lines.extend(
        [
            "",
            "## File inventory",
            "",
        ]
    )

    for directory in directories:
        lines.extend(
            [
                f"### `{directory}`",
                "",
                directory_description(directory),
                "",
                "| File | Category | Purpose |",
                "|---|---|---|",
            ]
        )

        for entry in sorted(
            grouped[directory],
            key=lambda item: item["path"].lower(),
        ):
            lines.append(
                "| "
                f"`{entry['path']}` | "
                f"{entry['category']} | "
                f"{escape_table_text(entry['description'])} |"
            )

        lines.append("")

    lines.extend(
        [
            "## Common commands",
            "",
            "Run these commands from the `local_hep_agent/` repository root.",
            "",
            "### Install",
            "",
            "```bash",
            'python -m pip install -e ".[web]"',
            "```",
            "",
            "### Run all tests",
            "",
            "```bash",
            "PYTHONPATH=src python -m unittest discover -s tests -v",
            "```",
            "",
            "### Launch the web interface",
            "",
            "```bash",
            "OLLAMA_HOST=http://HOST:11434 \\",
            "PYTHONPATH=src \\",
            "python -m streamlit run src/hep_agent/ui/web_app.py",
            "```",
            "",
            "### Regenerate this guide",
            "",
            "```bash",
            "PYTHONPATH=src python scripts/generate_repository_guide.py",
            "```",
            "",
        ]
    )

    conditional_commands = [
        (
            "Run explicit-process generalization evaluation",
            "evaluation/run_process_generalization_v1.py",
            [
                "OLLAMA_HOST=http://HOST:11434 \\",
                "PYTHONPATH=src \\",
                "python evaluation/run_process_generalization_v1.py \\",
                "  --profile qwen_primary \\",
                "  --groups core \\",
                "  --run-label documented_core_run",
            ],
        ),
        (
            "Run semantic-process evaluation",
            "evaluation/run_semantic_agent_eval.py",
            [
                "OLLAMA_HOST=http://HOST:11434 \\",
                "PYTHONPATH=src \\",
                "python evaluation/run_semantic_agent_eval.py \\",
                "  --model qwen3-coder-next:Q4_K_M \\",
                "  --run-label documented_semantic_run",
            ],
        ),
    ]

    for title, required_path, commands in conditional_commands:
        if not (ROOT / required_path).exists():
            continue

        lines.extend(
            [
                f"### {title}",
                "",
                "```bash",
                *commands,
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Documentation-maintenance rule",
            "",
            "Regenerate this guide after:",
            "",
            "- adding, removing, or renaming a source file;",
            "- changing the responsibility of a module;",
            "- adding a new evaluation suite;",
            "- adding the doctor or another major subsystem;",
            "- changing standard launch or test commands.",
            "",
            "The accompanying `docs/REPOSITORY_MANIFEST.json` provides the same",
            "inventory in machine-readable form for future doctor checks.",
            "",
        ]
    )

    return "\n".join(lines)


def update_readme() -> bool:
    readme_path = ROOT / "README.md"

    if not readme_path.exists():
        return False

    text = readme_path.read_text(
        encoding="utf-8"
    )

    guide_reference = "docs/REPOSITORY_GUIDE.md"

    if guide_reference in text:
        return False

    addition = """

## Repository documentation

See [`docs/REPOSITORY_GUIDE.md`](docs/REPOSITORY_GUIDE.md) for the
current architecture, directory responsibilities, complete source-file
inventory, common commands, and stability boundaries. The guide is generated
from the repository by `scripts/generate_repository_guide.py`.
"""

    readme_path.write_text(
        text.rstrip() + addition + "\n",
        encoding="utf-8",
    )

    return True


def validate_manifest(
    manifest: dict[str, Any],
) -> None:
    documented = {
        entry["path"]
        for entry in manifest["files"]
    }

    actual = {
        relative_path(path)
        for path in iter_project_files()
    }

    if documented != actual:
        missing = sorted(actual - documented)
        stale = sorted(documented - actual)

        raise RuntimeError(
            "Repository manifest mismatch. "
            f"Missing={missing}; stale={stale}"
        )

    for entry in manifest["files"]:
        path = ROOT / entry["path"]

        if not path.is_file():
            raise RuntimeError(
                "Documented path does not exist: "
                f"{entry['path']}"
            )


def main() -> None:
    DOCS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = iter_project_files()
    manifest = build_manifest(files)

    validate_manifest(manifest)

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )

    GUIDE_PATH.write_text(
        build_guide(manifest),
        encoding="utf-8",
    )

    readme_updated = update_readme()

    print(f"Repository root: {ROOT}")
    print(f"Documented files: {manifest['file_count']}")
    print(f"Wrote: {GUIDE_PATH}")
    print(f"Wrote: {MANIFEST_PATH}")
    print(
        "README link: "
        + (
            "added"
            if readme_updated
            else "already present or README absent"
        )
    )


if __name__ == "__main__":
    main()
