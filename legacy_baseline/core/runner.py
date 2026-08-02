# core/runner.py

import os
import subprocess
from typing import Optional, Dict

env = os.environ.copy()
env["BROWSER"] = "firefox"
def run_mg5_script(script_path: str, log_path: Optional[str] = None, mg5_cmd: str = "mg5_aMC") -> Dict:
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"MG5 script not found: {script_path}")

    cmd = f'{mg5_cmd} -f "{script_path}"'

    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True,
        env=env
    )

    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            f.write("=== STDOUT ===\n")
            f.write(result.stdout)
            f.write("\n\n=== STDERR ===\n")
            f.write(result.stderr)

    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }