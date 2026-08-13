#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
VENV_DIR="${PROJECT_ROOT}/.venv"
STACK_ROOT="${PROJECT_ROOT}/.hep-stack"
REMOVE_STACK=0
PURGE_RESULTS=0
DRY_RUN=0
ASSUME_YES=0

usage() {
    cat <<'EOF'
HEPLocalAgent uninstaller

Default cleanup removes only this clone's Python environment and generated
configuration. The multi-gigabyte clone-owned .hep-stack is preserved.

Options:
  --remove-stack     Also remove this clone's owned .hep-stack.
  --keep-stack       Explicitly preserve .hep-stack (the default).
  --purge-results    Also remove this clone's generated results.
  --yes              Confirm the displayed operation noninteractively.
  --dry-run          Show the plan without deleting anything.
  -h, --help         Show this help.

Legacy shared tools, external ROOT, Conda, Homebrew, Snap, and system packages
are never removed by this uninstaller.
EOF
}

while (($#)); do
    case "$1" in
        --remove-stack) REMOVE_STACK=1 ;;
        --keep-stack) REMOVE_STACK=0 ;;
        --purge-results) PURGE_RESULTS=1 ;;
        --yes) ASSUME_YES=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

[[ "${VENV_DIR}" == "${PROJECT_ROOT}/.venv" ]] || exit 2
[[ "${STACK_ROOT}" == "${PROJECT_ROOT}/.hep-stack" ]] || exit 2
[[ "${PROJECT_ROOT}" != "/" ]] || exit 2

if (( REMOVE_STACK )) && [[ -e "${STACK_ROOT}" ]]; then
    [[ -f "${STACK_ROOT}/manifest.json" ]] || {
        echo "Refusing to delete an unmarked stack without manifest.json: ${STACK_ROOT}" >&2
        exit 2
    }
    python_command="${VENV_DIR}/bin/python"
    if [[ ! -x "${python_command}" && -x "${STACK_ROOT}/runtime/bin/python" ]]; then
        python_command="${STACK_ROOT}/runtime/bin/python"
    fi
    if [[ ! -x "${python_command}" && -x /usr/bin/python3 ]]; then
        python_command=/usr/bin/python3
    fi
    [[ -x "${python_command}" ]] || {
        echo "Refusing stack deletion: no clone-owned or OS Python for ownership verification." >&2
        exit 2
    }
    "${python_command}" - "${PROJECT_ROOT}" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
stack = root / ".hep-stack"
payload = json.loads((stack / "manifest.json").read_text(encoding="utf-8"))
ownership = payload.get("ownership", {})
if payload.get("repository_root") != str(root):
    raise SystemExit("Refusing stack deletion: manifest belongs to another clone.")
if payload.get("stack_root") != str(stack):
    raise SystemExit("Refusing stack deletion: manifest boundary mismatch.")
if ownership.get("boundary") != str(stack):
    raise SystemExit("Refusing stack deletion: ownership boundary mismatch.")
if ownership.get("installation_id") != payload.get("installation_id"):
    raise SystemExit("Refusing stack deletion: ownership ID mismatch.")
PY
fi

echo "HEPLocalAgent uninstall plan"
echo "  Remove clone Python: ${VENV_DIR}"
if (( REMOVE_STACK )); then
    echo "  REMOVE OWNED MULTI-GIGABYTE STACK: ${STACK_ROOT}"
else
    echo "  Keep managed stack: ${STACK_ROOT}"
fi
if (( PURGE_RESULTS )); then
    echo "  Remove clone results: ${PROJECT_ROOT}/results"
else
    echo "  Keep clone results."
fi
echo "  Preserve all external and legacy installations."

if (( ! DRY_RUN && ! ASSUME_YES )); then
    reply=""
    read -r -p "Proceed with exactly this plan? [y/N] " reply || exit 2
    [[ "${reply}" =~ ^[Yy]$ ]] || exit 0
fi

remove_owned() {
    local target="$1"
    if [[ ! -e "${target}" && ! -L "${target}" ]]; then
        return
    fi
    if (( DRY_RUN )); then
        echo "Would remove: ${target}"
    else
        rm -rf -- "${target}"
        echo "Removed: ${target}"
    fi
}

remove_owned "${VENV_DIR}"
remove_owned "${PROJECT_ROOT}/configs/local_paths.json"
if (( REMOVE_STACK )); then remove_owned "${STACK_ROOT}"; fi
if (( PURGE_RESULTS )); then remove_owned "${PROJECT_ROOT}/results"; fi

if (( DRY_RUN )); then echo "Dry run complete; nothing was removed."; fi
