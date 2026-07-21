#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd "${script_dir}/.." && pwd)
cd "${lab_dir}"

"${script_dir}/generate-certs.sh"
docker compose config --quiet
docker compose pull mailserver
docker compose build roundcube
docker compose up -d mailserver
"${script_dir}/create-accounts.sh"
docker compose up -d roundcube
"${script_dir}/run-tests.sh"
