# Three-way baseline comparison (Paper B)

Source: primary `evaluation/paper_b_end_to_end/results/20260815T110701Z`, extension `evaluation/paper_b_reviewer_extension/results/20260816T075420Z`, native `evaluation/paper_b_reviewer_extension/results/20260816T080835Z`.

Matched semantic units: **61** (20 requests x 4 models; infrastructure-unavailable units excluded).

| condition | pass | rate |
|---|---|---|
| A: native HEP commands | 2 | 3.3% |
| B: structured intent -> deterministic builder | 8 | 13.1% |
| C: full guarded HEPLocalAgent | 52 | 85.2% |

| transition | count |
|---|---|
| A fail -> B pass | 7 |
| B fail -> C pass | 44 |
| A fail -> C pass | 50 |
| A pass -> C fail | 0 |
| B pass -> C fail | 0 |
| A fail, B fail, C pass (rescued only by the full pipeline) | 43 |
| fail in all three | 9 |

## Limitations (stated explicitly)

- B $\rightarrow$ C is the guarded-pipeline improvement; it is NOT
  'repair lift' (0 model-repair calls in the primary experiment).
- The evaluation uses the existing automatic approval mechanism; human
  approval quality is not experimentally isolated.
- Matched pairs only; requests with infrastructure-unavailable rows are
  excluded from the semantic denominator and reported separately.
