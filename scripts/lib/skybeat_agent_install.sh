#!/usr/bin/env bash
fail() { printf '%s\n' "install-agent: $1" >&2; exit 1; }
config_dir=/etc/skybeat; config_file=/etc/skybeat/agent.env; opt_dir=/opt/skybeat; venv_dir=/opt/skybeat/venv; state_dir=/var/lib/skybeat
unit_source="$release_dir/deployment/systemd/skybeat-agent.service"
release_verifier="$release_dir/verify-agent-release.py"
server_validator="$release_dir/validate-agent-server-url.py"
install_outcome=FAILED; verification_token=''; existing_sha256=''; package_version=''
regular() { [[ -f "$1" && ! -L "$1" ]]; }
installed_sha256() { regular "$opt_dir/VERSION" || return 1; awk -F= '$1 == "sha256" && $2 ~ /^[0-9a-f]{64}$/ { print $2; exit }' "$opt_dir/VERSION"; }
installation_is_current() { local installed; installed="$(installed_sha256 || true)"; [[ "$installed" == "$expected_sha256" && -x "$venv_dir/bin/skybeat-agent" && -f /etc/systemd/system/skybeat-agent.service && ! -L /etc/systemd/system/skybeat-agent.service ]] && systemctl is-active --quiet skybeat-agent.service; }
preflight() { [[ ${EUID:-1} -eq 0 ]] || fail 'run as root'; . /etc/os-release; [[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04 && $(uname -m) == x86_64 ]] || fail 'Ubuntu 24.04 amd64 is required'; command -v python3.12 >/dev/null && command -v curl >/dev/null && command -v sha256sum >/dev/null && command -v systemctl >/dev/null || fail 'required command is missing'; regular "$package" && regular "$lockfile" && [[ -d "$wheelhouse" && ! -L "$wheelhouse" ]] && regular "$unit_source" && regular "$release_verifier" && regular "$server_validator" || fail 'release input is invalid'; [[ "$expected_sha256" =~ ^[0-9a-f]{64}$ ]] || fail 'expected sha256 is invalid'; local server_arguments=(--server "$server"); [[ $allow_insecure_local_server -eq 0 ]] || server_arguments+=(--allow-insecure-local-server); python3.12 "$server_validator" "${server_arguments[@]}" >/dev/null 2>&1 || fail 'agent server origin is invalid'; [[ -z "$token_file" || -f "$token_file" && ! -L "$token_file" ]] || fail 'enrollment token file is invalid'; }
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
install_package() { install -d -m 0755 -o root -g root "$opt_dir" "$state_dir" "$config_dir"; local staging="$opt_dir/venv.new"; rm -rf -- "$staging"; python3.12 -m venv "$staging"; "$staging/bin/python" -m pip install --no-index --find-links "$wheelhouse" --require-hashes -r "$lockfile"; "$staging/bin/python" -m pip install --no-index --no-deps "$package"; rm -rf -- "$opt_dir/venv.previous"; [[ ! -e "$venv_dir" ]] || mv "$venv_dir" "$opt_dir/venv.previous"; mv "$staging" "$venv_dir"; printf 'package=skybeat-agent\nversion=%s\nsha256=%s\ninstalled_at=%s\n' "$package_version" "$expected_sha256" "$(date -u +%FT%TZ)" >"$opt_dir/VERSION"; chmod 0644 "$opt_dir/VERSION"; }
enroll_device() { local enrollment_token response curl_config existing_device_id; enrollment_token="$token"; [[ -n "$token_file" ]] && enrollment_token="$(<"$token_file")"; [[ "$enrollment_token" =~ ^sbe1\.[0-9a-f-]{36}\.[A-Za-z0-9_-]{43}$ ]] || fail 'enrollment authorization is invalid'; umask 077; response="$(mktemp)"; curl_config="$(mktemp)"; trap 'rm -f -- "$response" "$curl_config"' RETURN; printf 'header = "Authorization: Bearer %s"\n' "$enrollment_token" >"$curl_config"; if [[ $re_enroll -eq 1 ]]; then existing_device_id="$(awk -F= '$1 == "SKYBEAT_DEVICE_ID" { print $2; exit }' "$config_file")"; [[ "$existing_device_id" =~ ^[0-9a-f-]{36}$ ]] || fail 're-enrollment requires an existing device configuration'; printf 'header = "X-SkyBeat-Reenroll-Device: %s"\n' "$existing_device_id" >>"$curl_config"; fi; curl --config "$curl_config" --fail --silent --show-error --connect-timeout 3 --max-time 10 --output "$response" "$server/api/v1/agent-enrollments/exchange" || fail 'enrollment exchange failed; do not retry an uncertain exchange'; mapfile -t values < <("$venv_dir/bin/python" - "$response" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); print(p['device_id']); print(p['credential']); print(p['verification_token'])
PY
); [[ ${#values[@]} -eq 3 && ${values[1]} == sb1.* && ${values[2]} == sbv1.* ]] || fail 'enrollment response is invalid'; local temporary="$config_dir/.agent.env.new"; printf 'SKYBEAT_SERVER_URL=%s\nSKYBEAT_DEVICE_ID=%s\nSKYBEAT_DEVICE_TOKEN=%s\n' "$server" "${values[0]}" "${values[1]}" >"$temporary"; install -m 0600 -o root -g root "$temporary" "$config_file"; rm -f -- "$temporary"; verification_token="${values[2]}"; }
configure_agent() { if [[ -f "$config_file" && $re_enroll -eq 0 ]]; then if [[ -n "$existing_sha256" && "$existing_sha256" != "$expected_sha256" ]]; then install_outcome=UPGRADED; else install_outcome=REPAIRED; fi; return; fi; [[ -n "$token$token_file" ]] || fail 'fresh installation requires an enrollment token'; enroll_device; install_outcome=INSTALLED; }
install_service() { id -u skybeat >/dev/null 2>&1 || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin skybeat; install -m 0644 -o root -g root "$unit_source" /etc/systemd/system/skybeat-agent.service; systemctl daemon-reload; systemctl enable --now skybeat-agent.service; service_started=1; }
poll_verification_receipt() { local response curl_config attempt; [[ -n "$verification_token" ]] || return 0; umask 077; response="$(mktemp)"; curl_config="$(mktemp)"; trap 'rm -f -- "$response" "$curl_config"' RETURN; printf 'header = "Authorization: Bearer %s"\n' "$verification_token" >"$curl_config"; for attempt in {1..12}; do if curl --config "$curl_config" --fail --silent --show-error --connect-timeout 3 --max-time 10 --output "$response" "$server/api/v1/agent-enrollments/verification" && "$venv_dir/bin/python" - "$response" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if payload == {"accepted_heartbeat": True} else 1)
PY
 then return 0; fi; [[ "$attempt" -eq 12 ]] || sleep 5; done; fail 'agent service started but fresh heartbeat was not verified by enrollment receipt'; }
verify_installation() { systemctl is-active --quiet skybeat-agent.service || fail 'agent service did not start'; poll_verification_receipt; }
