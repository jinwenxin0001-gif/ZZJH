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
python3 tests/listener_test.py | tee artifacts/listener-bindings.txt
python3 tests/protocol_smoke.py | tee artifacts/protocol-smoke.txt
python3 tests/attachment_analysis_test.py | tee artifacts/attachment-analysis.txt
python3 tests/open_relay_test.py | tee artifacts/open-relay.txt
python3 tests/roundcube_login_test.py | tee artifacts/roundcube-login.txt

http_code=$(curl --silent --output artifacts/roundcube-index.html --write-out '%{http_code}' \
  "http://127.0.0.1:${ROUNDCUBE_HOST_PORT:-8080}/")
if [[ "${http_code}" != "200" ]]; then
  echo "Roundcube HTTP check failed with status ${http_code}" >&2
  exit 1
fi
echo "PASS Roundcube HTTP status 200" | tee artifacts/roundcube-http.txt

docker compose ps | tee artifacts/compose-ps.txt
