#!/usr/bin/env bash
set -Eeuo pipefail

# Build a fresh Darwin HEP stack wholly inside this repository clone. Miniforge
# supplies a clone-owned Python/ROOT/build runtime; no user Conda, Homebrew, or
# external HEP prefix is discovered or executed.

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
STACK_ROOT="${PROJECT_ROOT}/.hep-stack"
DOWNLOADS="${STACK_ROOT}/downloads"
BUILD_ROOT="${STACK_ROOT}/build"
LOG_ROOT="${STACK_ROOT}/logs"
MINIFORGE_ROOT="${STACK_ROOT}/miniforge"
RUNTIME_ROOT="${STACK_ROOT}/runtime"
CONDA_PACKAGES="${STACK_ROOT}/conda-pkgs"
CONDARC="${STACK_ROOT}/condarc"
JOBS="${HEP_AGENT_BUILD_JOBS:-4}"
ARCH="$(uname -m)"
source "${PROJECT_ROOT}/scripts/managed_stack_ownership.sh"

CURRENT_STAGE="macOS installer preflight"
CURRENT_LOG="${LOG_ROOT}/preflight.log"
FAILURE_REPORTED=0

report_failure() {
    local status="$1"
    if (( FAILURE_REPORTED )); then
        return "${status}"
    fi
    FAILURE_REPORTED=1
    {
        echo
        echo "Managed HEP installation failed."
        echo "Failed stage: ${CURRENT_STAGE}"
        echo "Exit status: ${status}"
        echo "Relevant log: ${CURRENT_LOG}"
        echo "Verified downloads preserved: yes (${DOWNLOADS})"
        echo "Safe retry: cd \"${PROJECT_ROOT}\" && ./install.sh"
    } >&2
    return "${status}"
}
trap 'report_failure "$?"' ERR

stage() {
    CURRENT_STAGE="$1"
    CURRENT_LOG="${LOG_ROOT}/$2"
    printf '%s\n' "${CURRENT_STAGE}"
    : >"${CURRENT_LOG}"
}

run_logged() {
    local log_name="$1"
    shift
    CURRENT_LOG="${LOG_ROOT}/${log_name}"
    "$@" >"${CURRENT_LOG}" 2>&1
}

fail() {
    printf '%s\n' "$*" >&2
    return 2
}

if [[ "$(uname -s)" != "Darwin" || ( "${ARCH}" != "arm64" && "${ARCH}" != "x86_64" ) ]]; then
    echo "This builder supports Darwin arm64 and Darwin x86_64 only." >&2
    exit 2
fi
if [[ ! -x /usr/bin/clang || ! -x /usr/bin/clang++ || ! -x /usr/bin/xcrun ]]; then
    echo "Xcode Command Line Tools are required (Apple Clang was not found)." >&2
    echo "No Homebrew compiler fallback will be attempted." >&2
    exit 2
fi

validate_managed_stack_ownership "${PROJECT_ROOT}" "${STACK_ROOT}"
mkdir -p "${LOG_ROOT}"

sha256_file() {
    /usr/bin/shasum -a 256 "$1" | awk '{print $1}'
}
verify() {
    local filename="$1" expected="$2" actual
    [[ -f "${DOWNLOADS}/${filename}" ]] || {
        echo "Missing pinned archive: ${DOWNLOADS}/${filename}" >&2
        return 2
    }
    actual="$(sha256_file "${DOWNLOADS}/${filename}")"
    [[ "${actual}" == "${expected}" ]] || {
        echo "Checksum mismatch for ${filename}: expected ${expected}, got ${actual}" >&2
        return 2
    }
}

verify MG5_aMC_v3.5.13-github.tar.gz 0c75437481cc7808b59b578bc454d2c7bc12721b8bd848a287f35503202fabe7
verify pythia8317.tgz 1ae551d14dac495ddfe6b344792035ebe410fe6c6004d44a335e0ece0e745adf
verify Delphes-3.5.1.tar.gz b60d26d2ee2c84b58fbf2cf397fabd0ef3e89d3a0546d843c4ada82cc802d787
verify madanalysis5-v1.11.0.tar.gz 6d2e73ae6d7d71cffa12c7184e8b243e1260e2f1d8e784edbf3058d6fc4b5351
verify hepmc2.06.11.tgz 86b66ea0278f803cde5774de8bd187dd42c870367f1cbf6cdaec8dc7cf6afc10
verify MG5aMC_PY8_interface_V1.3.tar.gz 1a7a62e96207701f9a8a44fec01426b7f474b580ba2c4fbb82ecd0d83fcea332

if [[ "${ARCH}" == "arm64" ]]; then
    MINIFORGE_ARCHIVE=Miniforge3-26.3.2-2-MacOSX-arm64.sh
    MINIFORGE_SHA=2657d94152343cff7c06159ac9fc09624d7879fa9575c5a0a324c571c4df0ade
    ROOT_ARCHIVE=root_base-6.40.02-cxx20_h17fc236_2.conda
    ROOT_SHA=051cd5227127a5042837c56f64ae98652febf54b06bba1f7cac9dcf2850be497
    ROOT_MATCH=root_base=6.40.02=cxx20_h17fc236_2
else
    MINIFORGE_ARCHIVE=Miniforge3-26.3.2-2-MacOSX-x86_64.sh
    MINIFORGE_SHA=a755192103de19bb2782685ac78820c2e00702e5f33e6e4f0a3bf3c214f45d69
    ROOT_ARCHIVE=root_base-6.40.02-cxx23_h36fdf7c_2.conda
    ROOT_SHA=96150f5f313adccf584d46bb26acb73033f7b9ffe30b866a923281464302cf46
    ROOT_MATCH=root_base=6.40.02=cxx23_h36fdf7c_2
fi
verify "${MINIFORGE_ARCHIVE}" "${MINIFORGE_SHA}"
verify "${ROOT_ARCHIVE}" "${ROOT_SHA}"

CURRENT_STAGE="incomplete-installation recovery"
CURRENT_LOG="${LOG_ROOT}/recovery.log"
recover_incomplete_managed_stack "${PROJECT_ROOT}" "${STACK_ROOT}"
mkdir -p "${DOWNLOADS}" "${BUILD_ROOT}" "${LOG_ROOT}" "${STACK_ROOT}/launchers" "${CONDA_PACKAGES}"

printf '%s\n' \
    'channels:' \
    '  - conda-forge' \
    'channel_priority: strict' \
    'auto_activate_base: false' \
    'show_channel_urls: true' \
    'add_pip_as_python_dependency: false' >"${CONDARC}"

isolated_conda() {
    env -i \
        HOME="${HOME}" \
        TMPDIR="${TMPDIR:-/tmp}" \
        PATH="${MINIFORGE_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
        CONDARC="${CONDARC}" \
        CONDA_PKGS_DIRS="${CONDA_PACKAGES}" \
        CONDA_SOLVER=libmamba \
        PYTHONNOUSERSITE=1 \
        "${MINIFORGE_ROOT}/bin/conda" "$@"
}

stage "[1/8] Clone-owned Miniforge and ROOT" stage-1.log
run_logged miniforge-install.log env -i HOME="${HOME}" PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
    /bin/bash "${DOWNLOADS}/${MINIFORGE_ARCHIVE}" -b -p "${MINIFORGE_ROOT}"
cp -p -- "${DOWNLOADS}/${ROOT_ARCHIVE}" "${CONDA_PACKAGES}/${ROOT_ARCHIVE}"
run_logged runtime-create.log isolated_conda create --yes --prefix "${RUNTIME_ROOT}" \
    --override-channels -c conda-forge \
    "${ROOT_MATCH}" python=3.11 pip cmake make pkg-config git wget rsync \
    gfortran=13 zlib
run_logged root-package-validation.log "${RUNTIME_ROOT}/bin/python" \
    "${PROJECT_ROOT}/scripts/validate_macos_root_package.py" \
    --architecture "${ARCH}" --runtime-root "${RUNTIME_ROOT}" \
    --downloads "${DOWNLOADS}" --package-cache "${CONDA_PACKAGES}"

run_logged venv-create.log env -i \
    HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" \
    PATH="${RUNTIME_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    PYTHONNOUSERSITE=1 \
    "${RUNTIME_ROOT}/bin/python" -m venv --system-site-packages "${PROJECT_ROOT}/.venv"
run_logged pip-upgrade.log env -i \
    HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" \
    PATH="${PROJECT_ROOT}/.venv/bin:${RUNTIME_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    VIRTUAL_ENV="${PROJECT_ROOT}/.venv" PYTHONNOUSERSITE=1 \
    "${PROJECT_ROOT}/.venv/bin/python" -m pip install --upgrade pip
run_logged agent-install.log env -i \
    HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" \
    PATH="${PROJECT_ROOT}/.venv/bin:${RUNTIME_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    VIRTUAL_ENV="${PROJECT_ROOT}/.venv" PYTHONNOUSERSITE=1 \
    "${PROJECT_ROOT}/.venv/bin/python" -m pip install -e "${PROJECT_ROOT}[web]"

export ROOTSYS="${RUNTIME_ROOT}"
export PATH="${PROJECT_ROOT}/.venv/bin:${RUNTIME_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export DYLD_LIBRARY_PATH="${RUNTIME_ROOT}/lib"
export PYTHONNOUSERSITE=1
export CC=/usr/bin/clang
export CXX=/usr/bin/clang++
unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_SHLVL CONDA_PROMPT_MODIFIER CONDA_PYTHON_EXE
unset _CE_CONDA _CE_M PYTHONPATH PYTHONHOME PYTHIA8DATA ROOT_INCLUDE_PATH
unset LD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH
unset LIBRARY_PATH PKG_CONFIG_PATH CMAKE_PREFIX_PATH SDKROOT MACOSX_DEPLOYMENT_TARGET
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS FC F77 F90
unset AR AS LD NM RANLIB STRIP
export AR=/usr/bin/ar
export LD=/usr/bin/ld
export NM=/usr/bin/nm
export RANLIB=/usr/bin/ranlib
export STRIP=/usr/bin/strip
SDKROOT="$(env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin /usr/bin/xcrun --sdk macosx --show-sdk-path)"
[[ "${SDKROOT}" == /*.sdk && -d "${SDKROOT}" ]] || fail "xcrun returned an invalid macOS SDK: ${SDKROOT}"
export SDKROOT
run_logged root-smoke.log "${ROOTSYS}/bin/root-config" --version

stage "[2/8] MadGraph" stage-2.log
run_logged madgraph-extract.log tar -xzf "${DOWNLOADS}/MG5_aMC_v3.5.13-github.tar.gz" -C "${BUILD_ROOT}"
run_logged madgraph-install.log mv "${BUILD_ROOT}/mg5amcnlo-3.5.13" "${STACK_ROOT}/madgraph"

stage "[3/8] HepMC2" stage-3.log
run_logged hepmc2-extract.log tar -xzf "${DOWNLOADS}/hepmc2.06.11.tgz" -C "${BUILD_ROOT}"
run_logged hepmc2-configure.log "${RUNTIME_ROOT}/bin/cmake" -S "${BUILD_ROOT}/HepMC-2.06.11" -B "${BUILD_ROOT}/hepmc2-build" \
    -DCMAKE_INSTALL_PREFIX="${STACK_ROOT}/hepmc2" \
    -DCMAKE_C_COMPILER=/usr/bin/clang -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
    -DCMAKE_OSX_ARCHITECTURES="${ARCH}" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DBUILD_SHARED_LIBS=OFF -Dmomentum:STRING=GEV -Dlength:STRING=MM \
    -Dbuild_docs:BOOL=OFF
run_logged hepmc2-build.log "${RUNTIME_ROOT}/bin/cmake" --build "${BUILD_ROOT}/hepmc2-build" --parallel "${JOBS}"
run_logged hepmc2-install.log "${RUNTIME_ROOT}/bin/cmake" --install "${BUILD_ROOT}/hepmc2-build"

stage "[4/8] Pythia8" stage-4.log
run_logged pythia8-extract.log tar -xzf "${DOWNLOADS}/pythia8317.tgz" -C "${BUILD_ROOT}"
pushd "${BUILD_ROOT}/pythia8317" >/dev/null
run_logged pythia8-configure.log ./configure --prefix="${STACK_ROOT}/pythia8" --arch=DARWIN \
    --cxx=/usr/bin/clang++ --cxx-common="-O2 -std=c++11 -stdlib=libc++" \
    --with-hepmc2="${STACK_ROOT}/hepmc2" --with-gzip
run_logged pythia8-build.log "${RUNTIME_ROOT}/bin/make" -j"${JOBS}"
run_logged pythia8-install.log "${RUNTIME_ROOT}/bin/make" install
popd >/dev/null
CURRENT_LOG="${LOG_ROOT}/pythia8-link-order-patch.log"
"${PROJECT_ROOT}/.venv/bin/python" - \
    "${STACK_ROOT}/pythia8/share/Pythia8/examples/Makefile" \
    >"${CURRENT_LOG}" 2>&1 <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = (
    "CXX_COMMON:=$(OBJ_COMMON) -I$(PREFIX_INCLUDE) $(CXX_COMMON) $(GZIP_LIB)\n"
    "CXX_COMMON+= -L$(PREFIX_LIB) -Wl,-rpath,$(PREFIX_LIB) -lpythia8 -ldl\n"
)
new = (
    "CXX_COMMON:=$(OBJ_COMMON) -I$(PREFIX_INCLUDE) $(CXX_COMMON)\n"
    "CXX_COMMON+= -L$(PREFIX_LIB) -Wl,-rpath,$(PREFIX_LIB) -lpythia8 -ldl $(GZIP_LIB)\n"
)
if text.count(old) != 1:
    raise SystemExit("Pythia example link-order stanza was not found exactly once")
path.write_text(text.replace(old, new), encoding="utf-8")
PY
export PYTHIA8DATA="${STACK_ROOT}/pythia8/share/Pythia8/xmldoc"
export DYLD_LIBRARY_PATH="${STACK_ROOT}/pythia8/lib:${RUNTIME_ROOT}/lib:${STACK_ROOT}/hepmc2/lib"
run_logged pythia8-smoke.log "${STACK_ROOT}/pythia8/bin/pythia8-config" --version

stage "[5/8] MG5–Pythia interface" stage-5.log
run_logged mg5amc-py8-interface-mkdir.log mkdir "${STACK_ROOT}/mg5amc_py8_interface"
run_logged mg5amc-py8-interface-extract.log tar -xzf "${DOWNLOADS}/MG5aMC_PY8_interface_V1.3.tar.gz" -C "${STACK_ROOT}/mg5amc_py8_interface"
run_logged mg5amc-py8-interface-build.log "${PROJECT_ROOT}/.venv/bin/python" \
    "${STACK_ROOT}/mg5amc_py8_interface/compile.py" \
    "${STACK_ROOT}/pythia8" "${STACK_ROOT}/madgraph"

stage "[6/8] Delphes" stage-6.log
run_logged delphes-extract.log tar -xzf "${DOWNLOADS}/Delphes-3.5.1.tar.gz" -C "${BUILD_ROOT}"
run_logged delphes-install.log mv "${BUILD_ROOT}/delphes-3.5.1" "${STACK_ROOT}/delphes"
CURRENT_LOG="${LOG_ROOT}/delphes-patch.log"
"${PROJECT_ROOT}/.venv/bin/python" - "${STACK_ROOT}/delphes/Makefile" >"${CURRENT_LOG}" 2>&1 <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
needle = "include doc/Makefile.arch\n"
if needle not in text:
    raise SystemExit("Delphes Makefile.arch include was not found")
path.write_text(text.replace(needle, needle + "CXXFLAGS += -D_LIBCPP_DISABLE_AVAILABILITY\n", 1))
PY
run_logged delphes-build.log "${RUNTIME_ROOT}/bin/make" -C "${STACK_ROOT}/delphes" -j"${JOBS}"

stage "[7/8] MadAnalysis" stage-7.log
run_logged madanalysis5-extract.log tar -xzf "${DOWNLOADS}/madanalysis5-v1.11.0.tar.gz" -C "${BUILD_ROOT}"
run_logged madanalysis5-install.log mv "${BUILD_ROOT}/madanalysis5-1.11.0" "${STACK_ROOT}/madanalysis5"

stage "[8/8] Finalization, smoke tests, audit and manifest" stage-8.log
run_logged finalization.log "${PROJECT_ROOT}/.venv/bin/python" \
    "${PROJECT_ROOT}/scripts/finalize_managed_stack.py" --initialize
echo "Managed Darwin HEP stack installed at ${STACK_ROOT}"
