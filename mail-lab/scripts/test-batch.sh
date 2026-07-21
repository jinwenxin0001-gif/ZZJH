#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd "${script_dir}/.." && pwd)
cd "${lab_dir}"

set -a
# shellcheck disable=SC1091
source .env
set +a

mkdir -p artifacts
python3 tests/wait_for_services.py
python3 tests/batch_delivery_test.py | tee artifacts/batch-delivery.txt
