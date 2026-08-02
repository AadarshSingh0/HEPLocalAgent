# test_plots.py
from core.analyser import run_post_analysis
import os

# 1. CHANGE THIS to a folder name that actually exists in your /processes directory
target_dir = "pp_to_ee_20260315_114514_131175" 

print(f"🧪 Testing analysis on: {target_dir}")

# 2. Run the analysis
report, err = run_post_analysis(target_dir, "p p > e+ e-")

if err:
    print(f"❌ FAILED: {err}")
else:
    print(f"✅ SUCCESS! Report created at: {report}")
    # Try to open it
    os.system(f"firefox {report}")