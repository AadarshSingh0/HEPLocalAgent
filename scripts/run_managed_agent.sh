#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
MANIFEST="${PROJECT_ROOT}/.hep-stack/manifest.json"

[[ -x "${VENV_PYTHON}" ]] || { echo "Run ./install.sh first." >&2; exit 1; }
[[ -f "${MANIFEST}" ]] || { echo "Managed stack manifest is missing; run ./install.sh." >&2; exit 1; }

for variable in ROOTSYS PYTHIA8DATA LD_LIBRARY_PATH DYLD_LIBRARY_PATH \
    DYLD_FALLBACK_LIBRARY_PATH PYTHONPATH PYTHONHOME VIRTUAL_ENV \
    CMAKE_PREFIX_PATH ROOT_INCLUDE_PATH LIBRARY_PATH CPATH PKG_CONFIG_PATH \
    CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_SHLVL _CE_CONDA _CE_M; do
    unset "${variable}" || true
done

export PATH="${PROJECT_ROOT}/.venv/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export VIRTUAL_ENV="${PROJECT_ROOT}/.venv"
export PYTHONNOUSERSITE=1
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
export HEP_AGENT_DEFAULT_PROFILE="${HEP_AGENT_DEFAULT_PROFILE:-starter_local}"

cd "${PROJECT_ROOT}"
exec "${VENV_PYTHON}" -m streamlit run src/hep_agent/ui/web_app.py
