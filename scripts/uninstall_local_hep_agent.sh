#!/usr/bin/env bash
# Remove software and machine configuration created by HEPToolBench.

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPOSITORY_ROOT="$(cd -- "${PROJECT_ROOT}/.." && pwd)"

DEFAULT_TOOLS_ROOT="${HOME}/.local/share/hep-agent-tools"
TOOLS_ROOT="${DEFAULT_TOOLS_ROOT}"
TOOLS_MARKER_NAME=".heptoolbench-managed"
VENV_DIR="${PROJECT_ROOT}/.venv"
PROFILE_NAME="starter_local"
OLLAMA_HOST_VALUE="${OLLAMA_HOST:-}"
REMOVE_MODEL_NAME=""

ASSUME_YES=0
DRY_RUN=0
PURGE_RESULTS=0

usage() {
    cat <<'EOF'
HEPToolBench uninstaller

Usage:
  ./uninstall.sh [options]

Default cleanup:
  - removes local_hep_agent/.venv
  - removes ~/.local/share/hep-agent-tools
  - removes generated machine-path and Ollama-host configuration
  - restores pre-install configuration backups when present
  - removes the generated starter_local profile

The repository, benchmark/agent results, Ollama, downloaded Ollama models,
and operating-system packages are preserved by default.

Options:
  --yes                  Skip the final confirmation prompt.
  --dry-run              Show the cleanup plan without deleting anything.
  --tools-root PATH      Remove a custom HEP tools directory.
  --profile NAME         Remove this generated agent profile.
  --purge-results        Also delete locally generated agent and benchmark runs.
  --remove-model NAME    Also remove one model from a local Ollama server.
  --ollama-host URL      Local Ollama URL used by --remove-model.
  -h, --help             Show this help.

Examples:
  ./uninstall.sh
  ./uninstall.sh --dry-run --purge-results
  ./uninstall.sh --purge-results --remove-model qwen2.5-coder:7b --yes
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

log() {
    printf '%s\n' "$*"
}

absolute_path() {
    local input="$1"

    if command -v python3 >/dev/null 2>&1; then
        python3 - "${input}" <<'PY'
import sys
from pathlib import Path

print(Path(sys.argv[1]).expanduser().resolve())
PY
        return
    fi

    case "${input}" in
        /*) printf '%s\n' "${input}" ;;
        *) printf '%s/%s\n' "$(pwd -P)" "${input}" ;;
    esac
}

is_local_ollama_host() {
    case "${OLLAMA_HOST_VALUE}" in
        http://localhost:*|https://localhost:*|\
        http://127.0.0.1:*|https://127.0.0.1:*|\
        http://localhost|https://localhost|\
        http://127.0.0.1|https://127.0.0.1)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

while (($#)); do
    case "$1" in
        --yes)
            ASSUME_YES=1
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        --tools-root)
            shift
            [[ $# -gt 0 ]] || die "--tools-root requires a value."
            TOOLS_ROOT="$(absolute_path "$1")"
            ;;
        --profile)
            shift
            [[ $# -gt 0 ]] || die "--profile requires a value."
            PROFILE_NAME="$1"
            ;;
        --purge-results)
            PURGE_RESULTS=1
            ;;
        --remove-model)
            shift
            [[ $# -gt 0 ]] || die "--remove-model requires a value."
            REMOVE_MODEL_NAME="$1"
            ;;
        --ollama-host)
            shift
            [[ $# -gt 0 ]] || die "--ollama-host requires a value."
            OLLAMA_HOST_VALUE="$1"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
    shift
done

if [[ -z "${OLLAMA_HOST_VALUE}" &&
    -r "${PROJECT_ROOT}/configs/ollama_host" ]]; then
    IFS= read -r OLLAMA_HOST_VALUE < \
        "${PROJECT_ROOT}/configs/ollama_host"
fi
OLLAMA_HOST_VALUE="${OLLAMA_HOST_VALUE:-http://localhost:11434}"

if [[ -n "${REMOVE_MODEL_NAME}" ]]; then
    case "${OLLAMA_HOST_VALUE}" in
        http://*|https://*)
            ;;
        *)
            die "--ollama-host must begin with http:// or https://."
            ;;
    esac
    case "${OLLAMA_HOST_VALUE}" in
        *[[:space:]]*)
            die "--ollama-host cannot contain spaces or tabs."
            ;;
    esac
    [[ "${REMOVE_MODEL_NAME}" =~ ^[A-Za-z0-9._:/-]+$ ]] || \
        die "--remove-model contains unsupported characters."
    is_local_ollama_host || \
        die "--remove-model is limited to localhost; refusing to modify a remote Ollama server."
fi

if [[ -e "${TOOLS_ROOT}" || -L "${TOOLS_ROOT}" ]]; then
    case "${TOOLS_ROOT}" in
        "${DEFAULT_TOOLS_ROOT}")
            ;;
        *)
            [[ -f "${TOOLS_ROOT}/${TOOLS_MARKER_NAME}" ]] || \
                die "Refusing to remove custom tools root without ${TOOLS_MARKER_NAME}: ${TOOLS_ROOT}"
            ;;
    esac
fi

[[ "${VENV_DIR}" == "${PROJECT_ROOT}/.venv" ]] || \
    die "Internal safety check failed for the isolated environment."
[[ "${PROJECT_ROOT}" != "/" && "${REPOSITORY_ROOT}" != "/" ]] || \
    die "Internal safety check resolved a repository path to /."
[[ "${TOOLS_ROOT}" != "/" && "${TOOLS_ROOT}" != "${HOME}" ]] || \
    die "Refusing to remove a broad tools path: ${TOOLS_ROOT}"

log "============================================================"
log "HEPTOOLBENCH UNINSTALL PLAN"
log "============================================================"
log "Remove isolated Python environment:"
log "  ${VENV_DIR}"
log "Remove project-managed HEP tools:"
log "  ${TOOLS_ROOT}"
log "Clean generated machine configuration in:"
log "  ${PROJECT_ROOT}/configs"
log "Remove generated profile:"
log "  ${PROFILE_NAME}"

if (( PURGE_RESULTS )); then
    log "Delete generated agent and benchmark runs:"
    log "  ${PROJECT_ROOT}/results"
    log "  ${REPOSITORY_ROOT}/local_llm_benchmark/runs"
    log "  ${REPOSITORY_ROOT}/local_llm_benchmark/results/all_runs_long.csv"
else
    log "Preserve generated agent and benchmark results."
fi

if [[ -n "${REMOVE_MODEL_NAME}" ]]; then
    log "Remove local Ollama model:"
    log "  ${REMOVE_MODEL_NAME}"
fi

log ""
log "Preserved: repository source, Ollama application, other Ollama models,"
log "and operating-system packages."
log ""

if (( ! ASSUME_YES && ! DRY_RUN )); then
    reply=""
    if ! read -r -p "Proceed with this cleanup? [y/N] " reply; then
        die "No interactive input is available. Rerun with --yes."
    fi
    [[ "${reply}" =~ ^[Yy]$ ]] || {
        log "Cleanup cancelled."
        exit 0
    }
fi

remove_path() {
    local path="$1"

    if [[ ! -e "${path}" && ! -L "${path}" ]]; then
        log "Already absent: ${path}"
        return 0
    fi

    if (( DRY_RUN )); then
        log "Would remove: ${path}"
    else
        rm -rf "${path}"
        log "Removed: ${path}"
    fi
}

restore_or_remove_file() {
    local path="$1"
    local backup="${path}.before_bootstrap"

    if [[ -e "${backup}" ]]; then
        if (( DRY_RUN )); then
            log "Would restore: ${backup} -> ${path}"
        else
            rm -f "${path}"
            mv "${backup}" "${path}"
            log "Restored pre-install configuration: ${path}"
        fi
    else
        remove_path "${path}"
    fi
}

remove_generated_profile() {
    local profiles_path="${PROJECT_ROOT}/configs/agent_profiles.json"
    local backup="${profiles_path}.before_bootstrap"
    local python_command=""

    if [[ -e "${backup}" ]]; then
        restore_or_remove_file "${profiles_path}"
        return 0
    fi

    [[ -f "${profiles_path}" ]] || return 0

    if [[ -x "${VENV_DIR}/bin/python" ]]; then
        python_command="${VENV_DIR}/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        python_command="$(command -v python3)"
    else
        die "Python is required to remove the generated profile safely."
    fi

    if (( DRY_RUN )); then
        log "Would remove profile '${PROFILE_NAME}' from ${profiles_path}"
        return 0
    fi

    "${python_command}" - "${profiles_path}" "${PROFILE_NAME}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
profile_name = sys.argv[2]
payload = json.loads(path.read_text(encoding="utf-8"))

if payload.pop(profile_name, None) is not None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
    log "Removed generated profile when present: ${PROFILE_NAME}"
}

remove_local_model() {
    local model_name="$1"
    local python_command=""
    local payload=""

    if (( DRY_RUN )); then
        log "Would remove local Ollama model: ${model_name}"
        return 0
    fi

    export OLLAMA_HOST="${OLLAMA_HOST_VALUE}"

    if command -v ollama >/dev/null 2>&1; then
        ollama rm "${model_name}"
        log "Removed local Ollama model: ${model_name}"
        return 0
    fi

    command -v curl >/dev/null 2>&1 || \
        die "Ollama CLI or curl is required to remove the requested model."

    if [[ -x "${VENV_DIR}/bin/python" ]]; then
        python_command="${VENV_DIR}/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        python_command="$(command -v python3)"
    else
        die "Python is required to construct the Ollama delete request."
    fi

    payload="$(
        "${python_command}" -c \
            'import json, sys; print(json.dumps({"model": sys.argv[1]}))' \
            "${model_name}"
    )"
    curl \
        --fail \
        --show-error \
        --silent \
        --request DELETE \
        --header "Content-Type: application/json" \
        --data "${payload}" \
        "${OLLAMA_HOST_VALUE%/}/api/delete"
    log "Removed local Ollama model: ${model_name}"
}

if [[ -n "${REMOVE_MODEL_NAME}" ]]; then
    remove_local_model "${REMOVE_MODEL_NAME}"
fi

remove_generated_profile
restore_or_remove_file "${PROJECT_ROOT}/configs/local_paths.json"
remove_path "${PROJECT_ROOT}/configs/ollama_host"
remove_path "${PROJECT_ROOT}/configs/conda_root"

remove_path "${VENV_DIR}"
remove_path "${TOOLS_ROOT}"

if (( PURGE_RESULTS )); then
    remove_path "${PROJECT_ROOT}/results"
    remove_path "${REPOSITORY_ROOT}/local_llm_benchmark/runs"
    remove_path \
        "${REPOSITORY_ROOT}/local_llm_benchmark/results/all_runs_long.csv"
fi

log ""
if (( DRY_RUN )); then
    log "Dry run complete. Nothing was deleted."
else
    log "HEPToolBench-managed software cleanup complete."
fi
