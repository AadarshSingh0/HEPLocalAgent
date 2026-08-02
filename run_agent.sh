#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
OLLAMA_HOST_FILE="${PROJECT_ROOT}/configs/ollama_host"
CONDA_ROOT_FILE="${PROJECT_ROOT}/configs/conda_root"

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "The project environment is missing."
    echo "Run ./install.sh first."
    exit 1
fi

if [[ -z "${OLLAMA_HOST:-}" && -r "${OLLAMA_HOST_FILE}" ]]; then
    IFS= read -r OLLAMA_HOST < "${OLLAMA_HOST_FILE}"
fi

export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
export HEP_AGENT_DEFAULT_PROFILE="${HEP_AGENT_DEFAULT_PROFILE:-starter_local}"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export PATH="${PROJECT_ROOT}/.venv/bin:${PATH}"

if [[ -r "${CONDA_ROOT_FILE}" ]]; then
    IFS= read -r CONDA_ROOT < "${CONDA_ROOT_FILE}"
    CONDA_SETUP="${CONDA_ROOT}/etc/profile.d/conda.sh"

    if [[ -f "${CONDA_SETUP}" ]]; then
        CONDA_SOURCE_STATUS=0

        set +u
        # shellcheck disable=SC1090
        source "${CONDA_SETUP}" || CONDA_SOURCE_STATUS=$?
        if (( CONDA_SOURCE_STATUS == 0 )); then
            conda activate "${PROJECT_ROOT}/.venv" || \
                CONDA_SOURCE_STATUS=$?
        fi
        set -u

        if (( CONDA_SOURCE_STATUS != 0 )); then
            echo "WARNING: Conda environment activation failed: ${CONDA_SETUP}"
        fi
    fi
fi

ROOT_SETUP="${HEP_AGENT_ROOT_SETUP:-${HOME}/.local/share/hep-agent-tools/root/bin/thisroot.sh}"

if [[ -f "${ROOT_SETUP}" ]]; then
    ROOT_SOURCE_STATUS=0

    set +u
    # shellcheck disable=SC1090
    source "${ROOT_SETUP}" || ROOT_SOURCE_STATUS=$?
    set -u

    if (( ROOT_SOURCE_STATUS != 0 )); then
        echo "WARNING: ROOT environment activation failed: ${ROOT_SETUP}"
    fi
fi

if ! curl -fsS "${OLLAMA_HOST%/}/api/tags" >/dev/null 2>&1; then
    echo "WARNING: Ollama is not reachable at ${OLLAMA_HOST}."
    echo "Chat and model planning will fail until Ollama is started."
    case "${OLLAMA_HOST}" in
        http://localhost:*|https://localhost:*|\
        http://127.0.0.1:*|https://127.0.0.1:*)
            echo "Try: ollama serve"
            ;;
        *)
            echo "Check that the remote Ollama computer is running and reachable."
            ;;
    esac
    echo
fi

cd "${PROJECT_ROOT}"
exec "${VENV_PYTHON}" -m streamlit run \
    src/hep_agent/ui/web_app.py
