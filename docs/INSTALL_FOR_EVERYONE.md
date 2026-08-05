# Beginner installation

This installer is intended for people who want to try the local HEP agent
without manually configuring Python, MadGraph, Ollama, or local paths.

## Supported systems

- Ubuntu, Debian, Linux Mint, or Pop!_OS on x86-64
- macOS on Intel or Apple Silicon
- Internet connection
- Apple command-line tools on macOS
- Administrator password only when Linux system packages or Ollama must be
  installed

The installer supports the Python 3.11 environment, web agent, MadGraph
3.5.13, Pythia8, ROOT, Delphes, and MadAnalysis 5 on both supported Linux and
macOS systems. On macOS, these tools are built inside one pinned Miniforge
environment so that they use a consistent Python and compiler toolchain.

Local Ollama has narrower macOS requirements: the current release requires
Apple Silicon and macOS 14 or newer. Intel Macs and older macOS releases can
use a remote Ollama server while running the HEP tools locally. See the
[official Ollama macOS requirements](https://docs.ollama.com/macos).

## Three steps

Open a terminal in the repository and run:

```bash
chmod +x install.sh run_agent.sh scripts/bootstrap_local_hep_agent.sh
./install.sh
./run_agent.sh
```

The installer asks before installing system packages, Ollama, the starter model, Pythia8, Delphes, or MadAnalysis5.

## Safe preview

To see every planned command without changing the machine:

```bash
# Linux complete-stack preview
./install.sh --dry-run --full

# macOS full HEP-stack preview with remote Ollama
./install.sh --dry-run \
  --install-system-deps \
  --with-pythia8 \
  --with-delphes \
  --with-madanalysis5 \
  --deep-doctor \
  --ollama-host http://OTHER-COMPUTER:11434
```

## Recommended Linux installation

```bash
./install.sh \
  --install-system-deps \
  --install-ollama \
  --pull-model
```

This installs the Python environment, web interface, MadGraph, Ollama, and the smaller `starter_local` model profile.

## Recommended macOS installation

First make sure the Apple command-line tools are installed. Then run:

```bash
./install.sh --install-system-deps
```

The installer downloads a checksum-verified, pinned Miniforge release and
creates `.venv` with Python 3.11, gfortran, and the required build tools. It
also creates a MadGraph launcher that always uses this isolated environment
instead of whichever `python3` happens to be installed system-wide.

### Apple Silicon with macOS 14 or newer

To also install local Ollama and the starter model:

```bash
./install.sh \
  --install-system-deps \
  --install-ollama \
  --pull-model
```

Automatic Ollama installation uses its current Homebrew cask. If Homebrew is
not installed, install the Ollama application manually and omit
`--install-ollama`.

To install the complete local stack, including the HEP tools:

```bash
./install.sh --full
```

### Intel Mac or older macOS with remote Ollama

Current Ollama requires Apple Silicon and macOS 14 or newer. An Intel Mac or
an older macOS release can still run the agent and complete HEP stack locally
while a second computer runs Ollama:

```bash
./install.sh \
  --install-system-deps \
  --with-pythia8 \
  --with-delphes \
  --with-madanalysis5 \
  --deep-doctor \
  --ollama-host http://OTHER-COMPUTER:11434
```

Replace `OTHER-COMPUTER` with the IP address or hostname of the computer
running Ollama. The installer saves this address, so it does not need to be
entered every time the agent starts.

For an Intel Mac, use the remote-Ollama setup even if it has macOS 14 or
newer. Do not pass `--install-ollama` or `--full`, because `--full` includes a
local Ollama installation.

## Complete optional HEP stack

```bash
./install.sh --full
```

The complete option installs system dependencies and local Ollama, pulls the
starter model, installs Pythia8, ROOT, Delphes, and MadAnalysis 5, and then
runs the deep doctor. Use it on Ubuntu/Debian or Apple Silicon with macOS 14
or newer.

For Intel or older Macs, request the same HEP tools explicitly and provide a
remote Ollama host, as shown above. On macOS, ROOT is installed through
conda-forge; Delphes and MadAnalysis 5 are installed through MadGraph. The
installer applies the required conda libc++ compatibility setting when
building Delphes. On Apple Silicon, HepMC2 and Pythia8 are instead built
together with Apple Clang and the native macOS `libc++`. This avoids the
obsolete architecture detector bundled with MadGraph's older HepMC2 source
and prevents the Pythia shutdown crash that can occur when Conda and native
C++ runtimes are loaded into the same interface process.

An Apple-Silicon installation made with an earlier combined package can be
repaired without reinstalling MadGraph, ROOT, Delphes, MadAnalysis, Ollama, or
the agent environment:

```bash
HEP_AGENT_TOOL_TIMEOUT_SECONDS=7200 \
  ./install.sh --with-pythia8 --yes
```

The installer recognizes the older Pythia build, compiles a native replacement,
updates existing MadGraph `PROC_*` configuration files, and verifies that the
new Pythia library no longer links to the Conda `libc++`.

Third-party HEP tools may require substantial download and compilation time.
Installation failures are retained in the log and reported by the doctor.

## Re-running is safe

The installer is designed to be resumable. Existing downloads, the virtual environment, MadGraph, and installed HEP tools are reused when found.

## Uninstalling

From the HEPLocalAgent repository root, preview the cleanup first:

```bash
./uninstall.sh --dry-run
```

Then remove the project-managed software:

```bash
./uninstall.sh
```

This removes the isolated `.venv`, the HEPLocalAgent-managed tools directory
(including Miniforge, MadGraph, Pythia8, ROOT, Delphes, and MadAnalysis 5),
generated machine configuration, and the generated starter profile. The
repository and all run results are preserved.

To also delete locally generated agent runs:

```bash
./uninstall.sh --purge-results
```

To explicitly remove the starter model from a local Ollama server at the same
time:

```bash
./uninstall.sh \
  --purge-results \
  --remove-model qwen2.5-coder:7b
```

The uninstaller does not implicitly remove the Ollama application, unrelated
Ollama models, Apple command-line tools, Homebrew, or Linux system packages,
because these may be shared with other projects. It also never deletes the
downloaded HEPLocalAgent source directory.

## Files created

- `.venv/`: isolated Python environment
- `~/.local/share/hep-agent-tools/`: Miniforge on macOS, MadGraph, and
  optional HEP tools
- `configs/local_paths.json`: detected executable paths
- `configs/ollama_host`: saved local or remote Ollama address
- `configs/conda_root`: generated macOS environment location
- `results/bootstrap/`: installation logs
- `results/doctor/latest.json`: latest doctor report

## Starting later

From the repository root:

```bash
./run_agent.sh
```

The launcher selects the lightweight `starter_local` profile by default. A different profile can be selected in the left sidebar.

## Validate the complete HEP stack

After installing the optional HEP tools, run a fixed 20-event validation that
does not contact Ollama:

```bash
source .venv/bin/activate
python scripts/validate_full_stack.py
```

The command checks MadGraph execution, LHE output, Pythia8 HepMC output, a
Delphes ROOT file, and MadAnalysis HTML reports and plots. MadAnalysis uses
the HepMC file when available; the Delphes ROOT artifact is validated as a
separate detector-level output.

Results and a machine-readable summary are saved under:

```text
results/full_stack_validation/
```

## Troubleshooting

Run:

```bash
source .venv/bin/activate
hep-agent-doctor --profile starter_local --deep --timeout 600 --save
```

Then inspect:

```text
results/doctor/latest.json
results/bootstrap/
```

For a remote Ollama setup, verify the second computer from the Mac with:

```bash
curl http://OTHER-COMPUTER:11434/api/tags
```

If this cannot connect, the network or Ollama server must be corrected before
model planning will work. MadGraph installation itself remains usable.
