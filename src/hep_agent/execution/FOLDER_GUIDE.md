# Execution — Practical Guide

This folder runs already-built and already-validated collider-tool
artifacts.

The execution layer does not:

- interpret physics;
- call an LLM;
- change generated commands;
- repair semantic errors.

The current runner is:

    madgraph_runner.py

It:

- writes the validated MG5 commands to commands.mg5;
- launches MadGraph without shell=True;
- applies a timeout;
- saves stdout.log and stderr.log;
- records the return code and wall time;
- distinguishes configuration, startup, timeout, and nonzero-exit
  failures.

The tests use fake executables. They do not run real MadGraph.

Run all tests with:

    cd HEPLocalAgent
    PYTHONPATH=src python -m unittest discover -s tests -v

Real MadGraph execution will be tested only after its executable path
has been confirmed.

## Result parsing

The file:

    result_parser.py

extracts physics information from completed MadGraph output.

It currently records:

- cross section in pb;
- cross-section uncertainty in pb;
- generated event count;
- the primary unweighted LHE file;
- Pythia8 HepMC output when present;
- Delphes ROOT output when present;
- nonfatal warnings such as a missing LHAPDF Python interface.

A normal event-generation run succeeds only when the subprocess succeeds,
the physics summary is parsed, the parton-level LHE file exists, and every
requested later-stage artifact exists: HepMC for Pythia8 and ROOT for
Delphes. Missing requested artifacts are recorded explicitly in the run
record. This prevents a printed cross section from masking a failed requested
stage.
