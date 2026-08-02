# Tests — Practical Guide

This folder checks that new agent components behave as expected.

The tests should be run after changing source code.

The first tests check the collider-workflow schema. They confirm that it
can represent:

- simple proton collisions;
- partonic processes inside proton beams;
- asymmetric electron and positron beams;
- nested top and W decay chains;
- rejection of duplicate internal branch identifiers.

Run the current tests with:

    cd ~/Benchmark/HEPLocalAgent
    PYTHONPATH=src python -m unittest discover -s tests -v

A successful run ends with:

    OK

If a test fails, do not continue building later components until the
failure is understood.
