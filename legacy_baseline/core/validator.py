# core/validator.py

import re
from datetime import datetime
from core.constants import PARTICLE_ALIASES, MODELS as MODEL_ALIASES



def normalize_particle(p: str) -> str:
    key = p.strip().lower().replace(" ", "")
    return PARTICLE_ALIASES.get(key, p.strip())


def normalize_model(model: str) -> str:
    key = model.strip().lower()
    return MODEL_ALIASES.get(key, model.strip())


def safe_name(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "process"


def make_unique_name(base: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{safe_name(base)}_{stamp}"


def validate_and_normalize(params):
    # 1. Keep Normalization (needed so 'electron' becomes 'e-')
    params.model = normalize_model(params.model)
    if params.initial_state:
        params.initial_state = [normalize_particle(x) for x in params.initial_state]
    if params.final_state:
        params.final_state = [normalize_particle(x) for x in params.final_state]

    if not params.model:
        raise ValueError("Model is missing.")

    # 2. Keep Process String Awareness (needed for pp > z > ee logic)
    if not params.process_string or not params.process_string.strip():
        if not params.initial_state:
            raise ValueError("Initial state is empty.")
        if not params.final_state:
            raise ValueError("Final state is empty.")
    
    # 3. PURE ENERGY CHECK (No division logic anymore!)
    # We trust the LLM completely. We only check if it is a positive number.
    if params.beam_energy_gev <= 0:
        raise ValueError("Beam energy must be positive.")

    if params.nevents <= 0:
        raise ValueError("Number of events must be positive.")

    # 4. Keep Directory naming (needed for folder organization)
    if not params.output_dir or not params.output_dir.strip():
        if params.process_string:
            base = safe_name(params.process_string[:20])
        else:
            base = f"{'_'.join(params.initial_state)}_to_{'_'.join(params.final_state)}"
        params.output_dir = base

    params.output_dir = make_unique_name(params.output_dir)

    return params