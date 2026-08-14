# Apple Silicon fresh-stack validation handoff

This gate must be run on a real Apple Silicon Mac before publication. The
Linux-side change supplies Darwin arm64 and x86-64 code and hermetic tests; it
does not claim physical macOS validation. Intel macOS remains unverified until
this same gate is run on real Intel hardware.

## Preconditions

- Use a genuinely fresh clone and leave existing Homebrew, user Conda, ROOT,
  MG5, Pythia8, Delphes, MA5, and old HEPLocalAgent installations in place.
- Do not activate an existing virtual environment or Conda environment.
- Xcode Command Line Tools must provide `/usr/bin/clang`,
  `/usr/bin/clang++`, `/usr/bin/otool`, and `/usr/bin/xcrun`.
- Allow enough free disk space for a second complete clone-owned HEP stack.

Confirm the checkout and empty install boundary:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
test ! -e .hep-stack
test ! -e .venv
uname -s
uname -m
```

Expected platform: `Darwin arm64`.

## Install

Preview the exact clone-owned paths and pinned Darwin archives, then install:

```bash
./install.sh --dry-run --yes
./install.sh --yes
```

The only accepted HEP/runtime prefixes are inside this clone:

```text
.venv/
.hep-stack/miniforge/
.hep-stack/runtime/
.hep-stack/madgraph/
.hep-stack/pythia8/
.hep-stack/hepmc2/
.hep-stack/delphes/
.hep-stack/madanalysis5/
.hep-stack/mg5amc_py8_interface/
.hep-stack/launchers/
.hep-stack/manifest.json
```

Do not accept a successful install if the installer invokes Homebrew, the
user's Conda, an old clone, or an external HEP executable.

## Automated and static gates

```bash
.venv/bin/python -m unittest discover -s tests -v
bash -n install.sh run_agent.sh uninstall.sh scripts/*.sh
git diff --check
.venv/bin/python scripts/audit_managed_stack.py
.venv/bin/python -m hep_agent.doctor.cli --deep --timeout 180
```

The linkage audit must use `otool` for Mach-O files and `ar` for the
managed static HepMC2 archive. Every non-system resolved library must be under
this clone's `.hep-stack`; `/usr/lib` and `/System/Library` are permitted
operating-system dependencies. Pythia must resolve
`/usr/lib/libc++.1.dylib`, not a Conda or Homebrew libc++.

## Clean full pipeline

The full-stack validator calls the normal `run_end_to_end` orchestration path
with a fixed local planner, so this is also the required normal agent
execution—not only a special self-test:

```bash
.venv/bin/python scripts/validate_full_stack.py \
  --events 100 \
  --output-directory results/macos_fresh_clean_100
```

Then run the deterministic self-test:

```bash
.venv/bin/python -m hep_agent.selftest --events 100
```

Both must report MadGraph, Pythia8, Delphes, MadAnalysis, and the overall
result as passing.

## Poisoned-shell full pipeline

Create fake executable names without modifying any existing installation:

```bash
poison_dir="$(mktemp -d)"
for name in root root-config mg5_aMC pythia8-config DelphesHepMC2 ma5 conda; do
  printf '#!/bin/sh\necho EXTERNAL-POISON-RAN >&2\nexit 97\n' >"${poison_dir}/${name}"
  chmod +x "${poison_dir}/${name}"
done

env -i \
  HOME="${HOME}" \
  TMPDIR="${TMPDIR:-/tmp}" \
  PATH="${poison_dir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  ROOTSYS="/opt/homebrew/opt/root" \
  PYTHIA8DATA="/tmp/external-pythia/xmldoc" \
  DYLD_LIBRARY_PATH="/opt/homebrew/lib:/tmp/external-root/lib" \
  LD_LIBRARY_PATH="/tmp/external-linux-lib" \
  PYTHONPATH="/tmp/old-clone/.venv/lib/python3.11/site-packages" \
  VIRTUAL_ENV="/tmp/old-clone/.venv" \
  CONDA_PREFIX="${HOME}/miniforge3" \
  CONDA_DEFAULT_ENV="base" \
  CONDA_SHLVL="3" \
  CMAKE_PREFIX_PATH="/opt/homebrew" \
  ROOT_INCLUDE_PATH="/opt/homebrew/include/root" \
  LIBRARY_PATH="/opt/homebrew/lib" \
  CPATH="/opt/homebrew/include" \
  PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig" \
  "$(pwd)/.venv/bin/python" scripts/validate_full_stack.py \
    --events 100 \
    --output-directory results/macos_fresh_poisoned_100
```

No log may contain `EXTERNAL-POISON-RAN`. Re-run the linkage audit after the
poisoned pipeline.

## Two-clone protection

A second clone must have different absolute `.venv`, `.hep-stack`,
manifest, and launcher paths. Installing or previewing clone B must not alter
clone A. At minimum, record clone A's hashes, run clone B's dry run and
hermetic tests, then compare:

```bash
shasum -a 256 .hep-stack/manifest.json .hep-stack/launchers/* > /tmp/clone-a.before
# In a second fresh clone:
# ./install.sh --dry-run --yes
# .venv/bin/python -m unittest tests.test_stack_runtime tests.test_macos_managed_stack -v
shasum -a 256 .hep-stack/manifest.json .hep-stack/launchers/* > /tmp/clone-a.after
diff -u /tmp/clone-a.before /tmp/clone-a.after
```

For the strongest physical gate, fully install clone B as well and confirm each
manifest records its own repository path and stack boundary.

## Final gate

After clean and poisoned 100-event runs pass:

```bash
.venv/bin/python -m hep_agent.selftest --events 1000
.venv/bin/python scripts/audit_managed_stack.py --json \
  > results/macos_final_linkage_audit.json
git status --short
```

Preserve all logs, validation summaries, the manifest, exact Conda package
records, doctor output, and linkage audit. Do not push, merge, tag, or release
until the Apple Silicon evidence has been reviewed. Intel macOS must still be
reported as physically unverified.
