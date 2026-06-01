"""Module 2 — iSCSI initiator via iscsiadm."""

from __future__ import annotations

import re
from pathlib import Path

from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, device_size_bytes, human_size, require_root, run_cmd

log = get_logger()


def _portal(host: str, port: int) -> str:
    return f"{host}:{port}"


def cmd_discover(host: str, port: int = 3260) -> None:
    require_root()
    check_tools("initiator")
    portal = _portal(host, port)
    log.info("Discovering targets at %s", portal)
    result = run_cmd(
        ["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", portal],
        capture=True,
    )
    print(result.stdout)
    cfg = load_config()
    cfg.setdefault("initiator", {})["last_discovery"] = {
        "host": host,
        "port": port,
        "portal": portal,
    }
    save_config(cfg)


def cmd_login(host: str, iqn: str, port: int = 3260) -> None:
    require_root()
    check_tools("initiator")
    portal = _portal(host, port)
    log.info("Logging in to %s at %s", iqn, portal)

    run_cmd(["iscsiadm", "-m", "node", "-T", iqn, "-p", portal, "--login"])
    run_cmd(["iscsiadm", "-m", "node", "-T", iqn, "-p", portal, "-o", "update", "-n", "node.startup", "-v", "automatic"])

    device = _find_session_device(iqn)
    if device:
        size = device_size_bytes(device)
        print(f"Logged in. Device: {device} ({human_size(size)})")
    else:
        print(f"Logged in to {iqn}. Run 'lustre-cli initiator status' to find device.")

    cfg = load_config()
    sessions_cfg = cfg.setdefault("initiator", {}).setdefault("sessions", [])
    entry = {"host": host, "port": port, "iqn": iqn, "portal": portal, "device": device}
    sessions_cfg = [s for s in sessions_cfg if s.get("iqn") != iqn]
    sessions_cfg.append(entry)
    cfg["initiator"]["sessions"] = sessions_cfg
    save_config(cfg)


def _find_session_device(iqn: str) -> str | None:
    result = run_cmd(["iscsiadm", "-m", "session", "-P", "3"], capture=True, check=False)
    if result.returncode != 0:
        return None
    current_iqn = None
    for line in result.stdout.splitlines():
        m = re.search(r"Target:\s+(\S+)", line)
        if m:
            current_iqn = m.group(1)
        if current_iqn == iqn:
            dm = re.search(r"Attached scsi disk (\S+)", line)
            if dm:
                dev = dm.group(1)
                return dev if dev.startswith("/dev/") else f"/dev/{dev}"
    # fallback: newest sd device from lsblk
    lsblk = run_cmd(["lsblk", "-dn", "-o", "NAME,TYPE,TRAN"], capture=True, check=False)
    for line in reversed(lsblk.stdout.splitlines()):
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "disk" and parts[2] == "iscsi":
            return f"/dev/{parts[0]}"
    return None


def cmd_logout(host: str, iqn: str, port: int = 3260) -> None:
    require_root()
    check_tools("initiator")
    portal = _portal(host, port)
    run_cmd(["iscsiadm", "-m", "node", "-T", iqn, "-p", portal, "--logout"])
    cfg = load_config()
    sessions = cfg.get("initiator", {}).get("sessions", [])
    cfg.setdefault("initiator", {})["sessions"] = [
        s for s in sessions if not (s.get("iqn") == iqn and s.get("host") == host)
    ]
    save_config(cfg)
    print(f"Logged out from {iqn}")


def cmd_status() -> None:
    check_tools("initiator")
    result = run_cmd(["iscsiadm", "-m", "session"], capture=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        print("No active iSCSI sessions.")
    else:
        print("Active sessions:")
        print(result.stdout)

    detail = run_cmd(["iscsiadm", "-m", "session", "-P", "3"], capture=True, check=False)
    if detail.stdout:
        print("\nSession details:")
        print(detail.stdout)

    cfg = load_config()
    for s in cfg.get("initiator", {}).get("sessions", []):
        dev = s.get("device")
        if dev and Path(dev).exists():
            try:
                size = human_size(device_size_bytes(dev))
                print(f"Config: {s['iqn']} -> {dev} ({size})")
            except CLIError:
                print(f"Config: {s['iqn']} -> {dev}")
