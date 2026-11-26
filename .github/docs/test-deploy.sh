#!/bin/bash
set -euo pipefail

docs_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
sha=0123456789abcdef0123456789abcdef01234567
workflow_run=100-1
docs_ip=172.30.10.10
expected='Expected a full commit SHA, workflow run and attempt, and IPv4 address.'
reject_deploy_arguments() {
    local output
    if output=$(bash "$docs_dir/deploy-docs.sh" "$@" 2>&1) || [[ "$output" != "$expected" ]]; then
        echo 'The deployment script accepted invalid arguments.' >&2
        exit 1
    fi
}
reject_deploy_arguments "$sha" "$workflow_run"
reject_deploy_arguments bad-sha "$workflow_run" "$docs_ip"
reject_deploy_arguments "$sha" invalid-run "$docs_ip"
reject_deploy_arguments "$sha" "$workflow_run" '172.300.10.10'
reject_deploy_arguments "$sha" "$workflow_run" "$docs_ip" extra

if command -v flock >/dev/null; then
    test_home=$(mktemp -d)
    trap 'rm -rf -- "$test_home"' EXIT
    mkdir "$test_home/bin"
    cat > "$test_home/bin/ssh" <<'SH'
#!/bin/bash
set -euo pipefail
exec bash -c "${@: -1}"
SH
    chmod +x "$test_home/bin/ssh"

    for _ in 1 2; do
        HOME="$test_home" PATH="$test_home/bin:$PATH" SSH_HOST=docs.example.invalid SSH_PORT=22 \
            SSH_USER=deploy SSH_PRIVATE_KEY=mock SSH_HOST_KEY='ssh-ed25519 AAAA' \
            bash "$docs_dir/prepare-over-ssh.sh" "$sha"
    done
    prepared="$test_home/.local/share/django-rmq-docs/$sha"
    cmp -s "$docs_dir/deploy-docs.sh" "$prepared/deploy-docs.sh"
    cmp -s "$docs_dir/compose.yml" "$prepared/compose.yml"
    cmp -s "$docs_dir/compose.network.yml" "$prepared/compose.network.yml"

    cat > "$test_home/bin/docker" <<'SH'
#!/bin/bash
set -euo pipefail

case "$1 $2" in
    'network inspect')
        [[ "$*" == 'network inspect docs_net' && "$TEST_NETWORK_EXISTS" == true ]]
        ;;
    'image load')
        [[ "$*" == 'image load --quiet' ]]
        [[ "$(gzip -dc)" == "$TEST_LOADED_RUN" ]]
        ;;
    'image inspect')
        printf '%s %s\n' "$TEST_DOCS_SHA" "$TEST_LOADED_RUN"
        ;;
    'image tag')
        [[ "$3" == previous-image && "$4" == *:rollback ]]
        ;;
    'compose --project-name')
        shift 7
        [[ "$1" == --file && "$2" == */compose.network.yml && -n "$DOCS_IP" ]]
        shift 2
        case "$*" in
            'ps --all --quiet docs')
                if [[ "$TEST_HEALTH" != healthy ]]; then
                    printf '%s\n' previous
                fi
                ;;
            'up --detach --no-build --wait --wait-timeout 60')
                if [[ "$DOCS_IMAGE" == *:rollback ]]; then
                    [[ "$DOCS_IP" == "${TEST_PREVIOUS_IP:-$TEST_DOCS_IP}" ]]
                    touch "$HOME/container-restored"
                else
                    [[ "$DOCS_IP" == "$TEST_DOCS_IP" ]]
                    touch "$HOME/container-started"
                fi
                ;;
            'ps --quiet docs') printf '%s\n' docs ;;
            *) exit 1 ;;
        esac
        ;;
    'inspect --format')
        case "$3 $4" in
            *NetworkSettings*' previous') printf '%s\n' "$TEST_PREVIOUS_IP" ;;
            '{{.Image}} previous') printf '%s\n' previous-image ;;
            *' previous') exit 1 ;;
            *) printf '%s %s %s\n' "$TEST_DOCS_SHA" "$TEST_LOADED_RUN" "$TEST_HEALTH" ;;
        esac
        ;;
    *) exit 1 ;;
esac
SH
    chmod +x "$test_home/bin/docker"

    deploy_test_image() {
        printf '%s' "$1" | gzip -1 |
            HOME="$test_home" PATH="$test_home/bin:$PATH" DOCKER_CONTEXT=docs-test \
                TEST_DOCS_SHA="$sha" TEST_LOADED_RUN="$1" TEST_HEALTH="$2" \
                TEST_NETWORK_EXISTS="${TEST_NETWORK_EXISTS:-true}" TEST_DOCS_IP="$docs_ip" \
                TEST_PREVIOUS_IP="${TEST_PREVIOUS_IP:-}" \
                bash "$prepared/deploy-docs.sh" "$sha" "$workflow_run" "$docs_ip"
    }

    if TEST_NETWORK_EXISTS=false deploy_test_image "$workflow_run" healthy || [[ -e "$test_home/container-started" ]]; then
        echo 'The deployment accepted a missing external network.' >&2
        exit 1
    fi
    if deploy_test_image 100-2 healthy || [[ -e "$test_home/container-started" ]]; then
        echo 'An unexpected image reached the documentation service.' >&2
        exit 1
    fi
    deploy_test_image "$workflow_run" healthy
    test -e "$test_home/container-started"
    for previous_ip in '' 172.30.10.11; do
        rm -f "$test_home/container-restored"
        if TEST_PREVIOUS_IP="$previous_ip" deploy_test_image "$workflow_run" unhealthy; then
            echo 'The deployment accepted an unhealthy documentation container.' >&2
            exit 1
        fi
        test -e "$test_home/container-restored"
    done
fi

export DOCS_IMAGE=django-rmq-docs:test
compose_config() {
    docker compose --env-file /dev/null --file "$docs_dir/compose.yml" "$@" config --format json
}

compose_config | jq -e '(.services.docs.ports // []) | length == 0' >/dev/null

DOCS_IP="$docs_ip" compose_config --file "$docs_dir/compose.network.yml" |
    jq -e --arg ip "$docs_ip" '
        ((.services.docs.ports // []) | length == 0) and
        .networks.docs_net.external == true and .networks.docs_net.name == "docs_net" and
        .services.docs.networks.docs_net.ipv4_address == $ip
    ' >/dev/null

if DOCS_IP='' compose_config --file "$docs_dir/compose.network.yml" >/dev/null 2>&1; then
    echo 'Compose accepted a missing documentation container IP.' >&2
    exit 1
fi
