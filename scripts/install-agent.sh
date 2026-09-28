#!/usr/bin/env bash
set -euo pipefail
release_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$release_dir/lib/skybeat_agent_install.sh"
usage() { printf '%s\n' 'usage: sudo ./install-agent.sh --server URL --package WHEEL --sha256 HEX --wheelhouse DIR --lockfile FILE [--token-file FILE|--token TOKEN] [--allow-insecure-local-server] [--re-enroll]' >&2; }
server='' package='' expected_sha256='' wheelhouse='' lockfile='' token_file='' token='' allow_insecure_local_server=0 re_enroll=0
while [[ $# -gt 0 ]]; do case "$1" in --server|--package|--sha256|--wheelhouse|--lockfile|--token-file|--token) [[ $# -ge 2 ]] || { usage; exit 64; }; case "$1" in --server) server="$2";;--package) package="$2";;--sha256) expected_sha256="$2";;--wheelhouse) wheelhouse="$2";;--lockfile) lockfile="$2";;--token-file) token_file="$2";;--token) token="$2";;esac; shift 2;; --allow-insecure-local-server) allow_insecure_local_server=1; shift;; --re-enroll) re_enroll=1; shift;; *) usage; exit 64;; esac; done
[[ -n "$server$package$expected_sha256$wheelhouse$lockfile" ]] || { usage; exit 64; }
[[ -z "$token" || -z "$token_file" ]] || fail 'use only one enrollment token source'
[[ -z "$token" ]] || printf '%s\n' 'install-agent: warning: use --token-file in production; --token exposes a short-lived secret to process inspection.' >&2
service_started=0
cleanup() { local status=$?; if [[ $status -ne 0 && $service_started -eq 1 ]]; then systemctl disable --now skybeat-agent.service >/dev/null 2>&1 || true; fi; exit "$status"; }
trap cleanup EXIT
preflight; verify_package
if installation_is_current; then
    install_outcome=ALREADY_CURRENT
    verify_installation
else
    existing_sha256="$(installed_sha256 || true)"
    install_package; configure_agent; install_service; verify_installation
fi
trap - EXIT
printf '%s\n' "$install_outcome"
