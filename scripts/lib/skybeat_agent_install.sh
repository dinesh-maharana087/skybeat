#!/usr/bin/env bash
fail() { printf '%s\n' "install-agent: $1" >&2; exit 1; }
config_dir=/etc/skybeat; config_file=/etc/skybeat/agent.env; opt_dir=/opt/skybeat; venv_dir=/opt/skybeat/venv; state_dir=/var/lib/skybeat
unit_source="$release_dir/deployment/systemd/skybeat-agent.service"
release_verifier="$release_dir/verify-agent-release.py"
server_validator="$release_dir/validate-agent-server-url.py"
install_outcome=FAILED; verification_token=''; existing_sha256=''; package_version=''
regular() { [[ -f "$1" && ! -L "$1" ]]; }
installed_sha256() { regular "$opt_dir/VERSION" || return 1; local value; value="$(sed -n 's/^sha256=//p' "$opt_dir/VERSION" | head -n 1)"; [[ "$value" =~ ^[0-9a-f]{64}$ ]] || return 1; printf '%s\n' "$value"; }
installation_is_current() { local installed; installed="$(installed_sha256 || true)"; [[ "$installed" == "$expected_sha256" && -x "$venv_dir/bin/skybeat-agent" && -f /etc/systemd/system/skybeat-agent.service && ! -L /etc/systemd/system/skybeat-agent.service ]] && systemctl is-active --quiet skybeat-agent.service; }
preflight() { [[ ${EUID:-1} -eq 0 ]] || fail 'run as root'; . /etc/os-release; [[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04 && $(uname -m) == x86_64 ]] || fail 'Ubuntu 24.04 amd64 is required'; command -v python3.12 >/dev/null && command -v curl >/dev/null && command -v sha256sum >/dev/null && command -v systemctl >/dev/null || fail 'required command is missing'; regular "$package" && regular "$lockfile" && [[ -d "$wheelhouse" && ! -L "$wheelhouse" ]] && regular "$unit_source" && regular "$release_verifier" && regular "$server_validator" && regular "$release_dir/agent-updater.py" && regular "$release_dir/deployment/systemd/skybeat-updater.service" && regular "$release_dir/deployment/systemd/skybeat-updater.timer" || fail 'release input is invalid'; [[ "$expected_sha256" =~ ^[0-9a-f]{64}$ ]] || fail 'expected sha256 is invalid'; local server_arguments=(--server "$server"); [[ $allow_insecure_local_server -eq 0 ]] || server_arguments+=(--allow-insecure-local-server); python3.12 "$server_validator" "${server_arguments[@]}" >/dev/null 2>&1 || fail 'agent server origin is invalid'; [[ -z "$token_file" || -f "$token_file" && ! -L "$token_file" ]] || fail 'enrollment token file is invalid'; }
preflight_config() {
    [[ ! -L "$opt_dir" && ! -L "$state_dir" && ! -L "$config_dir" ]] || fail 'agent directories must not be symlinks'
    local directory mode
    for directory in "$opt_dir" "$state_dir" "$config_dir"; do
        [[ ! -e "$directory" ]] && continue
        mode="$(stat -c %a "$directory")"
        [[ $(stat -c %u "$directory") == 0 && "$mode" =~ ^[0-7]{3,4}$ ]] && (( (8#$mode & 8#22) == 0 )) || fail 'agent directory permissions are invalid'
    done
    [[ ! -e "$config_file" ]] && return 0
    regular "$config_file" || fail 'protected agent configuration is invalid'
    [[ $(stat -c %u "$config_file") == 0 && $(stat -c %a "$config_file") == 600 ]] || fail 'protected agent configuration permissions are invalid'
    if [[ $re_enroll -eq 0 ]]; then
        local configured_server
        configured_server="$(sed -n 's/^SKYBEAT_SERVER_URL=//p' "$config_file" | head -n 1)"
        [[ "$configured_server" == "$server" ]] || fail 'server URL differs from the protected agent configuration'
    fi
}
verify_package() { [[ $(sha256sum "$package" | awk '{print $1}') == "$expected_sha256" ]] || fail 'package sha256 mismatch'; python3.12 "$release_verifier" --bundle "$(dirname "$package")" >/dev/null || fail 'release bundle verification failed'; package_version="$(python3.12 - "$package" <<'PY'
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    metadata = next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))
    for line in archive.read(metadata).decode('utf-8').splitlines():
        if line.startswith('Version: '):
            print(line.removeprefix('Version: '))
            break
    else:
        raise SystemExit(1)
PY
)" || fail 'package version is invalid'; }
install_package() {
    install -d -m 0755 -o root -g root "$opt_dir" "$state_dir" "$config_dir"
    [[ ! -e "$state_dir/install.marker" ]] || fail 'an interrupted install requires local recovery before another install'
    [[ ! -L "$opt_dir/venv.new" && ! -L "$venv_dir" && ! -L "$opt_dir/venv.previous" ]] || fail 'agent environment symlink is invalid'
    rm -rf -- "$opt_dir/venv.new"
    python3.12 -m venv "$opt_dir/venv.new"
    "$opt_dir/venv.new/bin/python" -m pip install --no-index --find-links "$wheelhouse" --require-hashes -r "$lockfile"
    "$opt_dir/venv.new/bin/python" -m pip install --no-index --no-deps "$package"
    [[ $("$opt_dir/venv.new/bin/python" -c 'from importlib.metadata import version; print(version("skybeat-agent"))') == "$package_version" ]] || fail 'staged package version mismatch'
}
write_install_marker() {
    local phase="$1" temp="$state_dir/.install.marker.new"
    (umask 077; printf 'phase=%s\ntarget_sha256=%s\nprevious_sha256=%s\nwas_active=%s\nwas_enabled=%s\n' "$phase" "$expected_sha256" "$existing_sha256" "$was_active" "$was_enabled" >"$temp")
    mv -f -- "$temp" "$state_dir/install.marker"
    sync -f "$state_dir/install.marker" "$state_dir"
}
verify_agent_config() {
    local interpreter="$1"
    "$interpreter" - "$config_file" <<'PY'
import sys
from skybeat_agent.config import Config

values = {}
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#"):
        key, separator, value = line.partition("=")
        if not separator or not key.startswith("SKYBEAT_"):
            raise SystemExit(1)
        values[key] = value.strip('"')
Config.from_env(values)
PY
}
verify_local_health() {
    local expected_version="$1" first_pid first_restarts second_pid second_restarts actual
    verify_agent_config "$venv_dir/bin/python" || return 1
    actual="$("$venv_dir/bin/python" -c 'from importlib.metadata import version; print(version("skybeat-agent"))')" || return 1
    [[ "$actual" == "$expected_version" ]] || return 1
    systemctl is-active --quiet skybeat-agent.service || return 1
    first_pid="$(systemctl show skybeat-agent.service -p MainPID --value)"
    first_restarts="$(systemctl show skybeat-agent.service -p NRestarts --value)"
    [[ "$first_pid" =~ ^[1-9][0-9]*$ ]] || return 1
    sleep 15
    systemctl is-active --quiet skybeat-agent.service || return 1
    second_pid="$(systemctl show skybeat-agent.service -p MainPID --value)"
    second_restarts="$(systemctl show skybeat-agent.service -p NRestarts --value)"
    [[ "$first_pid" == "$second_pid" && "$first_restarts" == "$second_restarts" ]]
}
switch_package() {
    was_active=0 was_enabled=0 switch_started=0
    [[ ! -e "$venv_dir" ]] || { systemctl is-active --quiet skybeat-agent.service && was_active=1 || true; systemctl is-enabled --quiet skybeat-agent.service && was_enabled=1 || true; }
    [[ ! -e "$venv_dir" || $was_active -eq 1 ]] || fail 'existing agent service must be active for an upgrade'
    [[ ! -e "$opt_dir/venv.candidate" ]] || fail 'interrupted agent switch requires recovery'
    [[ ! -e "$opt_dir/VERSION" ]] || cp -p -- "$opt_dir/VERSION" "$opt_dir/VERSION.candidate"
    [[ ! -e /etc/systemd/system/skybeat-agent.service ]] || cp -p -- /etc/systemd/system/skybeat-agent.service "$state_dir/skybeat-agent.service.candidate"
    write_install_marker STAGED
    switch_started=1
    write_install_marker SWITCHING
    [[ $was_active -eq 0 ]] || systemctl stop skybeat-agent.service
    [[ ! -e "$venv_dir" ]] || mv "$venv_dir" "$opt_dir/venv.candidate"
    mv "$opt_dir/venv.new" "$venv_dir"
    printf 'package=skybeat-agent\nversion=%s\nsha256=%s\ninstalled_at=%s\n' "$package_version" "$expected_sha256" "$(date -u +%FT%TZ)" >"$opt_dir/.VERSION.new"
    chmod 0644 "$opt_dir/.VERSION.new"
    mv -f -- "$opt_dir/.VERSION.new" "$opt_dir/VERSION"
    write_install_marker SWITCHED
}
rollback_switch() {
    [[ ${switch_started:-0} -eq 1 ]] || return 0
    systemctl stop skybeat-agent.service >/dev/null 2>&1 || true
    if [[ -d "$opt_dir/venv.candidate" ]]; then
        rm -rf -- "$venv_dir"
        mv "$opt_dir/venv.candidate" "$venv_dir"
        [[ ! -f "$opt_dir/VERSION.candidate" ]] || mv -f -- "$opt_dir/VERSION.candidate" "$opt_dir/VERSION"
    fi
    if [[ -f "$state_dir/skybeat-agent.service.candidate" ]]; then
        cp -p -- "$state_dir/skybeat-agent.service.candidate" /etc/systemd/system/skybeat-agent.service
        systemctl daemon-reload
    fi
    if [[ ${was_enabled:-0} -eq 1 ]]; then systemctl enable skybeat-agent.service >/dev/null; else systemctl disable skybeat-agent.service >/dev/null; fi
    if [[ ${was_active:-0} -eq 1 ]]; then
        systemctl start skybeat-agent.service
        local previous_version
        previous_version="$("$venv_dir/bin/python" -c 'from importlib.metadata import version; print(version("skybeat-agent"))')"
        verify_local_health "$previous_version" || { write_install_marker ROLLBACK_FAILED; return 1; }
    fi
    write_install_marker ROLLED_BACK
    rm -f -- "$opt_dir/VERSION.candidate" "$state_dir/skybeat-agent.service.candidate"
    rm -f -- "$state_dir/install.marker"
}
accept_switch() {
    # Local health has passed. If pruning is interrupted, the timer completes
    # acceptance from the SWITCHED marker instead of disturbing the new agent.
    switch_started=0
    [[ ! -e "$opt_dir/venv.previous" ]] || rm -rf -- "$opt_dir/venv.previous"
    [[ ! -e "$opt_dir/venv.candidate" ]] || mv "$opt_dir/venv.candidate" "$opt_dir/venv.previous"
    if [[ -f "$opt_dir/VERSION.candidate" ]]; then mv -f -- "$opt_dir/VERSION.candidate" "$opt_dir/VERSION.previous"; fi
    if [[ -f "$state_dir/skybeat-agent.service.candidate" ]]; then mv -f -- "$state_dir/skybeat-agent.service.candidate" "$state_dir/skybeat-agent.service.previous"; fi
    rm -f -- "$state_dir/install.marker"
}
enroll_device() { local enrollment_token response curl_config existing_device_id insecure_local_server; enrollment_token="$token"; [[ -n "$token_file" ]] && enrollment_token="$(<"$token_file")"; [[ "$enrollment_token" =~ ^sbe1\.[0-9a-f-]{36}\.[A-Za-z0-9_-]{43}$ ]] || fail 'enrollment authorization is invalid'; umask 077; response="$(mktemp)"; curl_config="$(mktemp)"; trap 'rm -f -- "$response" "$curl_config"' RETURN; printf 'header = "Authorization: Bearer %s"\n' "$enrollment_token" >"$curl_config"; if [[ $re_enroll -eq 1 ]]; then existing_device_id="$(awk -F= '$1 == "SKYBEAT_DEVICE_ID" { print $2; exit }' "$config_file")"; [[ "$existing_device_id" =~ ^[0-9a-f-]{36}$ ]] || fail 're-enrollment requires an existing device configuration'; printf 'header = "X-SkyBeat-Reenroll-Device: %s"\n' "$existing_device_id" >>"$curl_config"; fi; curl --config "$curl_config" --fail --silent --show-error --connect-timeout 3 --max-time 10 --output "$response" "$server/api/v1/agent-enrollments/exchange" || fail 'enrollment exchange failed; do not retry an uncertain exchange'; mapfile -t values < <("$opt_dir/venv.new/bin/python" - "$response" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); print(p['device_id']); print(p['credential']); print(p['verification_token'])
PY
); [[ ${#values[@]} -eq 3 && ${values[1]} == sb1.* && ${values[2]} == sbv1.* ]] || fail 'enrollment response is invalid'; insecure_local_server=false; [[ $allow_insecure_local_server -eq 0 ]] || insecure_local_server=true; local temporary="$config_dir/.agent.env.new"; printf 'SKYBEAT_SERVER_URL=%s\nSKYBEAT_ALLOW_INSECURE_LOCAL_SERVER=%s\nSKYBEAT_DEVICE_ID=%s\nSKYBEAT_DEVICE_TOKEN=%s\n' "$server" "$insecure_local_server" "${values[0]}" "${values[1]}" >"$temporary"; install -m 0600 -o root -g root "$temporary" "$config_file"; rm -f -- "$temporary"; verification_token="${values[2]}"; }
configure_agent() { if [[ -f "$config_file" && $re_enroll -eq 0 ]]; then if [[ -n "$existing_sha256" && "$existing_sha256" != "$expected_sha256" ]]; then install_outcome=UPGRADED; else install_outcome=REPAIRED; fi; return; fi; [[ -n "$token$token_file" ]] || fail 'fresh installation requires an enrollment token'; enroll_device; install_outcome=INSTALLED; }
install_service() {
    id -u skybeat >/dev/null 2>&1 || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin skybeat
    install -m 0644 -o root -g root "$unit_source" /etc/systemd/system/skybeat-agent.service
    systemctl daemon-reload
    if [[ ${was_enabled:-0} -eq 1 || ! -d "$opt_dir/venv.candidate" ]]; then systemctl enable skybeat-agent.service >/dev/null; fi
    systemctl restart skybeat-agent.service
}
poll_verification_receipt() { local response curl_config attempt; [[ -n "$verification_token" ]] || return 0; umask 077; response="$(mktemp)"; curl_config="$(mktemp)"; trap 'rm -f -- "$response" "$curl_config"' RETURN; printf 'header = "Authorization: Bearer %s"\n' "$verification_token" >"$curl_config"; for attempt in {1..12}; do if curl --config "$curl_config" --fail --silent --show-error --connect-timeout 3 --max-time 10 --output "$response" "$server/api/v1/agent-enrollments/verification" && "$venv_dir/bin/python" - "$response" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if payload == {"accepted_heartbeat": True} else 1)
PY
 then return 0; fi; [[ "$attempt" -eq 12 ]] || sleep 5; done; install_outcome=INSTALLED_AWAITING_SERVER; printf '%s\n' 'install-agent: local health passed; first heartbeat receipt is still pending.' >&2; }
verify_installation() { verify_local_health "$package_version" || fail 'agent service did not pass local health'; poll_verification_receipt; }
install_updater() {
    local updater_dir=/usr/local/libexec/skybeat
    install -d -m 0755 -o root -g root "$updater_dir"
    install -m 0755 -o root -g root "$release_dir/agent-updater.py" "$updater_dir/agent-updater.py"
    install -m 0644 -o root -g root "$release_dir/deployment/systemd/skybeat-updater.service" /etc/systemd/system/skybeat-updater.service
    install -m 0644 -o root -g root "$release_dir/deployment/systemd/skybeat-updater.timer" /etc/systemd/system/skybeat-updater.timer
    systemctl daemon-reload
    # Timer activation requires a separate operator action; preserve its existing state.
}
