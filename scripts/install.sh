#!/usr/bin/env bash
# Install lustre-cli on Ubuntu/RHEL Linux hosts.
set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
CONFIG_DIR="/etc/lustre-cli"
LOG_DIR="/var/log"
STATE_DIR="/var/lib/lustre-cli"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[-] ERROR: This script must be run as root. Try: sudo $0" >&2
  exit 1
fi

# Resilient project root path detection regardless of invocation location
REAL_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
CURRENT_DIR="$(dirname "${REAL_PATH}")"

if [[ -f "${CURRENT_DIR}/../config/config.yaml.example" ]]; then
  SCRIPT_DIR="$(cd "${CURRENT_DIR}/.." && pwd)"
elif [[ -f "${CURRENT_DIR}/config/config.yaml.example" ]]; then
  SCRIPT_DIR="${CURRENT_DIR}"
else
  echo "[-] ERROR: Cannot locate repository assets folder tree structure." >&2
  exit 1
fi

echo "==> Validating operating system package availability..."
if command -v apt-get &>/dev/null; then
  apt-get update -qq
  if ! apt-cache show lustre-client-utils &>/dev/null; then
    echo "[-] WARNING: 'lustre-client-utils' not found in active apt repositories." >&2
    echo "    Please configure the Whamcloud or vendor PPA prior to installation." >&2
  fi
  apt-get install -y python3 python3-pip python3-yaml \
    open-iscsi targetcli-fb fio util-linux
    
  if apt-cache show lustre-client-utils &>/dev/null; then
    apt-get install -y lustre-client-utils
  fi

elif command -v dnf &>/dev/null; then
  if ! dnf info lustre-client &>/dev/null; then
    echo "[-] WARNING: 'lustre-client' package is not available in active dnf mirrors." >&2
    echo "    Ensure the appropriate Lustre repo definitions are enabled in /etc/yum.repos.d/" >&2
  fi
  dnf install -y python3 python3-pip python3-pyyaml \
    iscsi-initiator-utils targetcli fio util-linux
    
  if dnf info lustre-client &>/dev/null; then
    dnf install -y lustre-client
  fi
else
  echo "[!] Unknown distribution engine. Install dependencies manually: python3, PyYAML, targetcli, open-iscsi, lustre-utils, fio"
fi

echo "==> Injecting core python application elements..."
# FIXED: Added --prefix="${PREFIX}" to ensure your custom install paths work correctly
if pip3 install --help 2>&1 | grep -q "break-system-packages"; then
  pip3 install "${SCRIPT_DIR}" --prefix="${PREFIX}" --break-system-packages
else
  pip3 install "${SCRIPT_DIR}" --prefix="${PREFIX}"
fi

mkdir -p "${CONFIG_DIR}" "${STATE_DIR}/benchmarks"
if [[ ! -f "${CONFIG_DIR}/config.yaml" ]]; then
  cp "${SCRIPT_DIR}/config/config.yaml.example" "${CONFIG_DIR}/config.yaml"
  echo "[+] Initial baseline configuration generated at ${CONFIG_DIR}/config.yaml"
fi

touch "${LOG_DIR}/lustre-cli.log"
chmod 644 "${LOG_DIR}/lustre-cli.log"

echo "==> Activating storage transport services..."
systemctl daemon-reload

# Manage initiator daemon activation
systemctl enable --now iscsid 2>/dev/null || systemctl start iscsid || true

# FIXED: Replaced brittle grep filtering with clean systemctl cat lookups
if systemctl cat target.service &>/dev/null; then
  systemctl enable --now target
elif systemctl cat rtslib-fb-targetctl.service &>/dev/null; then
  systemctl enable --now rtslib-fb-targetctl
elif systemctl cat targetcli.service &>/dev/null; then
  systemctl enable --now targetcli
else
  echo "[-] WARNING: Unable to establish local storage kernel target subsystem daemon handle automatically." >&2
fi

echo "========================================================================="
echo "==> Deployment successful!"
echo "==> Run tasks using: lustre-cli --version && lustre-cli check-deps"
echo "========================================================================="
