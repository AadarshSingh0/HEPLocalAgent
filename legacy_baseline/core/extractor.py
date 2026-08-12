"""
Parameter Extractor
===================
Sends user input to a local Llama3 8B (via Ollama) or any OpenAI-compatible
endpoint and extracts ONLY structured JSON — never MadGraph syntax.

The LLM's job description is exactly this:
  "Read the user's physics request. Return a JSON object with these fields.
   Do NOT write any MadGraph commands."
"""

import json
import re
from typing import Any
import requests

from config import DEFAULT_OLLAMA_HOST, DEFAULT_OPENAI_BASE_URL
from core.tree_builder import ProcessParams, build_launch_script, build_proc_card
from typing import Any, Dict
# ─────────────────────────────────────────────────
# Prompt engineering
# ─────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a high-energy physics parameter extractor.
Your ONLY job is to read a user's particle physics request and return a single JSON object.
You MUST NOT write any MadGraph commands or code.
You MUST respond with valid JSON only — no explanation, no markdown, no extra text.

The JSON must have these fields (use defaults where unspecified):

{
  "model": string,              // "sm" | "mssm" | "2hdm" | "heft" | "dm_scalar" | "dm_vector" | "feynrules"
                                // default: "sm"
  "initial_state": [string],    // list of particles, e.g. ["p","p"] or ["e-","e+"]
  "final_state": [string],      // list of particles, e.g. ["e-","e+","a"] 
  "process_string": string | null, // Use for complex topologies like "p p > t t~, (t > w+ b)"
                                   // If simple, leave null.

  "extra_processes": [string],  // optional additional processes, e.g. ["p p > mu- mu+"]
  "beam_energy_gev": number,    // energy PER BEAM in GeV. For 13 TeV LHC → 6500. Default 6500.
  "beam_type": string,          // "proton" | "electron" | "positron". Default "proton"
  "nevents": integer,           // number of events. Default 10000
  "output_dir": string,         // short directory name, snake_case. Default "my_process"
  "pythia8": boolean,           // whether to run Pythia8 shower. Default false
  "delphes": boolean,           // whether to run Delphes detector sim. Default false
  "qcd_order": integer | null,  // e.g. 0 for EW-only. null = MadGraph default
  "qed_order": integer | null   // null = MadGraph default
}

Rules for particles — use these exact MadGraph5 tokens:
  proton beam    → "p"
  electron beam  → "e-"
  positron beam  → "e+"
  muon           → "mu-" or "mu+"
  tau            → "ta-" or "ta+"
  neutrino (e)   → "ve" or "ve~"
  photon         → "a"
  gluon          → "g"
  Z boson        → "z"
  W boson        → "w+" or "w-"
  Higgs          → "h"
  jets           → "j"
  top quark      → "t" or "t~"
  bottom quark   → "b" or "b~"

For antiparticles add tilde: u~ d~ s~ c~ b~ t~ e+ mu+ etc.

CRITICAL RULES:
1. Beam Energy: If the user says "14 TeV", you MUST return 7000 (energy per beam).
2. Process String: If the user specifies a decay or intermediate particle (like "p p > z > mu+ mu-"), 
   put the ENTIRE string in "process_string" and leave "final_state" empty.
3. Only use "initial_state" and "final_state" for simple 2->2 or 2->N processes.
4. Always separate final state particles with spaces. 
Example: "h h" (Correct) vs "hh" (Wrong). "e+ e-" (Correct) vs "e+e-" (Wrong).

ENERGY RULES:
- You MUST return the BEAM ENERGY (E_beam) in GeV. 
- Math: E_beam = (Total Collider Energy) / 2.
- Examples: 
  "500 GeV" -> 250
  "13 TeV"  -> 6500
  "2 TeV"   -> 1000
  "90 GeV"  -> 45

ENERGY CALCULATION RULES:
- You are a calculator. You MUST divide the user's collider energy by 2.
- If user says "345 GeV", you MUST return 172.5. 
- If user says "13 TeV", you MUST return 6500.
- If user says "1 TeV", you MUST return 500.
- NEVER assume TeV if the user wrote GeV.
- Output ONLY the number in GeV for the "beam_energy_gev" field.

MADGRAPH SYNTAX RULES (Use in "process_string"):
1. Exclusions: To exclude a particle from ALL diagrams, use '/'. 
   Example: "p p > e+ e- / z" (Excludes Z boson)
2. S-Channel Removal: To remove s-channel propagators, use '$'.
   Example: "p p > j j $ z"
3. Decays: Use '>' and parentheses. 
   Example: "p p > t t~, (t > w+ b), (t~ > w- b~)"
4. NLO/Precision: Use [QCD] for NLO. Do NOT use [NLO].
   Example: "p p > t t~ [QCD]"
5. Couplings: Specify orders with '='.
   Example: "p p > e+ e- QED=2 QCD=0"

If the user request is complex (using any of the above), put the ENTIRE command in "process_string" and leave "final_state" empty.

Examples of correct output:
  Input: "generate p p to Z to e+ e-"
  Output: {"model":"sm","initial_state":["p","p"],"final_state":["z"],"extra_processes":[],"beam_energy_gev":6500,"beam_type":"proton","nevents":10000,"output_dir":"pp_to_z_ll","pythia8":false,"delphes":false,"qcd_order":null,"qed_order":null}

  Input: "p p > t t~ at 14 TeV with 50000 events, shower with pythia8"
  Output: {"model":"sm","initial_state":["p","p"],"final_state":["t","t~"],"extra_processes":[],"beam_energy_gev":7000,"beam_type":"proton","nevents":50000,"output_dir":"pp_ttbar","pythia8":true,"delphes":false,"qcd_order":null,"qed_order":null}
  
  Input: "top pair production with leptonic decay at 13 TeV"
  Output: {"model":"sm", "process_string":"p p > t t~, (t > w+ b, w+ > l+ vl), (t~ > w- b~, w- > l- vl~)", ...}

  Input: "e+ e- collision at 250 GeV producing Higgs with 100k events, full detector sim"
  Output: {"model":"sm","initial_state":["e-","e+"],"final_state":["h"],"extra_processes":[],"beam_energy_gev":125,"beam_type":"electron","nevents":100000,"output_dir":"ee_higgs","pythia8":true,"delphes":true,"qcd_order":null,"qed_order":null}
"""


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """Robustly parse JSON even if LLM wraps it in markdown."""
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    cleaned = re.sub(r"```", "", cleaned).strip()

    # Find first { ... } block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in LLM response:\n{text}")


def json_to_params(data: Dict[str, Any]) -> ProcessParams:
    """Map extracted JSON dict → ProcessParams dataclass."""
    p = ProcessParams()
    p.process_string = data.get("process_string")

    p.model          = data.get("model", "sm")
    p.initial_state  = data.get("initial_state", ["p", "p"])
    p.final_state    = data.get("final_state",   ["e-", "e+"])
    p.extra_processes = data.get("extra_processes", [])
    p.beam_energy_gev = float(data.get("beam_energy_gev", 6500))
    p.beam_type      = data.get("beam_type", "proton")
    p.nevents        = int(data.get("nevents", 10000))
    p.output_dir     = data.get("output_dir", "my_process")
    p.pythia8        = bool(data.get("pythia8", False))
    p.delphes        = bool(data.get("delphes", False))
    p.qcd_order      = data.get("qcd_order", None)
    p.qed_order      = data.get("qed_order", None)

    return p


# ─────────────────────────────────────────────────
# Ollama backend (local Llama3 8B)
# ─────────────────────────────────────────────────

def call_ollama(
    user_input: str,
    model: str = "llama3:8b",
    host: str = DEFAULT_OLLAMA_HOST,
) -> str:
    """Call a local Ollama instance."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system",  "content": SYSTEM_PROMPT},
            {"role": "user",    "content": user_input},
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,     # deterministic — we want JSON, not creativity
            "num_predict": 512,
        }
    }
    resp = requests.post(f"{host}/api/chat", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ─────────────────────────────────────────────────
# OpenAI-compatible backend (vLLM, LM Studio, etc.)
# ─────────────────────────────────────────────────

def call_openai_compat(
    user_input: str,
    model: str = "llama3:8b",
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    api_key: str = "none"
) -> str:
    """Call any OpenAI-compatible endpoint."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system",  "content": SYSTEM_PROMPT},
            {"role": "user",    "content": user_input},
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ─────────────────────────────────────────────────
# Main extraction pipeline
# ─────────────────────────────────────────────────

def extract_params(
    user_input: str,
    backend: str = "ollama",
    **kwargs
) -> ProcessParams:
    """
    Full pipeline: user text → ProcessParams

    Args:
        user_input: natural language physics request
        backend: "ollama" | "openai"
        **kwargs: passed to the backend call (model, host, base_url, etc.)
    """
    if backend == "ollama":
        raw = call_ollama(user_input, **kwargs)
    elif backend == "openai":
        raw = call_openai_compat(user_input, **kwargs)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    data   = extract_json_from_text(raw)
    params = json_to_params(data)
    return params

# ------------- Self-Healing Loop for LLM Syntax Errors (Bonus) -------------
def fix_syntax_error(
    query,
    error_log,
    model="llama3:8b",
    host=DEFAULT_OLLAMA_HOST,
):
    """Ask the AI to fix a specific MadGraph error."""
    # Only send the last few lines of the error to save tokens
    clean_error = error_log[-800:] if len(error_log) > 800 else error_log
    
    repair_prompt = f"""
    The user wants: {query}
    MadGraph5 failed with this error:
    ---
    {clean_error}
    ---
    Identify the syntax error in the 'generate' command. 
    Return ONLY the corrected process string (e.g., 'p p > t t~'). 
    Do not explain. No markdown.
    """
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": repair_prompt}],
        "stream": False,
        "options": {"temperature": 0.0}
    }
    try:
        resp = requests.post(f"{host}/api/chat", json=payload, timeout=40)
        content = resp.json()["message"]["content"]
        # Clean up any "generate" word if the LLM added it
        return content.lower().replace("generate", "").strip().strip("'").strip('"')
    except:
        return None
    

# ADD THIS REPAIR FUNCTION AT THE BOTTOM:
def fix_syntax_error(
    query,
    error_log,
    model="llama3:8b",
    host=DEFAULT_OLLAMA_HOST,
):
    clean_error = error_log[-800:]
    
    repair_prompt = f"""
    The user wants: {query}
    MadGraph failed: "{clean_error}"
    
    PARTICLE CHEAT SHEET:
    - Standard Model: h, z, w+, w-, t, b, g, a
    - MSSM: h1, h2, h3, h+, h-, go, n1, n2
    - HEFT: h, z, w+, w-
    
    If you tried 'h1' and it failed, the model might be 'sm' and the particle 'h'.
    If you tried 'h' and it failed, the model might be 'mssm' and the particle 'h1'.
    
    You MUST respond ONLY in this format:
    MODEL: [model_name]
    PROCESS: [process_string]
    """
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": repair_prompt}],
        "stream": False,
        "options": {"temperature": 0.7} # Increase temperature so it tries different things
    }
    try:
        resp = requests.post(f"{host}/api/chat", json=payload, timeout=40)
        return resp.json()["message"]["content"].strip()
    except:
        return None
