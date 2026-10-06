#!/usr/bin/env bash
# Login-node entry point. The scheduled program is still the binary itself.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export DMA_PROFILE=study
exec bash "$script_dir/run_dma.sh" "$@"
