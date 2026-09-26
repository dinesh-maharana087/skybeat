#!/usr/bin/env bash
# Build a reviewed local-only SkyBeat agent release bundle. This never installs an agent.
set -euo pipefail

usage() {
    printf '%s\n' 'usage: ./scripts/build-agent-release.sh --output <release-directory>' >&2
}

fail() {
    printf '%s\n' "build-agent-release: $1" >&2
    exit 1
}

output=''
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            [[ $# -ge 2 ]] || fail 'missing --output value'
            output="$2"
            shift 2
            ;;
        *)
            usage
            exit 64
            ;;
    esac
done
[[ -n "$output" ]] || { usage; exit 64; }

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(dirname -- "$script_dir")"
agent_dir="$repository_root/agent"
lockfile="$agent_dir/requirements.lock"
verifier="$script_dir/verify-agent-release.py"
[[ -f "$agent_dir/pyproject.toml" && -f "$lockfile" && -f "$verifier" ]] || fail 'committed agent release inputs are missing'
command -v uv >/dev/null 2>&1 || fail 'uv is required to build a release bundle'
command -v python3.12 >/dev/null 2>&1 || fail 'python3.12 is required to build a release bundle'

version="$(python3.12 -c 'import tomllib,sys; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$agent_dir/pyproject.toml")"
[[ "$version" =~ ^[0-9]+(\.[0-9]+){1,3}([a-zA-Z0-9.+-]*)?$ ]] || fail 'agent version is invalid'
mkdir -p "$output"
[[ ! -L "$output" ]] || fail 'release output directory must not be a symlink'
staging="$(mktemp -d "${output%/}/.skybeat-release.XXXXXX")"
trap 'rm -rf -- "$staging"' EXIT
bundle="$staging/skybeat-agent-$version"
wheelhouse="$bundle/wheelhouse"
mkdir -p "$wheelhouse"

uv build --wheel --out-dir "$bundle" "$agent_dir"
wheel="$(find "$bundle" -maxdepth 1 -type f -name "skybeat_agent-${version}-*.whl" -print -quit)"
[[ -n "$wheel" && -f "$wheel" ]] || fail 'expected agent wheel was not built'
(
    cd "$bundle"
    sha256sum "$(basename "$wheel")" >"$bundle/wheel.sha256"
)
uv venv "$staging/build-venv" --python python3.12 --seed
build_python="$staging/build-venv/bin/python"
[[ -x "$build_python" ]] || build_python="$staging/build-venv/Scripts/python.exe"
[[ -x "$build_python" ]] || fail 'created build virtual environment has no Python interpreter'
"$build_python" -m pip download --require-hashes --only-binary=:all: --dest "$wheelhouse" \
    --platform manylinux_2_17_x86_64 --implementation cp --python-version 3.12 --abi cp312 \
    -r "$lockfile"
cp "$lockfile" "$bundle/requirements.lock"

"$build_python" - "$bundle" "$wheel" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

bundle = Path(sys.argv[1])
wheel = Path(sys.argv[2])
sha256 = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
version = wheel.name.split("-")[1]
manifest = {
    "format": 1,
    "package": {"name": "skybeat-agent", "version": version, "filename": wheel.name, "sha256": sha256(wheel)},
    "requirements_lock": {"filename": "requirements.lock", "sha256": sha256(bundle / "requirements.lock")},
    "wheelhouse": [
        {"filename": path.name, "sha256": sha256(path)}
        for path in sorted((bundle / "wheelhouse").iterdir())
        if path.is_file() and not path.is_symlink()
    ],
}
(bundle / "release-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
PY
python3.12 "$verifier" --bundle "$bundle"
final_bundle="${output%/}/skybeat-agent-$version"
[[ ! -e "$final_bundle" ]] || fail 'release bundle already exists'
mv "$bundle" "$final_bundle"
printf '%s\n' "SkyBeat agent release bundle created: $final_bundle"
