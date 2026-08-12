# core/bootstrap.py
import os
import shutil
import subprocess
from config import MA5_PATH

def heal_environment():
    """
    Checks if MadAnalysis5 has Python 3.9 syntax errors and fixes them
    for Python 3.8 compatibility.
    """
    # 1. Calculate the path to the problematic file based on MA5_PATH.
    # A bare fallback command is safe for subprocess execution, but must be
    # discovered before deriving a filesystem location from it.
    ma5_executable = (
        MA5_PATH if os.path.dirname(MA5_PATH) else shutil.which(MA5_PATH)
    )
    if not ma5_executable:
        return "⚠️ MadAnalysis5 executable not found. Skipping auto-repair."

    # MA5_PATH is .../bin/ma5, we need .../madanalysis/misc/theoretical_error_setup.py
    ma5_root = os.path.dirname(os.path.dirname(ma5_executable))
    target_file = os.path.join(ma5_root, "madanalysis", "misc", "theoretical_error_setup.py")

    if not os.path.exists(target_file):
        return "⚠️ MadAnalysis5 file not found. Skipping auto-repair."

    # 2. Check if the file contains Python 3.9 "bracket" syntax
    needs_fixing = False
    with open(target_file, 'r') as f:
        content = f.read()
        if "dict[" in content or "list[" in content:
            needs_fixing = True

    if needs_fixing:
        try:
            # Run the repair commands
            subprocess.run([f"sed -i 's/dict\\[.*\\]/dict/g' {target_file}"], shell=True)
            subprocess.run([f"sed -i 's/list\\[.*\\]/list/g' {target_file}"], shell=True)
            subprocess.run([f"sed -i 's/-> dict.*/:/g' {target_file}"], shell=True)
            return "✅ MadAnalysis5 successfully patched for Python 3.8 compatibility."
        except Exception as e:
            return f"❌ Failed to patch MadAnalysis5: {str(e)}"
    
    return "🛡️ Environment is healthy (No patching required)."
