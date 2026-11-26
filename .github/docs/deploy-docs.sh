#!/bin/bash
set -euo pipefail
umask 077

ipv4_octet='(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])'
if (( $# != 3 )) || [[ ! "$1" =~ ^[0-9a-f]{40}$ || ! "$2" =~ ^[0-9]+-[0-9]+$ ||
      ! "$3" =~ ^($ipv4_octet\.){3}$ipv4_octet$ ]]; then
    echo 'Expected a full commit SHA, workflow run and attempt, and IPv4 address.' >&2
    exit 1
fi
sha=$1
export DOCS_IP=$3
image_build="$sha $2"

state_dir="$HOME/.local/state/django-rmq-docs"
deploy_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Use a rootless socket when SSH did not start a session and Docker has no custom context.
docker_socket="/run/user/$(id -u)/docker.sock"
if [[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" && -S "$docker_socket" ]] &&
   [[ "$(docker context show)" == default ]]; then
    export DOCKER_HOST="unix://$docker_socket"
fi

mkdir -p "$state_dir"
exec 9>"$state_dir/deploy.lock"
echo 'Waiting for the documentation deployment lock.'
flock -w 300 9

compose() {
    docker compose --project-name django-rmq-docs --env-file /dev/null \
        --file "$deploy_dir/compose.yml" --file "$deploy_dir/compose.network.yml" "$@"
}

cleanup() {
    local status=$?
    trap - EXIT
    trap '' HUP INT TERM

    if [[ "$restore_service" == true ]]; then
        echo 'Deployment failed. Restoring the previous documentation service.' >&2
        if [[ -n "$previous_image" ]]; then
            export DOCS_IMAGE=django-rmq-docs:rollback DOCS_IP="${previous_ip:-$DOCS_IP}"
            if ! { docker image tag "$previous_image" "$DOCS_IMAGE" && compose up --detach --no-build --wait --wait-timeout 60; }; then
                echo 'Could not restore the previous documentation image.' >&2
            fi
        else
            compose down || echo 'Could not remove the failed documentation container.' >&2
        fi
    fi

    exit "$status"
}

restore_service=false
previous_image=''
previous_ip=''
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

export DOCS_IMAGE=django-rmq-docs:"$sha"
if ! docker network inspect docs_net >/dev/null; then
    echo 'The external Docker network docs_net must exist on the documentation server.' >&2
    exit 1
fi

previous_container=$(compose ps --all --quiet docs)
if [[ -n "$previous_container" ]]; then
    previous_ip=$(docker inspect --format '{{with index .NetworkSettings.Networks "docs_net"}}{{if and .IPAMConfig .IPAMConfig.IPv4Address}}{{.IPAMConfig.IPv4Address}}{{else}}{{.IPAddress}}{{end}}{{end}}' "$previous_container")
    previous_image=$(docker inspect --format '{{.Image}}' "$previous_container")
fi

echo 'Loading the documentation image built by GitHub Actions.'
docker image load --quiet
image_labels='{{index .Config.Labels "org.opencontainers.image.revision"}} {{index .Config.Labels "org.rddlab.docs.workflow-run"}}'
if [[ "$(docker image inspect --format "$image_labels" "$DOCS_IMAGE")" != "$image_build" ]]; then
    echo 'The loaded documentation image does not match the requested revision and workflow run.' >&2
    exit 1
fi

echo 'Starting the documentation container and checking readiness.'
restore_service=true
compose up --detach --no-build --wait --wait-timeout 60
running_container=$(compose ps --quiet docs)
if [[ -z "$running_container" ]] ||
   [[ "$(docker inspect --format "$image_labels {{.State.Health.Status}}" "$running_container")" != "$image_build healthy" ]]; then
    echo 'The new documentation image did not become healthy.' >&2
    exit 1
fi
restore_service=false
echo "Deployed documentation from $sha."
