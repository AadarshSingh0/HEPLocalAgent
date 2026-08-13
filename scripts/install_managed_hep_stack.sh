#!/usr/bin/env bash
set -euo pipefail

# Build the publication-default, clone-owned Linux HEP stack.  This script
# refuses to reuse any installed component.  Exact archives may already be in
# .hep-stack/downloads, but every archive is checksum-verified before use.

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
STACK_ROOT="${PROJECT_ROOT}/.hep-stack"
DOWNLOADS="${STACK_ROOT}/downloads"
BUILD_ROOT="${STACK_ROOT}/build"
LOG_ROOT="${STACK_ROOT}/logs"
JOBS="${HEP_AGENT_BUILD_JOBS:-4}"

if [[ "$(uname -s)" == "Darwin" ]]; then
    exec /bin/bash "${PROJECT_ROOT}/scripts/install_managed_hep_stack_macos.sh"
fi

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
    echo "This installer implementation supports Linux x86-64 only." >&2
    echo "The manifest/runtime contract is cross-platform; macOS installation uses its managed Miniforge path." >&2
    exit 2
fi

if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    echo "Missing clone-owned Python at ${PROJECT_ROOT}/.venv/bin/python." >&2
    echo "Create the repository .venv before installing the native HEP stack." >&2
    exit 2
fi

for directory in root madgraph pythia8 hepmc2 delphes madanalysis5 mg5amc_py8_interface launchers; do
    if [[ -e "${STACK_ROOT}/${directory}" ]]; then
        echo "Refusing to reuse or overwrite existing managed component: ${STACK_ROOT}/${directory}" >&2
        exit 2
    fi
done

mkdir -p "${DOWNLOADS}" "${BUILD_ROOT}" "${LOG_ROOT}" "${STACK_ROOT}/launchers"

verify() {
    local filename="$1"
    local expected="$2"
    local actual
    [[ -f "${DOWNLOADS}/${filename}" ]] || {
        echo "Missing pinned archive: ${DOWNLOADS}/${filename}" >&2
        exit 2
    }
    actual="$(sha256sum "${DOWNLOADS}/${filename}" | awk '{print $1}')"
    if [[ "${actual}" != "${expected}" ]]; then
        echo "Checksum mismatch for ${filename}: expected ${expected}, got ${actual}" >&2
        exit 2
    fi
}

verify "MG5_aMC_v3.5.13-github.tar.gz" "0c75437481cc7808b59b578bc454d2c7bc12721b8bd848a287f35503202fabe7"
verify "pythia8317.tgz" "1ae551d14dac495ddfe6b344792035ebe410fe6c6004d44a335e0ece0e745adf"
verify "root_v6.40.02.Linux-ubuntu24.04-x86_64-gcc13.3.tar.gz" "127db12fa498b51ce89e242bc787d7ed24dfe4cee935783ed13d39e7969eb486"
verify "Delphes-3.5.1.tar.gz" "b60d26d2ee2c84b58fbf2cf397fabd0ef3e89d3a0546d843c4ada82cc802d787"
verify "madanalysis5-v1.11.0.tar.gz" "6d2e73ae6d7d71cffa12c7184e8b243e1260e2f1d8e784edbf3058d6fc4b5351"
verify "hepmc2.06.11.tgz" "86b66ea0278f803cde5774de8bd187dd42c870367f1cbf6cdaec8dc7cf6afc10"
verify "MG5aMC_PY8_interface_V1.3.tar.gz" "1a7a62e96207701f9a8a44fec01426b7f474b580ba2c4fbb82ecd0d83fcea332"

echo "[1/7] Installing ROOT 6.40.02"
tar -xzf "${DOWNLOADS}/root_v6.40.02.Linux-ubuntu24.04-x86_64-gcc13.3.tar.gz" -C "${STACK_ROOT}"

export ROOTSYS="${STACK_ROOT}/root"
export PATH="${PROJECT_ROOT}/.venv/bin:${ROOTSYS}/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export LD_LIBRARY_PATH="${ROOTSYS}/lib"
export PYTHONNOUSERSITE=1
unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_SHLVL PYTHONPATH PYTHONHOME PYTHIA8DATA ROOT_INCLUDE_PATH
unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH CPATH LIBRARY_PATH PKG_CONFIG_PATH CMAKE_PREFIX_PATH

"${ROOTSYS}/bin/root-config" --version | tee "${LOG_ROOT}/root-smoke.log"

echo "[2/7] Installing MadGraph 3.5.13"
tar -xzf "${DOWNLOADS}/MG5_aMC_v3.5.13-github.tar.gz" -C "${BUILD_ROOT}"
mv "${BUILD_ROOT}/mg5amcnlo-3.5.13" "${STACK_ROOT}/madgraph"

echo "[3/7] Building HepMC 2.06.11"
tar -xzf "${DOWNLOADS}/hepmc2.06.11.tgz" -C "${BUILD_ROOT}"
cmake -S "${BUILD_ROOT}/HepMC-2.06.11" -B "${BUILD_ROOT}/hepmc2-build" \
    -DCMAKE_INSTALL_PREFIX="${STACK_ROOT}/hepmc2" \
    -Dmomentum:STRING=GEV -Dlength:STRING=MM \
    -Dbuild_docs:BOOL=OFF >"${LOG_ROOT}/hepmc2-configure.log" 2>&1
cmake --build "${BUILD_ROOT}/hepmc2-build" --parallel "${JOBS}" >"${LOG_ROOT}/hepmc2-build.log" 2>&1
cmake --install "${BUILD_ROOT}/hepmc2-build" >"${LOG_ROOT}/hepmc2-install.log" 2>&1

echo "[4/7] Building Pythia 8.317"
tar -xzf "${DOWNLOADS}/pythia8317.tgz" -C "${BUILD_ROOT}"
(
    cd "${BUILD_ROOT}/pythia8317"
    ./configure --prefix="${STACK_ROOT}/pythia8" \
        --with-hepmc2="${STACK_ROOT}/hepmc2" --with-gzip \
        >"${LOG_ROOT}/pythia8-configure.log" 2>&1
    make -j"${JOBS}" >"${LOG_ROOT}/pythia8-build.log" 2>&1
    make install >"${LOG_ROOT}/pythia8-install.log" 2>&1
)
export PYTHIA8DATA="${STACK_ROOT}/pythia8/share/Pythia8/xmldoc"
export LD_LIBRARY_PATH="${ROOTSYS}/lib:${STACK_ROOT}/pythia8/lib:${STACK_ROOT}/hepmc2/lib"
"${STACK_ROOT}/pythia8/bin/pythia8-config" --version | tee "${LOG_ROOT}/pythia8-smoke.log"

echo "[5/7] Building MG5-Pythia interface 1.3"
mkdir "${STACK_ROOT}/mg5amc_py8_interface"
tar -xzf "${DOWNLOADS}/MG5aMC_PY8_interface_V1.3.tar.gz" -C "${STACK_ROOT}/mg5amc_py8_interface"
"${PROJECT_ROOT}/.venv/bin/python" "${STACK_ROOT}/mg5amc_py8_interface/compile.py" \
    "${STACK_ROOT}/pythia8" "${STACK_ROOT}/madgraph" \
    >"${LOG_ROOT}/mg5amc-py8-interface-build.log" 2>&1

echo "[6/7] Building Delphes 3.5.1 against managed ROOT"
tar -xzf "${DOWNLOADS}/Delphes-3.5.1.tar.gz" -C "${BUILD_ROOT}"
mv "${BUILD_ROOT}/delphes-3.5.1" "${STACK_ROOT}/delphes"
make -C "${STACK_ROOT}/delphes" -j"${JOBS}" >"${LOG_ROOT}/delphes-build.log" 2>&1

echo "[7/7] Installing and initializing MadAnalysis 1.11.0"
tar -xzf "${DOWNLOADS}/madanalysis5-v1.11.0.tar.gz" -C "${BUILD_ROOT}"
mv "${BUILD_ROOT}/madanalysis5-1.11.0" "${STACK_ROOT}/madanalysis5"

"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/scripts/finalize_managed_stack.py" \
    --initialize

echo "Managed HEP stack installed at ${STACK_ROOT}"
