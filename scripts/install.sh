#!/usr/bin/env bash
# Install lustre-cli on Ubuntu/RHEL Linux hosts.
set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
CONFIG_DIR="/etc/lustre-cli"
LOG_DIR="/var/log"
STATE_DIR="/var/lib/lustre-cli"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

echo "==> Installing OS packages (adjust for your distro)..."
if command -v apt-get &>/dev/null; then
  apt-get update -qq
  apt-get install -y python3 python3-pip python3-yaml \
    open-iscsi targetcli-fb lustre-client-utils fio util-linux
elif command -v dnf &>/dev/null; then
  dnf install -y python3 python3-pip python3-pyyaml \
    iscsi-initiator-utils targetcli lustre-client fio util-linux
else
  echo "Install manually: python3, PyYAML, targetcli, open-iscsi, lustre-utils, fio"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pip3 install "${SCRIPT_DIR}" --break-system-packages 2>/dev/null || pip3 install "${SCRIPT_DIR}"

mkdir -p "${CONFIG_DIR}" "${STATE_DIR}/benchmarks"
if [[ ! -f "${CONFIG_DIR}/config.yaml" ]]; then
  cp "${SCRIPT_DIR}/config/config.yaml.example" "${CONFIG_DIR}/config.yaml"
  echo "Created ${CONFIG_DIR}/config.yaml"
fi

touch "${LOG_DIR}/lustre-cli.log"
chmod 644 "${LOG_DIR}/lustre-cli.log"

systemctl enable iscsid 2>/dev/null || true
systemctl enable target 2>/dev/null || true

echo "==> Installed. Verify with: lustre-cli --version && lustre-cli check-deps"
