#!/usr/bin/env bash
# Translate only missing dumped stages; validate before adding private cache files.
# Usage: wsl-translate-shaders.sh [shader_misses directory] [spirv directory]
# Defaults use SP2_DATA_ROOT, or ./private; SP2PORT selects the external runtime.
# Restart the game afterward: shader misses and resource records are process-cached.
set -euo pipefail

if (( $# > 2 )); then
    echo "usage: $0 [shader_misses directory] [spirv directory]" >&2
    exit 2
fi
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
run_dir=$(mktemp -d "${TMPDIR:-/tmp}/sp2-shader-misses.XXXXXXXX")
trap 'rm -rf -- "$run_dir"' EXIT
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
data_root=${SP2_DATA_ROOT:-"$PWD/private"}
python3 "$script_dir/translate_shader_misses.py" \
    "${1:-$data_root/shader_misses}" "${2:-$data_root/spirv}" "$run_dir"
