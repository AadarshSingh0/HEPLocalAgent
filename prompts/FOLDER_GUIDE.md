# Prompts — Practical Guide

This folder contains instructions sent to local language models.

The first prompt is:

    planner_system.txt

It tells the planner to convert a natural-language collider request into
the structured WorkflowIntent schema.

The prompt deliberately forbids unrestricted MadGraph commands.

Prompt changes can affect agent results. Therefore, later evaluations
must record the prompt file hash.

To read the planner prompt:

    cd HEPLocalAgent
    cat prompts/planner_system.txt

## Repair prompt

The file:

    repair_system.txt

is used only after deterministic validation has rejected a structured
workflow.

The repair model receives:

- the original user request;
- the invalid structured workflow;
- exact validator error codes and messages.

It must return a complete corrected WorkflowIntent JSON object.
