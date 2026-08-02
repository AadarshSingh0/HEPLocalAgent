# Scans — Practical Guide

This folder implements deterministic multi-run parameter scans.

The first supported scan axis is total collider centre-of-mass energy.

A scan contains:

- one already validated base `WorkflowIntent`;
- two or more collider-energy points;
- the same requested event count at each point;
- a unique deterministic seed for every point;
- a unique output directory for every point;
- a continue-or-stop policy for later execution.

## Safety limits

The initial implementation allows:

- at most 20 energy points;
- at most 200,000 total requested events.

These limits prevent an ambiguous natural-language request from
silently launching an unexpectedly expensive computation.

## Expansion

`expand_energy_scan()` produces ordinary independent
`WorkflowIntent` objects.

This is important because each point can reuse the existing:

- deterministic MG5 builder;
- validators;
- execution runner;
- result parser;
- MadAnalysis stage;
- JSON provenance machinery.

The scan planner does not generate arbitrary MG5 scripts and does not
execute any external software.

## Natural-language range representation

A planner may represent a request such as:

    Scan from 1 TeV to 5 TeV in steps of 500 GeV.

using an `EnergyScanRequest` containing:

- `base_workflow`;
- `energy_range.start`;
- `energy_range.stop`;
- `energy_range.step`;
- `energy_range.include_stop`;
- `continue_on_failure`.

Every numerical energy carries its own unit. This permits mixed-unit
requests such as TeV endpoints with a GeV step.

The LLM does not enumerate the grid. `generate_energy_grid()` converts
all values to GeV and generates the points deterministically using
decimal arithmetic.

Inclusive endpoints must be reached by an integer number of steps.
The system rejects an irregular final interval rather than silently
changing the requested spacing.

## Deterministic natural-language range extraction

`text_parser.py` recognizes explicit regular scan expressions such as:

- `from 1 TeV to 5 TeV in steps of 500 GeV`;
- `from 1 TeV to 5 TeV in 500 GeV steps`;
- `from 1 TeV to 5 TeV every 500 GeV`;
- `between 1 TeV and 5 TeV in increments of 500 GeV`;
- `at a distance of 500 GeV`.

The parser extracts only explicitly stated numerical information.
It does not guess omitted units or step sizes.

After extracting the range, it rewrites the request as an ordinary
single-energy request using the starting energy. The existing planner
can therefore construct the base collider workflow without having to
represent several energies inside one `WorkflowIntent`.

Requests containing scan wording but missing a start, stop, step, or
unit are rejected instead of silently becoming a single-point run.

## Scan preparation

`preparation.py` connects natural-language scan extraction to the
existing validated workflow planner.

The preparation sequence is:

1. deterministically recognize and extract the energy range;
2. rewrite the request as one representative single-energy request;
3. call the existing structured planner exactly once;
4. apply the existing grounding corrections and validators;
5. expand the validated base workflow into all scan points;
6. assign unique deterministic random seeds and output names.

No external HEP software is executed during scan preparation.

Ordinary single-energy requests return `None` and continue through the
existing non-scan orchestration path.

A failed base-workflow preparation produces an unready
`PreparedEnergyScan`; it does not create partially valid scan points.

## Sequential execution and aggregation

`execution.py` controls scan-level execution after the complete scan
has received one approval.

The scan executor:

1. calls a supplied point executor sequentially;
2. never calls an LLM;
3. records successful, failed, and skipped points;
4. obeys the scan's continue-on-failure policy;
5. writes `scan_results.csv`;
6. writes `scan_summary.json`;
7. writes `cross_section_vs_energy.svg`;
8. reports the largest sampled cross section.

The maximum analysis warns when:

- the largest sampled value occurs at the first or final scan point;
- the two largest values are compatible within one combined standard
  uncertainty.

The SVG plot is generated using only the Python standard library so
scan aggregation does not introduce a plotting-library dependency.

The point executor is intentionally injected. The next adapter connects
it to the existing deterministic MadGraph runner, result parser,
MadAnalysis stage, and ordinary point-level run records.

## Existing-pipeline point adapter

`point_adapter.py` connects each deterministic scan point to the
existing single-run execution stack.

For every point it:

- builds the MG5 artifact deterministically;
- validates the exact artifact;
- creates a point-level run record;
- records zero point-level LLM calls;
- invokes the existing `execute_prepared()` function;
- therefore reuses MG5 execution, result parsing, MA5 execution,
  failure classification, and record updates;
- returns the parsed cross section to the scan aggregator.

The original LLM planning call belongs to scan preparation. It is not
repeated for each point.

Each point receives a deterministic run ID:

    <scan_id>_point_001
    <scan_id>_point_002
    ...

A failed point retains its point-level JSON record path for diagnosis.
