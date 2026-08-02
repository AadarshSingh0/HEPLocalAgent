# core/result_parser.py
import os
import re
from typing import Optional, Dict

def parse_cross_section(result: Dict, output_dir: str) -> Optional[float]:
    """
    Tries to find the cross section in the summary file first, 
    then falls back to stdout.
    """
    # 1. Try to find the summary.txt or crossx.html inside the process folder
    summary_path = os.path.join("processes", output_dir, "crossx.html")
    
    if os.path.exists(summary_path):
        with open(summary_path, "r") as f:
            content = f.read()
            # Look for the cross section in the HTML table
            # Format usually: 881.3 <font ...> +- 1.2
            match = re.search(r'([\d.eE+-]+)\s*<font', content)
            if match:
                return float(match.group(1))

    # 2. Fallback to Log Parsing (what you already had)
    patterns = [
        r"Cross-section\s*:\s*([0-9eE\+\-\.]+)",
        r"Integrated weight \(pb\)\s*:\s*([0-9eE\+\-\.]+)",
    ]
    
    for text in [result.get("stdout", ""), result.get("stderr", "")]:
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return float(m.group(1))
    
    return None