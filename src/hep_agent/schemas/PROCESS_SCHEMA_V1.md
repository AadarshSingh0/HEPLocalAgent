# Process Schema Version 1

This document defines how the agent should represent collider processes
internally.

It is a design document only. No Python code uses it yet.

## Main idea

The schema must separate:

1. the physical collider beams;
2. the incoming particles used in the hard process;
3. produced particles;
4. decay chains;
5. MadGraph restrictions and coupling orders.

This allows the same structure to describe both simple and complicated
collider workflows.

## 1. Collider beams

The collider section describes the real accelerator beams.

Example:

    collider type: hadron
    beam 1: proton
    beam 2: proton
    total centre-of-mass energy: 13000 GeV

Another example:

    collider type: lepton
    beam 1: electron
    beam 2: positron
    total centre-of-mass energy: 250 GeV

The collider beams are not always the same as the particles written in
the hard process.

For example:

    collider beams: proton and proton
    hard process: q q~ > mu+ mu-

The quarks are partons inside the proton beams.

## 2. Physics model

The model section stores:

    model name
    model source
    model path when needed
    valid particles
    available parameters

Examples:

    sm
    loop_sm
    MSSM
    user UFO model

For an installed UFO model, the agent should inspect the model instead
of guessing which particles exist.

## 3. Process list

A workflow may contain one or more processes.

Each process contains:

    process identifier
    incoming particles
    produced final-state particles
    coupling-order restrictions
    required intermediate particles
    excluded particles
    optional decay chains

A list is used because MadGraph workflows may contain a main process and
one or more additional processes.

## 4. Particle entries

Each produced particle should have:

    a unique branch identifier
    a particle name
    an optional decay
    an optional label for display

Unique branch identifiers are needed when two identical particles decay
differently.

Example:

    branch: z1
    particle: z
    decay: e+ e-

    branch: z2
    particle: z
    decay: mu+ mu-

The branch identifiers are internal. They are not written directly into
MadGraph syntax.

## 5. Recursive decays

A particle decay contains:

    parent branch
    daughter particles

Each daughter particle may itself contain another decay.

Example:

    hard process:
        p p > t t~

    branch top1:
        t > w+ b

    branch wplus1:
        w+ > mu+ vm

    branch antitop1:
        t~ > w- b~

    branch wminus1:
        w- > j j

This recursive structure can represent long cascade decays without
allowing the LLM to write unrestricted parentheses or commas.

## 6. Inclusive particle groups

The schema may use recognised particle groups such as:

    p
    j
    q
    q~
    l+
    l-
    vl
    vl~

These groups must be resolved by the deterministic system.

They should not depend only on the LLM's memory.

For UFO models, the agent may create model-specific particle groups when
their definitions are known.

## 7. Intermediate-particle requirements

Some requests specify an intermediate resonance.

Example:

    p p > zprime > mu+ mu-

The schema should store:

    required intermediate particle: zprime

The deterministic builder then decides the correct MadGraph syntax.

The LLM should not construct the full process string itself.

## 8. Excluded particles

A request may exclude particles from diagrams.

Example:

    p p > e+ e- excluding photon diagrams

The schema should store the excluded particles as a list.

The deterministic builder will translate this into the appropriate tool
syntax.

## 9. Coupling orders

Coupling restrictions should be represented as structured values.

Example:

    QCD: 2
    QED: 2

Possible comparison types may include:

    exact
    maximum
    minimum

The builder should create the tool-specific syntax.

## 10. Field provenance

The agent should record where important values came from.

Possible sources are:

    user
    validated_default
    model_inference
    repair
    fallback_review

Example:

    collider.energy_gev: user
    run.nevents: validated_default
    process.model: user

A model inference that changes the physical meaning of the request must
not be silently executed.

## 11. Example structured workflow

A proton-proton top-pair process with nested decays could be represented
conceptually as:

    collider:
        beams: p, p
        total energy: 13000 GeV

    model:
        name: sm

    process:
        incoming: p, p
        final:
            - branch top1, particle t
            - branch antitop1, particle t~

    decays:
        top1:
            t > w+ b

        wplus1:
            w+ > mu+ vm

        antitop1:
            t~ > w- b~

        wminus1:
            w- > j j

    run:
        events: 10000

    pipeline:
        madgraph: enabled
        pythia8: enabled
        delphes: disabled

## Design boundary

The schema should describe physics intent.

It should not contain unrestricted MadGraph command strings.

If a requested feature cannot yet be represented safely, the workflow
should report that the feature is unsupported rather than bypassing the
schema.
