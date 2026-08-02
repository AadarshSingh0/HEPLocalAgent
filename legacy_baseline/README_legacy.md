# MadGraph5 File Generator

Generates correct MadGraph5 input files from plain English using a **two-stage architecture** that keeps a small LLM (Llama3 8B) reliable by giving it only one job.

---

## The Core Idea

```
User: "p p > t t~ at 14 TeV, 50k events, shower with pythia8"
         │
         ▼
┌─────────────────────────────────────┐
│  LLM  (Llama3 8B / any model)       │
│  Job: extract parameters → JSON     │
│  NO MadGraph syntax ever written    │
└──────────────────┬──────────────────┘
                   │
                   ▼  {"model":"sm", "initial":["p","p"],
                        "final":["t","t~"], "energy":7000,
                        "pythia8":true, ...}
                   │
         ┌─────────▼──────────┐
         │  Decision Tree      │  ← pure Python, deterministic
         │  (tree_builder.py)  │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────────────┐
         │  proc_card.dat             │
         │  run_card.dat              │
         │  launch_pp_ttbar.mg5       │
         └────────────────────────────┘
```

**Why this works where RAG / full-generation fails:**

| Approach          | Problem                                          |
|-------------------|--------------------------------------------------|
| LLM writes syntax | Hallucinated keywords, wrong order, format errors |
| RAG on manual     | 8B model can't reliably follow multi-page rules   |
| **This approach** | LLM only extracts 10 simple fields → tree writes correct syntax every time |

---

## Decision Tree Structure

```
Root
├── [1] import model          → resolved from MODELS table
│         sm | mssm | heft | 2hdm | dm_scalar | feynrules ...
│
├── [2] define multiparticles  → only injected when p or j beams detected
│         define p = p b b~
│         define j = j b b~
│
├── [3] generate <process>     → particles resolved via PARTICLE_ALIASES table
│         generate p p > e- e+
│         [optional: QCD=N / QED=N]
│
├── [4] add process ...         → repeated for each extra_processes entry
│
└── [5] output <dir>
```

---

## Quick Start

### Test without any LLM (JSON bypass)
```bash
python main.py --json '{"model":"sm","initial_state":["p","p"],"final_state":["e-","e+"],"beam_energy_gev":6500,"nevents":10000,"output_dir":"pp_ll","pythia8":false,"delphes":false}' --dry-run
```

### With local Llama3 via Ollama
```bash
# Start Ollama first:  ollama run llama3
python main.py "p p > e- e+ at 13 TeV"
python main.py "p p > t t~ at 14 TeV with 50000 events, run pythia8 and delphes"
python main.py "e+ e- collision at 250 GeV, produce Higgs, 100k events, full sim"
```

### With vLLM / LM Studio (OpenAI-compat)
```bash
python main.py --backend openai --base-url http://localhost:8000/v1 "p p > h at LHC"
```

### Write files to disk
```bash
python main.py "p p > w+ w-" --out-dir ./my_run
# → ./my_run/proc_card.dat
# → ./my_run/run_card.dat
# → ./my_run/launch_my_process.mg5

# Then run MadGraph:
mg5_aMC < my_run/proc_card.dat
mg5_aMC < my_run/launch_my_process.mg5
```

---

## Supported Processes (examples)

| Natural language | Generated syntax |
|---|---|
| `p p > e- e+` | `generate p p > e- e+` |
| `p p > t t~ at 14 TeV` | `generate p p > t t~` + 7000 GeV beams |
| `gg > h (Higgs via HEFT)` | `import model heft` + `generate p p > h` |
| `p p > neutralino pair (MSSM)` | `import model MSSM_SLHA2` + `generate p p > n1 n1` |
| `e+ e- > h at 250 GeV` | `generate e- e+ > h` + 125 GeV beams + `lpp1=11` |
| `p p > w+ j` | `generate p p > w+ j` |

---

## Extending the Tree

### Add a new model
Edit `core/tree_builder.py`:
```python
MODELS["my_bsm"] = "MyBSM_UFO"
```

### Add a new particle alias
```python
PARTICLE_ALIASES["gravitino"] = "gr"
```

### Add a new run_card parameter
Add to `ProcessParams` dataclass and `build_run_card()`.

---

## Project Structure

```
madgraph_gen/
├── main.py               ← CLI entry point
├── core/
│   ├── tree_builder.py   ← decision tree + file generators (NO LLM)
│   └── extractor.py      ← LLM prompt + JSON → ProcessParams
└── tests.py              ← 7 test cases covering common processes
```

---

## LLM Prompt Strategy

The system prompt in `extractor.py` is engineered for small models:

1. **Single output type**: only JSON, never MadGraph syntax
2. **Temperature = 0**: deterministic extraction  
3. **Three worked examples**: few-shot in the system prompt
4. **Exact token table**: lists every valid particle name so the model doesn't invent tokens
5. **Strict field list**: 10 well-defined fields with types and defaults

This makes even a 7B/8B model reliable because classification + extraction is much easier than syntax generation.
