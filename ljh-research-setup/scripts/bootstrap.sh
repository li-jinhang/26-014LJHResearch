#!/bin/sh
set -eu
python_cmd='' apply=0 papers=0 runtime_url='' runtime_hash=''
runtime_dir="${XDG_DATA_HOME:-$HOME/.local/share}/ljh-research"
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
while [ "$#" -gt 0 ]; do
    case "$1" in
        --python) python_cmd=$2; shift 2;;
        --runtime-dir) runtime_dir=$2; shift 2;;
        --runtime-url) runtime_url=$2; shift 2;;
        --runtime-sha256) runtime_hash=$2; shift 2;;
        --apply) apply=1; shift;;
        --papers) papers=1; shift;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2;;
    esac
done
if [ -z "$python_cmd" ]; then python_cmd=$(command -v python3 || true); fi
if [ -n "$python_cmd" ] && ! "$python_cmd" -I -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null; then python_cmd=''; fi
if [ -z "$python_cmd" ]; then
    printf 'Bundle: %s\nUser runtime: %s\nPython: missing\n' "$script_dir/.." "$runtime_dir"
    [ "$apply" -eq 1 ] || exit 0
    case "$runtime_url" in https://github.com/astral-sh/python-build-standalone/releases/download/*) ;; *) printf 'Provide a verified official standalone runtime URL\n' >&2; exit 2;; esac
    [ "${#runtime_hash}" -eq 64 ] || { printf 'A trusted SHA256 checksum is required\n' >&2; exit 2; }
    umask 077
    mkdir -p "$runtime_dir"
    archive="$runtime_dir/python-runtime.tar.gz"
    curl --fail --location --proto '=https' --tlsv1.2 "$runtime_url" --output "$archive"
    printf '%s  %s\n' "$runtime_hash" "$archive" | sha256sum --check --status || { printf 'Runtime hash mismatch\n' >&2; exit 2; }
    if tar -tzf "$archive" | grep -E '(^/|(^|/)\.\.(/|$))' >/dev/null; then printf 'Unsafe runtime archive\n' >&2; exit 2; fi
    [ ! -e "$runtime_dir/python" ] || { printf 'Runtime destination exists; inspect it before retrying\n' >&2; exit 2; }
    stage=$(mktemp -d "$runtime_dir/stage.XXXXXXXX")
    tar -xzf "$archive" -C "$stage" --no-same-owner
    [ -x "$stage/python/bin/python3" ] || { printf 'Archive has no expected Python executable\n' >&2; exit 2; }
    mv "$stage/python" "$runtime_dir/python"
    rmdir "$stage"
    python_cmd="$runtime_dir/python/bin/python3"
fi
set -- "$script_dir/install_runtime.py" --runtime-dir "$runtime_dir"
[ "$apply" -ne 1 ] || set -- "$@" --apply
[ "$papers" -ne 1 ] || set -- "$@" --papers
exec "$python_cmd" -I "$@"
