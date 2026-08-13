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

if [[ "$(uname -s)" != "Darwin" || ( "${ARCH}" != "arm64" && "${ARCH}" != "x86_64" ) ]]; then
    echo "This builder supports Darwin arm64 and Darwin x86_64 only." >&2
    exit 2
fi
if [[ ! -x /usr/bin/clang || ! -x /usr/bin/clang++ || ! -x /usr/bin/xcrun ]]; then
    echo "Xcode Command Line Tools are required (Apple Clang was not found)." >&2
    echo "No Homebrew compiler fallback will be attempted." >&2
    exit 2
fi

for directory in miniforge runtime conda-pkgs root madgraph pythia8 hepmc2 delphes madanalysis5 mg5amc_py8_interface launchers; do
    if [[ -e "${STACK_ROOT}/${directory}" ]]; then
        echo "Refusing to reuse or overwrite existing managed component: ${STACK_ROOT}/${directory}" >&2
        exit 2
    fi
done
mkdir -p "${DOWNLOADS}" "${BUILD_ROOT}" "${LOG_ROOT}" "${STACK_ROOT}/launchers" "${CONDA_PACKAGES}"

sha256_file() {
    /usr/bin/shasum -a 256 "$1" | awk '{print $1}'
}
verify() {
    local filename="$1" expected="$2" actual
    [[ -f "${DOWNLOADS}/${filename}" ]] || {
        echo "Missing pinned archive: ${DOWNLOADS}/${filename}" >&2
        exit 2
    }
    actual="$(sha256_file "${DOWNLOADS}/${filename}")"
    [[ "${actual}" == "${expected}" ]] || {
        echo "Checksum mismatch for ${filename}: expected ${expected}, got ${actual}" >&2
        exit 2
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
else
    MINIFORGE_ARCHIVE=Miniforge3-26.3.2-2-MacOSX-x86_64.sh
    MINIFORGE_SHA=a755192103de19bb2782685ac78820c2e00702e5f33e6e4f0a3bf3c214f45d69
    ROOT_ARCHIVE=root_base-6.40.02-cxx23_h36fdf7c_2.conda
    ROOT_SHA=96150f5f313adccf584d46bb26acb73033f7b9ffe30b866a923281464302cf46
fi
verify "${MINIFORGE_ARCHIVE}" "${MINIFORGE_SHA}"
verify "${ROOT_ARCHIVE}" "${ROOT_SHA}"

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
        PYTHONNOUSERSITE=1 \
        "${MINIFORGE_ROOT}/bin/conda" "$@"
}

echo "[1/8] Installing clone-owned Miniforge and pinned ROOT 6.40.02"
env -i HOME="${HOME}" PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
    /bin/bash "${DOWNLOADS}/${MINIFORGE_ARCHIVE}" -b -p "${MINIFORGE_ROOT}" \
    >"${LOG_ROOT}/miniforge-install.log" 2>&1
isolated_conda create --yes --prefix "${RUNTIME_ROOT}" --override-channels -c conda-forge \
    "${DOWNLOADS}/${ROOT_ARCHIVE}" python=3.11 pip cmake make pkg-config git wget rsync \
    gfortran=13 zlib >"${LOG_ROOT}/runtime-create.log" 2>&1

env -i \
    HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" \
    PATH="${RUNTIME_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    PYTHONNOUSERSITE=1 \
    "${RUNTIME_ROOT}/bin/python" -m venv --system-site-packages "${PROJECT_ROOT}/.venv"
env -i \
    HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" \
    PATH="${PROJECT_ROOT}/.venv/bin:${RUNTIME_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    VIRTUAL_ENV="${PROJECT_ROOT}/.venv" PYTHONNOUSERSITE=1 \
    "${PROJECT_ROOT}/.venv/bin/python" -m pip install --upgrade pip \
    >"${LOG_ROOT}/pip-upgrade.log" 2>&1
env -i \
    HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" \
    PATH="${PROJECT_ROOT}/.venv/bin:${RUNTIME_ROOT}/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    VIRTUAL_ENV="${PROJECT_ROOT}/.venv" PYTHONNOUSERSITE=1 \
    "${PROJECT_ROOT}/.venv/bin/python" -m pip install -e "${PROJECT_ROOT}[web]" \
    >"${LOG_ROOT}/agent-install.log" 2>&1

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
"${ROOTSYS}/bin/root-config" --version >"${LOG_ROOT}/root-smoke.log"

echo "[2/8] Installing MadGraph 3.5.13"
tar -xzf "${DOWNLOADS}/MG5_aMC_v3.5.13-github.tar.gz" -C "${BUILD_ROOT}"
mv "${BUILD_ROOT}/mg5amcnlo-3.5.13" "${STACK_ROOT}/madgraph"

echo "[3/8] Building HepMC 2.06.11 with Apple Clang"
tar -xzf "${DOWNLOADS}/hepmc2.06.11.tgz" -C "${BUILD_ROOT}"
"${RUNTIME_ROOT}/bin/cmake" -S "${BUILD_ROOT}/HepMC-2.06.11" -B "${BUILD_ROOT}/hepmc2-build" \
    -DCMAKE_INSTALL_PREFIX="${STACK_ROOT}/hepmc2" \
    -DCMAKE_C_COMPILER=/usr/bin/clang -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
    -DCMAKE_OSX_ARCHITECTURES="${ARCH}" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DBUILD_SHARED_LIBS=OFF -Dmomentum:STRING=GEV -Dlength:STRING=MM \
    -Dbuild_docs:BOOL=OFF >"${LOG_ROOT}/hepmc2-configure.log" 2>&1
"${RUNTIME_ROOT}/bin/cmake" --build "${BUILD_ROOT}/hepmc2-build" --parallel "${JOBS}" \
    >"${LOG_ROOT}/hepmc2-build.log" 2>&1
"${RUNTIME_ROOT}/bin/cmake" --install "${BUILD_ROOT}/hepmc2-build" \
    >"${LOG_ROOT}/hepmc2-install.log" 2>&1

echo "[4/8] Building Pythia 8.317 with Apple Clang/libc++"
tar -xzf "${DOWNLOADS}/pythia8317.tgz" -C "${BUILD_ROOT}"
(
    cd "${BUILD_ROOT}/pythia8317"
    ./configure --prefix="${STACK_ROOT}/pythia8" --arch=DARWIN \
        --cxx=/usr/bin/clang++ --cxx-common="-O2 -std=c++11 -stdlib=libc++" \
        --with-hepmc2="${STACK_ROOT}/hepmc2" --with-gzip="${RUNTIME_ROOT}" \
        >"${LOG_ROOT}/pythia8-configure.log" 2>&1
    "${RUNTIME_ROOT}/bin/make" -j"${JOBS}" >"${LOG_ROOT}/pythia8-build.log" 2>&1
    "${RUNTIME_ROOT}/bin/make" install >"${LOG_ROOT}/pythia8-install.log" 2>&1
)
export PYTHIA8DATA="${STACK_ROOT}/pythia8/share/Pythia8/xmldoc"
export DYLD_LIBRARY_PATH="${STACK_ROOT}/pythia8/lib:${RUNTIME_ROOT}/lib:${STACK_ROOT}/hepmc2/lib"
"${STACK_ROOT}/pythia8/bin/pythia8-config" --version >"${LOG_ROOT}/pythia8-smoke.log"

echo "[5/8] Building MG5-Pythia interface 1.3"
mkdir "${STACK_ROOT}/mg5amc_py8_interface"
tar -xzf "${DOWNLOADS}/MG5aMC_PY8_interface_V1.3.tar.gz" -C "${STACK_ROOT}/mg5amc_py8_interface"
"${PROJECT_ROOT}/.venv/bin/python" "${STACK_ROOT}/mg5amc_py8_interface/compile.py" \
    "${STACK_ROOT}/pythia8" "${STACK_ROOT}/madgraph" \
    >"${LOG_ROOT}/mg5amc-py8-interface-build.log" 2>&1

echo "[6/8] Building Delphes 3.5.1 against clone-owned ROOT"
tar -xzf "${DOWNLOADS}/Delphes-3.5.1.tar.gz" -C "${BUILD_ROOT}"
mv "${BUILD_ROOT}/delphes-3.5.1" "${STACK_ROOT}/delphes"
"${PROJECT_ROOT}/.venv/bin/python" - "${STACK_ROOT}/delphes/Makefile" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
needle = "include doc/Makefile.arch\n"
if needle not in text:
    raise SystemExit("Delphes Makefile.arch include was not found")
path.write_text(text.replace(needle, needle + "CXXFLAGS += -D_LIBCPP_DISABLE_AVAILABILITY\n", 1))
PY
"${RUNTIME_ROOT}/bin/make" -C "${STACK_ROOT}/delphes" -j"${JOBS}" \
    >"${LOG_ROOT}/delphes-build.log" 2>&1

echo "[7/8] Installing MadAnalysis 1.11.0"
tar -xzf "${DOWNLOADS}/madanalysis5-v1.11.0.tar.gz" -C "${BUILD_ROOT}"
mv "${BUILD_ROOT}/madanalysis5-1.11.0" "${STACK_ROOT}/madanalysis5"

echo "[8/8] Configuring, smoke-testing, auditing, and writing the manifest"
"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/scripts/finalize_managed_stack.py" --initialize
echo "Managed Darwin HEP stack installed at ${STACK_ROOT}"
