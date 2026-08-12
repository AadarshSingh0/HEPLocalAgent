# Models — Practical Guide

This folder contains communication with local language models and the
configuration used to choose those models.

The Ollama client uses the native endpoint:

    /api/chat

The host is taken from the OLLAMA_HOST environment variable when one is
available.

For an Ollama server running on another computer, replace the illustrative
hostname and set:

    export OLLAMA_HOST=http://OTHER-COMPUTER:11434

The model profiles are stored in:

    configs/agent_profiles.json

The three initial profiles are:

- legacy_llama3
- qwen_primary
- qwen_cascade

The tests do not contact the real Ollama server. They use a simulated
response.

Run all tests with:

    cd HEPLocalAgent
    PYTHONPATH=src python -m unittest discover -s tests -v

Important:

An Ollama connection failure or timeout is an infrastructure failure.
It must not be counted as a physics or model-semantic failure.
