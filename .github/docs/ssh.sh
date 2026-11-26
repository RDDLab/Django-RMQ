#!/bin/bash
set -euo pipefail

if [[ ! "${SSH_HOST:-}" =~ ^[[:alnum:].:-]+$ ||
      ! "${SSH_PORT:-}" =~ ^[1-9][0-9]{0,4}$ ]] ||
   (( SSH_PORT > 65535 )) ||
   [[ ! "${SSH_USER:-}" =~ ^[a-z_][a-z0-9_-]*$ ||
      -z "${SSH_PRIVATE_KEY:-}" || ! "${SSH_HOST_KEY:-}" =~ ^ssh-ed25519[[:blank:]]+[A-Za-z0-9+/]+=*$ ]]; then
    echo 'Invalid or missing docs-production SSH settings.' >&2
    exit 1
fi

umask 077
ssh_dir=$(mktemp -d)
trap 'rm -rf -- "$ssh_dir"' EXIT
printf '%s\n' "$SSH_PRIVATE_KEY" > "$ssh_dir/key"
known_host=$SSH_HOST
if (( SSH_PORT != 22 )); then
    known_host="[$SSH_HOST]:$SSH_PORT"
fi
printf '%s %s\n' "$known_host" "$SSH_HOST_KEY" > "$ssh_dir/known_hosts"
unset SSH_PRIVATE_KEY

ssh -F /dev/null -T -p "$SSH_PORT" -l "$SSH_USER" -i "$ssh_dir/key" \
    -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    -o "UserKnownHostsFile=$ssh_dir/known_hosts" -o GlobalKnownHostsFile=/dev/null \
    -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -- "$SSH_HOST" "$@"
