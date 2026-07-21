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

before=$(python3 tests/count_imap_messages.py)
docker compose restart mailserver
python3 tests/wait_for_services.py --mail-only

after=$(python3 tests/count_imap_messages.py)
if [[ "${before}" != "${after}" ]]; then
  echo "Persistence check failed: before=${before}, after=${after}" >&2
  exit 1
fi
echo "PASS persistence: ${after} messages remained after restart" \
  | tee artifacts/persistence.txt
