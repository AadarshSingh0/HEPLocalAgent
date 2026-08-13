#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec "${ROOT}/scripts/bootstrap_independent_hep_agent.sh" "$@"
