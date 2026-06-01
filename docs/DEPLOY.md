# Deploy lustre-cli for download on any Linux machine

This guide is for **you (publisher)** and **end users** who install on Ubuntu, RHEL, Rocky, etc.

---

## For you: publish the project (one time)

### Step 1 — Push to GitHub

On your Windows/Mac dev machine:

```bash
cd lustre-cli   # your project folder
git init
git add .
git commit -m "Release lustre-cli v1.0.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/lustre-cli.git
git push -u origin main
```

### Step 2 — Create a release (recommended)

1. GitHub → your repo → **Releases** → **Create a new release**
2. Tag: `v1.0.0`
3. Upload is optional (GitHub auto-packages source zip/tar.gz)
4. Publish

Users can then download a fixed version without using Git.

### Step 3 — Share this with users

Give them **one** of:

| Method | URL / command |
|--------|----------------|
| Clone | `git clone https://github.com/YOUR_USERNAME/lustre-cli.git` |
| Release ZIP | `https://github.com/YOUR_USERNAME/lustre-cli/archive/refs/tags/v1.0.0.tar.gz` |
| One-line install | See below |

---

## For users: install on any Linux machine

Requirements:

- Linux with `bash`, `python3` (3.9+), `pip`
- `sudo` / root for storage commands
- Distro packages: `targetcli`, `open-iscsi`, Lustre utils, `fio` (names differ on Ubuntu vs RHEL)

### Method A — Git clone + install script (best)

```bash
git clone https://github.com/YOUR_USERNAME/lustre-cli.git
cd lustre-cli
chmod +x scripts/install.sh
sudo ./scripts/install.sh
lustre-cli check-deps
```

### Method B — Download release tarball (no Git)

```bash
curl -sL https://github.com/YOUR_USERNAME/lustre-cli/archive/refs/tags/v1.0.0.tar.gz -o lustre-cli.tar.gz
tar xzf lustre-cli.tar.gz
cd lustre-cli-1.0.0
chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

(Adjust folder name if tag differs.)

### Method C — pip install from GitHub

```bash
sudo pip3 install "git+https://github.com/YOUR_USERNAME/lustre-cli.git"
sudo mkdir -p /etc/lustre-cli /var/lib/lustre-cli/benchmarks
sudo curl -sL https://raw.githubusercontent.com/YOUR_USERNAME/lustre-cli/main/config/config.yaml.example \
  -o /etc/lustre-cli/config.yaml
lustre-cli check-deps
```

### Method D — One-line remote install (after publishing)

Replace `YOUR_USERNAME` and branch/tag:

```bash
curl -sL https://raw.githubusercontent.com/YOUR_USERNAME/lustre-cli/main/scripts/install.sh | sudo bash -s -- --from-github YOUR_USERNAME
```

Or clone via curl + install:

```bash
curl -sL https://github.com/YOUR_USERNAME/lustre-cli/archive/refs/heads/main.tar.gz | tar xz
cd lustre-cli-main && sudo ./scripts/install.sh
```

---

## After install (every machine)

```bash
# Verify CLI
lustre-cli --version
lustre-cli --help

# Check system tools
sudo lustre-cli check-deps

# Edit config
sudo nano /etc/lustre-cli/config.yaml

# Logs
sudo tail -f /var/log/lustre-cli.log
```

---

## Distro notes

| Distro | Package manager | Notes |
|--------|-----------------|-------|
| Ubuntu 22.04/24.04 | `apt` | `install.sh` uses apt; Lustre may need extra repo |
| RHEL / Rocky / Alma | `dnf` | `install.sh` uses dnf |
| Other | manual | Install deps by hand, then `pip3 install .` in repo |

If `lustre-client-utils` is not available, install Lustre from your organization’s repo, then:

```bash
cd lustre-cli
sudo pip3 install .
```

---

## Uninstall

```bash
sudo pip3 uninstall lustre-cli
sudo rm -rf /etc/lustre-cli   # optional, removes config
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `lustre-cli: command not found` | Re-run `sudo pip3 install .` in project dir |
| `check-deps` fails | Install listed packages for your distro |
| `install.sh: bad interpreter` | Run `sed -i 's/\r$//' scripts/install.sh` |
| Permission errors | Use `sudo` for target/initiator/deploy commands |
