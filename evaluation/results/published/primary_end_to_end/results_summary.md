# Paper B end-to-end results summary

Source rows: `evaluation/paper_b_end_to_end/results/20260815T110701Z/rows.csv` (60 rows)

Semantic measurements: 47; infrastructure_unavailable: 13; legacy infrastructure_invalid: 0.

Operational: 43/60 units completed on first attempt (0.7167); 44 infrastructure attempt(s), 44 timeout(s).

## llama3.3:70b

| Quantity | Value (normalized, PRIMARY) | Value (raw, SECONDARY) |
|---|---|---|
| N | 7 | 7 |
| P1 planner-only strict pass | 3/7 (42.9% [15.8%, 75.0%]) | 1/7 (14.3% [2.6%, 51.3%]) |
| P2 full-agent success at gate | 7/7 (100.0% [64.6%, 100.0%]) | 3/7 (42.9% [15.8%, 75.0%]) |
| P3 guarded-agent lift [pp] | 57.14 | 28.57 |
| P3 transitions FF/FP/PP/PF | 0/4/3/0 | 4/2/1/0 |
| P4 recovery | 4/4 (100.0% [51.0%, 100.0%]) | 2/6 (33.3% [9.7%, 70.0%]) |
| P5 gate leakage (invalid-ready/ready) | 0/7 (0.0% [0.0%, 35.4%]) | 4/7 (57.1% [25.1%, 84.2%]) |
| P6 false rejection (of initial-pass) | 0/3 (0.0% [0.0%, 56.1%]) | 0/1 (0.0% [0.0%, 79.3%]) |
| P6 valid-request non-ready | 0/7 (0.0% [0.0%, 35.4%]) | 0/7 (0.0% [0.0%, 35.4%]) |
| P7 requests with >=1 repair | 0/7 (0.0% [0.0%, 35.4%]) | 0/7 (0.0% [0.0%, 35.4%]) |
| P7 mean repair attempts | 0.0 | 0.0 |
| P7 success after repair | - | - |
| P7 fallback used | 0 | 0 |
| P8 mean initial score | 0.659 | 0.549 |
| P8 mean full score | 0.845 | 0.713 |
| Initial physics content | 3/7 (42.9% [15.8%, 75.0%]) | - |
| Full physics content | 6/7 (85.7% [48.7%, 97.4%]) | - |

## qwen2.5-coder:7b

| Quantity | Value (normalized, PRIMARY) | Value (raw, SECONDARY) |
|---|---|---|
| N | 20 | 20 |
| P1 planner-only strict pass | 0/20 (0.0% [0.0%, 16.1%]) | 0/20 (0.0% [0.0%, 16.1%]) |
| P2 full-agent success at gate | 16/20 (80.0% [58.4%, 91.9%]) | 6/20 (30.0% [14.5%, 51.9%]) |
| P3 guarded-agent lift [pp] | 80.0 | 30.0 |
| P3 transitions FF/FP/PP/PF | 4/16/0/0 | 14/6/0/0 |
| P4 recovery | 16/20 (80.0% [58.4%, 91.9%]) | 6/20 (30.0% [14.5%, 51.9%]) |
| P5 gate leakage (invalid-ready/ready) | 4/20 (20.0% [8.1%, 41.6%]) | 14/20 (70.0% [48.1%, 85.5%]) |
| P6 false rejection (of initial-pass) | - | - |
| P6 valid-request non-ready | 0/20 (0.0% [0.0%, 16.1%]) | 0/20 (0.0% [0.0%, 16.1%]) |
| P7 requests with >=1 repair | 0/20 (0.0% [0.0%, 16.1%]) | 0/20 (0.0% [0.0%, 16.1%]) |
| P7 mean repair attempts | 0.0 | 0.0 |
| P7 success after repair | - | - |
| P7 fallback used | 0 | 0 |
| P8 mean initial score | 0.57 | 0.502 |
| P8 mean full score | 0.83 | 0.71 |
| Initial physics content | 0/20 (0.0% [0.0%, 16.1%]) | - |
| Full physics content | 15/20 (75.0% [53.1%, 88.8%]) | - |

## qwen3-coder-next:Q4_K_M

| Quantity | Value (normalized, PRIMARY) | Value (raw, SECONDARY) |
|---|---|---|
| N | 20 | 20 |
| P1 planner-only strict pass | 8/20 (40.0% [21.9%, 61.3%]) | 6/20 (30.0% [14.5%, 51.9%]) |
| P2 full-agent success at gate | 20/20 (100.0% [83.9%, 100.0%]) | 10/20 (50.0% [29.9%, 70.1%]) |
| P3 guarded-agent lift [pp] | 60.0 | 20.0 |
| P3 transitions FF/FP/PP/PF | 0/12/8/0 | 10/4/6/0 |
| P4 recovery | 12/12 (100.0% [75.8%, 100.0%]) | 4/14 (28.6% [11.7%, 54.6%]) |
| P5 gate leakage (invalid-ready/ready) | 0/19 (0.0% [0.0%, 16.8%]) | 10/19 (52.6% [31.7%, 72.7%]) |
| P6 false rejection (of initial-pass) | 1/8 (12.5% [2.2%, 47.1%]) | 1/6 (16.7% [3.0%, 56.4%]) |
| P6 valid-request non-ready | 1/20 (5.0% [0.9%, 23.6%]) | 1/20 (5.0% [0.9%, 23.6%]) |
| P7 requests with >=1 repair | 0/20 (0.0% [0.0%, 16.1%]) | 0/20 (0.0% [0.0%, 16.1%]) |
| P7 mean repair attempts | 0.0 | 0.0 |
| P7 success after repair | - | - |
| P7 fallback used | 0 | 0 |
| P8 mean initial score | 0.702 | 0.628 |
| P8 mean full score | 0.854 | 0.75 |
| Initial physics content | 7/20 (35.0% [18.1%, 56.7%]) | - |
| Full physics content | 15/20 (75.0% [53.1%, 88.8%]) | - |

## Overall (all models, semantic measurements only)

| Quantity | Value (normalized, PRIMARY) | Value (raw, SECONDARY) |
|---|---|---|
| N | 47 | 47 |
| P1 planner-only strict pass | 11/47 (23.4% [13.6%, 37.2%]) | 7/47 (14.9% [7.4%, 27.7%]) |
| P2 full-agent success at gate | 43/47 (91.5% [80.1%, 96.6%]) | 19/47 (40.4% [27.6%, 54.7%]) |
| P3 guarded-agent lift [pp] | 68.09 | 25.54 |
| P3 transitions FF/FP/PP/PF | 4/32/11/0 | 28/12/7/0 |
| P4 recovery | 32/36 (88.9% [74.7%, 95.6%]) | 12/40 (30.0% [18.1%, 45.4%]) |
| P5 gate leakage (invalid-ready/ready) | 4/46 (8.7% [3.4%, 20.3%]) | 28/46 (60.9% [46.5%, 73.6%]) |
| P6 false rejection (of initial-pass) | 1/11 (9.1% [1.6%, 37.7%]) | 1/7 (14.3% [2.6%, 51.3%]) |
| P6 valid-request non-ready | 1/47 (2.1% [0.4%, 11.1%]) | 1/47 (2.1% [0.4%, 11.1%]) |
| P7 requests with >=1 repair | 0/47 (0.0% [0.0%, 7.6%]) | 0/47 (0.0% [0.0%, 7.6%]) |
| P7 mean repair attempts | 0.0 | 0.0 |
| P7 success after repair | - | - |
| P7 fallback used | 0 | 0 |
| P8 mean initial score | 0.639 | 0.562 |
| P8 mean full score | 0.842 | 0.727 |
| Initial physics content | 10/47 (21.3% [12.0%, 34.9%]) | - |
| Full physics content | 36/47 (76.6% [62.8%, 86.4%]) | - |

## Per-family (overall, PRIMARY normalized)

| Family | N | Initial pass | Full success | Lift [pp] |
|---|---|---|---|---|
| drell_yan | 12 | 1/12 (8.3% [1.5%, 35.4%]) | 12/12 (100.0% [75.8%, 100.0%]) | 91.67 |
| top_pair | 13 | 3/13 (23.1% [8.2%, 50.3%]) | 13/13 (100.0% [77.2%, 100.0%]) | 76.92 |
| higgs_jet | 11 | 6/11 (54.5% [28.0%, 78.7%]) | 11/11 (100.0% [74.1%, 100.0%]) | 45.45 |
| ttbar_workflow | 11 | 1/11 (9.1% [1.6%, 37.7%]) | 7/11 (63.6% [35.4%, 84.8%]) | 54.55 |
