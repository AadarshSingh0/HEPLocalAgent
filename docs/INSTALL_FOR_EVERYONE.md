# Independent HEPLocalAgent installation

The publication-default installer creates one repository-owned installation:

```text
HEPLocalAgent/
├── .venv/                 agent Python and UI dependencies
├── .hep-stack/
│   ├── root/              ROOT 6.40.02 on Linux
│   ├── miniforge/         clone-owned macOS bootstrap (Darwin only)
│   ├── runtime/           clone-owned Python/ROOT runtime (Darwin only)
│   ├── conda-pkgs/        clone-owned package cache (Darwin only)
│   ├── madgraph/          MG5_aMC 3.5.13
│   ├── pythia8/           Pythia 8.317
│   ├── hepmc2/            HepMC 2.06.11 support library
│   ├── delphes/           Delphes 3.5.1
│   ├── madanalysis5/      MadAnalysis 1.11.0
│   ├── launchers/         clone-local managed launchers
│   └── manifest.json      authoritative paths, versions, sources, and linkage
└── configs/local_paths.json
```

No normal installation or execution path discovers or reuses ROOT, MadGraph,
Pythia, Delphes, or MadAnalysis from the caller's `PATH`, Conda, Homebrew,
Snap, `/opt`, another clone, or a shared tools directory. System compilers and
ordinary operating-system libraries remain build prerequisites.

## Supported code paths and validation status

Fresh installation is physically validated on Ubuntu 24.04 x86-64. The same
manifest, runtime builder, fail-closed linkage audit, launchers, doctor, and
self-test contract now has hermetic coverage for Darwin arm64 and Darwin
x86-64. The Darwin installer places Miniforge and its ROOT/Python runtime
inside this clone's `.hep-stack`, then builds every HEP component there with
Apple Clang.

No physical macOS installation is claimed by this Linux-side change.
Publication remains blocked until a fresh Apple Silicon installation and
poisoned-environment pipeline pass. Intel macOS remains explicitly unverified
until the same test is performed on real Intel hardware. Unsupported platforms
fail clearly rather than selecting external HEP packages.

## Preview and install

```bash
./install.sh --dry-run
./install.sh --yes
```

The installer always installs the full HEP stack. Archives are accepted from
the clone-local download cache only after their pinned SHA-256 checksum
matches. Installed binaries and generated launchers are never reused from an
old clone.

After installation:

```bash
.venv/bin/python -m hep_agent.doctor.cli --deep --timeout 180
.venv/bin/python -m hep_agent.selftest --events 100
.venv/bin/python scripts/validate_full_stack.py --events 100
./run_agent.sh
```

The self-test and normal agent execution use the same stack manifest and
runtime builder. MadAnalysis analyzes the managed Delphes ROOT output at
reconstructed level.

## Runtime isolation

Every managed HEP subprocess receives an explicit environment. Conflicting
ROOT, Pythia, Conda, Python, compiler, include, and library variables are
removed or replaced. `PATH` contains the clone's launchers, its `.venv`, the
managed component bins, and a minimal set of operating-system utility paths.

`configs/local_paths.json` must agree exactly with `.hep-stack/manifest.json`.
Stale clone paths, an altered manifest, an external HEP prefix, a failed smoke
test, or HEP linkage outside `.hep-stack` is a hard configuration error.

## Uninstall safely

The default removes the clone's Python environment and generated path config,
while preserving the multi-gigabyte HEP stack:

```bash
./uninstall.sh --dry-run --keep-stack
./uninstall.sh --yes --keep-stack
```

Deleting the clone-owned HEP stack requires both an explicit option and
confirmation:

```bash
./uninstall.sh --dry-run --remove-stack
./uninstall.sh --yes --remove-stack
```

The uninstaller validates the manifest ownership ID and boundary before stack
deletion. It never deletes legacy shared tools or any external HEP, Conda,
Homebrew, Snap, Ollama, or system installation.

## Legacy non-hermetic installer

The previous mixed-stack installer remains only as an explicitly unsupported
compatibility path. It is not called by `install.sh`, refuses to run without
`--unsupported-nonhermetic-external-stack`, and must not be used for
publication validation. It cannot supply or override the default clone-owned
stack.
