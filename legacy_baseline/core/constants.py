# core/constants.py
from typing import Dict

# Single source of truth for particle mapping
PARTICLE_ALIASES: Dict[str, str] = {
    # Quarks
    "u": "u", "d": "d", "s": "s", "c": "c", "b": "b", "t": "t",
    "u~": "u~", "d~": "d~", "s~": "s~", "c~": "c~", "b~": "b~", "t~": "t~",
    "top": "t", "antitop": "t~", "bottom": "b", "antibottom": "b~",
    
    # Leptons
    "e-": "e-", "e+": "e+", "mu-": "mu-", "mu+": "mu+", "ta-": "ta-", "ta+": "ta+",
    "ve": "ve", "vm": "vm", "vt": "vt", "ve~": "ve~", "vm~": "vm~", "vt~": "vt~",
    "electron": "e-", "positron": "e+", "muon": "mu-", "antimuon": "mu+", "tau": "ta-",
    
    # Bosons
    "g": "g", "a": "a", "z": "z", "w+": "w+", "w-": "w-", "h": "h",
    "photon": "a", "gluon": "g", "higgs": "h", "zboson": "z",
    
    # Multi-particle
    "p": "p", "j": "j", "l+": "l+", "l-": "l-", "vl": "vl", "vl~": "vl~",
    "proton": "p", "protons": "p", "jet": "j", "jets": "j"
}

MODELS: Dict[str, str] = {
    "sm": "sm",
    "mssm": "MSSM_SLHA2",
    "2hdm": "2HDM",
    "heft": "heft",
    "standard model": "sm"
}