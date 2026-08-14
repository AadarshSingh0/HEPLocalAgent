#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

exec "${ROOT}/scripts/uninstall_independent_hep_agent.sh" "$@"
