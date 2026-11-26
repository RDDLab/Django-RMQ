#!/bin/bash
set -euo pipefail
umask 077

if (( $# != 1 )) || [[ ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
    echo 'Expected a full workflow commit SHA.' >&2
    exit 1
fi

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base_dir="$HOME/.local/share/django-rmq-docs"
install_dir="$base_dir/$1"

mkdir -p -- "$base_dir"
staging_dir=$(mktemp -d "$base_dir/.prepare.XXXXXXXX")
trap 'rm -rf -- "$staging_dir"' EXIT

bash -n "$source_dir/deploy-docs.sh"
install -m 0700 "$source_dir/deploy-docs.sh" "$staging_dir/deploy-docs.sh"
install -m 0600 "$source_dir/compose.yml" "$source_dir/compose.network.yml" "$staging_dir/"

exec 9>"$base_dir/prepare.lock"
flock -w 60 9
if [[ -e "$install_dir" ]]; then
    if ! cmp -s "$staging_dir/deploy-docs.sh" "$install_dir/deploy-docs.sh" ||
       ! cmp -s "$staging_dir/compose.yml" "$install_dir/compose.yml" ||
       ! cmp -s "$staging_dir/compose.network.yml" "$install_dir/compose.network.yml"; then
        echo 'Prepared deployment files do not match this workflow revision.' >&2
        exit 1
    fi
else
    mv -- "$staging_dir" "$install_dir"
fi

printf 'Prepared documentation deployment files for %s.\n' "$1"
