#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd "${script_dir}/.." && pwd)
ca_dir="${lab_dir}/certs/ca"
server_dir="${lab_dir}/certs/server"
force=${1:-}

mkdir -p "${ca_dir}" "${server_dir}"

ca_key="${ca_dir}/zzjh-mail-lab-ca.key"
ca_cert="${ca_dir}/zzjh-mail-lab-ca.crt"
server_key="${server_dir}/mail.zzjh.test.key"
server_csr="${server_dir}/mail.zzjh.test.csr"
server_cert="${server_dir}/mail.zzjh.test.crt"

if [[ "${force}" != "--force" && -s "${ca_cert}" && -s "${server_cert}" && -s "${server_key}" ]]; then
  echo "Certificates already exist; leaving them unchanged."
  exit 0
fi

openssl genrsa -out "${ca_key}" 4096
openssl req -x509 -new -sha256 -days 3650 \
  -key "${ca_key}" \
  -subj "/CN=ZZJH Mail Lab CA/O=ZZJH Research Lab" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash" \
  -out "${ca_cert}"

openssl genrsa -out "${server_key}" 3072
openssl req -new -sha256 \
  -key "${server_key}" \
  -subj "/CN=mail.zzjh.test/O=ZZJH Research Lab" \
  -out "${server_csr}"

openssl x509 -req -sha256 -days 825 \
  -in "${server_csr}" \
  -CA "${ca_cert}" \
  -CAkey "${ca_key}" \
  -CAcreateserial \
  -extfile "${lab_dir}/certs/openssl-san.cnf" \
  -extensions v3_req \
  -out "${server_cert}"

chmod 600 "${ca_key}" "${server_key}"
chmod 644 "${ca_cert}" "${server_cert}"

openssl verify -CAfile "${ca_cert}" "${server_cert}"
openssl x509 -in "${server_cert}" -noout -subject -issuer -dates
