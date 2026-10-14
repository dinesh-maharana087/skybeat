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

mkdir -p "$bundle/lib" "$bundle/deployment/systemd"
cp "$script_dir/install-agent.sh" "$bundle/install-agent.sh"
cp "$script_dir/lib/skybeat_agent_install.sh" "$bundle/lib/skybeat_agent_install.sh"
cp "$script_dir/verify-agent-release.py" "$bundle/verify-agent-release.py"
cp "$script_dir/validate-agent-server-url.py" "$bundle/validate-agent-server-url.py"
cp "$script_dir/agent-updater.py" "$bundle/agent-updater.py"
cp "$repository_root/deployment/systemd/skybeat-agent.service" "$bundle/deployment/systemd/skybeat-agent.service"
cp "$repository_root/deployment/systemd/skybeat-updater.service" "$bundle/deployment/systemd/skybeat-updater.service"
cp "$repository_root/deployment/systemd/skybeat-updater.timer" "$bundle/deployment/systemd/skybeat-updater.timer"
printf '%s\n' 'SkyBeat agent deployment release. Use the dashboard-provided installation instructions.' >"$bundle/README.txt"
chmod 0755 "$bundle/install-agent.sh" "$bundle/verify-agent-release.py" "$bundle/validate-agent-server-url.py" "$bundle/agent-updater.py"

uv build --wheel --out-dir "$bundle" "$agent_dir"
rm -f "$bundle/.gitignore"
mapfile -t wheels < <(find "$bundle" -maxdepth 1 -type f -name "skybeat_agent-${version}-*.whl" -print | LC_ALL=C sort)
[[ ${#wheels[@]} -eq 1 ]] || fail 'expected exactly one agent wheel was not built'
wheel="${wheels[0]}"
[[ "$(basename "$wheel")" != skybeat_server-* ]] || fail 'server wheel cannot be an agent release package'
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
installer_artifacts = [
    "install-agent.sh",
    "lib/skybeat_agent_install.sh",
    "verify-agent-release.py",
    "validate-agent-server-url.py",
    "agent-updater.py",
    "deployment/systemd/skybeat-agent.service",
    "deployment/systemd/skybeat-updater.service",
    "deployment/systemd/skybeat-updater.timer",
    "README.txt",
]
manifest = {
    "format": 2,
    "package": {"name": "skybeat-agent", "version": version, "filename": wheel.name, "sha256": sha256(wheel)},
    "requirements_lock": {"filename": "requirements.lock", "sha256": sha256(bundle / "requirements.lock")},
    "wheelhouse": [
        {"filename": path.name, "sha256": sha256(path)}
        for path in sorted((bundle / "wheelhouse").iterdir())
        if path.is_file() and not path.is_symlink()
    ],
    "installer_artifacts": [
        {"filename": filename, "sha256": sha256(bundle / filename)}
        for filename in installer_artifacts
    ],
}
(bundle / "release-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
(bundle / "SHA256SUMS").write_text(
    "".join(
        f"{sha256(bundle / filename)}  {filename}\n"
        for filename in [wheel.name, "requirements.lock", *sorted(installer_artifacts)]
    ),
    encoding="ascii",
)
PY
python3.12 "$verifier" --bundle "$bundle"
final_bundle="${output%/}/skybeat-agent-$version"
archive="$staging/skybeat-agent-${version}-linux.zip"
final_archive="${output%/}/skybeat-agent-${version}-linux.zip"
[[ ! -e "$final_bundle" ]] || fail 'release bundle already exists'
[[ ! -e "$final_archive" ]] || fail 'release archive already exists'
python3.12 - "$bundle" "$archive" <<'PY'
import sys
import zipfile
from pathlib import Path

bundle = Path(sys.argv[1])
archive = Path(sys.argv[2])
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        output.write(path, Path(bundle.name) / path.relative_to(bundle))
PY
mv "$bundle" "$final_bundle"
mv "$archive" "$final_archive"
printf '%s\n' "SkyBeat agent release bundle created: $final_bundle"
