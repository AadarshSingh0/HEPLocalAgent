# core/agents/confirmation.py
import requests

def get_confirmation_summary(params, query, host="http://10.42.106.85:11434"):
    """
    Turns the technical ProcessParams into a friendly confirmation message.
    """
    prompt = f"""
    The user asked for: "{query}"
    The system extracted these technical parameters:
    - Model: {params.model}
    - Initial State: {params.initial_state}
    - Final State: {params.final_state}
    - Process String: {params.process_string}
    - Beam Energy: {params.beam_energy_gev} GeV (sqrt(s) = {params.beam_energy_gev * 2 / 1000} TeV)
    - Events: {params.nevents}

    MADGRAPH DICTIONARY:
    - 'h' = Higgs boson (NOT hadron)
    - 't' = top quark
    - 'p' = proton
    - 'j' = jet (gluons/light quarks)
    - 'a' = photon
    
    Act as a Senior Physicist. Briefly explain the setup.
    Example: "Confirming: Proton-proton collision at 14 TeV for Higgs pair production (p p > h h)."
    Do NOT hallucinate 'heavy hadrons'. If you are not sure about what a particle is just say not sure for that particle. Do not hallucinate its name.
    Act as a helpful Physics Assistant. Summarize this setup to the user.
    Example: "I've set up a proton-proton collision at 13 TeV to produce a Z boson decaying into muons. Does this match your intent?"
    Keep it to 2 sentences.
    """
    
    payload = {
        "model": "llama3:8b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.0}
    }
    try:
        resp = requests.post(f"{host}/api/chat", json=payload, timeout=40)
        return resp.json()["message"]["content"]
    except:
        return "Extraction complete. Ready to run?"