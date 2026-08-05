#!/usr/bin/env bash
# Beginner-friendly installer for the local HEP agent.
# Supports Ubuntu/Debian Linux on x86_64 and macOS.

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PLATFORM="${HEP_AGENT_TEST_PLATFORM:-$(uname -s)}"
ARCH="${HEP_AGENT_TEST_ARCH:-$(uname -m)}"
MACOS_VERSION=""

MG5_VERSION="3.5.13"
MG5_ARCHIVE="MG5_aMC_v${MG5_VERSION}.tar.gz"
MG5_URL="https://launchpad.net/mg5amcnlo/3.0/3.6.x/+download/${MG5_ARCHIVE}"
MG5_SHA256="55ac5517eacde69d37a22ef2677a923a597b34b04578df9fe76519afaab088a2"
MG5_GITHUB_URL="https://github.com/mg5amcnlo/mg5amcnlo/archive/refs/tags/v${MG5_VERSION}.tar.gz"
MG5_GITHUB_SHA256="0c75437481cc7808b59b578bc454d2c7bc12721b8bd848a287f35503202fabe7"

HEPMC2_VERSION="2.06.11"
HEPMC2_ARCHIVE="hepmc${HEPMC2_VERSION}.tgz"
HEPMC2_URL="https://hepmc.web.cern.ch/hepmc/releases/${HEPMC2_ARCHIVE}"
HEPMC2_SHA256="86b66ea0278f803cde5774de8bd187dd42c870367f1cbf6cdaec8dc7cf6afc10"

MINIFORGE_VERSION="26.3.2-2"
MINIFORGE_DIR=""
CONDA_EXECUTABLE=""

TOOLS_ROOT="${HOME}/.local/share/hep-agent-tools"
DOWNLOADS_DIR="${TOOLS_ROOT}/downloads"
TOOLS_MARKER_NAME=".heptoolbench-managed"
VENV_DIR="${PROJECT_ROOT}/.venv"
PROFILE_NAME="starter_local"
MODEL_NAME="qwen2.5-coder:7b"
OLLAMA_HOST_VALUE="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_HOST_FILE="${PROJECT_ROOT}/configs/ollama_host"
CONDA_ROOT_FILE="${PROJECT_ROOT}/configs/conda_root"
PYTHON_REQUESTED="${HEP_AGENT_PYTHON:-}"
export OLLAMA_HOST="${OLLAMA_HOST_VALUE}"

ASSUME_YES=0
DRY_RUN=0
INSTALL_SYSTEM_DEPS=0
INSTALL_OLLAMA=0
PULL_MODEL=0
WITH_PYTHIA8=0
WITH_DELPHES=0
WITH_MADANALYSIS5=0
RUN_DEEP_DOCTOR=0
RUN_FULL_STACK_VALIDATION=0

LOG_DIR="${PROJECT_ROOT}/results/bootstrap"
LOG_FILE="${TMPDIR:-/tmp}/hep_agent_bootstrap_$$.log"

usage() {
    cat <<'EOF'
HEP Agent beginner installer

Usage:
  ./scripts/bootstrap_local_hep_agent.sh [options]

Default installation:
  - verifies Ubuntu/Debian or macOS and a compatible Python
  - creates .venv
  - installs the web agent
  - installs pinned MadGraph5_aMC@NLO 3.5.13 under ~/.local/share
  - makes MadGraph use the same isolated Python environment
  - writes configs/local_paths.json
  - creates a starter_local model profile
  - runs the standard doctor

Options:
  --yes                  Accept prompts automatically.
  --dry-run              Print planned actions without changing the system.
  --install-system-deps  Install compiler/Python prerequisites for this OS.
  --install-ollama       Install Ollama when it is missing.
  --pull-model           Pull the selected Ollama model.
  --model NAME           Starter model (default: qwen2.5-coder:7b).
  --profile NAME         Starter profile name (default: starter_local).
  --python PATH          Python executable to use for the isolated environment.
  --ollama-host URL      Local or remote Ollama URL; saved for future launches.
  --tools-root PATH      HEP software directory.
  --with-pythia8         Ask MG5 to install Pythia8.
  --with-delphes         Ask MG5 to install Delphes.
  --with-madanalysis5    Ask MG5 to install MadAnalysis5.
  --full                 Enable system deps, local Ollama, model, and all HEP tools.
  --deep-doctor          Run deep doctor after installation.
  --validate-full-stack  Generate real events through MG5, Pythia8, Delphes, and MA5.
  -h, --help             Show this help.

Examples:
  ./install.sh
  ./install.sh --install-system-deps --install-ollama --pull-model
  ./install.sh --install-system-deps --ollama-host http://OTHER-COMPUTER:11434
  ./install.sh --full
  ./install.sh --dry-run --full
EOF
}

log() {
    printf '%s\n' "$*" | tee -a "${LOG_FILE}"
}

warn() {
    log "WARNING: $*"
}

die() {
    log "ERROR: $*"
    exit 1
}

quote_command() {
    printf '%q ' "$@"
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

version_at_least() {
    local current="$1"
    local required="$2"
    local current_major="${current%%.*}"
    local current_tail="${current#*.}"
    local current_minor="${current_tail%%.*}"
    local required_major="${required%%.*}"
    local required_tail="${required#*.}"
    local required_minor="${required_tail%%.*}"

    [[ "${current_major}" =~ ^[0-9]+$ ]] || return 1
    [[ "${current_minor}" =~ ^[0-9]+$ ]] || current_minor=0
    [[ "${required_major}" =~ ^[0-9]+$ ]] || return 1
    [[ "${required_minor}" =~ ^[0-9]+$ ]] || required_minor=0

    if (( current_major > required_major )); then
        return 0
    fi

    if (( current_major < required_major )); then
        return 1
    fi

    (( current_minor >= required_minor ))
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

run_cmd() {
    log "+ $(quote_command "$@")"
    if (( DRY_RUN )); then
        return 0
    fi
    "$@" 2>&1 | tee -a "${LOG_FILE}"
}

confirm() {
    local prompt="$1"

    if (( ASSUME_YES )); then
        return 0
    fi

    local reply
    read -r -p "${prompt} [y/N] " reply
    [[ "${reply}" =~ ^[Yy]$ ]]
}

wait_for_ollama() {
    local attempt

    if (( DRY_RUN )); then
        return 0
    fi

    for attempt in $(seq 1 30); do
        if curl -fsS "${OLLAMA_HOST_VALUE%/}/api/tags" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done

    return 1
}

on_error() {
    local exit_code=$?
    local line_number=${BASH_LINENO[0]:-unknown}
    log "ERROR: installation stopped near line ${line_number} (exit ${exit_code})."
    log "The script is resumable: correct the reported issue and run it again."
    exit "${exit_code}"
}

trap on_error ERR

while (($#)); do
    case "$1" in
        --yes)
            ASSUME_YES=1
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        --install-system-deps)
            INSTALL_SYSTEM_DEPS=1
            ;;
        --install-ollama)
            INSTALL_OLLAMA=1
            ;;
        --pull-model)
            PULL_MODEL=1
            ;;
        --model)
            shift
            [[ $# -gt 0 ]] || die "--model requires a value."
            MODEL_NAME="$1"
            ;;
        --profile)
            shift
            [[ $# -gt 0 ]] || die "--profile requires a value."
            PROFILE_NAME="$1"
            ;;
        --python)
            shift
            [[ $# -gt 0 ]] || die "--python requires a value."
            PYTHON_REQUESTED="$1"
            ;;
        --ollama-host)
            shift
            [[ $# -gt 0 ]] || die "--ollama-host requires a value."
            OLLAMA_HOST_VALUE="$1"
            export OLLAMA_HOST="${OLLAMA_HOST_VALUE}"
            ;;
        --tools-root)
            shift
            [[ $# -gt 0 ]] || die "--tools-root requires a value."
            TOOLS_ROOT="$(absolute_path "$1")"
            DOWNLOADS_DIR="${TOOLS_ROOT}/downloads"
            ;;
        --with-pythia8)
            WITH_PYTHIA8=1
            ;;
        --with-delphes)
            WITH_DELPHES=1
            ;;
        --with-madanalysis5)
            WITH_MADANALYSIS5=1
            ;;
        --deep-doctor)
            RUN_DEEP_DOCTOR=1
            ;;
        --validate-full-stack)
            RUN_FULL_STACK_VALIDATION=1
            ;;
        --full)
            INSTALL_SYSTEM_DEPS=1
            INSTALL_OLLAMA=1
            PULL_MODEL=1
            WITH_PYTHIA8=1
            WITH_DELPHES=1
            WITH_MADANALYSIS5=1
            RUN_DEEP_DOCTOR=1
            RUN_FULL_STACK_VALIDATION=1
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

if (( RUN_FULL_STACK_VALIDATION )) &&
    (( ! WITH_PYTHIA8 || ! WITH_DELPHES || ! WITH_MADANALYSIS5 )); then
    die "--validate-full-stack requires --with-pythia8, --with-delphes, and --with-madanalysis5."
fi

if (( DRY_RUN )); then
    LOG_FILE="/dev/null"
else
    mkdir -p "${LOG_DIR}"
    LOG_FILE="${LOG_DIR}/bootstrap_$(date -u +%Y%m%dT%H%M%SZ).log"
fi

[[ -f "${PROJECT_ROOT}/pyproject.toml" ]] || die "Run this script from the local_hep_agent repository."
[[ -d "${PROJECT_ROOT}/src/hep_agent" ]] || die "src/hep_agent is missing."

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

log "============================================================"
log "HEP AGENT INSTALLER"
log "============================================================"
log "Project: ${PROJECT_ROOT}"
log "Tools:   ${TOOLS_ROOT}"
log "Model:   ${MODEL_NAME}"
log "Profile: ${PROFILE_NAME}"
log "Platform: ${PLATFORM} ${ARCH}"
log "Ollama:  ${OLLAMA_HOST_VALUE}"
log "Log:     ${LOG_FILE}"
log ""

case "${PLATFORM}" in
    Linux)
        [[ -r /etc/os-release ]] || \
            die "Linux installation currently supports Ubuntu/Debian-family distributions only."

        # shellcheck disable=SC1091
        source /etc/os-release
        case "${ID:-}" in
            ubuntu|debian|linuxmint|pop)
                ;;
            *)
                die "Unsupported distribution '${ID:-unknown}'. Use Ubuntu/Debian for this installer."
                ;;
        esac

        [[ "${ARCH}" == "x86_64" || "${ARCH}" == "amd64" ]] || \
            die "Linux installation currently supports x86_64 only; detected ${ARCH}."
        ;;
    Darwin)
        [[ "${ARCH}" == "x86_64" || "${ARCH}" == "arm64" ]] || \
            die "Unsupported macOS architecture: ${ARCH}."

        if [[ -n "${HEP_AGENT_TEST_MACOS_VERSION:-}" ]]; then
            MACOS_VERSION="${HEP_AGENT_TEST_MACOS_VERSION}"
        else
            MACOS_VERSION="$(
                sw_vers -productVersion 2>/dev/null ||
                    printf 'unknown'
            )"
        fi
        log "macOS:   ${MACOS_VERSION}"

        MINIFORGE_DIR="${TOOLS_ROOT}/miniforge3"
        if [[ -r "${CONDA_ROOT_FILE}" ]]; then
            IFS= read -r STORED_CONDA_ROOT < "${CONDA_ROOT_FILE}"
            if [[ -x "${STORED_CONDA_ROOT}/bin/conda" ]]; then
                MINIFORGE_DIR="${STORED_CONDA_ROOT}"
            fi
        fi
        CONDA_EXECUTABLE="${MINIFORGE_DIR}/bin/conda"

        if (( INSTALL_OLLAMA || PULL_MODEL )) &&
            is_local_ollama_host &&
            [[ "${ARCH}" != "arm64" ]]; then
            die "Current Ollama for macOS requires Apple Silicon. Intel Macs must use --ollama-host with Ollama running on another computer."
        fi

        if (( INSTALL_OLLAMA || PULL_MODEL )) &&
            is_local_ollama_host &&
            [[ "${MACOS_VERSION}" != "unknown" ]] &&
            ! version_at_least "${MACOS_VERSION}" "14.0"; then
            die "Ollama requires macOS 14 or newer. This Mac must use --ollama-host with Ollama running on another computer."
        fi
        ;;
    *)
        die "Unsupported operating system '${PLATFORM}'. Use Ubuntu/Debian Linux or macOS."
        ;;
esac

if (( ! ASSUME_YES )); then
    if (( ! INSTALL_SYSTEM_DEPS )) && confirm "Install the required compiler and pinned Python packages"; then
        INSTALL_SYSTEM_DEPS=1
    fi

    if (( ! INSTALL_OLLAMA )) &&
        ! command -v ollama >/dev/null 2>&1 &&
        is_local_ollama_host &&
        {
            [[ "${PLATFORM}" != "Darwin" ]] ||
                {
                    [[ "${ARCH}" == "arm64" ]] &&
                        {
                            [[ "${MACOS_VERSION}" == "unknown" ]] ||
                                version_at_least "${MACOS_VERSION}" "14.0"
                        }
                }
        }; then
        if confirm "Install Ollama for local model access"; then
            INSTALL_OLLAMA=1
        fi
    fi

    if (( ! PULL_MODEL )) &&
        {
            ! is_local_ollama_host ||
                [[ "${PLATFORM}" != "Darwin" ]] ||
                {
                    [[ "${ARCH}" == "arm64" ]] &&
                        {
                            [[ "${MACOS_VERSION}" == "unknown" ]] ||
                                version_at_least "${MACOS_VERSION}" "14.0"
                        }
                }
        } &&
        confirm "Download the starter model ${MODEL_NAME} (about 4.7 GB)"; then
        PULL_MODEL=1
    fi

    if (( ! WITH_PYTHIA8 )) && confirm "Also install Pythia8 (optional; can take a while)"; then
        WITH_PYTHIA8=1
    fi

    if (( ! WITH_DELPHES )) && confirm "Also install ROOT and Delphes (optional; can take a while)"; then
        WITH_DELPHES=1
    fi

    if (( ! WITH_MADANALYSIS5 )) && confirm "Also install ROOT and MadAnalysis5 (optional; can take a while)"; then
        WITH_MADANALYSIS5=1
    fi
fi

if (( INSTALL_SYSTEM_DEPS )); then
    case "${PLATFORM}" in
        Linux)
            if (( DRY_RUN )); then
                log "+ sudo apt-get update"
                log "+ sudo apt-get install -y python3 python3-venv python3-dev python3-pip git curl wget ca-certificates build-essential gfortran make cmake pkg-config rsync tar gzip unzip xz-utils zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev"
            else
                command -v sudo >/dev/null 2>&1 || \
                    die "sudo is required for --install-system-deps."
                run_cmd sudo apt-get update
                run_cmd sudo apt-get install -y \
                    python3 python3-venv python3-dev python3-pip \
                    git curl wget ca-certificates \
                    build-essential gfortran make cmake pkg-config rsync \
                    tar gzip unzip xz-utils \
                    zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
                    libffi-dev liblzma-dev
            fi
            ;;
        Darwin)
            if (( ! DRY_RUN )); then
                command -v xcode-select >/dev/null 2>&1 || \
                    die "Apple Xcode command-line tools are required. Run: xcode-select --install"
                xcode-select -p >/dev/null 2>&1 || \
                    die "Apple Xcode command-line tools are missing. Run 'xcode-select --install', then rerun this installer."
            fi

            MINIFORGE_SHA256=""
            case "${ARCH}" in
                x86_64)
                    MINIFORGE_SHA256="a755192103de19bb2782685ac78820c2e00702e5f33e6e4f0a3bf3c214f45d69"
                    ;;
                arm64)
                    MINIFORGE_SHA256="2657d94152343cff7c06159ac9fc09624d7879fa9575c5a0a324c571c4df0ade"
                    ;;
            esac

            MINIFORGE_ARCHIVE="Miniforge3-${MINIFORGE_VERSION}-MacOSX-${ARCH}.sh"
            MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/${MINIFORGE_ARCHIVE}"
            MINIFORGE_ARCHIVE_PATH="${DOWNLOADS_DIR}/${MINIFORGE_ARCHIVE}"

            run_cmd mkdir -p "${TOOLS_ROOT}" "${DOWNLOADS_DIR}"

            if [[ ! -x "${CONDA_EXECUTABLE}" ]]; then
                if [[ ! -s "${MINIFORGE_ARCHIVE_PATH}" ]]; then
                    run_cmd curl \
                        --fail \
                        --location \
                        --retry 3 \
                        --retry-delay 3 \
                        --output "${MINIFORGE_ARCHIVE_PATH}.partial" \
                        "${MINIFORGE_URL}"

                    if (( ! DRY_RUN )); then
                        mv \
                            "${MINIFORGE_ARCHIVE_PATH}.partial" \
                            "${MINIFORGE_ARCHIVE_PATH}"
                    fi
                fi

                if (( DRY_RUN )); then
                    log "+ verify SHA-256 ${MINIFORGE_SHA256} for ${MINIFORGE_ARCHIVE_PATH}"
                else
                    command -v shasum >/dev/null 2>&1 || \
                        die "The shasum command is required to verify Miniforge."
                    ACTUAL_MINIFORGE_SHA256="$(
                        shasum -a 256 "${MINIFORGE_ARCHIVE_PATH}" |
                            awk '{print $1}'
                    )"
                    [[ "${ACTUAL_MINIFORGE_SHA256}" == "${MINIFORGE_SHA256}" ]] || \
                        die "Miniforge checksum verification failed."
                fi

                run_cmd bash \
                    "${MINIFORGE_ARCHIVE_PATH}" \
                    -b \
                    -p "${MINIFORGE_DIR}"
            else
                log "Miniforge already exists: ${MINIFORGE_DIR}"
            fi
            ;;
    esac
fi

for command_name in curl tar; do
    command -v "${command_name}" >/dev/null 2>&1 || \
        die "Missing '${command_name}'. Rerun with --install-system-deps."
done

run_cmd mkdir -p "${TOOLS_ROOT}" "${DOWNLOADS_DIR}" "${PROJECT_ROOT}/results"

if (( DRY_RUN )); then
    log "+ create ${TOOLS_ROOT}/${TOOLS_MARKER_NAME}"
else
    printf '%s\n' \
        "HEPLocalAgent managed tools directory" \
        > "${TOOLS_ROOT}/${TOOLS_MARKER_NAME}"
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    if [[ "${PLATFORM}" == "Darwin" && -z "${PYTHON_REQUESTED}" ]]; then
        if [[ ! -x "${CONDA_EXECUTABLE}" ]] &&
            ! (( DRY_RUN && INSTALL_SYSTEM_DEPS )); then
            die "The pinned macOS environment is missing. Rerun with --install-system-deps."
        fi

        run_cmd "${CONDA_EXECUTABLE}" create \
            --yes \
            --prefix "${VENV_DIR}" \
            python=3.11 \
            pip \
            "gfortran=13" \
            make \
            cmake \
            pkg-config \
            git \
            wget \
            rsync
    else
        if [[ -n "${PYTHON_REQUESTED}" ]]; then
            if command -v "${PYTHON_REQUESTED}" >/dev/null 2>&1; then
                PYTHON_COMMAND="$(command -v "${PYTHON_REQUESTED}")"
            elif [[ -x "${PYTHON_REQUESTED}" ]]; then
                PYTHON_COMMAND="${PYTHON_REQUESTED}"
            else
                die "Requested Python executable is unavailable: ${PYTHON_REQUESTED}"
            fi
        else
            PYTHON_COMMAND="$(command -v python3 || true)"
        fi

        [[ -n "${PYTHON_COMMAND}" ]] || \
            die "A compatible Python is required. Rerun with --install-system-deps."
        run_cmd "${PYTHON_COMMAND}" -m venv "${VENV_DIR}"
    fi
else
    log "Existing isolated environment found: ${VENV_DIR}"
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"

if (( DRY_RUN )) && [[ ! -x "${VENV_PYTHON}" ]]; then
    PYTHON_VERSION="3.11 (planned)"
else
    PYTHON_VERSION="$("${VENV_PYTHON}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"

    if ! "${VENV_PYTHON}" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
        die "Python ${PYTHON_VERSION} is too old. Python 3.10 or newer is required."
    fi

    if [[ "${PLATFORM}" == "Darwin" ]] &&
        ! "${VENV_PYTHON}" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)
PY
    then
        die "The macOS HEP environment must use Python 3.11; found ${PYTHON_VERSION}."
    fi
fi

log "Isolated Python ${PYTHON_VERSION}: ${VENV_PYTHON}"
export PATH="${VENV_DIR}/bin:${PATH}"

USING_CONDA_ENVIRONMENT=0
if [[ "${PLATFORM}" == "Darwin" ]] &&
    {
        [[ -d "${VENV_DIR}/conda-meta" ]] ||
            (( DRY_RUN && ! ${#PYTHON_REQUESTED} ))
    }; then
    USING_CONDA_ENVIRONMENT=1

    if (( DRY_RUN )); then
        log "+ activate pinned Conda environment ${VENV_DIR}"
    else
        [[ -f "${MINIFORGE_DIR}/etc/profile.d/conda.sh" ]] || \
            die "Miniforge activation script is missing."

        set +u
        # shellcheck disable=SC1090
        source "${MINIFORGE_DIR}/etc/profile.d/conda.sh"
        conda activate "${VENV_DIR}"
        set -u

        printf '%s\n' "${MINIFORGE_DIR}" > "${CONDA_ROOT_FILE}"
    fi
elif (( ! DRY_RUN )); then
    rm -f "${CONDA_ROOT_FILE}"
fi

if (( ! DRY_RUN )); then
    for command_name in git make gfortran; do
        command -v "${command_name}" >/dev/null 2>&1 || \
            die "Missing build tool '${command_name}'. Rerun with --install-system-deps."
    done
fi

if (( DRY_RUN )); then
    log "+ ${VENV_PYTHON} -m pip install --upgrade pip setuptools wheel"
    log "+ ${VENV_PYTHON} -m pip install -e ${PROJECT_ROOT}[web]"
else
    run_cmd "${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel
    run_cmd "${VENV_PYTHON}" -m pip install -e "${PROJECT_ROOT}[web]"
fi

MG5_LINK="${TOOLS_ROOT}/MG5_aMC"
MG5_NATIVE_EXECUTABLE="${MG5_LINK}/bin/mg5_aMC"
MG5_EXECUTABLE="${MG5_LINK}/bin/hep-agent-mg5"

if [[ ! -x "${MG5_NATIVE_EXECUTABLE}" ]]; then
    ARCHIVE_PATH="${DOWNLOADS_DIR}/${MG5_ARCHIVE}"

    if [[ ! -s "${ARCHIVE_PATH}" ]]; then
        if ! run_cmd curl --fail --location \
            --connect-timeout 30 \
            --speed-limit 1024 \
            --speed-time 30 \
            --max-time 300 \
            --retry 1 \
            --retry-delay 3 \
            --output "${ARCHIVE_PATH}.partial" \
            "${MG5_URL}"; then
            warn "Launchpad download failed; trying the official GitHub v${MG5_VERSION} tag."
            if (( ! DRY_RUN )); then
                rm -f "${ARCHIVE_PATH}.partial"
            fi
            run_cmd curl --fail --location \
                --connect-timeout 30 \
                --speed-limit 1024 \
                --speed-time 30 \
                --max-time 600 \
                --retry 3 \
                --retry-delay 3 \
                --output "${ARCHIVE_PATH}.partial" \
                "${MG5_GITHUB_URL}"
        fi
        if (( ! DRY_RUN )); then
            mv "${ARCHIVE_PATH}.partial" "${ARCHIVE_PATH}"
        fi
    else
        log "Using existing MG5 archive: ${ARCHIVE_PATH}"
    fi

    if (( DRY_RUN )); then
        log "+ verify SHA-256 against the pinned Launchpad or GitHub archive for ${ARCHIVE_PATH}"
        log "+ tar -tzf ${ARCHIVE_PATH} >/dev/null"
        log "+ tar -xzf ${ARCHIVE_PATH} -C ${TOOLS_ROOT}"
    else
        ACTUAL_MG5_SHA256="$(
            "${VENV_PYTHON}" -c \
                'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
                "${ARCHIVE_PATH}"
        )"
        [[ "${ACTUAL_MG5_SHA256}" == "${MG5_SHA256}" ||
            "${ACTUAL_MG5_SHA256}" == "${MG5_GITHUB_SHA256}" ]] || \
            die "MadGraph archive checksum verification failed."
        tar -tzf "${ARCHIVE_PATH}" >/dev/null || die "Downloaded MG5 archive is invalid."
        TOP_DIRECTORY="$("${VENV_PYTHON}" -c 'import sys, tarfile; archive = tarfile.open(sys.argv[1], "r:gz"); member = next(iter(archive), None); print(member.name.split("/", 1)[0]) if member else sys.exit("MadGraph archive is empty.")' "${ARCHIVE_PATH}")"
        [[ -n "${TOP_DIRECTORY}" ]] || die "Could not identify the MG5 archive directory."

        if [[ ! -d "${TOOLS_ROOT}/${TOP_DIRECTORY}" ]]; then
            run_cmd tar -xzf "${ARCHIVE_PATH}" -C "${TOOLS_ROOT}"
        fi

        [[ -x "${TOOLS_ROOT}/${TOP_DIRECTORY}/bin/mg5_aMC" ]] || \
            die "MG5 extraction completed but bin/mg5_aMC is missing."

        ln -sfn "${TOOLS_ROOT}/${TOP_DIRECTORY}" "${MG5_LINK}"
    fi
else
    log "MadGraph already exists: ${MG5_NATIVE_EXECUTABLE}"
fi

if (( ! DRY_RUN )); then
    [[ -x "${MG5_NATIVE_EXECUTABLE}" ]] || \
        die "MadGraph executable is unavailable after installation."

    {
        printf '%s\n' '#!/usr/bin/env bash'

        if (( USING_CONDA_ENVIRONMENT )); then
            printf 'exec %q run --no-capture-output --prefix %q python %q "$@"\n' \
                "${CONDA_EXECUTABLE}" \
                "${VENV_DIR}" \
                "${MG5_NATIVE_EXECUTABLE}"
        else
            printf 'exec %q %q "$@"\n' \
                "${VENV_PYTHON}" \
                "${MG5_NATIVE_EXECUTABLE}"
        fi
    } > "${MG5_EXECUTABLE}"
    chmod +x "${MG5_EXECUTABLE}"
    log "Pinned MadGraph launcher: ${MG5_EXECUTABLE}"
else
    log "+ create ${MG5_EXECUTABLE} using isolated Python ${VENV_PYTHON}"
fi

if (( DRY_RUN )); then
    log "+ verify MadGraph starts with the isolated Python environment"
else
    MG5_SMOKE_COMMAND_FILE="$(mktemp)"
    printf '%s\n' \
        "import model sm" \
        "display multiparticles" \
        "quit" > "${MG5_SMOKE_COMMAND_FILE}"

    if ! run_cmd "${MG5_EXECUTABLE}" "${MG5_SMOKE_COMMAND_FILE}"; then
        rm -f "${MG5_SMOKE_COMMAND_FILE}"
        die "MadGraph could not start inside the isolated Python environment."
    fi
    rm -f "${MG5_SMOKE_COMMAND_FILE}"
    log "MadGraph isolated-Python smoke test passed."
fi

MG5_TOOL_TIMEOUT_SECONDS="${HEP_AGENT_TOOL_TIMEOUT_SECONDS:-2700}"
[[ "${MG5_TOOL_TIMEOUT_SECONDS}" =~ ^[0-9]+$ ]] || \
    die "HEP_AGENT_TOOL_TIMEOUT_SECONDS must be a positive integer."

OPTIONAL_FAILURES=()

ROOT_VERSION="6.40.02"
ROOT_ARCHIVE="root_v${ROOT_VERSION}.Linux-ubuntu24.04-x86_64-gcc13.3.tar.gz"
ROOT_URL="https://root.cern/download/${ROOT_ARCHIVE}"
ROOT_DIR="${TOOLS_ROOT}/root-${ROOT_VERSION}"
ROOT_LINK="${TOOLS_ROOT}/root"
ROOT_SETUP="${ROOT_LINK}/bin/thisroot.sh"
ROOT_ARCHIVE_PATH="${DOWNLOADS_DIR}/${ROOT_ARCHIVE}"

find_pythia_install() {
    local candidate

    while IFS= read -r candidate; do
        if [[ -x "${candidate}" ]]; then
            printf '%s\n' "${candidate}"
            return
        fi
    done < <(
        find -L "${MG5_LINK}" \
            -type f \
            -name "pythia8-config" \
            -print \
            2>/dev/null
    )
}

find_delphes_hepmc2() {
    local candidate="${MG5_LINK}/Delphes/DelphesHepMC2"

    if [[ -x "${candidate}" ]]; then
        printf '%s\n' "${candidate}"
        return
    fi

    find -L "${MG5_LINK}" \
        -type f \
        -name "DelphesHepMC2" \
        -perm -u+x \
        -print \
        -quit \
        2>/dev/null ||
        true

    return 0
}

verify_linux_delphes_runtime() {
    local candidate="$1"
    local relocation_report
    local root_prefix
    local root_libdir
    local loaded_core
    local resolved_root_libdir
    local resolved_loaded_core

    [[ "${PLATFORM}" == "Linux" ]] || return 0
    [[ -x "${candidate}" ]] || return 1
    activate_root || return 1

    root_prefix="$(root-config --prefix)" || return 1
    root_libdir="$(root-config --libdir)" || return 1

    relocation_report="$(
        LD_BIND_NOW=1 ldd -r "${candidate}" 2>&1
    )" || return 1

    if grep -Eiq \
        'undefined symbol|not found|symbol lookup error' \
        <<< "${relocation_report}"; then
        return 1
    fi

    loaded_core="$(
        ldd "${candidate}" 2>/dev/null |
            awk '$1 == "libCore.so" {print $3; exit}'
    )"
    [[ -n "${loaded_core}" && -e "${loaded_core}" ]] || return 1

    resolved_root_libdir="$(readlink -f "${root_libdir}")"
    resolved_loaded_core="$(readlink -f "${loaded_core}")"
    case "${resolved_loaded_core}" in
        "${resolved_root_libdir}"/*)
            ;;
        *)
            return 1
            ;;
    esac

    # Catch the exact mixed-build failure found in the Linux acceptance test:
    # Delphes was compiled with Snap ROOT headers/runpath but loaded /opt/root.
    if [[ "${root_prefix}" != /snap/* ]] &&
        readelf -d "${candidate}" 2>/dev/null |
            grep -Fq "/snap/root-framework/"; then
        return 1
    fi

    return 0
}

find_delphes_install() {
    local candidate

    candidate="$(find_delphes_hepmc2)"
    if [[ -n "${candidate}" ]]; then
        if [[ "${PLATFORM}" != "Linux" ]] ||
            verify_linux_delphes_runtime "${candidate}"; then
            printf '%s\n' "${candidate}"
            return
        fi
    fi

    # Non-Linux installations may provide a different Delphes frontend.
    if [[ "${PLATFORM}" == "Linux" ]]; then
        return 0
    fi

    for candidate in \
        "${MG5_LINK}/Delphes/DelphesHepMC" \
        "${MG5_LINK}/Delphes/DelphesHepMC3" \
        "${MG5_LINK}/Delphes/DelphesSTDHEP" \
        "${MG5_LINK}/Delphes/DelphesPythia8"; do
        if [[ -x "${candidate}" ]]; then
            printf '%s\n' "${candidate}"
            return
        fi
    done

    return 0
}

find_ma5_install() {
    local candidate

    while IFS= read -r candidate; do
        if [[ -x "${candidate}" ]]; then
            printf '%s\n' "${candidate}"
            return
        fi
    done < <(
        find -L "${MG5_LINK}" \
            -type f \
            -path "*/madanalysis5/*/bin/ma5" \
            -print \
            2>/dev/null
    )
}

root_config_is_supported() {
    local root_config="${1:-}"
    local root_prefix

    [[ -n "${root_config}" && -x "${root_config}" ]] || return 1
    root_prefix="$("${root_config}" --prefix 2>/dev/null)" || return 1

    if [[ "${PLATFORM}" == "Linux" ]]; then
        case "${root_config}" in
            /snap/*)
                return 1
                ;;
        esac
        case "${root_prefix}" in
            /snap/*)
                return 1
                ;;
        esac
    fi

    return 0
}

activate_root() {
    local root_config
    local root_libdir
    local root_prefix
    local root_setup_candidate=""
    local source_status

    if [[ -f "${ROOT_DIR}/bin/thisroot.sh" && ! -e "${ROOT_LINK}" ]]; then
        ln -sfn "${ROOT_DIR}" "${ROOT_LINK}"
    fi

    if [[ -f "${ROOT_SETUP}" ]]; then
        root_setup_candidate="${ROOT_SETUP}"
    elif [[ "${PLATFORM}" == "Linux" &&
        -f "/opt/root/bin/thisroot.sh" ]]; then
        # Prefer the conventional unpacked ROOT installation over Snap ROOT.
        # Snap's relocated rootcint cannot reliably build Delphes/MA5 using
        # their relative LinkDef header paths.
        root_setup_candidate="/opt/root/bin/thisroot.sh"
    fi

    if [[ -n "${root_setup_candidate}" ]]; then
        set +u
        # shellcheck disable=SC1090
        source "${root_setup_candidate}"
        source_status=$?
        set -u

        (( source_status == 0 )) || return 1
    fi

    root_config="$(command -v root-config 2>/dev/null || true)"
    root_config_is_supported "${root_config}" || return 1

    root_prefix="$("${root_config}" --prefix)" || return 1
    root_libdir="$("${root_config}" --libdir)" || return 1

    # Set these unconditionally so a previously activated Snap ROOT cannot
    # leak into the selected, supported ROOT environment.
    export ROOTSYS="${root_prefix}"
    export PATH="$(dirname -- "${root_config}"):${PATH}"
    if [[ "${PLATFORM}" == "Darwin" ]]; then
        export DYLD_LIBRARY_PATH="${root_libdir}${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
    else
        export LD_LIBRARY_PATH="${root_libdir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    fi

    command -v rootcint >/dev/null 2>&1 || return 1
}

verify_root_runtime() {
    activate_root || return 1

    local missing_libraries
    missing_libraries=""

    if [[ "${PLATFORM}" == "Linux" ]]; then
        missing_libraries="$(
            ldd "$(command -v rootcint)" 2>/dev/null |
                awk '/not found/ {print $1}' ||
                true
        )"
    fi

    if [[ -n "${missing_libraries}" ]]; then
        warn "ROOT has unresolved runtime libraries:"
        while IFS= read -r library; do
            [[ -n "${library}" ]] && warn "  ${library}"
        done <<< "${missing_libraries}"
        return 1
    fi

    root-config --version >/dev/null 2>&1 || return 1
    return 0
}

install_root_dependency() {
    if [[ "${PLATFORM}" == "Darwin" ]]; then
        if verify_root_runtime; then
            log "ROOT $(root-config --version) is available."
            return 0
        fi

        if [[ ! -x "${CONDA_EXECUTABLE}" ]] &&
            ! (( DRY_RUN && INSTALL_SYSTEM_DEPS )); then
            warn "The pinned Miniforge installation is required for ROOT on macOS."
            warn "Rerun with --install-system-deps."
            return 1
        fi

        if (( DRY_RUN )); then
            log "+ ${CONDA_EXECUTABLE} install --yes --prefix ${VENV_DIR} --channel conda-forge --strict-channel-priority root"
            return 0
        fi

        log "Installing ROOT in the pinned macOS environment through conda-forge."
        if ! run_cmd "${CONDA_EXECUTABLE}" install \
            --yes \
            --prefix "${VENV_DIR}" \
            --channel conda-forge \
            --strict-channel-priority \
            root; then
            warn "ROOT installation through conda-forge failed."
            return 1
        fi

        hash -r
        if ! verify_root_runtime; then
            warn "ROOT was installed but its runtime validation failed."
            return 1
        fi

        log "ROOT $(root-config --version) installed in ${VENV_DIR}."
        return 0
    fi

    if command -v root-config >/dev/null 2>&1 &&
        ! root_config_is_supported "$(command -v root-config)"; then
        warn "Ignoring unsupported Snap ROOT: $(command -v root-config)"
        warn "Using /opt/root when available, otherwise installing a managed ROOT copy."
    fi

    if verify_root_runtime; then
        log "ROOT $(root-config --version) is available."
        return 0
    fi

    log "Installing ROOT runtime dependencies."

    local -a root_packages=(
        binutils
        cmake
        dpkg-dev
        g++
        gcc
        libssl-dev
        git
        libx11-dev
        libxext-dev
        libxft-dev
        libxpm-dev
        python3
        libtbb12
        libtbb-dev
        libvdt-dev
        libgif-dev
    )

    if (( DRY_RUN )); then
        log "+ sudo apt-get update"
        log "+ sudo apt-get install -y $(printf '%q ' "${root_packages[@]}")"
        log "+ curl -fL --retry 3 -o ${ROOT_ARCHIVE_PATH} ${ROOT_URL}"
        log "+ tar -xzf ${ROOT_ARCHIVE_PATH} -C ${ROOT_DIR} --strip-components=1"
        log "+ source ${ROOT_SETUP}"
        return 0
    fi

    command -v sudo >/dev/null 2>&1 || {
        warn "sudo is required to install ROOT runtime dependencies."
        return 1
    }

    if ! run_cmd sudo apt-get update; then
        warn "Could not update apt package metadata for ROOT."
        return 1
    fi

    if ! run_cmd sudo apt-get install -y "${root_packages[@]}"; then
        warn "Could not install the required ROOT runtime packages."
        return 1
    fi

    # An existing ROOT installation may only have been missing runtime
    # libraries such as libtbb.so.12.
    if verify_root_runtime; then
        log "ROOT $(root-config --version) is now usable."
        return 0
    fi

    if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
        warn "Automatic ROOT download currently supports Ubuntu 24.04 only."
        warn "Install ROOT manually and rerun the installer."
        return 1
    fi

    if [[ ! -s "${ROOT_ARCHIVE_PATH}" ]]; then
        if ! run_cmd curl \
            --fail \
            --location \
            --retry 3 \
            --retry-delay 3 \
            --output "${ROOT_ARCHIVE_PATH}.partial" \
            "${ROOT_URL}"; then
            warn "ROOT download failed."
            return 1
        fi

        if ! mv \
            "${ROOT_ARCHIVE_PATH}.partial" \
            "${ROOT_ARCHIVE_PATH}"; then
            warn "Could not finalize the downloaded ROOT archive."
            return 1
        fi
    else
        log "Using existing ROOT archive: ${ROOT_ARCHIVE_PATH}"
    fi

    if ! tar -tzf "${ROOT_ARCHIVE_PATH}" >/dev/null; then
        warn "Downloaded ROOT archive is invalid."
        return 1
    fi

    rm -rf "${ROOT_DIR}"

    if ! mkdir -p "${ROOT_DIR}"; then
        warn "Could not create the ROOT installation directory."
        return 1
    fi

    if ! run_cmd tar \
        -xzf "${ROOT_ARCHIVE_PATH}" \
        -C "${ROOT_DIR}" \
        --strip-components=1; then
        warn "ROOT archive extraction failed."
        return 1
    fi

    if [[ ! -f "${ROOT_DIR}/bin/thisroot.sh" ]]; then
        warn "ROOT extraction finished without bin/thisroot.sh."
        return 1
    fi

    ln -sfn "${ROOT_DIR}" "${ROOT_LINK}"

    if ! verify_root_runtime; then
        warn "ROOT was extracted but its runtime validation failed."
        return 1
    fi

    log "ROOT $(root-config --version) installed at ${ROOT_DIR}."
    return 0
}

run_timed_command() {
    local timeout_seconds="$1"
    shift

    "${VENV_PYTHON}" - "${timeout_seconds}" "$@" <<'PY'
import os
import signal
import subprocess
import sys

timeout_seconds = int(sys.argv[1])
command = sys.argv[2:]
process = subprocess.Popen(
    command,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)

try:
    raise SystemExit(process.wait(timeout=timeout_seconds))
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    raise SystemExit(124)
PY
}

install_mg5_tool() {
    local display_name="$1"
    local mg5_command="$2"
    local verifier="$3"
    local debug_mode="${4:-0}"
    local force_reinstall="${5:-0}"
    local native_apple_clang="${6:-0}"

    local installed_path
    installed_path="$("${verifier}")"

    if (( ! DRY_RUN && ! force_reinstall )) && [[ -n "${installed_path}" ]]; then
        log "${display_name} is already installed: ${installed_path}"
        return 0
    fi

    log "Installing ${display_name} through MadGraph."
    log "Maximum installation time: ${MG5_TOOL_TIMEOUT_SECONDS} seconds."

    if (( DRY_RUN )); then
        if (( native_apple_clang )); then
            log "+ compile with CC=/usr/bin/clang and CXX=/usr/bin/clang++ without Conda compiler/linker flags"
        fi
        if (( debug_mode )); then
            log "+ isolated-Python timeout ${MG5_TOOL_TIMEOUT_SECONDS}s ${MG5_EXECUTABLE} --debug <command-file>"
        else
            log "+ isolated-Python timeout ${MG5_TOOL_TIMEOUT_SECONDS}s ${MG5_EXECUTABLE} <command-file>"
        fi
        return 0
    fi

    local command_file
    command_file="$(mktemp)"
    printf '%s\nquit\n' "${mg5_command}" > "${command_file}"

    # Apple still ships Bash 3.2, where expanding an empty array under
    # `set -u` raises "unbound variable". Keep the invocation array non-empty
    # so the normal (non-debug) Pythia8 path works on macOS as well as Linux.
    local -a mg5_invocation=("${MG5_EXECUTABLE}")
    if (( native_apple_clang )); then
        # Invoke MG5 with the pinned Python directly. Using `conda run` here
        # would reintroduce the Conda compiler/linker environment that caused
        # Pythia's std::locale destructor to free memory owned by a different
        # libc++ runtime on Apple Silicon.
        mg5_invocation=("${VENV_PYTHON}" "${MG5_NATIVE_EXECUTABLE}")
    fi
    if (( debug_mode )); then
        mg5_invocation+=(--debug)
    fi
    mg5_invocation+=("${command_file}")

    local tool_status=0
    local tee_status=0
    local -a pipeline_statuses=()

    if (( native_apple_clang )); then
        if (
            unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
            unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH
            export CC="/usr/bin/clang"
            export CXX="/usr/bin/clang++"

            run_timed_command \
                "${MG5_TOOL_TIMEOUT_SECONDS}" \
                "${mg5_invocation[@]}"
        ) 2>&1 | tee -a "${LOG_FILE}"; then
            :
        else
            pipeline_statuses=("${PIPESTATUS[@]}")
            tool_status="${pipeline_statuses[0]}"
            tee_status="${pipeline_statuses[1]}"
        fi
    else
        if run_timed_command \
            "${MG5_TOOL_TIMEOUT_SECONDS}" \
            "${mg5_invocation[@]}" \
            2>&1 | tee -a "${LOG_FILE}"; then
            :
        else
            pipeline_statuses=("${PIPESTATUS[@]}")
            tool_status="${pipeline_statuses[0]}"
            tee_status="${pipeline_statuses[1]}"
        fi
    fi

    rm -f "${command_file}"

    if (( tee_status != 0 )); then
        warn "Could not write the installer log during ${display_name} installation."
        return 1
    fi

    if (( tool_status == 124 || tool_status == 137 )); then
        warn "${display_name} installation exceeded the configured timeout."
        return 1
    fi

    if (( tool_status != 0 )); then
        warn "${display_name} installer returned exit code ${tool_status}."
        return 1
    fi

    installed_path="$("${verifier}")"

    if [[ -z "${installed_path}" ]]; then
        warn "${display_name} reported completion but no runnable installation was found."
        return 1
    fi

    log "${display_name} installation verified: ${installed_path}"
    return 0
}

install_macos_arm64_native_hepmc2() {
    local native_prefix="${MG5_LINK}/HEPTools/hepmc2-native-${HEPMC2_VERSION}"
    local hepmc_library="${native_prefix}/lib/libHepMC.a"
    local hepmc_headers="${native_prefix}/include/HepMC"
    local hepmc_marker="${native_prefix}/.heptoolbench-apple-clang"
    local hepmc_archive_path="${DOWNLOADS_DIR}/${HEPMC2_ARCHIVE}"
    local build_root
    local source_root
    local cmake_file
    local candidate_root
    local build_jobs="${HEP_AGENT_BUILD_JOBS:-2}"

    [[ "${PLATFORM}" == "Darwin" && "${ARCH}" == "arm64" ]] || return 1
    [[ "${build_jobs}" =~ ^[1-9][0-9]*$ ]] || {
        warn "HEP_AGENT_BUILD_JOBS must be a positive integer."
        return 1
    }

    if [[ -e "${hepmc_library}" &&
        -d "${hepmc_headers}" &&
        -f "${hepmc_marker}" ]]; then
        log "Apple-Clang HepMC2 dependency is available in ${native_prefix}."
        MACOS_ARM64_HEPMC2_PREFIX="${native_prefix}"
        return 0
    fi

    if (( ! DRY_RUN )); then
        for command_name in cmake shasum; do
            command -v "${command_name}" >/dev/null 2>&1 || {
                warn "The '${command_name}' command is required for native HepMC2."
                warn "Rerun with --install-system-deps."
                return 1
            }
        done

        [[ -x /usr/bin/clang && -x /usr/bin/clang++ ]] || {
            warn "Apple Clang is required for native HepMC2."
            warn "Install the Xcode command-line tools and rerun."
            return 1
        }
    fi

    if [[ ! -s "${hepmc_archive_path}" ]]; then
        if ! run_cmd curl \
            --fail \
            --location \
            --retry 3 \
            --retry-delay 3 \
            --output "${hepmc_archive_path}.partial" \
            "${HEPMC2_URL}"; then
            warn "HepMC2 source download failed."
            return 1
        fi

        if (( ! DRY_RUN )); then
            mv "${hepmc_archive_path}.partial" "${hepmc_archive_path}"
        fi
    else
        log "Using existing HepMC2 archive: ${hepmc_archive_path}"
    fi

    if (( DRY_RUN )); then
        log "+ verify SHA-256 ${HEPMC2_SHA256} for ${hepmc_archive_path}"
        log "+ build static HepMC2 ${HEPMC2_VERSION} with /usr/bin/clang++"
        log "+ install native HepMC2 to ${native_prefix}"
        MACOS_ARM64_HEPMC2_PREFIX="${native_prefix}"
        return 0
    fi

    local actual_hepmc2_sha256
    actual_hepmc2_sha256="$(
        shasum -a 256 "${hepmc_archive_path}" |
            awk '{print $1}'
    )"
    if [[ "${actual_hepmc2_sha256}" != "${HEPMC2_SHA256}" ]]; then
        warn "HepMC2 checksum verification failed."
        return 1
    fi

    if ! tar -tzf "${hepmc_archive_path}" >/dev/null; then
        warn "Downloaded HepMC2 archive is invalid."
        return 1
    fi

    build_root="$(mktemp -d)"
    if ! tar -xzf "${hepmc_archive_path}" -C "${build_root}"; then
        warn "Could not extract HepMC2."
        rm -rf "${build_root}"
        return 1
    fi

    # The download is named hepmc2.06.11.tgz, but its top-level source
    # directory is HepMC-2.06.11. Discover the source by its contents instead
    # of deriving a directory name from the archive filename.
    source_root=""
    while IFS= read -r cmake_file; do
        candidate_root="${cmake_file%/CMakeLists.txt}"
        if [[ -d "${candidate_root}/HepMC" &&
            -d "${candidate_root}/src" ]]; then
            source_root="${candidate_root}"
            break
        fi
    done < <(
        find "${build_root}" \
            -mindepth 1 \
            -maxdepth 3 \
            -type f \
            -name "CMakeLists.txt" \
            -print 2>/dev/null
    )
    if [[ -z "${source_root}" ]]; then
        warn "Could not locate the extracted HepMC2 source root."
        rm -rf "${build_root}"
        return 1
    fi

    # This prefix belongs exclusively to HEPLocalAgent and is safe to replace.
    rm -rf "${native_prefix}"

    (
        unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
        unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH
        export CC="/usr/bin/clang"
        export CXX="/usr/bin/clang++"

        run_timed_command \
            "${MG5_TOOL_TIMEOUT_SECONDS}" \
            cmake \
            -S "${source_root}" \
            -B "${build_root}/build" \
            -DCMAKE_BUILD_TYPE=Release \
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
            -DCMAKE_INSTALL_PREFIX="${native_prefix}" \
            -DCMAKE_OSX_ARCHITECTURES=arm64 \
            -DBUILD_SHARED_LIBS=OFF \
            -Dmomentum:STRING=GEV \
            -Dlength:STRING=MM &&
            run_timed_command \
                "${MG5_TOOL_TIMEOUT_SECONDS}" \
                cmake \
                --build "${build_root}/build" \
                --parallel "${build_jobs}" &&
            run_timed_command \
                "${MG5_TOOL_TIMEOUT_SECONDS}" \
                cmake \
                --install "${build_root}/build"
    ) 2>&1 | tee -a "${LOG_FILE}"
    local build_status="${PIPESTATUS[0]}"
    rm -rf "${build_root}"

    if (( build_status != 0 )); then
        warn "Native Apple-Clang HepMC2 build failed."
        return 1
    fi

    if [[ ! -e "${hepmc_library}" || ! -d "${hepmc_headers}" ]]; then
        warn "Native HepMC2 was built but its static library or headers are missing."
        return 1
    fi

    printf '%s\n' \
        "HepMC2 ${HEPMC2_VERSION}; Apple Clang; static; arm64" \
        > "${hepmc_marker}"

    MACOS_ARM64_HEPMC2_PREFIX="${native_prefix}"
    log "Native Apple-Clang HepMC2 installed in ${native_prefix}."
    return 0
}

configure_mg5_pythia_paths() {
    local hepmc_prefix="$1"
    local pythia_prefix="$2"
    local -a configuration_files=()
    local configuration_file

    if (( DRY_RUN )); then
        log "+ set hepmc_path = ${hepmc_prefix} and pythia8_path = ${pythia_prefix} in MG5 and existing process configurations"
        return 0
    fi

    while IFS= read -r configuration_file; do
        configuration_files+=("${configuration_file}")
    done < <(
        find -L "${MG5_LINK}" \
            -maxdepth 4 \
            -type f \
            \( \
                -name "mg5_configuration.txt" \
                -o -name "me5_configuration.txt" \
                -o -name "amcatnlo_configuration.txt" \
            \) \
            -print \
            2>/dev/null
    )

    if (( ${#configuration_files[@]} == 0 )); then
        warn "No MadGraph configuration files were found."
        return 1
    fi

    if ! "${VENV_PYTHON}" - \
        "${hepmc_prefix}" \
        "${pythia_prefix}" \
        "${configuration_files[@]}" <<'PY'
from pathlib import Path
import re
import sys

hepmc_path = sys.argv[1]
pythia_path = sys.argv[2]
paths = [Path(value) for value in sys.argv[3:]]
settings = {
    "hepmc_path": hepmc_path,
    "pythia8_path": pythia_path,
}

for path in paths:
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = []
    written = set()

    for line in lines:
        matched = False
        for key, value in settings.items():
            pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=.*$")
            if pattern.match(line):
                if key not in written:
                    updated.append(f"{key} = {value}")
                    written.add(key)
                matched = True
                break
        if not matched:
            updated.append(line)

    for key, value in settings.items():
        if key not in written:
            updated.append(f"{key} = {value}")

    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY
    then
        warn "Could not register native Pythia8 and HepMC2 paths with MadGraph."
        return 1
    fi

    log "Registered native Pythia8 and HepMC2 paths in ${#configuration_files[@]} MadGraph configuration file(s)."
    return 0
}

verify_macos_arm64_native_pythia() {
    local pythia_config
    local pythia_prefix
    local pythia_library
    local marker
    local linked_libraries

    pythia_config="$(find_pythia_install)"
    [[ -n "${pythia_config}" ]] || return 1

    pythia_prefix="$(cd -- "$(dirname -- "${pythia_config}")/.." && pwd)"
    marker="${pythia_prefix}/.heptoolbench-apple-clang"
    pythia_library="$(
        find "${pythia_prefix}/lib" \
            -maxdepth 1 \
            -type f \
            -name "libpythia8*.dylib" \
            -print \
            2>/dev/null |
            head -n 1
    )"

    [[ -n "${pythia_library}" && -f "${marker}" ]] || return 1

    linked_libraries="$(otool -L "${pythia_library}")" || return 1

    if grep -Fq "${VENV_DIR}/lib/libc++" <<< "${linked_libraries}"; then
        warn "Pythia8 still links to the Conda libc++ runtime."
        return 1
    fi

    if ! grep -Fq \
        "/usr/lib/libc++.1.dylib" \
        <<< "${linked_libraries}"; then
        warn "Pythia8 does not link to the native macOS libc++ runtime."
        return 1
    fi

    return 0
}

patch_macos_delphes_makefile() {
    local delphes_makefile="${MG5_LINK}/Delphes/Makefile"

    [[ -f "${delphes_makefile}" ]] || return 1

    if grep -Fq \
        "CXXFLAGS += -D_LIBCPP_DISABLE_AVAILABILITY" \
        "${delphes_makefile}"; then
        return 0
    fi

    "${VENV_PYTHON}" - "${delphes_makefile}" <<'PY'
from pathlib import Path
import sys

makefile = Path(sys.argv[1])
text = makefile.read_text(encoding="utf-8")
anchor = "include doc/Makefile.arch\n"
addition = (
    "\n"
    "# HEPLocalAgent macOS compatibility: Delphes' platform makefile replaces\n"
    "# environment CXXFLAGS, so this flag must be added after that include.\n"
    "CXXFLAGS += -D_LIBCPP_DISABLE_AVAILABILITY\n"
)

if anchor not in text:
    raise SystemExit("Could not find Delphes Makefile.arch include")

makefile.write_text(
    text.replace(anchor, anchor + addition, 1),
    encoding="utf-8",
)
PY
}

repair_macos_delphes_build() {
    local delphes_dir="${MG5_LINK}/Delphes"
    local build_jobs="${HEP_AGENT_BUILD_JOBS:-2}"
    local installed_path

    [[ "${PLATFORM}" == "Darwin" ]] || return 1
    [[ -f "${delphes_dir}/Makefile" ]] || return 1
    [[ "${build_jobs}" =~ ^[1-9][0-9]*$ ]] || {
        warn "HEP_AGENT_BUILD_JOBS must be a positive integer."
        return 1
    }

    log "Repairing the downloaded Delphes build for conda-forge libc++."

    if ! patch_macos_delphes_makefile; then
        warn "Could not add the libc++ compatibility flag to the Delphes Makefile."
        return 1
    fi

    # A previous MG5 attempt may have produced object files without the
    # required definition. Clean first so every translation unit is rebuilt.
    if ! run_timed_command \
        "${MG5_TOOL_TIMEOUT_SECONDS}" \
        make -C "${delphes_dir}" clean; then
        warn "Could not clean the partial Delphes build."
        return 1
    fi

    if ! run_timed_command \
        "${MG5_TOOL_TIMEOUT_SECONDS}" \
        make -C "${delphes_dir}" -j"${build_jobs}"; then
        warn "The repaired Delphes build failed."
        return 1
    fi

    installed_path="$(find_delphes_install)"
    if [[ -z "${installed_path}" ]]; then
        warn "Delphes compiled without producing a runnable executable."
        return 1
    fi

    log "Delphes installation verified after macOS repair: ${installed_path}"
    return 0
}

repair_linux_delphes_build() {
    local delphes_dir="${MG5_LINK}/Delphes"
    local build_jobs="${HEP_AGENT_BUILD_JOBS:-2}"
    local root_config
    local root_bindir
    local root_libdir
    local root_prefix
    local clean_path
    local installed_path
    local -a clean_environment=()

    [[ "${PLATFORM}" == "Linux" ]] || return 1
    [[ -f "${delphes_dir}/Makefile" ]] || return 1
    [[ "${build_jobs}" =~ ^[1-9][0-9]*$ ]] || {
        warn "HEP_AGENT_BUILD_JOBS must be a positive integer."
        return 1
    }

    if ! activate_root; then
        warn "Cannot rebuild Delphes because ROOT is not active."
        return 1
    fi

    root_config="$(command -v root-config)"
    root_bindir="$(dirname -- "${root_config}")"
    root_libdir="$(root-config --libdir)"
    root_prefix="$(root-config --prefix)"
    clean_path="${root_bindir}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    clean_environment=(
        env
        -u CFLAGS
        -u CXXFLAGS
        -u CPPFLAGS
        -u LDFLAGS
        -u CPATH
        -u C_INCLUDE_PATH
        -u CPLUS_INCLUDE_PATH
        -u LIBRARY_PATH
        -u PKG_CONFIG_PATH
        -u ROOT_INCLUDE_PATH
        "ROOTSYS=${root_prefix}"
        "PATH=${clean_path}"
        "LD_LIBRARY_PATH=${root_libdir}"
    )

    log "Rebuilding Delphes against one Linux ROOT installation."
    log "ROOT configuration: ${root_config}"
    log "ROOT prefix:        ${root_prefix}"

    # MG5 may have compiled some objects before the final ROOT environment was
    # selected. A clean rebuild is required because those objects retain the
    # C++ ABI of the ROOT headers used for their original compilation.
    if ! run_timed_command \
        "${MG5_TOOL_TIMEOUT_SECONDS}" \
        "${clean_environment[@]}" \
        make -C "${delphes_dir}" clean; then
        warn "Could not clean the existing Linux Delphes build."
        return 1
    fi

    if ! run_timed_command \
        "${MG5_TOOL_TIMEOUT_SECONDS}" \
        "${clean_environment[@]}" \
        make -C "${delphes_dir}" -j"${build_jobs}"; then
        warn "The clean Linux Delphes rebuild failed."
        return 1
    fi

    installed_path="$(find_delphes_install)"
    if [[ -z "${installed_path}" ]]; then
        warn "DelphesHepMC2 still has unresolved or mismatched ROOT symbols."
        return 1
    fi

    log "Linux Delphes runtime verified after clean rebuild: ${installed_path}"
    return 0
}

ROOT_READY=1
if (( WITH_DELPHES || WITH_MADANALYSIS5 )); then
    if ! install_root_dependency; then
        ROOT_READY=0
        OPTIONAL_FAILURES+=("ROOT")
    fi
fi

if (( WITH_PYTHIA8 )); then
    PYTHIA8_INSTALL_COMMAND="install pythia8 --force"
    PYTHIA8_DEPENDENCIES_READY=1
    PYTHIA8_FORCE_REINSTALL=0
    PYTHIA8_NATIVE_APPLE_CLANG=0

    if [[ "${PLATFORM}" == "Darwin" && "${ARCH}" == "arm64" ]]; then
        # MG5's bundled HepMC 2.06.09 rejects Apple's arm64 build triplet.
        # A Conda HepMC2 workaround can compile, but mixing Conda libc++ with
        # MG5's Pythia/interface causes an invalid free in Pythia::~Pythia().
        # Build static HepMC2 and Pythia with one Apple Clang/libc++ toolchain.
        if verify_macos_arm64_native_pythia; then
            log "Native Apple-Clang Pythia8 installation is already verified."
            PYTHIA8_FORCE_REINSTALL=0
        elif install_macos_arm64_native_hepmc2; then
            PYTHIA8_INSTALL_COMMAND+=" --with_hepmc=${MACOS_ARM64_HEPMC2_PREFIX}"
            PYTHIA8_FORCE_REINSTALL=1
            PYTHIA8_NATIVE_APPLE_CLANG=1
        else
            PYTHIA8_DEPENDENCIES_READY=0
        fi
    fi

    if (( ! PYTHIA8_DEPENDENCIES_READY )); then
        warn "Skipping Pythia8 because its Apple Silicon HepMC2 dependency is unavailable."
        OPTIONAL_FAILURES+=("Pythia8")
    elif install_mg5_tool \
        "Pythia8" \
        "${PYTHIA8_INSTALL_COMMAND}" \
        find_pythia_install \
        0 \
        "${PYTHIA8_FORCE_REINSTALL}" \
        "${PYTHIA8_NATIVE_APPLE_CLANG}"; then
        if [[ "${PLATFORM}" == "Darwin" && "${ARCH}" == "arm64" ]]; then
            if (( DRY_RUN )); then
                PYTHIA_PREFIX="${MG5_LINK}/HEPTools/pythia8"
                configure_mg5_pythia_paths \
                    "${MACOS_ARM64_HEPMC2_PREFIX}" \
                    "${PYTHIA_PREFIX}"
            else
                PYTHIA_CONFIG_PATH="$(find_pythia_install)"
                PYTHIA_PREFIX="$(
                    cd -- "$(dirname -- "${PYTHIA_CONFIG_PATH}")/.." &&
                        pwd
                )"

                if (( PYTHIA8_FORCE_REINSTALL )); then
                    printf '%s\n' \
                        "Pythia8; Apple Clang; native libc++; arm64" \
                        > "${PYTHIA_PREFIX}/.heptoolbench-apple-clang"
                fi

                if ! verify_macos_arm64_native_pythia; then
                    warn "Pythia8 compiled, but its Apple-Clang runtime verification failed."
                    OPTIONAL_FAILURES+=("Pythia8 runtime")
                elif ! configure_mg5_pythia_paths \
                    "${MACOS_ARM64_HEPMC2_PREFIX:-${MG5_LINK}/HEPTools/hepmc2-native-${HEPMC2_VERSION}}" \
                    "${PYTHIA_PREFIX}"; then
                    OPTIONAL_FAILURES+=("Pythia8 configuration")
                fi
            fi
        fi
    else
        OPTIONAL_FAILURES+=("Pythia8")
    fi
fi

if (( WITH_DELPHES )); then
    if (( ! ROOT_READY )); then
        warn "Skipping Delphes because ROOT is unavailable."
        OPTIONAL_FAILURES+=("Delphes")
    else
        if [[ "${PLATFORM}" == "Darwin" ]]; then
            # The conda-forge environment ships its own modern libc++, so its
            # symbols are available even when Clang targets an older macOS SDK.
            # Delphes' Makefile replaces environment CXXFLAGS, so the repair
            # path below also writes the flag into the downloaded Makefile.
            export CXXFLAGS="${CXXFLAGS:+${CXXFLAGS} }-D_LIBCPP_DISABLE_AVAILABILITY"
            log "Using the conda-forge libc++ compatibility flag for Delphes."
        fi

        DELPHES_ALREADY_READY=""
        if [[ "${PLATFORM}" == "Linux" ]]; then
            DELPHES_ALREADY_READY="$(find_delphes_install)"
        fi

        if [[ -n "${DELPHES_ALREADY_READY}" ]]; then
            log "DelphesHepMC2 ROOT runtime is already verified: ${DELPHES_ALREADY_READY}"
        elif repair_macos_delphes_build; then
            :
        elif repair_linux_delphes_build; then
            :
        elif install_mg5_tool \
            "Delphes" \
            "install Delphes --force" \
            find_delphes_install; then
            :
        elif repair_macos_delphes_build; then
            :
        elif repair_linux_delphes_build; then
            :
        else
            OPTIONAL_FAILURES+=("Delphes")
        fi
    fi
fi

if (( WITH_MADANALYSIS5 )); then
    if (( ! ROOT_READY )); then
        warn "Skipping MadAnalysis5 because ROOT is unavailable."
        OPTIONAL_FAILURES+=("MadAnalysis5")
    elif ! install_mg5_tool \
        "MadAnalysis5" \
        "install MadAnalysis5 --force" \
        find_ma5_install \
        1; then
        OPTIONAL_FAILURES+=("MadAnalysis5")
    fi
fi


if (( INSTALL_OLLAMA )) && ! command -v ollama >/dev/null 2>&1; then
    case "${PLATFORM}" in
        Linux)
            if (( DRY_RUN )); then
                log "+ curl -fsSL https://ollama.com/install.sh | sh"
            else
                log "Installing Ollama using its official Linux installer."
                curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tee -a "${LOG_FILE}"
            fi
            ;;
        Darwin)
            if (( ! DRY_RUN )); then
                command -v brew >/dev/null 2>&1 || \
                    die "Homebrew is required to install the Ollama macOS app. Install it from https://brew.sh or install Ollama manually."
            fi
            run_cmd brew install --cask ollama-app
            ;;
    esac
fi

if is_local_ollama_host; then
    if [[ "${PLATFORM}" == "Linux" ]] &&
        command -v ollama >/dev/null 2>&1 &&
        command -v systemctl >/dev/null 2>&1; then
        if (( DRY_RUN )); then
            log "+ sudo systemctl enable --now ollama"
        elif sudo -n true >/dev/null 2>&1 || confirm "Start the Ollama system service now?"; then
            sudo systemctl enable --now ollama 2>&1 | tee -a "${LOG_FILE}" || \
                warn "Could not start Ollama through systemd. Start it manually with 'ollama serve'."
        fi
    elif [[ "${PLATFORM}" == "Darwin" ]] &&
        {
            command -v ollama >/dev/null 2>&1 ||
                (( INSTALL_OLLAMA ))
        } &&
        ! wait_for_ollama; then
        if (( DRY_RUN )); then
            log "+ open -a Ollama"
        elif command -v open >/dev/null 2>&1; then
            open -a Ollama 2>&1 | tee -a "${LOG_FILE}" || \
                warn "Could not open the Ollama application. Start it manually."
        fi
    fi
fi

OLLAMA_READY=0
if wait_for_ollama; then
    OLLAMA_READY=1
elif (( DRY_RUN && INSTALL_OLLAMA )); then
    OLLAMA_READY=1
fi

if (( OLLAMA_READY )); then
    if (( PULL_MODEL )); then
        if (( DRY_RUN )); then
            log "+ pull ${MODEL_NAME} from ${OLLAMA_HOST_VALUE}"
        elif command -v ollama >/dev/null 2>&1; then
            run_cmd ollama pull "${MODEL_NAME}"
        else
            MODEL_PAYLOAD="$(
                "${VENV_PYTHON}" -c \
                    'import json, sys; print(json.dumps({"name": sys.argv[1], "stream": False}))' \
                    "${MODEL_NAME}"
            )"
            run_cmd curl \
                --fail \
                --show-error \
                --silent \
                --request POST \
                --header "Content-Type: application/json" \
                --data "${MODEL_PAYLOAD}" \
                "${OLLAMA_HOST_VALUE%/}/api/pull"
        fi
    fi
else
    if [[ "${PLATFORM}" == "Darwin" ]] &&
        is_local_ollama_host &&
        [[ "${ARCH}" != "arm64" ]]; then
        warn "Current Ollama for macOS requires Apple Silicon. Rerun with --ollama-host http://OTHER-COMPUTER:11434."
    elif [[ "${PLATFORM}" == "Darwin" ]] &&
        [[ "${MACOS_VERSION}" != "unknown" ]] &&
        ! version_at_least "${MACOS_VERSION}" "14.0" &&
        is_local_ollama_host; then
        warn "This macOS version cannot run current Ollama. Rerun with --ollama-host http://OTHER-COMPUTER:11434."
    else
        warn "Ollama is not reachable. Chat and model planning require local Ollama or a reachable --ollama-host."
    fi
fi

if (( DRY_RUN )); then
    log "+ save Ollama host in ${OLLAMA_HOST_FILE}"
else
    printf '%s\n' "${OLLAMA_HOST_VALUE}" > "${OLLAMA_HOST_FILE}"
fi

if (( DRY_RUN )); then
    log "+ create/update configs/agent_profiles.json with profile ${PROFILE_NAME}"
else
    "${VENV_PYTHON}" - "${PROJECT_ROOT}/configs/agent_profiles.json" "${PROFILE_NAME}" "${MODEL_NAME}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
profile_name = sys.argv[2]
model_name = sys.argv[3]
payload = json.loads(path.read_text(encoding="utf-8"))

desired = {
    "primary_model": model_name,
    "fallback_model": None,
    "primary_timeout_seconds": 300,
    "fallback_timeout_seconds": None,
    "max_repairs": 2,
}

if profile_name in payload and payload[profile_name] != desired:
    protected = {"legacy_llama3", "qwen_primary", "qwen_cascade"}
    if profile_name in protected:
        raise SystemExit(
            f"Refusing to overwrite built-in profile {profile_name!r}. "
            "Choose a separate --profile name."
        )

    backup = path.with_suffix(path.suffix + ".before_bootstrap")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

payload[profile_name] = desired
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
fi

find_ma5() {
    find_ma5_install
}

find_pythia() {
    find_pythia_install
}

find_delphes() {
    find_delphes_install
}

MA5_EXECUTABLE=""
PYTHIA_CONFIG=""
DELPHES_EXECUTABLE=""

if (( ! DRY_RUN )); then
    MA5_EXECUTABLE="$(find_ma5)"
    PYTHIA_CONFIG="$(find_pythia)"
    DELPHES_EXECUTABLE="$(find_delphes)"
fi

if (( DRY_RUN )); then
    log "+ write configs/local_paths.json"
else
    "${VENV_PYTHON}" - \
        "${PROJECT_ROOT}/configs/local_paths.json" \
        "${MG5_EXECUTABLE}" \
        "${MA5_EXECUTABLE}" \
        "${PYTHIA_CONFIG}" \
        "${DELPHES_EXECUTABLE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
mg5, ma5, pythia_config, delphes_executable = sys.argv[2:]

if path.exists():
    original = path.read_text(encoding="utf-8")
    payload = json.loads(original)
    backup = path.with_suffix(path.suffix + ".before_bootstrap")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
else:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {}

payload["mg5_executable"] = mg5

if ma5:
    payload["madanalysis5_executable"] = ma5
else:
    payload.pop("madanalysis5_executable", None)

if pythia_config:
    payload["pythia8_path"] = str(Path(pythia_config).parent.parent)
else:
    payload.pop("pythia8_path", None)

if delphes_executable:
    payload["delphes_path"] = str(Path(delphes_executable).parent)
else:
    payload.pop("delphes_path", None)

path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
fi

if (( DRY_RUN )); then
    log "+ run standard doctor for ${PROFILE_NAME}"
else
    log "Running the standard doctor."
    DOCTOR_STATUS=0
    TEE_STATUS=0

    if OLLAMA_HOST="${OLLAMA_HOST_VALUE}" PYTHONPATH="${PROJECT_ROOT}/src" \
        "${VENV_PYTHON}" -m hep_agent.doctor.cli \
        --profile "${PROFILE_NAME}" --save 2>&1 | tee -a "${LOG_FILE}"; then
        :
    else
        PIPE_STATUSES=("${PIPESTATUS[@]}")
        DOCTOR_STATUS="${PIPE_STATUSES[0]}"
        TEE_STATUS="${PIPE_STATUSES[1]}"
    fi

    (( TEE_STATUS == 0 )) || die "Could not write the installer log while running the standard doctor."

    if (( DOCTOR_STATUS != 0 )); then
        warn "The standard doctor found required issues. Review results/doctor/latest.json and this log."
    fi
fi

if (( RUN_DEEP_DOCTOR )); then
    if (( DRY_RUN )); then
        log "+ run deep doctor for ${PROFILE_NAME}"
    else
        log "Running the deep doctor."
        DEEP_STATUS=0
        TEE_STATUS=0

        if OLLAMA_HOST="${OLLAMA_HOST_VALUE}" PYTHONPATH="${PROJECT_ROOT}/src" \
            "${VENV_PYTHON}" -m hep_agent.doctor.cli \
            --profile "${PROFILE_NAME}" --deep --timeout 600 --save \
            2>&1 | tee -a "${LOG_FILE}"; then
            :
        else
            PIPE_STATUSES=("${PIPESTATUS[@]}")
            DEEP_STATUS="${PIPE_STATUSES[0]}"
            TEE_STATUS="${PIPE_STATUSES[1]}"
        fi

        (( TEE_STATUS == 0 )) || die "Could not write the installer log while running the deep doctor."

        if (( DEEP_STATUS != 0 )); then
            warn "The deep doctor found required issues. The base installation is still preserved."
        fi
    fi
fi

if (( RUN_FULL_STACK_VALIDATION )); then
    if (( ${#OPTIONAL_FAILURES[@]} > 0 )); then
        warn "Skipping full-stack validation because an optional HEP tool failed to install."
    elif (( DRY_RUN )); then
        log "+ generate 10 real events through MadGraph, Pythia8, DelphesHepMC2, and MadAnalysis5"
    else
        log "Running the model-free full HEP stack validation with 10 events."
        FULL_STACK_STATUS=0
        TEE_STATUS=0

        if PYTHONPATH="${PROJECT_ROOT}/src" \
            "${VENV_PYTHON}" \
            "${PROJECT_ROOT}/scripts/validate_full_stack.py" \
            --events 10 \
            --timeout-seconds 3600 \
            --analysis-timeout-seconds 600 \
            2>&1 | tee -a "${LOG_FILE}"; then
            :
        else
            PIPE_STATUSES=("${PIPESTATUS[@]}")
            FULL_STACK_STATUS="${PIPE_STATUSES[0]}"
            TEE_STATUS="${PIPE_STATUSES[1]}"
        fi

        (( TEE_STATUS == 0 )) || die "Could not write the installer log during full-stack validation."

        if (( FULL_STACK_STATUS != 0 )); then
            warn "The real-event full-stack validation failed."
            OPTIONAL_FAILURES+=("full-stack validation")
        else
            log "Real-event full-stack validation passed."
        fi
    fi
fi

if (( ${#OPTIONAL_FAILURES[@]} > 0 )); then
    log ""
    log "============================================================"
    log "INSTALLATION COMPLETED WITH OPTIONAL TOOL FAILURES"
    log "============================================================"

    for failed_tool in "${OPTIONAL_FAILURES[@]}"; do
        log "  - ${failed_tool}"
    done

    log ""
    log "The base agent installation is preserved."
    log "Review the installer log and doctor report."
    exit 1
fi

log ""
log "============================================================"
log "INSTALLATION FINISHED"
log "============================================================"
log "Start the interface with:"
log "  ./run_agent.sh"
log ""
log "Selected starter profile: ${PROFILE_NAME}"
log "Selected starter model:   ${MODEL_NAME}"
log "Installation log:         ${LOG_FILE}"
log "Doctor report:            ${PROJECT_ROOT}/results/doctor/latest.json"
