#!/usr/bin/env python3
"""
MadGraph5 File Generator
========================
Usage:
    python main.py "p p > e- e+"
    python main.py "p p > t t~ at 14 TeV with 50000 events, run pythia8"
    python main.py --backend openai --base-url http://localhost:8000/v1 "p p > h at 13 TeV"

Options:
    --backend   ollama (default) | openai
    --model     model name for the LLM (default: llama3)
    --host      Ollama host (default: http://localhost:11434)
    --base-url  OpenAI-compat base URL
    --out-dir   output directory for generated files (default: ./output)
    --dry-run   print params without calling the LLM (for testing with --json)
    --json      raw JSON string to use instead of LLM (for testing)
"""

import argparse
import json
import sys
import os
import subprocess

# Allow running from project root
sys.path.insert(0, os.path.dirname(__file__))

from core.tree_builder import ProcessParams, write_madgraph_files, build_proc_card
from core.extractor    import extract_params, json_to_params
from core.validator import validate_and_normalize
from core.runner import run_mg5_script
from config import (
    DEFAULT_LOG_DIR,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OUTPUT_DIR,
    MG5_PATH,
)
from core.result_parser import parse_cross_section
from typing import Dict

def pretty_print_files(files: Dict[str, str]) -> None:
    for fname, content in files.items():
        print(f"\n{'═'*60}")
        print(f"  {fname}")
        print('═'*60)
        print(content)


def main():
    parser = argparse.ArgumentParser(description="Generate MadGraph5 input files from natural language")
    parser.add_argument("query", nargs="?", help="Physics process description")
    parser.add_argument("--backend",  default="ollama",                   help="ollama | openai")
    parser.add_argument("--model",    default="llama3:8b",                   help="LLM model name")
    parser.add_argument("--host", default=DEFAULT_OLLAMA_HOST, help="Ollama host")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_OPENAI_BASE_URL,
        help="OpenAI-compat URL",
    )
    parser.add_argument("--out-dir",  default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--json",     default=None,                       help="Skip LLM, pass raw JSON")
    parser.add_argument("--dry-run",  action="store_true",                help="Print files to stdout only")
    parser.add_argument("--run", action="store_true", help="Run MadGraph automatically after writing script")
    args = parser.parse_args()
    
    # ── Get ProcessParams ──────────────────────────────────────────────
    if args.json:
        # Testing mode: bypass LLM entirely
        data   = json.loads(args.json)
        params = json_to_params(data)
        print("⚡ Bypassing LLM — using provided JSON")

    elif args.query:
        print(f"🔍 Sending to {args.backend} ({args.model}): \"{args.query}\"")
        try:
            if args.backend == "ollama":
                params = extract_params(args.query, backend="ollama",
                                        model=args.model, host=args.host)
            else:
                params = extract_params(args.query, backend="openai",
                                        model=args.model, base_url=args.base_url)
        except Exception as e:
            print(f"❌ LLM call failed: {e}")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(0)

    # ── Validate / normalize parameters ───────────────────────────────
    params = validate_and_normalize(params)

    # ── Show extracted params ──────────────────────────────────────────
    print("\n✅ Extracted parameters:")
    print(f"   model        : {params.model}")
    if params.process_string:
        print(f"   process      : {params.process_string}")
    else:
        print(f"   initial state: {params.initial_state}")
        print(f"   final state  : {params.final_state}")
    print(f"   beam energy  : {params.beam_energy_gev} GeV ({params.beam_energy_gev*2/1000:.1f} TeV)")
    print(f"   nevents      : {params.nevents:,}")
    print(f"   pythia8      : {params.pythia8}")
    print(f"   delphes      : {params.delphes}")
    print(f"   output dir   : {params.output_dir}")

    # ── Build and write files ──────────────────────────────────────────
    if args.dry_run:
        from core.tree_builder import build_full_mg5_script

        script_name = f"launch_{params.output_dir}.mg5"
        files = {
            script_name: build_full_mg5_script(params)
        }

        pretty_print_files(files)

    else:
        files = write_madgraph_files(params, out_dir=args.out_dir)

        print(f"\n📁 Files written to: {os.path.abspath(args.out_dir)}/")
        for fname in files:
            print(f"   • {fname}")

        script_name = next(iter(files))
        script_path = os.path.join(args.out_dir, script_name)

        print("\n💡 To run MadGraph5 manually:")
        print(f"   mg5_aMC < {script_path}")

        if args.run:
            log_path = os.path.join(DEFAULT_LOG_DIR, f"{params.output_dir}.log")
            print("\n🚀 Running MadGraph5...")

            result = run_mg5_script(script_path, log_path=log_path, mg5_cmd=MG5_PATH)

            if result["success"]:
                print("✅ MadGraph run completed successfully.")

                

                html_path = os.path.join("processes", params.output_dir, "crossx.html")
                if os.path.exists(html_path):
                    subprocess.Popen(
                        ["firefox", html_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )

                xs = parse_cross_section(result, params.output_dir)

                if xs is not None:
                    print(f"\n📊 Cross section ≈ {xs:.6g} pb")
                else:
                    print("\n⚠ Could not extract cross section automatically.")
            else:
                print("❌ MadGraph run failed.")
                print(f"   return code: {result['returncode']}")

            print(f"📝 Log saved to: {log_path}")


if __name__ == "__main__":
    main()
