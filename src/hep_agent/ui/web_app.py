"""Streamlit research console for the local HEP agent."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from hep_agent.analysis import (
    MadAnalysisBuildError,
    compile_madanalysis_plan_commands,
    compile_madanalysis_quicklook_commands,
)

from hep_agent.doctor import (
    CheckStatus,
    DoctorReport,
    run_doctor,
)

from hep_agent.validation.workflow_request import (
    validate_workflow_request_minimum,
)
from hep_agent.conversation import (
    answer_chat,
)
from hep_agent.models import (
    OllamaClient,
    OllamaClientError,
    load_agent_profiles,
    profile_with_primary_model,
)
from hep_agent.orchestration import (
    EndToEndResult,
    PreparedEndToEnd,
    execute_prepared,
    prepare_end_to_end,
)
from hep_agent.builders.madgraph_workflow import (
    build_madgraph_workflow_artifact,
)
from hep_agent.scans import (
    EnergyScanExecutionSummary,
    ExistingPipelinePointExecutor,
    PreparedEnergyScan,
    ScanPointResult,
    execute_energy_scan,
    prepare_energy_scan,
)
from hep_agent.ui.cli import (
    load_json_object,
    resolve_project_path,
)
from hep_agent.ui.web_support import (
    archive_run_history,
    RunHistoryEntry,
    approval_countdown_seconds,
    detect_hep_tool_status,
    failure_validation_issues,
    load_run_history,
    ollama_model_options,
    read_text_tail,
    resolve_record_path,
    should_disable_request_input,
)
from hep_agent.selftest import (
    run_installation_selftest,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[3]
)

PROFILES_PATH = (
    PROJECT_ROOT
    / "configs"
    / "agent_profiles.json"
)

LOCAL_PATHS_PATH = (
    PROJECT_ROOT
    / "configs"
    / "local_paths.json"
)

RECORDS_DIRECTORY = (
    PROJECT_ROOT
    / "results"
    / "runs"
)

EXECUTIONS_DIRECTORY = (
    PROJECT_ROOT
    / "results"
    / "executions"
)

ANALYSES_DIRECTORY = (
    PROJECT_ROOT
    / "results"
    / "analyses"
)

SCAN_SUMMARIES_DIRECTORY = (
    PROJECT_ROOT
    / "results"
    / "scans"
)


STARTER_WORKFLOWS: tuple[
    tuple[str, str, str],
    ...,
] = (
    (
        "Drell-Yan",
        "A fast parton-level validation run.",
        (
            "At a 13 TeV proton-proton collider, generate "
            "p p > e+ e-. Generate 100 events. Do not use "
            "Pythia8, Delphes, or MadAnalysis."
        ),
    ),
    (
        "Top pair + detector",
        "Exercise showering and detector simulation.",
        (
            "Simulate top-pair production at 13 TeV in "
            "proton-proton collisions. Generate 100 events. "
            "Use Pythia8 and Delphes, but do not use "
            "MadAnalysis."
        ),
    ),
    (
        "Energy scan",
        "Prepare a deterministic multi-point scan.",
        (
            "Simulate p p to e+ e-. Do an energy scan from "
            "1 TeV to 2 TeV in steps of 500 GeV. Generate "
            "100 events per point. Do not use Pythia8, "
            "Delphes, or MadAnalysis."
        ),
    ),
)


def _initialize_state() -> None:
    defaults: dict[str, Any] = {
        "prepared_workflow": None,
        "final_result": None,
        "prepared_scan": None,
        "scan_result": None,
        "scan_run_id": None,
        "approval_run_id": None,
        "approval_deadline": None,
        "execution_in_progress": False,
        "request_draft_seed": "",
        "request_editor_version": 0,
        "doctor_report": None,
        "doctor_error": None,
        "agent_activity_events": [],
        "request_mode": "Chat",
        "reset_request_mode": False,
        "session_messages": [
            {
                "role": "assistant",
                "content": (
                    "Describe the collider workflow you want. "
                    "I will plan and validate it first, then show "
                    "the exact commands before any HEP software runs."
                ),
            }
        ],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _seed_starter_workflow(prompt: str) -> None:
    """Prefill, but never submit, a reviewed starter workflow."""

    st.session_state.request_mode = "Build workflow"
    st.session_state.request_draft_seed = prompt
    st.session_state.request_editor_version += 1


def _inject_style() -> None:
    st.markdown(
        """
<style>
    :root {
        --hep-canvas: #07111f;
        --hep-surface: rgba(15, 30, 46, 0.82);
        --hep-border: rgba(125, 211, 252, 0.18);
        --hep-muted: #9db0c5;
        --hep-radius: 0.9rem;
    }

    .stApp {
        background:
            radial-gradient(
                circle at 12% 5%,
                rgba(14, 165, 233, 0.13),
                transparent 26rem
            ),
            radial-gradient(
                circle at 90% 10%,
                rgba(139, 92, 246, 0.09),
                transparent 28rem
            ),
            var(--hep-canvas);
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 92rem;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    .hep-hero {
        position: relative;
        overflow: hidden;
        padding: 1.9rem 2rem 1.35rem;
        margin-bottom: 1.3rem;
        border: 1px solid var(--hep-border);
        border-radius: 1.1rem;
        background:
            linear-gradient(
                135deg,
                rgba(15, 23, 42, 0.98),
                rgba(15, 38, 61, 0.88)
            );
        box-shadow:
            0 22px 65px rgba(0, 0, 0, 0.24);
    }

    .hep-hero::after {
        position: absolute;
        width: 18rem;
        height: 18rem;
        right: -7rem;
        top: -10rem;
        border: 1px solid rgba(56, 189, 248, 0.15);
        border-radius: 50%;
        content: "";
        box-shadow:
            0 0 0 2.5rem rgba(56, 189, 248, 0.025),
            0 0 0 5rem rgba(167, 139, 250, 0.018);
        pointer-events: none;
    }

    .hep-eyebrow {
        color: #7dd3fc;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        margin-bottom: 0.55rem;
    }

    .hep-hero h1 {
        color: #f8fafc;
        font-size: 2.25rem;
        line-height: 1.05;
        margin: 0;
    }

    .hep-hero p {
        color: #b9c9dc;
        max-width: 52rem;
        margin: 0.8rem 0 0;
    }

    .hep-flow {
        position: relative;
        z-index: 1;
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.65rem;
        margin-top: 1.35rem;
        padding-top: 1rem;
        border-top: 1px solid rgba(148, 163, 184, 0.14);
    }

    .hep-flow-step {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        min-width: 0;
        padding: 0.55rem 0.65rem;
        border: 1px solid rgba(148, 163, 184, 0.13);
        border-radius: 0.7rem;
        background: rgba(2, 6, 23, 0.25);
    }

    .hep-flow-number {
        display: inline-grid;
        flex: 0 0 1.7rem;
        width: 1.7rem;
        height: 1.7rem;
        place-items: center;
        border: 1px solid rgba(56, 189, 248, 0.48);
        border-radius: 50%;
        color: #bae6fd;
        background: rgba(14, 165, 233, 0.13);
        font-size: 0.75rem;
        font-weight: 800;
    }

    .hep-flow-step strong {
        display: block;
        color: #f8fafc;
        font-size: 0.85rem;
        line-height: 1.15;
    }

    .hep-flow-step small {
        display: block;
        overflow: hidden;
        color: var(--hep-muted);
        font-size: 0.72rem;
        line-height: 1.2;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    [data-testid="stMetric"] {
        min-height: 6.15rem;
        background: var(--hep-surface);
        border: 1px solid rgba(148, 163, 184, 0.16);
        padding: 0.8rem;
        border-radius: var(--hep-radius);
        box-shadow: 0 8px 22px rgba(2, 6, 23, 0.12);
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(125, 211, 252, 0.12);
    }

    div[data-testid="stCodeBlock"] {
        border: 1px solid var(--hep-border);
        border-radius: 0.75rem;
    }

    div[data-testid="stAlert"] {
        border-radius: var(--hep-radius);
    }

    div[data-testid="stExpander"] details {
        overflow: hidden;
        border-color: rgba(148, 163, 184, 0.18);
        border-radius: var(--hep-radius);
        background: rgba(15, 30, 46, 0.42);
    }

    button:focus-visible,
    textarea:focus-visible,
    input:focus-visible,
    [role="tab"]:focus-visible {
        outline: 3px solid rgba(56, 189, 248, 0.42) !important;
        outline-offset: 2px;
    }

    @media (max-width: 800px) {
        [data-testid="stMainBlockContainer"] {
            padding-left: 1rem;
            padding-right: 1rem;
            padding-top: 1rem;
        }

        .hep-hero {
            padding: 1.35rem 1.15rem 1rem;
        }

        .hep-hero h1 {
            font-size: 1.8rem;
        }

        .hep-flow {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (max-width: 480px) {
        .hep-flow {
            grid-template-columns: 1fr;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            scroll-behavior: auto !important;
            transition-duration: 0.01ms !important;
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
        }
    }
</style>
""",
        unsafe_allow_html=True,
    )


def _value(
    payload: dict[str, Any],
    *names: str,
) -> Any:
    for name in names:
        value = payload.get(name)

        if value is not None:
            return value

    return None


def _resolve_payload_path(
    payload: dict[str, Any],
    *names: str,
) -> Path | None:
    return resolve_record_path(
        PROJECT_ROOT,
        _value(payload, *names),
    )


def _download_file(
    path: Path | None,
    *,
    label: str,
    key: str,
    mime: str,
) -> None:
    if path is None or not path.is_file():
        return

    st.download_button(
        label=label,
        data=path.read_bytes(),
        file_name=path.name,
        mime=mime,
        key=key,
        use_container_width=True,
    )


def _render_file_path(
    label: str,
    path: Path | None,
) -> None:
    st.markdown(f"**{label}**")

    if path is None:
        st.caption("Not produced")
        return

    st.code(str(path), language=None)


def _render_plots(
    payload: dict[str, Any],
    *,
    key_prefix: str,
) -> None:
    raw_plots = payload.get(
        "analysis_plot_files",
        [],
    )

    plots = [
        resolve_record_path(
            PROJECT_ROOT,
            value,
        )
        for value in raw_plots
    ]

    plots = [
        path
        for path in plots
        if path is not None and path.is_file()
    ]

    if not plots:
        return

    st.subheader("MadAnalysis quick-look plots")

    columns = st.columns(2)

    for index, plot in enumerate(plots):
        with columns[index % 2]:
            st.image(
                str(plot),
                caption=plot.stem,
                use_container_width=True,
            )


def _render_logs(
    payload: dict[str, Any],
) -> None:
    stdout_path = _resolve_payload_path(
        payload,
        "stdout_path",
    )
    stderr_path = _resolve_payload_path(
        payload,
        "stderr_path",
    )
    analysis_stdout = _resolve_payload_path(
        payload,
        "analysis_stdout_path",
    )
    analysis_stderr = _resolve_payload_path(
        payload,
        "analysis_stderr_path",
    )

    with st.expander(
        "Execution logs",
        expanded=False,
    ):
        log_tabs = st.tabs(
            [
                "MG5 stdout",
                "MG5 stderr",
                "MA5 stdout",
                "MA5 stderr",
            ]
        )

        paths = (
            stdout_path,
            stderr_path,
            analysis_stdout,
            analysis_stderr,
        )

        for tab, path in zip(
            log_tabs,
            paths,
            strict=True,
        ):
            with tab:
                tail = read_text_tail(path)

                if tail:
                    st.code(
                        tail,
                        language="text",
                    )
                else:
                    st.caption(
                        "No log content available."
                    )


def _render_record(
    payload: dict[str, Any],
    *,
    record_path: Path | None,
    key_prefix: str,
) -> None:
    status = str(
        payload.get("final_status")
        or payload.get("preexecution_status")
        or "prepared"
    )

    if status in {
        "execution_succeeded",
        "analysis_succeeded",
    }:
        st.success(
            f"Run status: {status}"
        )
    elif status in {
        "execution_failed",
        "analysis_failed",
        "preexecution_failed",
        "blocked",
    }:
        st.error(
            f"Run status: {status}"
        )
    elif status == "cancelled":
        st.warning("Run status: cancelled")
    else:
        st.info(f"Run status: {status}")

    cross_section = _value(
        payload,
        "cross_section_pb",
    )
    event_count = _value(
        payload,
        "generated_events",
        "generated_event_count",
        "event_count",
    )
    total_time = _value(
        payload,
        "end_to_end_wall_time_seconds",
    )
    llm_calls = _value(
        payload,
        "llm_call_count",
    )

    metrics = st.columns(4)

    metrics[0].metric(
        "Run ID",
        str(payload.get("run_id", "unknown")),
    )
    metrics[1].metric(
        "Cross section",
        (
            f"{cross_section:g} pb"
            if isinstance(
                cross_section,
                (int, float),
            )
            else "—"
        ),
    )
    metrics[2].metric(
        "Events",
        (
            str(event_count)
            if event_count is not None
            else "—"
        ),
    )
    metrics[3].metric(
        "Total time",
        (
            f"{total_time:.2f} s"
            if isinstance(
                total_time,
                (int, float),
            )
            else "—"
        ),
    )

    request = payload.get("user_request")

    if request:
        with st.chat_message("user"):
            st.write(request)

    workflow = payload.get("workflow")

    if isinstance(workflow, dict):
        with st.expander(
            "Structured workflow",
            expanded=False,
        ):
            st.json(workflow)

    st.subheader("Generated artifacts")

    artifact_columns = st.columns(3)

    with artifact_columns[0]:
        _render_file_path(
            "Parton-level LHE",
            _resolve_payload_path(
                payload,
                "primary_lhe_file",
                "parton_lhe_file",
            ),
        )

    with artifact_columns[1]:
        _render_file_path(
            "Showered HepMC",
            _resolve_payload_path(
                payload,
                "showered_hepmc_file",
            ),
        )

    with artifact_columns[2]:
        _render_file_path(
            "Detector ROOT",
            _resolve_payload_path(
                payload,
                "detector_root_file",
            ),
        )

    html_report = _resolve_payload_path(
        payload,
        "analysis_html_report",
    )
    pdf_report = _resolve_payload_path(
        payload,
        "analysis_pdf_report",
    )

    if html_report is not None:
        _render_file_path(
            "HTML analysis report",
            html_report,
        )

    if pdf_report is not None:
        _render_file_path(
            "PDF analysis report",
            pdf_report,
        )

    download_columns = st.columns(3)

    with download_columns[0]:
        _download_file(
            record_path,
            label="Download JSON record",
            key=f"{key_prefix}_json",
            mime="application/json",
        )

    with download_columns[1]:
        _download_file(
            pdf_report,
            label="Download MA5 PDF",
            key=f"{key_prefix}_pdf",
            mime="application/pdf",
        )

    command_path = _resolve_payload_path(
        payload,
        "command_script_path",
    )

    with download_columns[2]:
        _download_file(
            command_path,
            label="Download MG5 commands",
            key=f"{key_prefix}_commands",
            mime="text/plain",
        )

    if llm_calls is not None:
        st.caption(
            f"LLM calls: {llm_calls} · "
            f"Repairs: {payload.get('repair_attempts', 0)} · "
            f"Fallback used: "
            f"{payload.get('fallback_used', False)}"
        )

    _render_plots(
        payload,
        key_prefix=key_prefix,
    )
    _render_logs(payload)

    with st.expander(
        "Complete provenance record",
        expanded=False,
    ):
        st.json(payload)


AUTO_APPROVAL_SECONDS = 5


def _clear_approval_countdown() -> None:
    """Clear automatic-approval state."""

    st.session_state.approval_run_id = None
    st.session_state.approval_deadline = None
    st.session_state.execution_in_progress = False


def _store_execution_result(
    result: EndToEndResult,
) -> None:
    """Store one final result and its chat notification."""

    st.session_state.final_result = result

    st.session_state.session_messages.append(
        {
            "role": "assistant",
            "content": (
                "Execution finished with status "
                f"`{result.status.value}`. "
                "The full result and provenance are "
                "shown below."
            ),
        }
    )


@st.fragment(run_every=1)
def _render_auto_approval(
    prepared: PreparedEndToEnd,
    *,
    mg5_executable: str,
    madanalysis_executable: str | None,
) -> None:
    """Render a cancellable five-second automatic approval."""

    if st.session_state.final_result is not None:
        return

    run_id = prepared.record.run_id

    if (
        st.session_state.approval_run_id
        != run_id
    ):
        st.session_state.approval_run_id = run_id
        st.session_state.approval_deadline = (
            time.time()
            + AUTO_APPROVAL_SECONDS
        )
        st.session_state.execution_in_progress = False

    deadline = st.session_state.approval_deadline

    if deadline is None:
        deadline = (
            time.time()
            + AUTO_APPROVAL_SECONDS
        )
        st.session_state.approval_deadline = deadline

    remaining = approval_countdown_seconds(
        deadline_timestamp=float(deadline),
        current_timestamp=time.time(),
    )

    if st.session_state.execution_in_progress:
        st.info(
            "The validated workflow is executing."
        )
        return

    if remaining > 0:
        st.warning(
            "Validated workflow ready. "
            f"Automatic execution begins in "
            f"{remaining} second"
            f"{'s' if remaining != 1 else ''}."
        )

        st.progress(
            (
                AUTO_APPROVAL_SECONDS
                - remaining
            )
            / AUTO_APPROVAL_SECONDS,
            text=(
                "Reject now to cancel, or execute "
                "immediately."
            ),
        )
    else:
        st.info(
            "Approval countdown completed. "
            "Starting execution..."
        )

    execute_column, cancel_column = st.columns(
        [2, 1]
    )

    with execute_column:
        execute_now = st.button(
            "Execute immediately",
            type="primary",
            help=(
                "Run the exact validated artifact "
                "without waiting for the countdown."
            ),
            use_container_width=True,
            key=f"execute_{run_id}",
        )

    with cancel_column:
        cancel_now = st.button(
            "Reject and cancel",
            help=(
                "Cancel before external HEP software "
                "is started."
            ),
            use_container_width=True,
            key=f"cancel_{run_id}",
        )

    if cancel_now:
        cancelled = execute_prepared(
            prepared,
            approved=False,
            mg5_executable=mg5_executable,
            madanalysis_executable=(
                madanalysis_executable
            ),
            records_directory=RECORDS_DIRECTORY,
            executions_directory=(
                EXECUTIONS_DIRECTORY
            ),
            analyses_directory=(
                ANALYSES_DIRECTORY
            ),
            project_root=PROJECT_ROOT,
        )

        st.session_state.final_result = cancelled

        st.session_state.session_messages.append(
            {
                "role": "assistant",
                "content": (
                    "The prepared workflow was "
                    "cancelled before execution."
                ),
            }
        )

        _clear_approval_countdown()
        st.rerun()

    if execute_now or remaining <= 0:
        st.session_state.execution_in_progress = True

        status = st.status(
            "Executing the validated HEP workflow...",
            expanded=True,
        )

        status.write(
            "Using the exact prepared artifact. "
            "The planner is not being called again."
        )

        final_result = execute_prepared(
            prepared,
            approved=True,
            mg5_executable=mg5_executable,
            madanalysis_executable=(
                madanalysis_executable
            ),
            records_directory=RECORDS_DIRECTORY,
            executions_directory=(
                EXECUTIONS_DIRECTORY
            ),
            analyses_directory=(
                ANALYSES_DIRECTORY
            ),
            project_root=PROJECT_ROOT,
        )

        _store_execution_result(final_result)
        _clear_approval_countdown()

        if final_result.success:
            status.update(
                label=(
                    "Workflow completed successfully."
                ),
                state="complete",
                expanded=False,
            )
        else:
            status.update(
                label=(
                    "Workflow finished with status "
                    f"{final_result.status.value}."
                ),
                state="error",
                expanded=True,
            )

        st.rerun()


def _analysis_object_labels(
    objects: Any,
) -> str:
    """Return compact ranked object labels for UI tables."""

    labels = [
        f"{reference.particle}[{reference.rank}]"
        for reference in objects
    ]

    return ", ".join(labels) if labels else "—"


def _analysis_cut_rows(
    plan: Any,
) -> list[dict[str, Any]]:
    """Return display rows for structured selection cuts."""

    return [
        {
            "Cut ID": cut.cut_id,
            "Observable": cut.observable.value,
            "Objects": _analysis_object_labels(
                cut.objects
            ),
            "Requirement": (
                f"{cut.comparison.value} "
                f"{cut.value:g}"
            ),
            "Unit": (
                cut.unit.value
                if cut.unit is not None
                else "—"
            ),
        }
        for cut in plan.cuts
    ]


def _analysis_histogram_rows(
    plan: Any,
) -> list[dict[str, Any]]:
    """Return display rows for structured histograms."""

    return [
        {
            "Histogram ID": histogram.histogram_id,
            "Observable": histogram.observable.value,
            "Objects": _analysis_object_labels(
                histogram.objects
            ),
            "Bins": histogram.bins,
            "Range": (
                f"{histogram.minimum:g} "
                f"to {histogram.maximum:g}"
            ),
            "Unit": (
                histogram.unit.value
                if histogram.unit is not None
                else "—"
            ),
        }
        for histogram in plan.histograms
    ]


def _render_madanalysis_review(
    workflow: Any,
) -> bool:
    """Render the deterministic analysis plan before approval.

    Returns False when the MA5 analysis body cannot be compiled safely.
    The caller must not start automatic approval in that case.
    """

    if not workflow.pipeline.madanalysis:
        return True

    st.markdown(
        "### MadAnalysis review"
    )

    try:
        if workflow.analysis is None:
            commands = (
                compile_madanalysis_quicklook_commands(
                    workflow
                )
            )

            with st.container(border=True):
                st.info(
                    "Analysis mode: deterministic "
                    "process-aware quick-look"
                )

                st.caption(
                    "No custom analysis plan was requested. "
                    "The application will generate its "
                    "validated process-aware plot preset."
                )

                with st.expander(
                    "Exact deterministic MA5 "
                    "analysis commands",
                    expanded=False,
                ):
                    st.code(
                        "\n".join(commands),
                        language="text",
                    )

            return True

        plan = workflow.analysis

        commands = (
            compile_madanalysis_plan_commands(
                workflow,
                plan,
            )
        )

    except MadAnalysisBuildError as exc:
        st.error(
            "The requested MadAnalysis plan could not "
            "be compiled safely."
        )
        st.code(
            str(exc),
            language=None,
        )
        st.warning(
            "Automatic execution is blocked for this "
            "prepared workflow."
        )

        return False

    with st.container(border=True):
        st.success(
            "Analysis mode: custom structured analysis"
        )

        st.caption(
            "The local model supplied structured intent only. "
            "These commands were produced deterministically "
            "from the validated schema."
        )

        if plan.cuts:
            st.markdown(
                "**Selection cuts**"
            )

            st.dataframe(
                _analysis_cut_rows(plan),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption(
                "No numerical event-selection cuts "
                "were requested."
            )

        st.markdown(
            "**Histograms**"
        )

        st.dataframe(
            _analysis_histogram_rows(plan),
            hide_index=True,
            use_container_width=True,
        )

        if plan.cuts:
            st.caption(
                "All structured cuts are applied before "
                "the requested histograms."
            )

        with st.expander(
            "Exact deterministic MA5 "
            "analysis commands",
            expanded=True,
        ):
            st.code(
                "\n".join(commands),
                language="text",
            )

            st.caption(
                "The event import path and MA5 job directory "
                "are assigned later from the approved run ID. "
                "The analysis body shown here will not be "
                "regenerated by the planner."
            )

    return True


def _agent_activity_payload(
    event: Any,
) -> dict[str, Any]:
    """Convert one progress event to persistent web-session data."""

    return {
        "event_type": event.event_type,
        "message": event.message,
        "role": event.role,
        "model": event.model,
        "duration_seconds": event.duration_seconds,
        "issue_codes": list(
            event.issue_codes
        ),
    }


def _format_agent_activity(
    payload: dict[str, Any],
) -> str:
    """Format one operational event for Streamlit."""

    event_type = payload[
        "event_type"
    ]

    prefixes = {
        "model_call_started": "↻",
        "model_call_completed": "✓",
        "model_call_failed": "✗",
        "validation_passed": "✓",
        "validation_failed": "✗",
    }

    prefix = prefixes.get(
        event_type,
        "•",
    )

    message = payload["message"]

    duration = payload.get(
        "duration_seconds"
    )

    if duration is not None:
        message += (
            f" ({duration:.1f} s)"
        )

    return f"{prefix} {message}"


def _render_agent_activity_trace() -> None:
    """Render the retained planner/repair activity trace."""

    events = st.session_state.get(
        "agent_activity_events",
        [],
    )

    if not events:
        return

    with st.expander(
        "Agent activity trace",
        expanded=True,
    ):
        for event in events:
            st.markdown(
                _format_agent_activity(
                    event
                )
            )


def _render_prepared(
    prepared: PreparedEndToEnd,
    *,
    profile_name: str,
    mg5_executable: str,
    madanalysis_executable: str | None,
) -> None:
    """Render a concise review with optional technical detail."""

    result = prepared.result

    st.subheader("Review workflow")

    if not prepared.is_ready:
        st.error(
            result.failure_message
            or "The request could not be prepared."
        )

        with st.expander(
            "Failure details",
            expanded=False,
        ):
            if (
                result.failure_category
                is not None
            ):
                st.code(
                    result
                    .failure_category
                    .value,
                    language=None,
                )

            failure_issues = (
                failure_validation_issues(
                    result
                )
            )

            if failure_issues:
                st.json(
                    {
                        "issues": failure_issues
                    }
                )
            else:
                st.caption(
                    "No structured validation issues were "
                    "reported for this failure."
                )

        if st.button(
            "Dismiss failed request",
            use_container_width=True,
        ):
            st.session_state.prepared_workflow = None
            st.session_state.final_result = None
            st.rerun()

        return

    workflow = result.workflow
    artifact = result.artifact

    if workflow is None or artifact is None:
        st.error(
            "Prepared workflow is missing its "
            "deterministic artifact."
        )
        return

    process_commands = [
        command
        for command in artifact.commands
        if (
            command.startswith("generate ")
            or command.startswith(
                "add process "
            )
        )
    ]

    overview_tab, workflow_tab, diagnostics_tab = (
        st.tabs(
            [
                "🧭 Overview",
                "🛠️ Workflow",
                "🔍 Diagnostics",
            ]
        )
    )

    with overview_tab:
        st.success(
            "The workflow passed deterministic "
            "validation and is ready to run."
        )

        beams = " ".join(
            beam.particle
            for beam
            in workflow.collider.beams
        )

        energy_gev = (
            workflow
            .collider
            .energy
            .value_gev
        )

        energy_label = (
            f"{energy_gev / 1000:g} TeV"
            if energy_gev >= 1000
            else f"{energy_gev:g} GeV"
        )

        metrics = st.columns(4)

        metrics[0].metric(
            "Collider",
            beams,
        )
        metrics[1].metric(
            "Energy",
            energy_label,
        )
        metrics[2].metric(
            "Events",
            workflow.run.nevents,
        )
        metrics[3].metric(
            "Validation",
            "Ready",
        )

        st.markdown("**Process**")

        st.code(
            "\n".join(process_commands),
            language="text",
        )

        pipeline = workflow.pipeline
        stages = st.columns(4)

        stages[0].metric(
            "MadGraph",
            (
                "On"
                if pipeline.madgraph
                else "Off"
            ),
        )
        stages[1].metric(
            "Pythia8",
            (
                "On"
                if pipeline.pythia8
                else "Off"
            ),
        )
        stages[2].metric(
            "Delphes",
            (
                "On"
                if pipeline.delphes
                else "Off"
            ),
        )
        stages[3].metric(
            "MadAnalysis",
            (
                "On"
                if pipeline.madanalysis
                else "Off"
            ),
        )

        st.caption(
            "Execution uses the exact validated "
            "artifact shown in the Workflow tab. "
            "The model is not called again."
        )

    with workflow_tab:
        st.markdown(
            "#### Exact validated MG5 workflow"
        )

        st.code(
            artifact.text,
            language="text",
        )

        if result.corrections:
            with st.expander(
                "Deterministic corrections",
                expanded=False,
            ):
                for correction in (
                    result.corrections
                ):
                    st.markdown(
                        f"**`{correction.path}`**"
                    )
                    st.write(
                        correction.previous_value,
                        "→",
                        correction.corrected_value,
                    )
                    st.caption(
                        correction.reason
                    )

    with diagnostics_tab:
        metrics = st.columns(5)

        metrics[0].metric(
            "Profile",
            profile_name,
        )
        metrics[1].metric(
            "LLM calls",
            result.llm_call_count,
        )
        metrics[2].metric(
            "Repairs",
            result.repair_attempts,
        )
        metrics[3].metric(
            "Fallback",
            (
                "Yes"
                if result.fallback_used
                else "No"
            ),
        )
        metrics[4].metric(
            "Planning",
            (
                f"{prepared.preexecution_wall_time_seconds:.1f} s"
            ),
        )

        approval_reason = getattr(
            result.approval,
            "reason",
            None,
        )

        if approval_reason:
            st.info(approval_reason)

        with st.expander(
            "Raw structured workflow",
            expanded=False,
        ):
            st.json(
                workflow.model_dump(
                    mode="json"
                )
            )

    _render_auto_approval(
        prepared,
        mg5_executable=mg5_executable,
        madanalysis_executable=(
            madanalysis_executable
        ),
    )

def _render_final_result(
    result: EndToEndResult,
) -> None:
    """Render scientific results first and provenance on demand."""

    st.divider()
    st.subheader("Run result")

    record_path = (
        RECORDS_DIRECTORY
        / f"{result.final_record.run_id}.json"
    )

    payload = (
        result.final_record.model_dump(
            mode="json"
        )
    )

    results_tab, diagnostics_tab = st.tabs(
        [
            "📊 Results",
            "🔍 Diagnostics",
        ]
    )

    with results_tab:
        if result.success:
            st.success(
                "Workflow completed successfully."
            )
        else:
            st.error(
                "Workflow finished with status "
                f"{result.status.value}."
            )

        cross_section = _value(
            payload,
            "cross_section_pb",
        )
        event_count = _value(
            payload,
            "generated_events",
            "generated_event_count",
            "event_count",
        )
        total_time = _value(
            payload,
            (
                "end_to_end_"
                "wall_time_seconds"
            ),
        )

        metrics = st.columns(4)

        metrics[0].metric(
            "Run ID",
            str(
                payload.get(
                    "run_id",
                    "unknown",
                )
            ),
        )
        metrics[1].metric(
            "Cross section",
            (
                f"{cross_section:g} pb"
                if isinstance(
                    cross_section,
                    (int, float),
                )
                else "—"
            ),
        )
        metrics[2].metric(
            "Events",
            (
                str(event_count)
                if event_count is not None
                else "—"
            ),
        )
        metrics[3].metric(
            "Total time",
            (
                f"{total_time:.2f} s"
                if isinstance(
                    total_time,
                    (int, float),
                )
                else "—"
            ),
        )

        _render_plots(
            payload,
            key_prefix=(
                f"current_results_"
                f"{result.final_record.run_id}"
            ),
        )

        with st.expander(
            "Output files and downloads",
            expanded=False,
        ):
            file_specs = [
                (
                    "Parton-level LHE",
                    _resolve_payload_path(
                        payload,
                        "primary_lhe_file",
                        "parton_lhe_file",
                    ),
                ),
                (
                    "Showered HepMC",
                    _resolve_payload_path(
                        payload,
                        "showered_hepmc_file",
                    ),
                ),
                (
                    "Detector ROOT",
                    _resolve_payload_path(
                        payload,
                        "detector_root_file",
                    ),
                ),
                (
                    "HTML analysis report",
                    _resolve_payload_path(
                        payload,
                        "analysis_html_report",
                    ),
                ),
                (
                    "PDF analysis report",
                    _resolve_payload_path(
                        payload,
                        "analysis_pdf_report",
                    ),
                ),
            ]

            for label, file_path in file_specs:
                if file_path is not None:
                    _render_file_path(
                        label,
                        file_path,
                    )

            command_path = (
                _resolve_payload_path(
                    payload,
                    "command_script_path",
                )
            )

            download_columns = st.columns(3)

            with download_columns[0]:
                _download_file(
                    record_path,
                    label="Download run record",
                    key=(
                        "current_clean_json_"
                        f"{result.final_record.run_id}"
                    ),
                    mime="application/json",
                )

            with download_columns[1]:
                _download_file(
                    command_path,
                    label="Download MG5 commands",
                    key=(
                        "current_clean_commands_"
                        f"{result.final_record.run_id}"
                    ),
                    mime="text/plain",
                )

            with download_columns[2]:
                pdf_report = (
                    _resolve_payload_path(
                        payload,
                        "analysis_pdf_report",
                    )
                )

                _download_file(
                    pdf_report,
                    label="Download MA5 PDF",
                    key=(
                        "current_clean_pdf_"
                        f"{result.final_record.run_id}"
                    ),
                    mime="application/pdf",
                )

    with diagnostics_tab:
        _render_record(
            payload,
            record_path=record_path,
            key_prefix=(
                f"current_diagnostics_"
                f"{result.final_record.run_id}"
            ),
        )

    if st.button(
        "Start another request",
        use_container_width=True,
    ):
        st.session_state.prepared_workflow = None
        st.session_state.final_result = None
        st.rerun()

def _render_history_entry(
    entry: RunHistoryEntry,
) -> None:
    _render_record(
        entry.payload,
        record_path=entry.path,
        key_prefix=f"history_{entry.run_id}",
    )


def _make_web_scan_id() -> str:
    """Create one stable identifier for a web-submitted scan."""

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S")

    suffix = uuid.uuid4().hex[:8]

    return f"web_scan_{timestamp}_{suffix}"


def _scan_table_rows(
    prepared: PreparedEnergyScan,
) -> list[dict[str, Any]]:
    """Return display rows for a prepared scan grid."""

    if prepared.expanded is None:
        return []

    return [
        {
            "Point": point.index + 1,
            "Energy [TeV]": (
                point.energy_gev / 1000.0
            ),
            "Events": point.workflow.run.nevents,
            "Seed": point.random_seed,
            "Output": point.output_name,
        }
        for point in prepared.expanded.points
    ]


def _scan_result_rows(
    result: EnergyScanExecutionSummary,
) -> list[dict[str, Any]]:
    """Return display rows for completed scan points."""

    return [
        {
            "Point": point.index + 1,
            "Energy [TeV]": point.energy_tev,
            "Status": point.status.value,
            "Cross section [pb]": (
                point.cross_section_pb
            ),
            "Uncertainty [pb]": (
                point.cross_section_uncertainty_pb
            ),
            "Events": (
                point.generated_event_count
            ),
        }
        for point in result.point_results
    ]


def _render_scan_result(
    result: EnergyScanExecutionSummary,
) -> None:
    """Render one completed or partially completed scan."""

    st.divider()
    st.subheader("Energy-scan result")

    if result.status.value == "completed":
        st.success(
            "All requested scan points completed."
        )
    elif result.status.value == "partial":
        st.warning(
            "The scan completed only partially."
        )
    else:
        st.error(
            "No scan point completed successfully."
        )

    metrics = st.columns(5)

    metrics[0].metric(
        "Scan ID",
        result.scan_id,
    )
    metrics[1].metric(
        "Completed",
        (
            f"{result.completed_point_count}/"
            f"{result.requested_point_count}"
        ),
    )
    metrics[2].metric(
        "Failed",
        result.failed_point_count,
    )
    metrics[3].metric(
        "Generated events",
        result.total_generated_events,
    )
    metrics[4].metric(
        "Wall time",
        f"{result.wall_time_seconds:.1f} s",
    )

    st.dataframe(
        _scan_result_rows(result),
        hide_index=True,
        use_container_width=True,
    )

    if result.maximum is not None:
        maximum = result.maximum

        with st.container(border=True):
            st.markdown(
                "### Largest sampled cross section"
            )

            maximum_columns = st.columns(3)

            maximum_columns[0].metric(
                "Energy",
                f"{maximum.energy_tev:g} TeV",
            )
            maximum_columns[1].metric(
                "Cross section",
                (
                    f"{maximum.cross_section_pb:g} pb"
                ),
            )
            maximum_columns[2].metric(
                "At scan boundary",
                (
                    "Yes"
                    if maximum.at_scan_boundary
                    else "No"
                ),
            )

            if (
                maximum
                .cross_section_uncertainty_pb
                is not None
            ):
                st.caption(
                    "Integration uncertainty: "
                    f"{maximum.cross_section_uncertainty_pb:g} pb"
                )

            for warning in maximum.warnings:
                st.warning(warning)

    plot_path = Path(
        result.plot_path
    ) if result.plot_path else None

    if (
        plot_path is not None
        and plot_path.is_file()
    ):
        st.subheader(
            "Cross section versus energy"
        )

        st.image(
            str(plot_path),
            use_container_width=True,
        )

    csv_path = Path(result.csv_path)
    json_path = Path(result.json_path)

    download_columns = st.columns(3)

    with download_columns[0]:
        _download_file(
            csv_path,
            label="Download scan CSV",
            key=f"{result.scan_id}_csv",
            mime="text/csv",
        )

    with download_columns[1]:
        _download_file(
            json_path,
            label="Download scan JSON",
            key=f"{result.scan_id}_json",
            mime="application/json",
        )

    with download_columns[2]:
        _download_file(
            plot_path,
            label="Download scan plot",
            key=f"{result.scan_id}_plot",
            mime="image/svg+xml",
        )

    with st.expander(
        "Point-level provenance records",
        expanded=False,
    ):
        for point in result.point_results:
            st.markdown(
                f"**Point {point.index + 1}: "
                f"{point.energy_tev:g} TeV**"
            )

            if point.point_record_path is None:
                st.caption(
                    "No point-level record was produced."
                )
                continue

            record_path = Path(
                point.point_record_path
            )

            st.code(
                str(record_path),
                language=None,
            )

            _download_file(
                record_path,
                label=(
                    "Download point "
                    f"{point.index + 1} record"
                ),
                key=(
                    f"{result.scan_id}_"
                    f"point_{point.index + 1}"
                ),
                mime="application/json",
            )

    with st.expander(
        "Complete scan summary",
        expanded=False,
    ):
        st.json(
            result.model_dump(mode="json")
        )

    if st.button(
        "Start another independent request",
        key=f"new_after_{result.scan_id}",
        use_container_width=True,
    ):
        st.session_state.prepared_scan = None
        st.session_state.scan_result = None
        st.session_state.scan_run_id = None
        st.session_state.prepared_workflow = None
        st.session_state.final_result = None
        _clear_approval_countdown()
        st.rerun()


@st.fragment(run_every=1)
def _render_auto_scan_approval(
    prepared: PreparedEnergyScan,
    *,
    profile_name: str,
    profile: Any,
    mg5_executable: str,
    madanalysis_executable: str | None,
) -> None:
    """Render one approval countdown for the complete scan."""

    if st.session_state.scan_result is not None:
        return

    if prepared.expanded is None:
        st.error(
            "The prepared scan has no expanded points."
        )
        return

    if st.session_state.scan_run_id is None:
        st.session_state.scan_run_id = (
            _make_web_scan_id()
        )

    scan_id = st.session_state.scan_run_id

    if (
        st.session_state.approval_run_id
        != scan_id
    ):
        st.session_state.approval_run_id = (
            scan_id
        )
        st.session_state.approval_deadline = (
            time.time()
            + AUTO_APPROVAL_SECONDS
        )
        st.session_state.execution_in_progress = (
            False
        )

    deadline = (
        st.session_state.approval_deadline
    )

    if deadline is None:
        deadline = (
            time.time()
            + AUTO_APPROVAL_SECONDS
        )
        st.session_state.approval_deadline = (
            deadline
        )

    remaining = approval_countdown_seconds(
        deadline_timestamp=float(deadline),
        current_timestamp=time.time(),
    )

    if (
        st.session_state.execution_in_progress
    ):
        st.info(
            "The validated energy scan is executing."
        )
        return

    if remaining > 0:
        st.warning(
            "Validated energy scan ready. "
            "All points will execute sequentially "
            f"in {remaining} second"
            f"{'s' if remaining != 1 else ''}."
        )

        st.progress(
            (
                AUTO_APPROVAL_SECONDS
                - remaining
            )
            / AUTO_APPROVAL_SECONDS,
            text=(
                "Reject now to cancel the complete "
                "scan, or execute immediately."
            ),
        )
    else:
        st.info(
            "Approval countdown completed. "
            "Starting the energy scan..."
        )

    execute_column, cancel_column = (
        st.columns([2, 1])
    )

    with execute_column:
        execute_now = st.button(
            "Execute complete scan",
            type="primary",
            use_container_width=True,
            key=f"execute_scan_{scan_id}",
        )

    with cancel_column:
        cancel_now = st.button(
            "Reject and cancel",
            use_container_width=True,
            key=f"cancel_scan_{scan_id}",
        )

    if cancel_now:
        st.session_state.session_messages.append(
            {
                "role": "assistant",
                "content": (
                    "The complete energy scan was "
                    "cancelled before external HEP "
                    "software started."
                ),
            }
        )

        st.session_state.prepared_scan = None
        st.session_state.scan_result = None
        st.session_state.scan_run_id = None
        _clear_approval_countdown()
        st.rerun()

    if execute_now or remaining <= 0:
        st.session_state.execution_in_progress = (
            True
        )

        status = st.status(
            "Executing the validated energy scan...",
            expanded=True,
        )

        status.write(
            "The planner will not be called again. "
            "Each point uses deterministic workflow "
            "expansion and the existing validated "
            "MG5/MA5 pipeline."
        )

        progress = st.progress(
            0.0,
            text=(
                f"Preparing point 1 of "
                f"{prepared.point_count}"
            ),
        )

        result_placeholder = st.empty()
        observed_rows: list[
            dict[str, Any]
        ] = []

        def observe_point(
            point: ScanPointResult,
            completed: int,
            total: int,
        ) -> None:
            observed_rows.append(
                {
                    "Point": point.index + 1,
                    "Energy [TeV]": (
                        point.energy_tev
                    ),
                    "Status": (
                        point.status.value
                    ),
                    "Cross section [pb]": (
                        point.cross_section_pb
                    ),
                }
            )

            progress.progress(
                completed / total,
                text=(
                    f"Completed {completed} "
                    f"of {total} scan points"
                ),
            )

            result_placeholder.dataframe(
                observed_rows,
                hide_index=True,
                use_container_width=True,
            )

        point_executor = (
            ExistingPipelinePointExecutor(
                prepared_scan=prepared,
                scan_id=scan_id,
                profile_name=profile_name,
                profile=profile,
                mg5_executable=(
                    mg5_executable
                ),
                madanalysis_executable=(
                    madanalysis_executable
                ),
                records_directory=(
                    RECORDS_DIRECTORY
                ),
                executions_directory=(
                    EXECUTIONS_DIRECTORY
                ),
                analyses_directory=(
                    ANALYSES_DIRECTORY
                ),
                project_root=PROJECT_ROOT,
                analysis_timeout_seconds=300,
            )
        )

        scan_result = execute_energy_scan(
            prepared.expanded,
            point_executor=point_executor,
            output_directory=(
                SCAN_SUMMARIES_DIRECTORY
            ),
            scan_id=scan_id,
            point_observer=observe_point,
        )

        st.session_state.scan_result = (
            scan_result
        )

        st.session_state.session_messages.append(
            {
                "role": "assistant",
                "content": (
                    "Energy scan finished with status "
                    f"`{scan_result.status.value}`. "
                    f"{scan_result.completed_point_count} "
                    "point(s) completed successfully."
                ),
            }
        )

        _clear_approval_countdown()

        if (
            scan_result.status.value
            == "completed"
        ):
            status.update(
                label=(
                    "Energy scan completed "
                    "successfully."
                ),
                state="complete",
                expanded=False,
            )
        else:
            status.update(
                label=(
                    "Energy scan finished with status "
                    f"{scan_result.status.value}."
                ),
                state="error",
                expanded=True,
            )

        st.rerun()


def _render_prepared_scan(
    prepared: PreparedEnergyScan,
    *,
    profile_name: str,
    profile: Any,
    mg5_executable: str,
    madanalysis_executable: str | None,
) -> None:
    """Render a prepared multi-point energy scan."""

    st.subheader("Prepared energy scan")

    if not prepared.is_ready:
        st.error(
            prepared.failure_message
            or "The energy scan could not be prepared."
        )

        st.info(
            "This failed preparation does not require "
            "approval. You may submit another request."
        )

        if st.button(
            "Dismiss failed scan",
            use_container_width=True,
        ):
            st.session_state.prepared_scan = None
            st.session_state.scan_result = None
            st.session_state.scan_run_id = None
            st.rerun()

        return

    if prepared.expanded is None:
        st.error(
            "The prepared scan has no expanded points."
        )
        return

    workflow = prepared.base_result.workflow

    if workflow is None:
        st.error(
            "The prepared scan has no base workflow."
        )
        return

    metrics = st.columns(5)

    metrics[0].metric(
        "Profile",
        profile_name,
    )
    metrics[1].metric(
        "LLM calls",
        prepared.base_result.llm_call_count,
    )
    metrics[2].metric(
        "Scan points",
        prepared.point_count,
    )
    metrics[3].metric(
        "Events per point",
        workflow.run.nevents,
    )
    metrics[4].metric(
        "Total events",
        prepared.total_requested_events,
    )

    with st.container(border=True):
        beams = " ".join(
            beam.particle
            for beam in workflow.collider.beams
        )

        st.markdown(
            f"**Collider:** {beams}"
        )

        st.markdown("**Processes**")

        for process in workflow.processes:
            incoming = " ".join(
                process.incoming_particles
            )
            final = " ".join(
                node.particle
                for node in process.final_particles
            )

            st.code(
                f"{incoming} > {final}",
                language=None,
            )

        pipeline = workflow.pipeline

        st.caption(
            "Pipeline · "
            f"MG5={pipeline.madgraph} · "
            f"Pythia8={pipeline.pythia8} · "
            f"Delphes={pipeline.delphes} · "
            f"MadAnalysis={pipeline.madanalysis}"
        )

    st.markdown("### Deterministic scan grid")

    st.dataframe(
        _scan_table_rows(prepared),
        hide_index=True,
        use_container_width=True,
    )

    with st.expander(
        "Exact validated MG5 workflow for every point",
        expanded=False,
    ):
        for point in prepared.expanded.points:
            st.markdown(
                f"#### Point {point.index + 1}: "
                f"{point.energy_gev / 1000:g} TeV"
            )

            artifact = (
                build_madgraph_workflow_artifact(
                    point.workflow
                )
            )

            st.code(
                artifact.text,
                language="text",
            )

    st.caption(
        "One approval covers the complete displayed grid. "
        "Execution is sequential, and no point triggers "
        "another planner call."
    )

    _render_auto_scan_approval(
        prepared,
        profile_name=profile_name,
        profile=profile,
        mg5_executable=mg5_executable,
        madanalysis_executable=(
            madanalysis_executable
        ),
    )





def _render_installation_check(
    *,
    profile_name: str,
    ollama_host: str,
) -> None:
    """Render the first-run toolchain test and optional diagnostics."""

    st.subheader("Test your installation")

    st.write(
        "Recommended after installation: run one deterministic trial "
        "to confirm that the complete local HEP toolchain works before "
        "building your own workflow."
    )

    st.caption(
        "No model is involved. The test runs a fixed p p > e+ e- "
        "process through MadGraph, Pythia8, Delphes, and MadAnalysis. "
        "It generates events and can take a few minutes."
    )

    selftest_requested = st.button(
        "🚀 Run full installation test",
        type="primary",
        use_container_width=True,
        key="system_selftest_run",
    )

    with st.expander(
        "Test settings",
        expanded=False,
    ):
        selftest_events = st.number_input(
            "Trial events",
            min_value=100,
            max_value=100000,
            value=1000,
            step=100,
            key="system_selftest_events",
        )
        st.caption(
            "The default is a small validation run; no physics result "
            "from this trial is used by the agent."
        )

    if selftest_requested:
        try:
            local_paths = load_json_object(LOCAL_PATHS_PATH)
            mg5_executable = local_paths.get("mg5_executable")
            madanalysis_executable = local_paths.get(
                "madanalysis5_executable"
            )
            if not mg5_executable:
                raise ValueError(
                    "configs/local_paths.json does not define "
                    "'mg5_executable'."
                )
            with st.spinner(
                "Running the full toolchain (MadGraph, Pythia8, "
                "Delphes, MadAnalysis). This may take a few minutes..."
            ):
                st.session_state.selftest_result = (
                    run_installation_selftest(
                        mg5_executable=mg5_executable,
                        madanalysis_executable=(
                            madanalysis_executable
                        ),
                        nevents=int(selftest_events),
                        run_directory=str(
                            PROJECT_ROOT / "results" / "selftest"
                        ),
                    )
                )
            st.session_state.selftest_error = None
        except Exception as exc:
            st.session_state.selftest_result = None
            st.session_state.selftest_error = (
                f"{type(exc).__name__}: {exc}"
            )

    selftest_error = st.session_state.get("selftest_error")
    if selftest_error:
        st.error("The installation self-test could not run.")
        st.code(str(selftest_error), language=None)

    selftest_result = st.session_state.get("selftest_result")
    if selftest_result is not None:
        if selftest_result.success and selftest_result.missing:
            st.success(
                "Installed tools ran successfully. Not installed: "
                + ", ".join(selftest_result.missing)
                + " (⚠️ means not installed, not a failure)."
            )
        elif selftest_result.success:
            st.success(
                "All tools ran successfully - your installation works "
                "end to end."
            )
        else:
            st.error(
                "One or more installed tools failed. See the per-stage "
                "results."
            )
        _stage_icons = {
            "ok": "✅",
            "failed": "❌",
            "missing": "⚠️",
            "skipped": "⏭️",
        }
        for stage in selftest_result.stages:
            marker = _stage_icons.get(stage.status, "•")
            detail = (
                f" - {stage.detail}" if stage.detail else ""
            )
            st.markdown(f"{marker} **{stage.name}**{detail}")
        if selftest_result.cross_section_pb is not None:
            st.caption(
                f"Cross section: {selftest_result.cross_section_pb} "
                f"pb · events: {selftest_result.event_count}"
            )

    st.divider()

    st.subheader("Additional diagnostics")

    st.write(
        "Inspect the model service, selected profile, Python "
        "environment, repository configuration, writable output "
        "directories, and individual HEP tools."
    )

    st.caption(
        "Standard checks are lightweight. Deep checks additionally "
        "send one tiny model request and ask MadGraph to construct "
        "a temporary e+ e- > mu+ mu- process. No events are generated."
    )

    standard_column, deep_column, clear_column = (
        st.columns(
            [1.25, 1.25, 1],
        )
    )

    with standard_column:
        standard_requested = st.button(
            "🩺 Run standard doctor",
            use_container_width=True,
            key="system_doctor_standard",
        )

    with deep_column:
        deep_requested = st.button(
            "🧪 Run deep doctor",
            use_container_width=True,
            key="system_doctor_deep",
        )

    with clear_column:
        clear_requested = st.button(
            "Clear doctor report",
            use_container_width=True,
            key="system_doctor_clear",
        )

    if clear_requested:
        st.session_state.doctor_report = None
        st.session_state.doctor_error = None
        st.rerun()

    requested_mode: str | None = None

    if standard_requested:
        requested_mode = "standard"

    elif deep_requested:
        requested_mode = "deep"

    if requested_mode is not None:
        deep = requested_mode == "deep"

        status_text = (
            "Running deep environment checks..."
            if deep
            else "Running standard environment checks..."
        )

        try:
            with st.spinner(status_text):
                report = run_doctor(
                    project_root=PROJECT_ROOT,
                    selected_profile=profile_name,
                    ollama_host=ollama_host,
                    deep=deep,
                    timeout_seconds=(
                        600
                        if deep
                        else 60
                    ),
                )

            st.session_state.doctor_report = report
            st.session_state.doctor_error = None

        except Exception as exc:
            st.session_state.doctor_report = None
            st.session_state.doctor_error = (
                f"{type(exc).__name__}: {exc}"
            )

    doctor_error = st.session_state.get(
        "doctor_error"
    )

    if doctor_error:
        st.error(
            "The doctor itself encountered an unexpected error."
        )

        with st.expander(
            "Doctor error details",
            expanded=False,
        ):
            st.code(
                str(doctor_error),
                language=None,
            )

    report = st.session_state.get(
        "doctor_report"
    )

    if report is None:
        st.info(
            "No doctor report has been run in this session."
        )
        return

    if not isinstance(
        report,
        DoctorReport,
    ):
        st.warning(
            "The stored doctor report is incompatible with "
            "the current application version. Clear it and rerun."
        )
        return

    overall_column, pass_column, warning_column, failure_column = (
        st.columns(4)
    )

    overall_column.metric(
        "Overall",
        (
            "Healthy"
            if report.healthy
            else "Action required"
        ),
    )

    pass_column.metric(
        "Passed",
        len(report.passes),
    )

    warning_column.metric(
        "Warnings",
        len(report.warnings),
    )

    failure_column.metric(
        "Failures",
        len(report.failures),
    )

    if report.healthy:
        if report.warnings:
            st.warning(
                "All required checks passed, but optional or "
                "recommended components need attention."
            )
        else:
            st.success(
                "All required and optional checks passed."
            )
    else:
        st.error(
            "One or more required checks failed. Review the "
            "recommended actions before running workflows."
        )

    mode_label = (
        "Deep"
        if report.deep_checks
        else "Standard"
    )

    st.caption(
        f"{mode_label} report · profile `{report.selected_profile}` · "
        f"generated `{report.generated_at_utc}`"
    )

    st.markdown("### Checks")

    for index, check in enumerate(
        report.checks
    ):
        optional_label = (
            " · optional"
            if not check.required
            else ""
        )

        heading = (
            f"{check.label}{optional_label}"
        )

        message = (
            f"**{heading}**  \n"
            f"{check.summary}"
        )

        if check.status is CheckStatus.PASS:
            st.success(message)

        elif check.status is CheckStatus.WARNING:
            st.warning(message)

        else:
            st.error(message)

        if check.remediation:
            st.markdown(
                "**Recommended action:** "
                f"{check.remediation}"
            )

        if check.details:
            with st.expander(
                f"Technical details · {check.label}",
                expanded=False,
            ):
                st.json(
                    check.details
                )

    payload = report.to_dict()

    st.download_button(
        "Download doctor report",
        data=(
            json.dumps(
                payload,
                indent=2,
            )
            + "\n"
        ),
        file_name=(
            "hep_agent_doctor_"
            + (
                "deep"
                if report.deep_checks
                else "standard"
            )
            + ".json"
        ),
        mime="application/json",
        use_container_width=True,
        key="download_system_doctor_report",
    )


def _render_sidebar(
    profiles: dict[str, Any],
    local_paths: dict[str, Any],
) -> tuple[str, Any, str, str, str | None]:
    """Render compact controls with technical detail collapsed."""

    st.sidebar.markdown("## HEP Agent")

    profile_names = sorted(profiles)

    preferred_profile = os.environ.get(
        "HEP_AGENT_DEFAULT_PROFILE",
        "qwen_primary",
    )

    default_index = (
        profile_names.index(
            preferred_profile
        )
        if preferred_profile
        in profile_names
        else (
            profile_names.index(
                "qwen_primary"
            )
            if "qwen_primary"
            in profile_names
            else 0
        )
    )

    profile_name = st.session_state.get(
        "hep_agent_routing_profile",
        profile_names[default_index],
    )

    if profile_name not in profiles:
        profile_name = profile_names[default_index]

    selected_profile = profiles[
        profile_name
    ]

    default_ollama_host = (
        os.environ.get("OLLAMA_HOST")
        or "http://localhost:11434"
    )

    ollama_host = str(
        st.session_state.get(
            "hep_agent_ollama_host",
            default_ollama_host,
        )
    ).strip()

    if not ollama_host:
        ollama_host = default_ollama_host

    installed_models: list[str] = []
    discovery_error: str | None = None

    try:
        installed_models = OllamaClient(
            ollama_host
        ).list_models(
            timeout_seconds=3
        )
    except OllamaClientError as exc:
        discovery_error = str(exc)

    configured_models = [
        model
        for profile in profiles.values()
        for model in (
            profile.primary_model,
            profile.fallback_model,
        )
        if model is not None
    ]

    model_options = ollama_model_options(
        installed_models,
        configured_models,
    )

    if not model_options:
        st.sidebar.error(
            "No Ollama models are installed or configured."
        )
        st.stop()

    preferred_model = os.environ.get(
        "HEP_AGENT_DEFAULT_MODEL",
        selected_profile.primary_model,
    )

    current_model = st.session_state.get(
        "hep_agent_selected_model"
    )

    if current_model not in model_options:
        st.session_state.pop(
            "hep_agent_selected_model",
            None,
        )

    model_index = (
        model_options.index(preferred_model)
        if preferred_model in model_options
        else 0
    )

    selected_model = st.sidebar.selectbox(
        "Ollama model (new requests)",
        model_options,
        index=model_index,
        key="hep_agent_selected_model",
        help=(
            "Lists every model currently reported by the "
            "configured Ollama host. The selected model is used "
            "for both Chat and Build workflow requests."
        ),
    )

    profile_name = st.sidebar.selectbox(
        "Routing profile",
        profile_names,
        index=profile_names.index(profile_name),
        help=(
            "Controls retry limits and the optional validated "
            "repair fallback. The model selected above replaces "
            "the profile's configured primary model."
        ),
        key="hep_agent_routing_profile",
    )

    selected_profile = profiles[
        profile_name
    ]

    selected_profile = profile_with_primary_model(
        selected_profile,
        selected_model,
        known_profiles=profiles.values(),
    )

    if discovery_error is None and installed_models:
        st.sidebar.caption(
            f"{len(installed_models)} installed Ollama "
            "model(s) found."
        )
    elif discovery_error is not None:
        st.sidebar.warning(
            "Could not refresh installed Ollama models. "
            "Showing configured models instead."
        )
        st.sidebar.caption(discovery_error)
    else:
        st.sidebar.warning(
            "Ollama reported no installed models. Showing "
            "configured models instead."
        )

    st.sidebar.caption(
        "Selected primary model: "
        f"`{selected_profile.primary_model}`"
    )

    if (
        selected_profile.fallback_model
        is not None
    ):
        st.sidebar.caption(
            "Build-repair fallback: "
            f"`{selected_profile.fallback_model}`"
        )
    else:
        st.sidebar.caption(
            "Build-repair fallback: none"
        )

    st.sidebar.caption(
        "The selected primary model is used for both "
        "new Chat and Build-workflow requests. A fallback "
        "model, when configured, is used only by the "
        "validated Build repair path. Prepared workflows "
        "are never changed by switching profiles."
    )


    mg5_executable = str(
        local_paths.get(
            "mg5_executable",
            "",
        )
    )

    madanalysis_executable = (
        local_paths.get(
            "madanalysis5_executable"
        )
    )

    tool_statuses = (
        detect_hep_tool_status(
            local_paths
        )
    )

    available_count = sum(
        tool.available
        for tool in tool_statuses
    )

    st.sidebar.caption(
        f"Toolchain: {available_count}/"
        f"{len(tool_statuses)} available"
    )

    for tool in tool_statuses:
        icon = (
            "✅"
            if tool.available
            else "❌"
        )

        st.sidebar.markdown(
            f"{icon} {tool.label}"
        )

    with st.sidebar.expander(
        "Runtime and tool details",
        expanded=False,
    ):
        host_input_arguments: dict[str, Any] = {
            "key": "hep_agent_ollama_host",
        }

        if "hep_agent_ollama_host" not in st.session_state:
            host_input_arguments["value"] = ollama_host

        ollama_host = st.text_input(
            "Ollama host",
            **host_input_arguments,
        )

        ollama_host = (
            ollama_host.strip()
            or default_ollama_host
        )

        for tool in tool_statuses:
            st.markdown(
                f"**{tool.label}**"
            )
            st.caption(tool.detail)

            if tool.path is not None:
                st.code(
                    str(tool.path),
                    language=None,
                )

        st.caption(
            "Standalone Delphes availability "
            "and the optional MadAnalysis "
            "Delphes reader are separate "
            "capabilities."
        )

        st.caption(
            "Persistent records are stored "
            "under `results/runs/`."
        )

    st.sidebar.info(
        "Validated workflows execute after a "
        "cancellable review window."
    )

    return (
        profile_name,
        selected_profile,
        ollama_host,
        mg5_executable,
        madanalysis_executable,
    )



def _inject_tab_styling() -> None:
    """Make primary Streamlit tabs visually prominent."""

    st.markdown(
        """
        <style>
        /* Container holding the tab buttons. */
        div[data-baseweb="tab-list"] {
            gap: 0.55rem;
            padding: 0.45rem;
            margin-top: 0.35rem;
            margin-bottom: 1rem;
            border: 1px solid rgba(124, 58, 237, 0.30);
            border-radius: 14px;
            background:
                linear-gradient(
                    135deg,
                    rgba(124, 58, 237, 0.10),
                    rgba(37, 99, 235, 0.08)
                );
            box-shadow:
                0 4px 16px rgba(15, 23, 42, 0.10);
            overflow-x: auto;
            scrollbar-width: thin;
        }

        /* Every tab button. */
        button[data-baseweb="tab"] {
            flex: 0 0 auto;
            min-height: 46px;
            padding: 0.55rem 1.15rem !important;
            border: 1px solid rgba(100, 116, 139, 0.30);
            border-radius: 10px;
            background: rgba(30, 41, 59, 0.76);
            font-weight: 700;
            transition:
                transform 0.16s ease,
                box-shadow 0.16s ease,
                border-color 0.16s ease,
                background 0.16s ease;
        }

        /* Improve tab text visibility. */
        button[data-baseweb="tab"] p {
            color: rgba(241, 245, 249, 0.94);
            margin: 0;
            font-size: 0.98rem;
            font-weight: 700;
        }

        /* Hover state. */
        button[data-baseweb="tab"]:hover {
            transform: translateY(-1px);
            border-color: rgba(124, 58, 237, 0.75);
            background: rgba(51, 65, 85, 0.94);
            box-shadow:
                0 5px 14px rgba(79, 70, 229, 0.20);
        }

        /* Active tab. */
        button[data-baseweb="tab"][aria-selected="true"] {
            color: white !important;
            border-color: rgba(99, 102, 241, 1);
            background:
                linear-gradient(
                    135deg,
                    #7c3aed,
                    #2563eb
                );
            box-shadow:
                0 5px 16px rgba(79, 70, 229, 0.38),
                0 0 0 2px rgba(124, 58, 237, 0.12);
        }

        button[data-baseweb="tab"][aria-selected="true"] p {
            color: white !important;
        }

        /* Hide BaseWeb's thin underline because the selected
           tab already has a strong highlighted background. */
        div[data-baseweb="tab-highlight"] {
            display: none;
        }

        @media (max-width: 700px) {
            button[data-baseweb="tab"] {
                min-height: 42px;
                padding: 0.45rem 0.8rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )




def _inject_final_ui_polish() -> None:
    """Improve mode selection, composer, and chat readability."""

    st.markdown(
        """
        <style>
        /* ================================================
           Chat / Build-workflow mode selector
           ================================================ */

        div[data-testid="stSegmentedControl"] {
            padding: 0.55rem;
            margin: 0.35rem 0 1.05rem 0;
            border: 1px solid rgba(99, 102, 241, 0.42);
            border-radius: 16px;
            background:
                linear-gradient(
                    135deg,
                    rgba(30, 41, 59, 0.88),
                    rgba(30, 58, 88, 0.70)
                );
            box-shadow:
                0 8px 24px rgba(2, 6, 23, 0.26);
        }

        div[data-testid="stSegmentedControl"] button {
            min-height: 58px !important;
            padding: 0.75rem 1.65rem !important;
            border-radius: 12px !important;
            font-size: 1.05rem !important;
            font-weight: 800 !important;
            letter-spacing: 0.01em;
            transition:
                transform 0.16s ease,
                box-shadow 0.16s ease,
                background 0.16s ease;
        }

        div[data-testid="stSegmentedControl"] button:hover {
            transform: translateY(-1px);
            box-shadow:
                0 7px 18px rgba(56, 189, 248, 0.20);
        }

        /* Also covers horizontal radio controls if the mode
           selector is implemented using st.radio. */
        div[role="radiogroup"] {
            gap: 0.65rem;
        }

        div[role="radiogroup"] > label {
            min-height: 54px;
            padding: 0.65rem 1.15rem;
            border: 1px solid rgba(99, 102, 241, 0.34);
            border-radius: 12px;
            background: rgba(15, 23, 42, 0.66);
            font-size: 1rem;
            font-weight: 750;
        }

        div[role="radiogroup"] > label:hover {
            border-color: rgba(56, 189, 248, 0.82);
            box-shadow:
                0 5px 16px rgba(56, 189, 248, 0.16);
        }

        /* ================================================
           Request composer
           ================================================ */

        div[data-testid="stForm"] {
            margin-top: 0.8rem;
            padding: 1rem 1rem 0.85rem 1rem;
            border: 1px solid rgba(56, 189, 248, 0.26);
            border-radius: 16px;
            background:
                linear-gradient(
                    145deg,
                    rgba(15, 23, 42, 0.84),
                    rgba(15, 38, 61, 0.64)
                );
            box-shadow:
                0 10px 30px rgba(2, 6, 23, 0.20);
        }

        div[data-testid="stTextArea"] textarea {
            min-height: 108px;
            border: 1px solid rgba(148, 163, 184, 0.34);
            border-radius: 12px;
            background: rgba(2, 6, 23, 0.56);
            font-size: 0.98rem;
            line-height: 1.48;
        }

        div[data-testid="stTextArea"] textarea:focus {
            border-color: rgba(56, 189, 248, 0.92);
            box-shadow:
                0 0 0 2px rgba(56, 189, 248, 0.14);
        }

        /* ================================================
           Chat messages
           ================================================ */

        div[data-testid="stChatMessage"] {
            margin-bottom: 0.55rem;
            padding: 0.25rem 0.45rem;
            border-radius: 14px;
        }

        div[data-testid="stChatMessage"]:has(
            div[data-testid="chatAvatarIcon-user"]
        ) {
            border-left:
                3px solid rgba(56, 189, 248, 0.78);
        }

        div[data-testid="stChatMessage"]:has(
            div[data-testid="chatAvatarIcon-assistant"]
        ) {
            border-left:
                3px solid rgba(168, 85, 247, 0.72);
        }

        /* ================================================
           Buttons and sidebar profile
           ================================================ */

        button[kind="primary"] {
            border-radius: 11px !important;
            font-weight: 750 !important;
            box-shadow:
                0 6px 16px rgba(79, 70, 229, 0.24);
        }

        button[kind="primary"]:hover {
            box-shadow:
                0 8px 22px rgba(56, 189, 248, 0.26);
        }

        div[data-testid="stDownloadButton"] button {
            border-color: rgba(56, 189, 248, 0.28);
            border-radius: 11px;
        }

        div[data-testid="stSidebar"] div[data-baseweb="select"] {
            border-radius: 10px;
        }

        /* Keep expander controls small even though the mode
           selector and primary tabs are prominent. */
        details summary {
            font-weight: 650;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="HEPLocalAgent",
        page_icon="⚛️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    _inject_tab_styling()
    _inject_final_ui_polish()

    _inject_style()
    _initialize_state()

    profiles = load_agent_profiles(
        PROFILES_PATH
    )
    local_paths = load_json_object(
        LOCAL_PATHS_PATH
    )

    (
        profile_name,
        selected_profile,
        ollama_host,
        mg5_executable,
        madanalysis_executable,
    ) = _render_sidebar(
        profiles,
        local_paths,
    )

    profiles[profile_name] = selected_profile

    os.environ["OLLAMA_HOST"] = ollama_host

    st.markdown(
        """
<div class="hep-hero">
    <div class="hep-eyebrow">
        Local · Validated · Auditable
    </div>
    <h1>HEP Workflow Agent</h1>
    <p>
        Translate a natural-language collider request into a
        structured workflow, inspect deterministic corrections,
        approve the exact MadGraph commands, and revisit every
        generated artifact from one provenance record.
    </p>
    <div class="hep-flow" aria-label="Workflow stages">
        <div class="hep-flow-step">
            <span class="hep-flow-number">1</span>
            <div><strong>Describe</strong><small>Physics intent</small></div>
        </div>
        <div class="hep-flow-step">
            <span class="hep-flow-number">2</span>
            <div><strong>Validate</strong><small>Deterministic checks</small></div>
        </div>
        <div class="hep-flow-step">
            <span class="hep-flow-number">3</span>
            <div><strong>Approve</strong><small>Exact commands</small></div>
        </div>
        <div class="hep-flow-step">
            <span class="hep-flow-number">4</span>
            <div><strong>Inspect</strong><small>Results and provenance</small></div>
        </div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    (
        workspace_tab,
        installation_tab,
        history_tab,
    ) = st.tabs(
        [
            "🧰 Workspace",
            "🧪 Test installation",
            "📚 Run history",
        ]
    )

    with installation_tab:
        _render_installation_check(
            profile_name=profile_name,
            ollama_host=ollama_host,
        )

    with workspace_tab:
        with st.expander(
            "Session controls",
            expanded=False,
        ):
            clear_chat_requested = st.button(
                "Clear this conversation",
                use_container_width=True,
                key="clear_chat_history",
            )
            st.caption(
                "This clears only the current browser-session "
                "conversation. Persistent run records and "
                "scientific outputs are not removed."
            )

        if clear_chat_requested:
            st.session_state.session_messages = [
                {
                    "role": "assistant",
                    "content": (
                        "Describe the collider workflow you want. "
                        "I will plan and validate it first, then show "
                        "the exact commands before any HEP software runs."
                    ),
                }
            ]

            st.session_state.request_draft_seed = ""
            st.session_state.request_editor_version += 1

            st.rerun()

        for message_index, message in enumerate(
            st.session_state.session_messages
        ):
            with st.chat_message(
                message["role"]
            ):
                st.markdown(
                    message["content"]
                )

                if message["role"] == "user":
                    with st.expander(
                        "Copy or edit this request",
                        expanded=False,
                    ):
                        st.caption(
                            "Use the copy icon in the "
                            "top-right corner of the text box."
                        )

                        st.code(
                            message["content"],
                            language=None,
                        )

                        if st.button(
                            "✏️ Edit in composer",
                            key=(
                                "edit_user_message_"
                                f"{message_index}"
                            ),
                            use_container_width=True,
                        ):
                            st.session_state[
                                "request_draft_seed"
                            ] = message["content"]

                            st.session_state[
                                "request_editor_version"
                            ] += 1

                            st.rerun()

        prepared = (
            st.session_state.prepared_workflow
        )
        final_result = (
            st.session_state.final_result
        )
        prepared_scan = (
            st.session_state.prepared_scan
        )
        scan_result = (
            st.session_state.scan_result
        )

        if prepared_scan is not None:
            _render_prepared_scan(
                prepared_scan,
                profile_name=profile_name,
                profile=profiles[profile_name],
                mg5_executable=mg5_executable,
                madanalysis_executable=(
                    madanalysis_executable
                ),
            )

        elif prepared is not None:
            _render_prepared(
                prepared,
                profile_name=profile_name,
                mg5_executable=mg5_executable,
                madanalysis_executable=(
                    madanalysis_executable
                ),
            )

        if scan_result is not None:
            _render_scan_result(
                scan_result
            )

        elif final_result is not None:
            _render_final_result(
                final_result
            )

        active_prepared = (
            prepared_scan
            if prepared_scan is not None
            else prepared
        )

        active_final_exists = (
            scan_result is not None
            or final_result is not None
        )

        request_disabled = should_disable_request_input(
            prepared_exists=(
                active_prepared is not None
            ),
            prepared_is_ready=(
                active_prepared.is_ready
                if active_prepared is not None
                else False
            ),
            final_result_exists=(
                active_final_exists
            ),
        )

        if st.session_state.get(
            "reset_request_mode",
            False,
        ):
            st.session_state.request_mode = "Chat"
            st.session_state.reset_request_mode = False

        mode_options = [
            "Chat",
            "Build workflow",
        ]

        if hasattr(
            st,
            "segmented_control",
        ):
            request_mode = st.segmented_control(
                "Message mode",
                options=mode_options,
                key="request_mode",
                disabled=request_disabled,
                label_visibility="collapsed",
            )
        else:
            request_mode = st.radio(
                "Message mode",
                options=mode_options,
                key="request_mode",
                horizontal=True,
                disabled=request_disabled,
                label_visibility="collapsed",
            )

        if request_mode is None:
            request_mode = "Chat"

        if request_mode == "Chat":
            st.caption(
                "💬 Chat mode answers questions and never "
                "starts the simulation pipeline."
            )
            input_placeholder = (
                "Ask a particle-physics question..."
            )
        else:
            st.caption(
                "⚙️ Build-workflow mode sends one complete "
                "request through planning and validation."
            )
            input_placeholder = (
                "Specify process, energy, event count, "
                "and optional pipeline stages..."
            )

        if request_disabled:
            input_placeholder = (
                "Approve or cancel the prepared "
                "workflow first."
            )

        show_starters = (
            not request_disabled
            and len(
                st.session_state.session_messages
            ) == 1
        )

        if show_starters:
            st.markdown("#### Start with an example")
            st.caption(
                "Choose a tested pattern to prefill the editor. "
                "Nothing is submitted or executed automatically."
            )

            starter_columns = st.columns(
                len(STARTER_WORKFLOWS)
            )

            for column, starter in zip(
                starter_columns,
                STARTER_WORKFLOWS,
                strict=True,
            ):
                label, description, starter_prompt = starter

                with column:
                    with st.container(border=True):
                        st.markdown(f"**{label}**")
                        st.caption(description)
                        st.button(
                            "Use this example",
                            key=(
                                "starter_workflow_"
                                + label.lower().replace(
                                    " ",
                                    "_",
                                )
                            ),
                            use_container_width=True,
                            on_click=_seed_starter_workflow,
                            args=(starter_prompt,),
                        )

        draft_version = int(
            st.session_state[
                "request_editor_version"
            ]
        )

        draft_seed = str(
            st.session_state[
                "request_draft_seed"
            ]
        )

        with st.form(
            key=(
                "request_composer_"
                f"{draft_version}"
            ),
            clear_on_submit=False,
        ):
            st.markdown(
                "#### Compose your request"
            )

            st.caption(
                "Ask a particle-physics question in Chat "
                "mode, or describe a simulation in "
                "Build-workflow mode. Press Ctrl+Enter "
                "or click Send request to submit; Enter "
                "starts a new line."
            )

            draft = st.text_area(
                "Request",
                value=draft_seed,
                placeholder=input_placeholder,
                height=118,
                disabled=request_disabled,
                key=(
                    "request_draft_widget_"
                    f"{draft_version}"
                ),
                label_visibility="collapsed",
            )

            submit_column, clear_column = (
                st.columns(
                    [3, 1]
                )
            )

            with submit_column:
                submit_requested = (
                    st.form_submit_button(
                        "Send request  ·  Ctrl+Enter",
                        type="primary",
                        disabled=request_disabled,
                        use_container_width=True,
                    )
                )

            with clear_column:
                clear_requested = (
                    st.form_submit_button(
                        "Clear",
                        disabled=request_disabled,
                        use_container_width=True,
                    )
                )

        if clear_requested:
            st.session_state[
                "request_draft_seed"
            ] = ""

            st.session_state[
                "request_editor_version"
            ] += 1

            st.rerun()

        prompt = (
            draft.strip()
            if submit_requested
            else None
        )

        if submit_requested and not prompt:
            st.warning(
                "Enter a message before submitting."
            )

        if prompt:
            # The next composer starts empty. The current prompt
            # remains available in chat history for copying or
            # editing again.
            st.session_state[
                "request_draft_seed"
            ] = ""

            st.session_state[
                "request_editor_version"
            ] += 1

        if prompt:
            st.session_state.session_messages.append(
                {
                    "role": "user",
                    "content": prompt,
                }
            )

            # The chat history above was rendered before
            # st.chat_input returned this new prompt. Render the
            # submitted message immediately so it remains visible
            # while planning, validation, and repair are running.
            with st.chat_message("user"):
                st.markdown(prompt)

            if request_mode == "Chat":
                chat_status = st.status(
                    "Answering conversationally...",
                    expanded=True,
                )

                try:
                    chat_answer = answer_chat(
                        prompt,
                        client=OllamaClient(),
                        model=profiles[profile_name].primary_model,
                        history=(
                            st.session_state
                            .session_messages[:-1]
                        ),
                        timeout_seconds=180,
                    )

                    assistant_content = (
                        chat_answer.content
                    )

                    if chat_answer.model is None:
                        status_label = (
                            "Answered without starting "
                            "a simulation workflow."
                        )
                    else:
                        duration = (
                            chat_answer.duration_seconds
                        )

                        duration_text = (
                            f" in {duration:.1f} s"
                            if duration is not None
                            else ""
                        )

                        status_label = (
                            "Conversational response "
                            f"completed with "
                            f"{chat_answer.model}"
                            f"{duration_text}."
                        )

                    chat_status.update(
                        label=status_label,
                        state="complete",
                        expanded=False,
                    )

                except Exception as exc:
                    assistant_content = (
                        "I recognized this as a conversational "
                        "message rather than a simulation request, "
                        "but the conversational model could not "
                        f"respond: {exc}"
                    )

                    chat_status.update(
                        label=(
                            "Conversational response failed."
                        ),
                        state="error",
                        expanded=True,
                    )

                st.session_state.session_messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_content,
                    }
                )

                with st.chat_message("assistant"):
                    st.markdown(
                        assistant_content
                    )

                st.stop()

            # Build-workflow mode applies to one submitted message.
            # Reset to Chat on the next Streamlit rerun.
            st.session_state.reset_request_mode = True

            minimum_report = (
                validate_workflow_request_minimum(
                    prompt
                )
            )

            if not minimum_report.is_valid:
                issue_lines = "\n".join(
                    f"- {issue.message}"
                    for issue in minimum_report.errors
                )

                assistant_content = (
                    "I did not start the simulation pipeline "
                    "because the workflow request is incomplete.\n\n"
                    f"{issue_lines}\n\n"
                    "Select **Build workflow** again after adding "
                    "the missing information."
                )

                st.session_state.session_messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_content,
                    }
                )

                with st.chat_message("assistant"):
                    st.warning(
                        assistant_content
                    )

                st.stop()

            st.session_state.prepared_workflow = None
            st.session_state.final_result = None
            st.session_state.prepared_scan = None
            st.session_state.scan_result = None
            st.session_state.scan_run_id = None
            st.session_state.agent_activity_events = []
            _clear_approval_countdown()

            status = st.status(
                "Planning and validating request...",
                expanded=True,
            )

            def progress_observer(
                event: Any,
            ) -> None:
                payload = (
                    _agent_activity_payload(
                        event
                    )
                )

                st.session_state[
                    "agent_activity_events"
                ].append(payload)

                status.write(
                    _format_agent_activity(
                        payload
                    )
                )

            try:
                scan_prepared = prepare_energy_scan(
                    prompt,
                    client=OllamaClient(),
                    profile=profiles[
                        profile_name
                    ],
                )

                if scan_prepared is not None:
                    st.session_state.prepared_scan = (
                        scan_prepared
                    )

                    if scan_prepared.is_ready:
                        status.update(
                            label=(
                                "Energy scan prepared and "
                                "ready for approval."
                            ),
                            state="complete",
                            expanded=False,
                        )

                        st.session_state.session_messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    "The energy scan was planned "
                                    "once and expanded into a "
                                    "deterministic point grid. "
                                    "Review the complete scan below."
                                ),
                            }
                        )
                    else:
                        status.update(
                            label=(
                                "The energy scan could not be "
                                "prepared safely."
                            ),
                            state="error",
                            expanded=True,
                        )

                        st.session_state.session_messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    "The scan request was detected, "
                                    "but preparation failed. The "
                                    "failure details are shown below."
                                ),
                            }
                        )

                else:
                    prepared = prepare_end_to_end(
                        prompt,
                        client=OllamaClient(),
                        profile_name=profile_name,
                        profile=profiles[
                            profile_name
                        ],
                        records_directory=(
                            RECORDS_DIRECTORY
                        ),
                        progress_observer=(
                            progress_observer
                        ),
                    )

                    st.session_state.prepared_workflow = (
                        prepared
                    )

                    if prepared.is_ready:
                        status.update(
                            label=(
                                "Workflow prepared and "
                                "ready for approval."
                            ),
                            state="complete",
                            expanded=False,
                        )

                        st.session_state.session_messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    "The request was planned "
                                    "and validated. Review the "
                                    "exact workflow below before "
                                    "execution."
                                ),
                            }
                        )
                    else:
                        status.update(
                            label=(
                                "The request could not be "
                                "prepared safely."
                            ),
                            state="error",
                            expanded=True,
                        )

                        st.session_state.session_messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    "The request was not ready "
                                    "for execution. Its failure "
                                    "details are shown below."
                                ),
                            }
                        )

            except Exception as exc:
                status.update(
                    label=(
                        "Planning failed before a "
                        "workflow could be prepared."
                    ),
                    state="error",
                    expanded=True,
                )

                st.session_state.session_messages.append(
                    {
                        "role": "assistant",
                        "content": (
                            "Planning failed: "
                            f"`{type(exc).__name__}: "
                            f"{exc}`"
                        ),
                    }
                )

            st.rerun()

    with history_tab:
        st.subheader(
            "Run history"
        )

        history = load_run_history(
            RECORDS_DIRECTORY,
            limit=100,
        )

        if history:
            with st.expander(
                "History maintenance",
                expanded=False,
            ):
                st.warning(
                    "Clearing the displayed history archives "
                    "the JSON provenance records. Generated "
                    "events, execution directories, analyses, "
                    "plots, and scan outputs are not deleted."
                )

                archive_confirmed = st.checkbox(
                    "I understand that the run records will "
                    "be moved out of the active history.",
                    key="confirm_archive_run_history",
                )

                archive_requested = st.button(
                    "Archive and clear run history",
                    disabled=not archive_confirmed,
                    use_container_width=True,
                    key="archive_run_history",
                )

                if archive_requested:
                    try:
                        (
                            archive_directory,
                            archived_count,
                        ) = archive_run_history(
                            RECORDS_DIRECTORY,
                            (
                                PROJECT_ROOT
                                / "results"
                                / "archive"
                                / "run_history"
                            ),
                        )

                    except Exception as exc:
                        st.error(
                            "Run-history archiving failed. "
                            "Existing records were restored."
                        )

                        st.code(
                            (
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                            language=None,
                        )

                    else:
                        if archived_count:
                            st.success(
                                f"Archived {archived_count} "
                                "run record(s)."
                            )

                            if archive_directory is not None:
                                st.caption(
                                    "Archive location:"
                                )

                                st.code(
                                    str(
                                        archive_directory
                                    ),
                                    language=None,
                                )

                        history = load_run_history(
                            RECORDS_DIRECTORY,
                            limit=100,
                        )

        if not history:
            st.info(
                "No persistent run records were found."
            )

        else:
            selected_label = st.selectbox(
                "Choose a previous run",
                options=[
                    entry.label
                    for entry in history
                ],
            )

            selected = next(
                entry
                for entry in history
                if entry.label == selected_label
            )

            _render_history_entry(
                selected
            )

            st.caption(
                "History records are persistent. They are "
                "displayed for review but are not automatically "
                "inserted into later model prompts."
            )


if __name__ == "__main__":
    main()
