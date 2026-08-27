# MODEL_SELECTION — Reviewer-Extension Model Set (frozen 2026-08-16)

**Status: FROZEN before any reviewer-extension result is observed.**

## Rule (objective, pre-declared)

For each of the two required parameter bands:

- **Band M** (≈10–16B total parameters)
- **Band L** (≈17–35B total parameters)

select a model satisfying **ALL** of:

1. already installed on the current friend's remote Ollama server (verified via `/api/tags`);
2. already present in the frozen HEPToolBench evaluated model set
   (`HEPToolBench/local_llm_benchmark/results/stability_httpclean_modern_final_10models_1550rows.csv`);
3. publicly disclosed parameter count falls in the intended band;
4. no known infrastructure incompatibility with the current serving setup;
5. exact label recorded.

**Within each band:** list all eligible candidates with HEPToolBench main mean
score, pass count, and recorded latency; select the **highest mean-scoring**
candidate whose recorded latency is reasonably compatible with the overnight
experiment:

- Band M: prefer warm median ≤ 30 s where latency exists;
- Band L: prefer warm median ≤ 60 s where latency exists;
- if no candidate satisfies that, relax to ≤ 120 s.

Latency metadata in the frozen stability CSV: `wall_time_seconds` per row
(warm, per-call). Median used as the latency estimate.

**Forbidden:** using the new containment/extension results to choose models;
adding a fifth model; substituting tags; pulling models.

## Candidate data (from the frozen HEPToolBench stability CSV, n=155 rows/model)

| Band | Model label | Params | Q | HEPT mean score | pass | strict | wall median (s) | wall mean (s) | selected? |
|---|---|---|---|---|---|---|---|---|---|
| M | `qwen2.5-coder:14b` | 14.8B | Q4_K_M | **0.746** | 58 | 2 | **27.8** | 32.3 | **YES** |
| M | `phi4:14b` | 14.7B | (Q4_K_M per /api/show) | 0.728 | 57 | 0 | 26.8 | 31.2 | no |
| L | `qwen3.5:27b` | 27.8B | Q4_K_M | **0.795** | 75 | 60 | **73.4** | 79.1 | **YES** |
| L | `gemma4:26b` | 26B | (Q4_K_M) | 0.746 | 87 | 54 | 235.2 | 249.9 | no (latency incompatible: median 235 s > 120 s) |
| L | `granite4:32b-a9b-h` | 32B (9B active) | (Q4_K_M) | 0.713 | 44 | 28 | 27.0 | 32.4 | no (lower mean than qwen3.5:27b) |

## Selected four-model set (frozen)

| Role | Model label | Band | Params | Quantization | Rationale |
|---|---|---|---|---|---|
| fixed (primary) | `qwen2.5-coder:7b` | 7B | 7.6B | Q4_K_M | original frozen set |
| fixed (primary) | `qwen3-coder-next:Q4_K_M` | 30B-class | ~30B | Q4_K_M | original frozen set |
| **new M** | `qwen2.5-coder:14b` | 10–16B | 14.8B | Q4_K_M | highest HEPT mean (0.746) in band with median 27.8 s ≤ 30 s |
| **new L** | `qwen3.5:27b` | 17–35B | 27.8B | Q4_K_M | highest HEPT mean (0.795) in band; median 73.4 s ≤ relaxed 120 s |

`llama3.3:70b` is **not** reused in the extension: its frozen primary result
(13/20 infrastructure_unavailable under the 300 s timeout) is itself the
reported operational finding. That limitation is reported; it is not masked
by substitution.

## Remote verification (2026-08-16)

- Host: `http://PRIVATE_OLLAMA_HOST:11434` (per PAUSE_STATE.md; re-verified via `/api/tags`).
- `qwen2.5-coder:14b`: present — `general.parameter_count = 14,770,033,664`, `general.families = qwen2`, quantization `Q4_K_M`.
- `qwen3.5:27b`: present — `general.parameter_count = 27,781,427,952`, family `qwen35`, quantization `Q4_K_M`.
- Both labels recorded exactly as above; no substitution; no pull performed.

## Generation settings

Same frozen settings as the primary evaluation (inherited from
`evaluation/paper_b_end_to_end/profiles.json` style): structured planner
`temperature=0.0`, `num_predict=4096`; semantic planner `temperature=0.0`,
`num_predict=300`; repair via profile timeout (180 s); planner timeout 300 s
per the frozen infrastructure policy. New extension profiles added in
`profiles.json` (additive; the frozen primary profiles file is untouched).

## Operational smoke note

An operational connectivity/timeout smoke (does the model return within the
300 s frozen timeout for the extension planner calls) is permitted and is not
scored scientifically. If `qwen3.5:27b` repeatedly cannot return within 300 s
on the extension's own planner prompts, the pre-declared fallback is the next
eligible Band-L candidate by the same rule (`gemma4:26b` is latency-ineligible
per the 120 s relaxation, so the next eligible candidate would be
`granite4:32b-a9b-h`), and this document is updated BEFORE any extension
scoring with the recorded reason.

## FALLBACK APPLIED (2026-08-16, BEFORE any extension scoring)

**`qwen3.5:27b` was selected by the frozen rule, then rejected operationally
and replaced by `granite4:32b-a9b-h` per the pre-declared fallback rule.**

Recorded evidence (operational smoke, not scored scientifically):

- `qwen3.5:27b` on `http://PRIVATE_OLLAMA_HOST:11434` uses a custom `RENDERER
  qwen3.5` / `PARSER qwen3.5` template (see `/api/show` modelfile).
- A 256-token free-text request returned after 115 s with
  `message.content == ""` and all generated text in `message.thinking`
  (`done_reason: length`) — the model is a thinking-renderer variant and does
  not populate `content` on this server.
- A 1024-token free-text request exceeded the frozen 300 s planner timeout
  (`OllamaClientError: The Ollama request timed out.`).
- A 2048-token free-text request did not return within 400 s (curl timeout).
- A JSON-format request (structured-planner path) did not return within
  200 s.

Conclusion: `qwen3.5:27b` cannot produce a usable planner/native response
within the frozen 300 s timeout on this serving setup, and its empty
`content` field would break the agent harness which reads `content`. This
violates the frozen selection criterion "no known infrastructure
incompatibility with the current serving setup" (rule 4) and triggers the
pre-declared fallback: `granite4:32b-a9b-h` (Band L, 32B/9B-active MoE,
Q4_K_M, HEPToolBench mean 0.713, warm median 27.0 s).

**Fallback verified operationally** (smoke, not scored): `granite4:32b-a9b-h`
returned a real MadGraph Drell-Yan process card in 52.2 s (742 tokens,
1024-token budget) — well within the frozen 300 s timeout.

**Final frozen four-model set (updated):**

| Role | Model label | Band | Params | Quantization |
|---|---|---|---|---|
| fixed | `qwen2.5-coder:7b` | 7B | 7.6B | Q4_K_M |
| fixed | `qwen3-coder-next:Q4_K_M` | 30B-class | ~30B | Q4_K_M |
| new M | `qwen2.5-coder:14b` | 10–16B | 14.8B | Q4_K_M |
| new L | `granite4:32b-a9b-h` | 17–35B | 32B (9B active) | Q4_K_M |

This update was made BEFORE any extension or native-baseline scoring. No
observed semantic result caused any model/design change.
