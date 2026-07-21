#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd "${script_dir}/.." && pwd)
cd "${lab_dir}"

set -a
# shellcheck disable=SC1091
source .env
set +a

wait_for_mailserver() {
  local attempts=36
  while (( attempts > 0 )); do
    if docker compose exec -T mailserver true >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 5
  done
  echo "Mailserver did not become ready in time." >&2
  return 1
}

ensure_account() {
  local address=$1
  local password=$2
  local accounts_file="${lab_dir}/data/dms/config/postfix-accounts.cf"
  if [[ -f "${accounts_file}" ]] && grep -Fq "${address}|" "${accounts_file}"; then
    echo "Account already exists: ${address}"
  else
    docker compose exec -T mailserver setup email add "${address}" "${password}"
    echo "Created account: ${address}"
  fi
}

ensure_alias() {
  local source=$1
  local destination=$2
  local aliases_file="${lab_dir}/data/dms/config/postfix-virtual.cf"
  if [[ -f "${aliases_file}" ]] && grep -Fq "${source} " "${aliases_file}"; then
    echo "Alias already exists: ${source}"
  else
    docker compose exec -T mailserver setup alias add "${source}" "${destination}"
    echo "Created alias: ${source} -> ${destination}"
  fi
}

wait_for_mailserver
ensure_account "${ALICE_EMAIL}" "${ALICE_PASSWORD}"
ensure_account "${BOB_EMAIL}" "${BOB_PASSWORD}"
ensure_account "${POP3_EMAIL}" "${POP3_PASSWORD}"
ensure_account "${QUARANTINE_EMAIL}" "${QUARANTINE_PASSWORD}"
ensure_alias "postmaster@${MAIL_DOMAIN}" "${ALICE_EMAIL}"
ensure_alias "abuse@${MAIL_DOMAIN}" "${ALICE_EMAIL}"

echo "Configured accounts:"
cut -d'|' -f1 "${lab_dir}/data/dms/config/postfix-accounts.cf" | sed 's/^/  - /'
