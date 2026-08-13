#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
STACK_ROOT="${PROJECT_ROOT}/.hep-stack"
DOWNLOADS="${STACK_ROOT}/downloads"
PYTHON_COMMAND="python3"
DRY_RUN=0

usage() {
    cat <<'EOF'
HEPLocalAgent independent-stack installer

Usage: ./install.sh [--yes] [--dry-run] [--python PATH] [--full]

The publication-default installation always installs the complete pinned HEP
stack under this clone's .hep-stack. External ROOT, Conda, Homebrew, Snap, and
shared HEPLocalAgent tool directories are never discovered or reused.

Options:
  --yes                     Noninteractive mode (accepted for compatibility).
  --dry-run                 Print the fresh installation plan.
  --python PATH             OS Python used only to create this clone's .venv.
  --full                    Accepted; the independent installer is always full.
  --validate-full-stack     Run deterministic validation after installation.
  --ollama-host URL         Record the Ollama endpoint (not part of HEP stack).
  --root PATH               Rejected: external ROOT is not supported by default.
  -h, --help                Show this help.
EOF
}

VALIDATE=0
while (($#)); do
    case "$1" in
        --yes|--full|--with-pythia8|--with-delphes|--with-madanalysis5) ;;
        --dry-run) DRY_RUN=1 ;;
        --validate-full-stack) VALIDATE=1 ;;
        --python)
            shift
            [[ $# -gt 0 ]] || { echo "--python requires a path" >&2; exit 2; }
            PYTHON_COMMAND="$1"
            ;;
        --root|--tools-root)
            echo "External HEP prefixes are disabled for independent installations." >&2
            echo "Every HEP component must be installed under ${STACK_ROOT}." >&2
            exit 2
            ;;
        --ollama-host)
            shift
            [[ $# -gt 0 ]] || { echo "--ollama-host requires a URL" >&2; exit 2; }
            mkdir -p "${PROJECT_ROOT}/configs"
            printf '%s\n' "$1" >"${PROJECT_ROOT}/configs/ollama_host"
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
    echo "Fresh-stack installation is currently validated only on Linux x86-64." >&2
    echo "The shared manifest/runtime contract supports macOS, but publication remains blocked pending actual Apple Silicon and Intel validation." >&2
    exit 2
fi

if (( DRY_RUN )); then
    printf '%s\n' \
        "Create clone Python: ${PROJECT_ROOT}/.venv" \
        "Create fresh native stack: ${STACK_ROOT}" \
        "Download checksum-pinned MG5 3.5.13, Pythia 8.317, ROOT 6.40.02," \
        "Delphes 3.5.1, MA5 1.11.0, HepMC2 2.06.11, and interface 1.3." \
        "No external HEP installation will be selected."
    exit 0
fi

if [[ -e "${STACK_ROOT}/manifest.json" ]]; then
    echo "A managed stack already belongs to this clone: ${STACK_ROOT}/manifest.json" >&2
    echo "Refusing to overwrite it. Use doctor/self-test, or uninstall it explicitly first." >&2
    exit 2
fi

if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    "${PYTHON_COMMAND}" -m venv "${PROJECT_ROOT}/.venv"
fi
"${PROJECT_ROOT}/.venv/bin/python" -m pip install --upgrade pip
"${PROJECT_ROOT}/.venv/bin/python" -m pip install -e "${PROJECT_ROOT}[web]"

mkdir -p "${DOWNLOADS}"
download() {
    local filename="$1" url="$2" checksum="$3" actual=""
    if [[ -f "${DOWNLOADS}/${filename}" ]]; then
        actual="$(sha256sum "${DOWNLOADS}/${filename}" | awk '{print $1}')"
    fi
    if [[ "${actual}" != "${checksum}" ]]; then
        curl -fL --retry 3 -o "${DOWNLOADS}/${filename}.partial" "${url}"
        actual="$(sha256sum "${DOWNLOADS}/${filename}.partial" | awk '{print $1}')"
        [[ "${actual}" == "${checksum}" ]] || {
            echo "Checksum mismatch for ${filename}" >&2
            return 1
        }
        mv "${DOWNLOADS}/${filename}.partial" "${DOWNLOADS}/${filename}"
    fi
}

download MG5_aMC_v3.5.13-github.tar.gz https://github.com/mg5amcnlo/mg5amcnlo/archive/refs/tags/v3.5.13.tar.gz 0c75437481cc7808b59b578bc454d2c7bc12721b8bd848a287f35503202fabe7
download pythia8317.tgz https://pythia.org/releases/pythia83/pythia8317.tgz 1ae551d14dac495ddfe6b344792035ebe410fe6c6004d44a335e0ece0e745adf
download root_v6.40.02.Linux-ubuntu24.04-x86_64-gcc13.3.tar.gz https://root.cern/download/root_v6.40.02.Linux-ubuntu24.04-x86_64-gcc13.3.tar.gz 127db12fa498b51ce89e242bc787d7ed24dfe4cee935783ed13d39e7969eb486
download Delphes-3.5.1.tar.gz https://github.com/delphes/delphes/archive/refs/tags/3.5.1.tar.gz b60d26d2ee2c84b58fbf2cf397fabd0ef3e89d3a0546d843c4ada82cc802d787
download madanalysis5-v1.11.0.tar.gz https://github.com/MadAnalysis/madanalysis5/archive/refs/tags/v1.11.0.tar.gz 6d2e73ae6d7d71cffa12c7184e8b243e1260e2f1d8e784edbf3058d6fc4b5351
download hepmc2.06.11.tgz https://hepmc.web.cern.ch/hepmc/releases/hepmc2.06.11.tgz 86b66ea0278f803cde5774de8bd187dd42c870367f1cbf6cdaec8dc7cf6afc10
download MG5aMC_PY8_interface_V1.3.tar.gz https://madgraph.mi.infn.it/Downloads/MG5aMC_PY8_interface/MG5aMC_PY8_interface_V1.3.tar.gz 1a7a62e96207701f9a8a44fec01426b7f474b580ba2c4fbb82ecd0d83fcea332

bash "${PROJECT_ROOT}/scripts/install_managed_hep_stack.sh"

if (( VALIDATE )); then
    "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/scripts/validate_full_stack.py" --events 100
fi

echo "Independent HEPLocalAgent installation complete."
