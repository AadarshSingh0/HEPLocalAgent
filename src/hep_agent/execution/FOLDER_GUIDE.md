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

    cd ~/Benchmark/HEPLocalAgent
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
- nonfatal warnings such as a missing LHAPDF Python interface.

A successful subprocess and a successful physics-result parse are
recorded separately. This prevents a parser problem from being mistaken
for a MadGraph or model failure.
