# lustre-cli Setup Guide

## System requirements

### Hardware / topology

| Role | Minimum | Notes |
|------|---------|-------|
| Storage server | 1 node, 1+ block devices | Exports devices via iSCSI target |
| Lustre node(s) | 1+ nodes | Initiator imports LUNs; can colocate MGS/MDT/OST on one host for lab |

### Supported OS

- Ubuntu 22.04 / 24.04 LTS
- RHEL 8 / 9, Rocky Linux, AlmaLinux

### Kernel & packages

**Storage server (target):**

```bash
# Ubuntu
sudo apt install targetcli-fb

# RHEL
sudo dnf install targetcli
```

**Client (initiator + Lustre):**

```bash
# Ubuntu (enable Lustre PPA or vendor repo as required for your environment)
sudo apt install open-iscsi lustre-client-utils fio

# RHEL
sudo dnf install iscsi-initiator-utils lustre-client fio
```

**Python:**

- Python 3.9+
- PyYAML

## Installation

### Automated

```bash
git clone <repo-url> lustre-cli
cd lustre-cli
sudo ./scripts/install.sh
```

### Manual

```bash
pip3 install .
sudo mkdir -p /etc/lustre-cli /var/lib/lustre-cli/benchmarks
sudo cp config/config.yaml.example /etc/lustre-cli/config.yaml
# Edit mgsnode, devices, interfaces
sudo lustre-cli check-deps
```

## Configuration

Edit `/etc/lustre-cli/config.yaml`:

- `iscsi.portal_ip` — target listen address (`0.0.0.0` for all interfaces)
- `lustre.mgsnode` — MGS NID, e.g. `10.0.0.10@tcp`
- `lustre.lnet.interfaces` — NICs for LNet (`eth0`, etc.)
- `lustre.mount.client` — client mount path for validation/benchmarks

Override path:

```bash
export LUSTRE_CLI_CONFIG=/path/to/config.yaml
```

## Pre-flight checks

```bash
sudo lustre-cli check-deps    # targetcli, iscsiadm, mkfs.lustre, lctl, fio, ...
lsblk                         # identify local / iSCSI devices
sudo systemctl status iscsid  # initiator daemon
```

## Firewall

| Service | Port | Protocol |
|---------|------|----------|
| iSCSI | 3260 | TCP |

```bash
sudo firewall-cmd --add-port=3260/tcp --permanent && sudo firewall-cmd --reload
```

## Persistence

- **targetcli**: `saveconfig` on create/delete (stored under `/etc/target/`)
- **iscsiadm**: `node.startup=automatic` set on login
- **lustre-cli**: IQNs, sessions, devices in `/etc/lustre-cli/config.yaml`

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `Missing required tools` | Run `lustre-cli check-deps`, install packages |
| Initiator login fails | `ping` target, port 3260, correct IQN, `target list` on server |
| `mkfs.lustre` fails | Lustre modules loaded: `modprobe lustre`; device not mounted |
| Mount hangs | Wrong `mgsnode`, LNet down: `lnetctl lnet show` |
| Permission denied | Run with `sudo` |

Log file: `/var/log/lustre-cli.log`
