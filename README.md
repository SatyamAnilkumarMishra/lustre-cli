# lustre-cli

Linux command-line tool for **iSCSI block storage** (target and initiator) and **Lustre** distributed filesystem deployment, validation, benchmarking, and fault testing.

**Supported distros:** Ubuntu 22.04 / 24.04 LTS · Debian 12 · RHEL 8 / 9 · Rocky Linux · AlmaLinux

---

## Table of contents

- [Features](#features)
- [System requirements](#system-requirements)
- [Installation](#installation)
  - [Method 1 — Git clone (recommended)](#method-1--git-clone-recommended)
  - [Method 2 — Release tarball (no Git)](#method-2--release-tarball-no-git)
  - [Method 3 — pip from GitHub](#method-3--pip-from-github)
  - [Method 4 — Manual install](#method-4--manual-install)
  - [Method 5 — Copy project folder](#method-5--copy-project-folder)
- [Distro-specific setup](#distro-specific-setup)
  - [Ubuntu / Debian](#ubuntu--debian)
  - [RHEL / Rocky / AlmaLinux](#rhel--rocky--almalinux)
  - [Other Linux](#other-linux)
- [Configuration](#configuration)
- [Quick start](#quick-start)
- [Usage guide](#usage-guide)
  - [Single-machine lab](#single-machine-lab)
  - [Two-machine lab](#two-machine-lab)
  - [Full command reference](#full-command-reference)
- [Verification & testing](#verification--testing)
- [Logs & state](#logs--state)
- [Uninstall](#uninstall)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [License](#license)

---

## Features

| Module | Commands |
|--------|----------|
| iSCSI target | `target create`, `target list`, `target delete` |
| iSCSI initiator | `initiator discover`, `login`, `logout`, `status` |
| Lustre deploy | `deploy format`, `mount`, `status`, `unmount` |
| Validation | `validate basic`, `stripe`, `integrity` |
| Benchmark | `benchmark run`, `report` |
| Fault simulation | `fault simulate-ost-failure`, `simulate-bad-config`, `simulate-network-drop` |
| Cleanup | `teardown`, `reset --hard` |
| Utilities | `check-deps`, `--help`, `--version` |

---

## System requirements

| Requirement | Details |
|-------------|---------|
| OS | Linux (see supported distros above) |
| Python | 3.9+ with `pip` |
| Privileges | `root` / `sudo` for storage operations |
| RAM | 2 GB+ (lab); more for production |
| Network | TCP port **3260** open for iSCSI between nodes |
| Tools | `targetcli`, `iscsiadm`, `mkfs.lustre`, `lctl`, `lfs`, `lnetctl`, `fio`, `lsblk`, `wipefs` |

---

## Installation

Replace `YOUR_USERNAME` with your GitHub username after publishing the repository.

### Method 1 — Git clone (recommended)

Works on any distro with `git` installed.

```bash
sudo apt install -y git          # Ubuntu/Debian
# sudo dnf install -y git        # RHEL/Rocky

git clone https://github.com/YOUR_USERNAME/lustre-cli.git
cd lustre-cli
chmod +x scripts/install.sh
sudo ./scripts/install.sh
lustre-cli --version
sudo lustre-cli check-deps
```

### Method 2 — Release tarball (no Git)

Download a fixed version from GitHub Releases.

```bash
curl -sL https://github.com/YOUR_USERNAME/lustre-cli/archive/refs/tags/v1.0.0.tar.gz -o lustre-cli.tar.gz
tar xzf lustre-cli.tar.gz
cd lustre-cli-1.0.0
chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

### Method 3 — pip from GitHub

Installs only the CLI; you still need system packages (see [Distro-specific setup](#distro-specific-setup)).

```bash
sudo pip3 install "git+https://github.com/YOUR_USERNAME/lustre-cli.git"

sudo mkdir -p /etc/lustre-cli /var/lib/lustre-cli/benchmarks
sudo curl -sL https://raw.githubusercontent.com/YOUR_USERNAME/lustre-cli/main/config/config.yaml.example \
  -o /etc/lustre-cli/config.yaml

lustre-cli --version
sudo lustre-cli check-deps
```

### Method 4 — Manual install

From an extracted or cloned project directory:

```bash
cd lustre-cli
pip3 install .                    # or: sudo pip3 install .
sudo mkdir -p /etc/lustre-cli /var/lib/lustre-cli/benchmarks
sudo cp config/config.yaml.example /etc/lustre-cli/config.yaml
sudo touch /var/log/lustre-cli.log
lustre-cli check-deps
```

### Method 5 — Copy project folder

If you copied the folder from USB or `scp` (no GitHub):

```bash
cd /path/to/lustre-cli
# Fix Windows line endings if needed:
sudo apt install -y dos2unix && dos2unix scripts/*.sh
chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

---

## Distro-specific setup

`scripts/install.sh` auto-detects **apt** (Ubuntu/Debian) or **dnf** (RHEL family). Use the sections below if you prefer manual control or if `install.sh` cannot find Lustre packages.

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-yaml \
  open-iscsi targetcli-fb fio util-linux

# Lustre (may require your lab's repo on stock Ubuntu)
sudo apt install -y lustre-client-utils || echo "Install Lustre from org repo if missing"

sudo systemctl enable --now iscsid
```

Then install lustre-cli:

```bash
cd lustre-cli && sudo ./scripts/install.sh
```

### RHEL / Rocky / AlmaLinux

```bash
sudo dnf install -y python3 python3-pip python3-pyyaml \
  iscsi-initiator-utils targetcli lustre-client fio util-linux

sudo systemctl enable --now iscsid
```

Then:

```bash
cd lustre-cli && sudo ./scripts/install.sh
```

**Firewall (both families):**

```bash
# firewalld (RHEL)
sudo firewall-cmd --add-port=3260/tcp --permanent && sudo firewall-cmd --reload

# ufw (Ubuntu)
sudo ufw allow 3260/tcp
```

### Other Linux

Install equivalent packages for your distribution, then:

```bash
cd lustre-cli
pip3 install .
sudo lustre-cli check-deps    # lists anything still missing
```

---

## Configuration

Default config file: `/etc/lustre-cli/config.yaml`

```bash
sudo cp config/config.yaml.example /etc/lustre-cli/config.yaml
sudo nano /etc/lustre-cli/config.yaml
```

| Setting | Example | Purpose |
|---------|---------|---------|
| `lustre.mgsnode` | `192.168.1.10@tcp` | MGS network identity |
| `lustre.lnet.interfaces` | `eth0` | NIC for LNet |
| `iscsi.portal_ip` | `0.0.0.0` | Target listen address |
| `lustre.mount.client` | `/mnt/lustre/client` | Client mount for tests |

Use a custom config path:

```bash
export LUSTRE_CLI_CONFIG=/path/to/config.yaml
lustre-cli deploy status
```

---

## Quick start

```bash
sudo lustre-cli check-deps
lustre-cli --help
lustre-cli target create --help
```

---

## Usage guide

### Single-machine lab

Run target and initiator on one Ubuntu VM (good for projects and demos).

```bash
# 1. Create loop-backed disks (safe test devices)
sudo mkdir -p /var/lib/lustre-cli
sudo truncate -s 2G /var/lib/lustre-cli/disk0.img
sudo truncate -s 2G /var/lib/lustre-cli/disk1.img
sudo losetup -f /var/lib/lustre-cli/disk0.img
sudo losetup -f /var/lib/lustre-cli/disk1.img
lsblk    # note devices, e.g. /dev/loop0, /dev/loop1

# 2. Export via iSCSI target
export HOST_IP=$(hostname -I | awk '{print $1}')
sudo lustre-cli target create -d /dev/loop0 --lun 0
sudo lustre-cli target list

# 3. Import via initiator
sudo lustre-cli initiator discover --host 127.0.0.1
sudo lustre-cli initiator login --host 127.0.0.1 \
  --iqn iqn.2024-05.com.lustre-cli:lun0
sudo lustre-cli initiator status
lsblk    # note new /dev/sdX from iSCSI

# 4. Deploy Lustre (replace devices with yours)
sudo lustre-cli deploy format \
  --mgs-device /dev/sdX --mdt-device /dev/sdY \
  --ost-device /dev/sdZ --mgsnode ${HOST_IP}@tcp --force
sudo lustre-cli deploy mount
sudo lustre-cli deploy status

# 5. Validate
sudo lustre-cli validate basic
sudo lustre-cli validate stripe
sudo lustre-cli validate integrity

# 6. Cleanup
sudo lustre-cli teardown
```

### Two-machine lab

| Node | Role | Example IP |
|------|------|------------|
| Server A | iSCSI target (storage) | `10.0.0.10` |
| Server B | Initiator + Lustre client | `10.0.0.11` |

**On Server A:**

```bash
sudo lustre-cli target create -d /dev/sdb --lun 0
sudo lustre-cli target create -d /dev/sdc --lun 1
sudo lustre-cli target list
```

**On Server B:**

```bash
sudo lustre-cli initiator discover --host 10.0.0.10
sudo lustre-cli initiator login --host 10.0.0.10 --iqn iqn.2024-05.com.lustre-cli:lun0
sudo lustre-cli initiator login --host 10.0.0.10 --iqn iqn.2024-05.com.lustre-cli:lun1
sudo lustre-cli initiator status

sudo lustre-cli deploy format \
  --mgs-device /dev/sdb --mdt-device /dev/sdc \
  --ost-device /dev/sdd --mgsnode 10.0.0.10@tcp
sudo lustre-cli deploy mount
sudo lustre-cli validate basic
sudo lustre-cli benchmark run
sudo lustre-cli benchmark report
```

See `scripts/demo-workflow.sh` for a printable command checklist.

### Full command reference

```bash
# iSCSI target (storage server)
sudo lustre-cli target create -d /dev/sdb --lun 0 [--portal-ip IP] [--portal-port 3260]
sudo lustre-cli target list
sudo lustre-cli target delete [--iqn IQN] [--lun N]

# iSCSI initiator (client)
sudo lustre-cli initiator discover --host <IP> [--port 3260]
sudo lustre-cli initiator login --host <IP> --iqn <IQN> [--port 3260]
sudo lustre-cli initiator logout --host <IP> --iqn <IQN>
sudo lustre-cli initiator status

# Lustre
sudo lustre-cli deploy format [--mgs-device DEV] [--mdt-device DEV] \
  --ost-device DEV [--mgsnode IP@tcp] [--fsname NAME] [--force]
sudo lustre-cli deploy mount
sudo lustre-cli deploy status
sudo lustre-cli deploy unmount

# Validation & benchmark
sudo lustre-cli validate basic | stripe | integrity
sudo lustre-cli benchmark run [--runtime SEC] [--stripe N] [--dd]
sudo lustre-cli benchmark report [--file PATH]

# Fault simulation
sudo lustre-cli fault simulate-ost-failure [--index 0]
sudo lustre-cli fault simulate-bad-config
sudo lustre-cli fault simulate-network-drop [--host IP] [--iqn IQN]

# Cleanup
sudo lustre-cli teardown
sudo lustre-cli reset --hard

# Utilities
lustre-cli check-deps
lustre-cli --version
```

---

## Verification & testing

After installation on your Linux distro:

```bash
sudo lustre-cli check-deps          # all tools present
sudo lustre-cli validate basic      # after deploy mount
sudo lustre-cli benchmark run
sudo lustre-cli fault simulate-bad-config
```

Record results in [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for project submission.

---

## Logs & state

| Path | Purpose |
|------|---------|
| `/var/log/lustre-cli.log` | Timestamped operation log |
| `/etc/lustre-cli/config.yaml` | IQNs, devices, mount points |
| `/var/lib/lustre-cli/benchmarks/` | JSON benchmark reports |

```bash
sudo tail -f /var/log/lustre-cli.log
```

---

## Uninstall

```bash
sudo pip3 uninstall lustre-cli
sudo rm -rf /etc/lustre-cli          # optional — removes saved config
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `lustre-cli: command not found` | `cd lustre-cli && sudo pip3 install .` |
| `Missing required tools` | Run `sudo lustre-cli check-deps`; install listed packages for your distro |
| `Permission denied` | Use `sudo` for target, initiator, deploy, validate, fault, teardown |
| `install.sh: $'\r': command not found` | `sed -i 's/\r$//' scripts/install.sh` or `dos2unix scripts/*.sh` |
| Initiator cannot connect | Check IP, port 3260, `sudo systemctl status iscsid`, target ACLs |
| `mkfs.lustre` not found | Install Lustre client from distro or organization repo |
| Mount hangs | Verify `mgsnode` in config; run `sudo lnetctl lnet show` |

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/SETUP.md](docs/SETUP.md) | Detailed system requirements |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Publishing to GitHub and distribution |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How iSCSI and Lustre work together |
| [docs/TEST_REPORT.md](docs/TEST_REPORT.md) | Test report template for submission |

---

## License

MIT
