#!/usr/bin/env bash
# Install the reviewed SkyBeat agent package without accepting credentials on the command line.
set -euo pipefail

usage() {
    printf '%s\n' 'usage: sudo ./scripts/install-agent.sh <agent-source-directory> <protected-env-file>' >&2
}

fail() {
    printf '%s\n' "install-agent: $1" >&2
    exit 1
}

for argument in "$@"; do
    case "$argument" in
        --token | --credential | --secret | --token=* | --credential=* | --secret=*)
            fail 'credential command-line arguments are not accepted'
            ;;
    esac
done

[[ "$#" -eq 2 ]] || {
    usage
    exit 64
}

source_dir="$1"
environment_file="$2"
script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(dirname -- "$script_dir")"
unit_source="$repository_root/deployment/systemd/skybeat-agent.service"

[[ -d "$source_dir" ]] || fail 'agent source directory is invalid'
[[ -f "$source_dir/pyproject.toml" ]] || fail 'agent source directory is invalid'
[[ -f "$source_dir/requirements.lock" ]] || fail 'agent source directory is invalid'
[[ -d "$source_dir/src/skybeat_agent" ]] || fail 'agent source directory is invalid'
[[ -f "$environment_file" ]] || fail 'protected environment file is missing'
[[ -f "$unit_source" ]] || fail 'committed systemd unit is missing'
[[ "${EUID}" -eq 0 ]] || fail 'run this installer as root'
command -v python3.12 >/dev/null 2>&1 || fail 'python3.12 is required'
command -v systemctl >/dev/null 2>&1 || fail 'systemctl is required'

if ! id -u skybeat >/dev/null 2>&1; then
    if getent group skybeat >/dev/null 2>&1; then
        useradd --system --gid skybeat --no-create-home --shell /usr/sbin/nologin skybeat
    else
        useradd --system --user-group --no-create-home --shell /usr/sbin/nologin skybeat
    fi
fi

install -d -m 0755 -o skybeat -g skybeat /opt/skybeat
install -d -m 0755 -o root -g root /etc/skybeat-agent

if [[ ! -x /opt/skybeat/venv/bin/python ]]; then
    python3.12 -m venv /opt/skybeat/venv
fi

/opt/skybeat/venv/bin/python -m pip install --no-cache-dir --require-hashes -r "$source_dir/requirements.lock"
/opt/skybeat/venv/bin/python -m pip install --no-deps "$source_dir"
install -m 0600 -o root -g root "$environment_file" /etc/skybeat-agent/agent.env
install -m 0644 -o root -g root "$unit_source" /etc/systemd/system/skybeat-agent.service
systemctl daemon-reload
systemctl enable --now skybeat-agent.service
