#!/usr/bin/env bash
# Example end-to-end workflow (edit IPs/devices before running).
# Storage server: run target commands. Client: initiator + deploy + validate.
set -euo pipefail

TARGET_IP="${TARGET_IP:-10.0.0.10}"
CLIENT_CFG="${LUSTRE_CLI_CONFIG:-/etc/lustre-cli/config.yaml}"
IQN_PREFIX="iqn.2024-05.com.lustre-cli"

echo "=== On storage server (root) ==="
echo "lustre-cli target create -d /dev/sdb --lun 0"
echo "lustre-cli target create -d /dev/sdc --lun 1"
echo "lustre-cli target list"

echo ""
echo "=== On client (root) ==="
echo "lustre-cli initiator discover --host ${TARGET_IP}"
echo "lustre-cli initiator login --host ${TARGET_IP} --iqn ${IQN_PREFIX}:lun0"
echo "lustre-cli initiator login --host ${TARGET_IP} --iqn ${IQN_PREFIX}:lun1"
echo "lustre-cli initiator status"

echo ""
echo "=== Deploy Lustre ==="
echo "lustre-cli deploy format --mgs-device /dev/sdX --mdt-device /dev/sdY \\"
echo "  --ost-device /dev/sdZ --mgsnode ${TARGET_IP}@tcp"
echo "lustre-cli deploy mount"
echo "lustre-cli deploy status"

echo ""
echo "=== Validate & benchmark ==="
echo "lustre-cli validate basic"
echo "lustre-cli validate stripe"
echo "lustre-cli validate integrity"
echo "lustre-cli benchmark run"
echo "lustre-cli benchmark report"

echo ""
echo "=== Fault simulation ==="
echo "lustre-cli fault simulate-ost-failure --index 0"
echo "lustre-cli fault simulate-bad-config"
echo "lustre-cli fault simulate-network-drop"

echo ""
echo "=== Teardown ==="
echo "lustre-cli teardown"
echo "lustre-cli reset --hard"
