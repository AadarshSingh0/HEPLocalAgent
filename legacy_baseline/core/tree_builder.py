"""
MadGraph5 Tree Builder
======================
Deterministic syntax assembler. Takes structured JSON from the LLM
and walks a decision tree to produce correct MadGraph5 files.

The LLM is ONLY responsible for JSON extraction — never for syntax.
"""

from dataclasses import dataclass, field
from typing import Optional
import os
from datetime import datetime
from typing import Dict, List

from core.constants import PARTICLE_ALIASES, MODELS

# ─────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────
@dataclass
class ProcessParams:
    """Structured parameters extracted from user input by the LLM."""
    # Process
    model: str = "sm"
    process_string: Optional[str] = None # e.g. "p p > t t~, (t > w+ b)" — if provided, use this directly instead of building from lists
    initial_state: List[str] = field(default_factory=lambda: ["p", "p"])
    final_state: List[str] = field(default_factory=lambda: ["e-", "e+"])
    extra_processes: List[str] = field(default_factory=list) # add process lines

    # QCD order
    qcd_order: Optional[int] = None     # e.g. QCD=0 for EW only
    qed_order: Optional[int] = None

    # Beam / collider
    beam_energy_gev: float = 6500.0     # per beam, so 13 TeV = 6500
    beam_type: str = "proton"           # proton | electron | positron

    # Run settings
    nevents: int = 10000
    output_dir: str = "my_process"

    # Shower / detector
    pythia8: bool  = False
    delphes: bool  = False

    # Optional extras
    mur: float = 1.0    # renormalization scale factor
    muf: float = 1.0    # factorization scale factor
    pdlabel: str = "lhapdf"
    lhaid: int   = 263000  # NNPDF3.1 NNLO central

    # Custom UFO path (if model == "feynrules")
    ufo_path: Optional[str] = None


# ─────────────────────────────────────────────────
# Node helpers — each returns a string fragment
# ─────────────────────────────────────────────────
def make_unique_name(base: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{stamp}"


def node_import_model(p: ProcessParams) -> str:
    """Branch 1: resolve model import line."""
    model_key = p.model.lower().replace("-", "_").replace(" ", "_")
    mg5_name = MODELS.get(model_key, p.model)   # fall back to whatever user typed

    if mg5_name is None:  # feynrules / custom UFO
        if p.ufo_path:
            return f"import model {p.ufo_path}"
        else:
            return f"import model {p.model}  # <-- set correct UFO path"
    return f"import model {mg5_name}"


def node_define_multiparticles(p: ProcessParams) -> str:
    """Branch 2: add define lines when proton beams are used."""
    lines = []
    all_particles = p.initial_state + p.final_state
    if "p" in all_particles or "j" in all_particles:
        if p.model.lower() in ("sm", "sm-no-flav", "heft"):
            lines.append("define p = p b b~")
            lines.append("define j = j b b~")
    return "\n".join(lines)


def _resolve_particle(name: str) -> str:
    """Map human-readable particle name to MadGraph5 token."""
    key = name.lower().strip()
    return PARTICLE_ALIASES.get(key, name)   # unknown → pass through


def node_generate_process(p: ProcessParams) -> str:
    # If the LLM gave us a specific string, use it exactly.
    if p.process_string and p.process_string.strip():
        # Ensure it starts with 'generate' is not needed, we add it
        return f"generate {p.process_string}"
    
    # Fallback for simple lists
    init  = " ".join(_resolve_particle(x) for x in p.initial_state)
    final = " ".join(_resolve_particle(x) for x in p.final_state)
    return f"generate {init} > {final}"



def node_add_processes(p: ProcessParams) -> str:
    """Branch 4: optional extra processes."""
    if not p.extra_processes:
        return ""
    return "\n".join(f"add process {line}" for line in p.extra_processes)


def node_output(p: ProcessParams) -> str:
    """Branch 5: output directory."""
    return f"output processes/{p.output_dir}"


# ─────────────────────────────────────────────────
# Run card builder
# ─────────────────────────────────────────────────


def build_run_card(p: ProcessParams) -> str:
    """Generate a minimal run_card.dat with correct beam settings."""

    # beam pdg: 2212 = proton, 11 = electron, -11 = positron
    beam_pdg_map = {"proton": 2212, "electron": 11, "positron": -11}
    pdg = beam_pdg_map.get(p.beam_type, 2212)

    card = f"""#*********************************************************************
# MadGraph5 run_card.dat  (auto-generated)
#*********************************************************************

#  Number of events and rnd seed
  {p.nevents}  = nevents    ! Number of unweighted events requested
  0            = iseed      ! rnd seed (0 = auto)

#  Collider type and energy
  {pdg}  = lpp1      ! beam 1 type (2212=proton, 11=electron)
  {pdg}  = lpp2      ! beam 2 type
  {p.beam_energy_gev:.1f}  = ebeam1    ! beam 1 energy in GeV
  {p.beam_energy_gev:.1f}  = ebeam2    ! beam 2 energy in GeV

#  PDF set
  {p.pdlabel}  = pdlabel   ! PDF set label
  {p.lhaid}    = lhaid     ! LHAPDF id

#  Scale
  {p.mur:.1f}  = scalefact  ! muR / muF scale factor

#  Cuts (defaults — edit as needed)
  20.0   = ptj      ! min pT for jets
  10.0   = pta      ! min pT for photons
  10.0   = ptl      ! min pT for leptons
  -1.0   = ptbj     ! min pT for b-jets (-1 = inactive)
  2.5    = etaj     ! max |eta| for jets
  2.5    = etal     ! max |eta| for leptons
  0.4    = drjj     ! min dR between jets
  0.4    = drll     ! min dR between leptons
"""
    return card

def build_full_mg5_script(p: ProcessParams) -> str:
    proc = build_proc_card(p).rstrip()
    launch = build_launch_script(p).lstrip()
    return proc + "\n\n" + launch


# ─────────────────────────────────────────────────
# Launch script builder
# ─────────────────────────────────────────────────

def build_launch_script(p: ProcessParams) -> str:
    """Generate the launch block for MadGraph5."""
    shower_line   = "shower=Pythia8"   if p.pythia8 else "shower=OFF"
    detector_line = "detector=OFF"     # Keep off for now to stay lightweight
    
    # NEW: Add MadAnalysis5 logic
    analysis_line = "analysis=MadAnalysis5" if p.pythia8 else "analysis=OFF"

    script = f"""# Launch block
launch processes/{p.output_dir}
  {shower_line}
  {detector_line}
  {analysis_line}

  set nevents {p.nevents}
  set ebeam1 {p.beam_energy_gev}
  set ebeam2 {p.beam_energy_gev}
"""
    # If using MA5, we often need to tell it to run automatically
    if p.pythia8:
        script += "  done\n" # This confirms the default cards
    
    script += "done\n"
    return script

# ─────────────────────────────────────────────────
# Master tree walker
# ─────────────────────────────────────────────────

def build_proc_card(p: ProcessParams) -> str:
    """
    Walk the decision tree and assemble proc_card.dat content.

    Tree structure:
    Root
    ├── [1] import model
    ├── [2] define multiparticles  (only if p/j beams)
    ├── [3] generate <process>
    ├── [4] add process ...        (optional, repeat)
    └── [5] output <dir>
    """
    sections = []

    # Branch 1: model
    sections.append(node_import_model(p))

    # Branch 2: multiparticle definitions (conditional)
    mp = node_define_multiparticles(p)
    if mp:
        sections.append(mp)

    # Branch 3: main process
    sections.append(node_generate_process(p))

    # Branch 4: extra processes (optional)
    ap = node_add_processes(p)
    if ap:
        sections.append(ap)

    # Branch 5: output
    sections.append(node_output(p))

    return "\n".join(sections) + "\n"


# ─────────────────────────────────────────────────
# File writer
# ─────────────────────────────────────────────────

def write_madgraph_files(p: ProcessParams, out_dir: str = ".") -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)

    # unique_name = make_unique_name(p.output_dir)
    # p.output_dir = unique_name

    script_name = f"launch_{p.output_dir}.mg5"
    files = {
        script_name: build_full_mg5_script(p),
    }

    for fname, content in files.items():
        path = os.path.join(out_dir, fname)
        with open(path, "w") as f:
            f.write(content)

    return files
