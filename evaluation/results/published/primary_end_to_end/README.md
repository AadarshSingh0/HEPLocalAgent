# Primary end-to-end evaluation

Frozen Paper B primary run `20260815T110701Z`: 20 requests across three local models, one planned unit per model-request pair (60 total). `rows.csv` is the authoritative deduplicated matrix. `rows.jsonl` is the append-only audit log and contains 69 records because nine superseded resume records are retained. Aggregates use only `rows.csv`; infrastructure-unavailable units are excluded from semantic denominators.
