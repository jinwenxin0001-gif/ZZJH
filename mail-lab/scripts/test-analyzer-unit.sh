#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd "${script_dir}/.." && pwd)
cd "${lab_dir}"

docker compose run --rm --no-deps attachment-analyzer \
  python -m unittest discover -s /app/tests -v
