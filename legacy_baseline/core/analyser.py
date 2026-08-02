# core/analyser.py
import os
import subprocess
from config import MA5_PATH

def run_post_analysis(output_dir, query):
    # 1. Define where the event file is
    event_path = os.path.abspath(os.path.join("processes", output_dir, "Events", "run_01", "tag_1_pythia8_events.hepmc.gz"))
    
    if not os.path.exists(event_path):
        return None, "Error: No Pythia8 event file found. Ensure Pythia8 is active."

    # 2. Define where the analysis folder should go (INSIDE the process folder)
    # This matches your path: .../processes/[output_dir]/analysis_results
    analysis_dir = os.path.abspath(os.path.join("processes", output_dir, "analysis_results"))

    # 3. Create the MA5 script
    ma5_script = f"""
import {event_path}
set main.stacking_method = log
plot M(l+ l-) 50 0 200
plot PT(l+) 50 0 500
submit {analysis_dir}
exit
"""
    script_file = f"temp_analysis_{output_dir}.ma5"
    with open(script_file, "w") as f:
        f.write(ma5_script)

    try:
        # 4. Run MA5
        subprocess.run([MA5_PATH, "-s", script_file], check=True)
        
        # 5. Look for the HTML report in the exact path you found
        # We use 'MadAnalysis5job_0' as the default folder MA5 creates
        html_report = os.path.join(analysis_dir, "Output", "HTML", "MadAnalysis5job_0", "index.html")
        pdf_report  = os.path.join(analysis_dir, "Output", "PDF", "Main", "main.pdf")

        if os.path.exists(html_report):
            return html_report, None
        elif os.path.exists(pdf_report):
            return pdf_report, None
        else:
            # If the job folder has a different number, find it automatically
            base_html_dir = os.path.join(analysis_dir, "Output", "HTML")
            if os.path.exists(base_html_dir):
                for sub in os.listdir(base_html_dir):
                    if "MadAnalysis5job" in sub:
                        alt_path = os.path.join(base_html_dir, sub, "index.html")
                        if os.path.exists(alt_path):
                            return alt_path, None

            return None, f"Analysis finished but report not found in: {analysis_dir}"

    except Exception as e:
        return None, f"MadAnalysis5 failed: {str(e)}"