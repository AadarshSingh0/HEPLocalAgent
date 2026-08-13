#!/usr/bin/env bash

# Shared ownership checks for retrying an interrupted clone-owned installation.
# This file is sourced by the independent installer and the Darwin builder.

managed_stack_marker_content() {
    local project_root="$1" stack_root="$2"
    printf '%s\n' \
        'hep-local-agent-installer-ownership-v1' \
        "repository_root=${project_root}" \
        "stack_root=${stack_root}"
}

validate_managed_stack_boundary() {
    local project_root="$1" stack_root="$2" resolved_project resolved_stack
    resolved_project="$(cd -- "${project_root}" && pwd -P)" || return 2
    [[ "${project_root}" == "${resolved_project}" ]] || {
        echo "Refusing ambiguous repository path: ${project_root}" >&2
        return 2
    }
    [[ "${stack_root}" == "${resolved_project}/.hep-stack" ]] || {
        echo "Refusing managed stack outside the current clone: ${stack_root}" >&2
        return 2
    }
    if [[ -L "${stack_root}" ]]; then
        echo "Refusing symlinked managed stack boundary: ${stack_root}" >&2
        return 2
    fi
    if [[ -e "${stack_root}" ]]; then
        [[ -d "${stack_root}" ]] || {
            echo "Refusing non-directory managed stack boundary: ${stack_root}" >&2
            return 2
        }
        resolved_stack="$(cd -- "${stack_root}" && pwd -P)" || return 2
        [[ "${resolved_stack}" == "${stack_root}" ]] || {
            echo "Refusing managed stack that resolves outside the current clone: ${resolved_stack}" >&2
            return 2
        }
    fi
}

initialize_managed_stack_ownership() {
    local project_root="$1" stack_root="$2" marker actual expected temporary
    validate_managed_stack_boundary "${project_root}" "${stack_root}" || return
    marker="${stack_root}/.installer-ownership"
    expected="$(managed_stack_marker_content "${project_root}" "${stack_root}")"

    if [[ -e "${stack_root}" && ! -e "${marker}" ]]; then
        if find "${stack_root}" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
            echo "Refusing unowned existing managed stack: ${stack_root}" >&2
            return 2
        fi
    fi
    mkdir -p -- "${stack_root}"
    if [[ -L "${marker}" || ( -e "${marker}" && ! -f "${marker}" ) ]]; then
        echo "Refusing ambiguous installer ownership marker: ${marker}" >&2
        return 2
    fi
    if [[ -f "${marker}" ]]; then
        actual="$(<"${marker}")"
        [[ "${actual}" == "${expected}" ]] || {
            echo "Refusing managed stack with mismatched installer ownership: ${marker}" >&2
            return 2
        }
        return 0
    fi

    temporary="${marker}.new.$$"
    umask 077
    managed_stack_marker_content "${project_root}" "${stack_root}" >"${temporary}"
    mv -- "${temporary}" "${marker}"
}

validate_managed_stack_ownership() {
    local project_root="$1" stack_root="$2" marker actual expected
    validate_managed_stack_boundary "${project_root}" "${stack_root}" || return
    marker="${stack_root}/.installer-ownership"
    [[ -f "${marker}" && ! -L "${marker}" ]] || {
        echo "Refusing unowned or ambiguous managed stack: ${stack_root}" >&2
        return 2
    }
    expected="$(managed_stack_marker_content "${project_root}" "${stack_root}")"
    actual="$(<"${marker}")"
    [[ "${actual}" == "${expected}" ]] || {
        echo "Refusing managed stack owned by another checkout: ${stack_root}" >&2
        return 2
    }
}

recover_incomplete_managed_stack() {
    local project_root="$1" stack_root="$2" child recovered=0
    validate_managed_stack_ownership "${project_root}" "${stack_root}" || return
    if [[ -e "${stack_root}/manifest.json" ]]; then
        echo "Refusing recovery because manifest.json exists: ${stack_root}/manifest.json" >&2
        return 2
    fi

    # These are the only component paths created by the installer. Downloads
    # and the ownership marker are deliberately absent from this allowlist.
    for child in \
        miniforge runtime conda-pkgs root madgraph pythia8 hepmc2 delphes \
        madanalysis5 mg5amc_py8_interface launchers build logs; do
        if [[ -e "${stack_root}/${child}" || -L "${stack_root}/${child}" ]]; then
            rm -rf -- "${stack_root:?}/${child}"
            recovered=1
        fi
    done
    if [[ -e "${stack_root}/condarc" || -L "${stack_root}/condarc" ]]; then
        rm -f -- "${stack_root:?}/condarc"
        recovered=1
    fi
    if (( recovered )); then
        echo "Recovered incomplete clone-owned installation; verified downloads were preserved."
    fi
}
