# HEPLocalAgent curated evaluation-results review package

This package contains publication copies of four authoritative Paper B evaluation suites recovered from preserved HEPLocalAgent v0.1.1 evidence. No model was rerun. The trial rows and aggregates derive from existing frozen runs at source commit `feeccfb10fb424beaac3c6da4530128fc9cff585`.

The suites are:

- [Primary end-to-end](primary_end_to_end/): 60 planned model-request units, 47 semantic measurements and 13 infrastructure-unavailable units.
- [Reviewer extension](reviewer_extension/): 160 planned units, 158 semantic measurements and 2 infrastructure-unavailable units.
- [Native baseline](native_baseline/): 80 planned units, 63 semantic measurements and 17 infrastructure-unavailable units.
- [Capability supplement](capability_supplement/): 6 semantic units covering energy scans, MadAnalysis, and user-UFO workflows.

`source_inventory.csv` records accepted and rejected candidates. `publication_manifest.csv` maps each public file to its source hash and any privacy-only transformation. `CHECKSUMS.sha256` verifies this package. Machine-specific absolute paths and private Ollama hosts are replaced only in publication copies; scientific values and result classifications are unchanged.

The five general-purpose runners checked into `evaluation/` had no preserved aggregate output under the bounded search roots. These published results instead come from the dedicated, frozen Paper B end-to-end and reviewer-extension harnesses preserved in the evidence bundle.
