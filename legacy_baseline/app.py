import streamlit as st
import os
import subprocess
from core.extractor import extract_params
from core.validator import validate_and_normalize
from core.tree_builder import write_madgraph_files
from core.runner import run_mg5_script
from core.result_parser import parse_cross_section
from config import (
    DEFAULT_LOG_DIR,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OUTPUT_DIR,
    MG5_PATH,
)
from core.bootstrap import heal_environment

# Run the environment check once when the app starts
if "bootstrapped" not in st.session_state:
    status_msg = heal_environment()
    print(status_msg) # This will show in your terminal
    st.session_state.bootstrapped = True

# --- INITIALIZE AGENT STATE ---
if "confirmed" not in st.session_state:
    st.session_state.confirmed = False
if "pending_params" not in st.session_state:
    st.session_state.pending_params = None

if "current_run" not in st.session_state:
    st.session_state.current_run = None

# --- INITIALIZE HISTORY ---
if "history" not in st.session_state:
    st.session_state.history = []

st.set_page_config(page_title="MicroMadAgent | HEP AI", page_icon="⚛️", layout="wide")

# --- SIDEBAR: HISTORY & SETTINGS ---
with st.sidebar:
    st.title("⚛️ Agent Control")
    
    if st.button("🗑️ Clear History"):
        st.session_state.history = []
        st.rerun()

    st.divider()
    st.subheader("Run History")
    if not st.session_state.history:
        st.caption("No previous runs.")
    else:
        for item in reversed(st.session_state.history):
            with st.expander(f"📌 {item['query'][:30]}..."):
                st.write(f"**Process:** `{item['proc']}`")
                st.write(f"**XS:** `{item['xs']} pb`")
                st.write(f"**Energy:** `{item['energy']} TeV`")
    
    st.divider()
    st.subheader("Analysis")
    do_plots = st.checkbox("🎨 Generate Fancy Plots", value=False, help="Requires Pythia8 and MadAnalysis5")
    if do_plots:
        st.info("Note: Plotting requires Pythia8 showering.")

    st.divider()
    model_name = st.text_input("LLM Model", value="llama3:8b")
    ollama_host = st.text_input("Ollama Host", value=DEFAULT_OLLAMA_HOST)
    num_events = st.number_input("Events", value=10000, step=1000)

# --- MAIN UI ---
st.title("⚛️ MicroMadAgent")
st.markdown("#### **AI-Driven Collider Phenomenology Pipeline**")

# --- FORM FOR "ENTER" KEY SUPPORT ---
with st.form(key="physics_form", clear_on_submit=False):
    query = st.text_input("What process would you like to simulate?", 
                          placeholder="e.g., p p > t t~ at 13 TeV")
    submit_button = st.form_submit_button(label="Execute Simulation")

# Placeholder for results of the CURRENT run
result_placeholder = st.container()

# --- STEP 1: INTERPRETATION (Triggers when user hits "Execute Simulation") ---
if submit_button:
    if not query:
        st.error("Please enter a query.")
    else:
        # Clear everything old
        st.session_state.current_run = None
        st.session_state.confirmed = False
        
        with st.status("Agent interpreting query...", expanded=True):
            params = extract_params(query, backend="ollama", model=model_name, host=ollama_host)
            params.nevents = num_events
            params.pythia8 = do_plots 
            params = validate_and_normalize(params)
            
            st.session_state.pending_params = params
            st.session_state.pending_query = query
            
            from core.agents.confirmation import get_confirmation_summary
            summary = get_confirmation_summary(params, query, host=ollama_host)
            st.session_state.summary = summary
            st.rerun() # Force screen refresh to show Confirmation UI

# --- STEP 2: CONFIRMATION UI (Only shows if we have params but NOT yet confirmed) ---
if st.session_state.get("pending_params") and not st.session_state.confirmed:
    st.divider()
    st.subheader("🤖 Agent's Interpretation")
    st.info(st.session_state.summary)
    
    col_confirm, col_cancel = st.columns([1, 4])
    if col_confirm.button("✅ Yes, Execute"):
        st.session_state.confirmed = True
        st.rerun()
    if col_cancel.button("❌ No, Restart"):
        st.session_state.pending_params = None
        st.session_state.summary = None
        st.rerun()

# --- STEP 3: SIMULATION (Only shows after "Yes" is clicked) ---
if st.session_state.confirmed and st.session_state.get("pending_params"):
    params = st.session_state.pending_params
    query = st.session_state.pending_query
    
    with st.status("Executing Physics Workflow...", expanded=True) as status:
        MAX_ATTEMPTS = 4
        success = False
        xs = None
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            status.write(f"🕵️ **Attempt {attempt}**: Running MadGraph...")

            # --- THE REPAIR BRAIN (Starts from Attempt 2) ---
            if attempt > 1:
                status.write("⚠️ Previous attempt failed. Agent is analyzing the error...")
                from core.extractor import fix_syntax_error
                import re

                # Feed the error log back to the AI
                combined_log = (result["stdout"] or "") + (result["stderr"] or "")
                raw_fix = fix_syntax_error(query, combined_log, model=model_name, host=ollama_host)

                if raw_fix:
                    # Extract the fix (e.g., MODEL: mssm PROCESS: p p > hl h)
                    model_match = re.search(r"MODEL:\s*(\w+)", raw_fix, re.IGNORECASE)
                    proc_match = re.search(r"PROCESS:\s*(.+)", raw_fix, re.IGNORECASE)
                    
                    if model_match: 
                        params.model = model_match.group(1).strip().lower()
                    if proc_match:
                        # Clean common spacing issues
                        new_proc = proc_match.group(1).strip().lower().replace("hh", "h h").replace("tt~", "t t~")
                        params.process_string = new_proc
                    
                    status.write(f"🔧 **Repairing**: Switching to `{params.model}` model and process: `{params.process_string}`")

            # --- RUN MADGRAPH ---
            files = write_madgraph_files(params, out_dir=DEFAULT_OUTPUT_DIR)
            script_path = os.path.join(DEFAULT_OUTPUT_DIR, next(iter(files)))
            result = run_mg5_script(script_path, mg5_cmd=MG5_PATH)
            xs = parse_cross_section(result, params.output_dir)
            
            # If we have a cross-section, we win!
            if result["success"] and xs is not None:
                success = True
                break
        
        # --- FINAL RESULTS ---
        if success:
            status.update(label="Simulation Successful!", state="complete")
            st.session_state.current_run = {
                "query": query, 
                "params": params, 
                "xs": xs, 
                "output_dir": params.output_dir
            }
            # Add to history
            st.session_state.history.append({
                "query": query,
                "proc": params.process_string if params.process_string else "Process",
                "xs": f"{xs:.4e}",
                "energy": params.beam_energy_gev * 2 / 1000
            })
            # Open results
            html_path = os.path.abspath(os.path.join("processes", params.output_dir, "crossx.html"))
            if os.path.exists(html_path):
                subprocess.Popen(["firefox", html_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            status.update(label="Agent Exhausted All Attempts", state="error")
            st.error("MadGraph failed to produce a result. The process might be physically impossible or the model is missing.")
        
        # Cleanup
        st.session_state.pending_params = None
        st.session_state.confirmed = False

# --- RENDER RESULTS (This is OUTSIDE the submit button block) ---
if st.session_state.current_run:
    run = st.session_state.current_run
    
    with result_placeholder:
        st.success("Simulation results ready.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Cross Section", f"{run['xs']:.4f} pb")
        c2.metric("Beam Energy", f"{run['params'].beam_energy_gev} GeV")
        c3.metric("LHC Energy", f"{(run['params'].beam_energy_gev * 2 / 1000)} TeV")
        
        # Open standard results
        html_path = os.path.abspath(os.path.join("processes", run['output_dir'], "crossx.html"))
        if os.path.exists(html_path):
            st.info(f"Summary available: {html_path}")

        # --- MODULAR ANALYSIS BUTTON ---
        if run['params'].pythia8:
            st.divider()
            st.subheader("📊 Advanced Analysis")
            if st.button("🎨 Generate Fancy Plots"):
                with st.spinner("MadAnalysis5 is processing events..."):
                    from core.analyser import run_post_analysis
                    report_path, err = run_post_analysis(run['output_dir'], run['query'])
                    
                    if err:
                        st.error(err)
                    else:
                        st.success("Analysis Complete!")
                        subprocess.Popen(["firefox", report_path])
