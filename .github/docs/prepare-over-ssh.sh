#!/bin/bash
set -euo pipefail

if (( $# != 1 )) || [[ ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
    echo 'Expected a full workflow commit SHA.' >&2
    exit 1
fi

docs_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
remote_command=$(cat <<'SH'
set -eu
upload_dir=$(mktemp -d)
trap 'rm -rf -- "$upload_dir"' EXIT
tar -xf - -C "$upload_dir" -- prepare-server.sh deploy-docs.sh compose.yml compose.network.yml
bash "$upload_dir/prepare-server.sh" "$DOCS_WORKFLOW_SHA" >&2
uname -m
SH
)
tar -C "$docs_dir" -cf - prepare-server.sh deploy-docs.sh compose.yml compose.network.yml |
    bash "$docs_dir/ssh.sh" "export DOCS_WORKFLOW_SHA=$1; $remote_command"
