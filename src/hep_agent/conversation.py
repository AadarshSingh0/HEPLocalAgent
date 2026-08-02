"""Conversational routing for the local HEP agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from hep_agent.models.ollama import (
    OllamaClient,
)


class ConversationRoute(str, Enum):
    """Top-level route for one user message."""

    CHAT = "chat"
    WORKFLOW = "workflow"


@dataclass(frozen=True)
class ChatAnswer:
    """One conversational response."""

    content: str
    model: str | None
    duration_seconds: float | None


_GREETING_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        hi
        | hello
        | hey
        | greetings
        | good\ morning
        | good\ afternoon
        | good\ evening
        | thanks
        | thank\ you
    )
    [\s!.?]*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CAPABILITY_PATTERN = re.compile(
    r"""
    \b
    (?:
        what\ can\ you\ do
        | what\ do\ you\ do
        | how\ can\ you\ help
        | show\ me\ your\ capabilities
        | what\ is\ this\ agent
        | help
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_EXPLANATORY_PREFIX_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        what
        | why
        | explain
        | tell\ me
        | define
        | how\ does
        | how\ do\ i
        | how\ can\ i
        | is
        | are
        | does
        | do
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_WORKFLOW_ACTION_PATTERN = re.compile(
    r"""
    \b
    (?:
        simulate
        | generate
        | execute
        | run
        | prepare
        | create
        | build
        | shower
        | reconstruct
        | scan
        | produce
        | calculate
        | compute
        | plot
        | analyze
        | analyse
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SOFTWARE_PATTERN = re.compile(
    r"""
    \b
    (?:
        madgraph
        | mg5
        | mg5_amc
        | pythia
        | pythia8
        | delphes
        | madanalysis
        | madanalysis5
        | ma5
        | lhe
        | hepmc
        | root\ file
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_WORKFLOW_OBJECT_PATTERN = re.compile(
    r"""
    \b
    (?:
        events?
        | collisions?
        | cross[\s-]?section
        | run[\s-]?card
        | param[\s-]?card
        | cutflow
        | histogram
        | detector\ simulation
        | parton[\s-]?level
        | energy\ scan
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PROCESS_PATTERN = re.compile(
    r"""
    (?:
        \bproton[\s-]?proton\b
        | \bpp\b
        | \bp\s+p\b
        | \be\+\s*e-\b
        | \bmu\+\s*mu-\b
        | \b[A-Za-z0-9+~_-]+\s*(?:>|->)\s*
          [A-Za-z0-9+~_\-\s]+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_NUMERICAL_RUN_PATTERN = re.compile(
    r"""
    (?:
        \b\d+(?:\.\d+)?\s*(?:TeV|GeV)\b
        | \b\d+\s+events?\b
        | \bnevents?\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def classify_user_message(
    user_message: str,
) -> ConversationRoute:
    """Route chat separately from executable workflow requests."""

    text = " ".join(
        user_message.strip().split()
    )

    if not text:
        return ConversationRoute.CHAT

    if _GREETING_PATTERN.search(text):
        return ConversationRoute.CHAT

    if _CAPABILITY_PATTERN.search(text):
        return ConversationRoute.CHAT

    action = bool(
        _WORKFLOW_ACTION_PATTERN.search(text)
    )
    software = bool(
        _SOFTWARE_PATTERN.search(text)
    )
    workflow_object = bool(
        _WORKFLOW_OBJECT_PATTERN.search(text)
    )
    process = bool(
        _PROCESS_PATTERN.search(text)
    )
    numerical_run = bool(
        _NUMERICAL_RUN_PATTERN.search(text)
    )
    explanatory = bool(
        _EXPLANATORY_PREFIX_PATTERN.search(text)
    )

    # Questions asking how or why something works remain ordinary
    # conversation, even when they mention simulation software.
    if explanatory:
        return ConversationRoute.CHAT

    # Explicit commands involving HEP software are workflows.
    if action and software:
        return ConversationRoute.WORKFLOW

    # Simulation-style action plus a process or run specification.
    if action and (
        process
        or workflow_object
        or numerical_run
    ):
        return ConversationRoute.WORKFLOW

    # Compact process requests often omit the verb:
    # "pp > e+ e- at 13 TeV, 100 events".
    if process and numerical_run:
        return ConversationRoute.WORKFLOW

    return ConversationRoute.CHAT


def _canned_response(
    user_message: str,
) -> str | None:
    """Return instant responses for obvious conversational messages."""

    text = " ".join(
        user_message.strip().split()
    )

    if _GREETING_PATTERN.search(text):
        return (
            "Hello! I can answer particle-physics questions and "
            "prepare validated MadGraph, Pythia8, Delphes, and "
            "MadAnalysis workflows. Describe a concrete process "
            "when you want to run a simulation."
        )

    if _CAPABILITY_PATTERN.search(text):
        return (
            "I can discuss particle physics normally, or turn a "
            "concrete collider request into a structured workflow. "
            "For a run, specify the process, collider energy, event "
            "count, and any Pythia8, Delphes, or MadAnalysis steps."
        )

    return None


def answer_chat(
    user_message: str,
    *,
    client: OllamaClient,
    model: str = "llama3:8b",
    history: Iterable[
        dict[str, str]
    ] = (),
    timeout_seconds: int = 180,
) -> ChatAnswer:
    """Answer without invoking the workflow planner."""

    canned = _canned_response(
        user_message
    )

    if canned is not None:
        return ChatAnswer(
            content=canned,
            model=None,
            duration_seconds=0.0,
        )

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are the conversational front end of a local "
                "high-energy-physics workflow agent. Answer ordinary "
                "HEP and particle-physics questions clearly and "
                "concisely. Explain what the agent can do when asked. "
                "Do not claim that a simulation was run. Do not invent "
                "cross sections, files, validation results, or execution "
                "results. When the user wants an actual simulation, "
                "tell them to provide a concrete process, collider "
                "energy, event count, and requested pipeline stages."
            ),
        }
    ]

    cleaned_history = [
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in history
        if item.get("role") in {
            "user",
            "assistant",
        }
        and isinstance(
            item.get("content"),
            str,
        )
    ]

    messages.extend(
        cleaned_history[-8:]
    )

    if (
        not messages
        or messages[-1].get("content")
        != user_message
    ):
        messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

    response = client.chat(
        model=model,
        messages=messages,
        response_schema=None,
        temperature=0.2,
        num_predict=600,
        timeout_seconds=timeout_seconds,
    )

    content = response.content.strip()

    if not content:
        content = (
            "I could not produce a conversational response. "
            "Please rephrase the question."
        )

    return ChatAnswer(
        content=content,
        model=response.model,
        duration_seconds=(
            response.total_duration_seconds
        ),
    )
