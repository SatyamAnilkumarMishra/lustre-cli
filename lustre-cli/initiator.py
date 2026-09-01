"""Module 2 — iSCSI initiator via iscsiadm with CHAP and state tracking."""

from __future__ import annotations

import re
from pathlib import Path

from lustre_cli.config import load_config, save_config, load_secrets
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, device_size_bytes, human_size, require_root, run_cmd
from lustre_cli.state import load_state, save_state

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
    log.info(result.stdout)
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
    state = load_state()

    # Check if already logged in (idempotency)
    sessions_res = run_cmd(["iscsiadm", "-m", "session"], check=False, capture=True)
    if sessions_res.returncode == 0 and iqn in sessions_res.stdout:
        log.info("Session to %s already active. Skipping login.", iqn)
        device = _find_session_device(iqn)
        _record_login_state(state, host, port, iqn, portal, device)
        return

    log.info("Logging in to %s at %s", iqn, portal)

    # Ensure node record exists in db
    run_cmd(["iscsiadm", "-m", "node", "-o", "new", "-T", iqn, "-p", portal], check=False)

    # Support CHAP authentication
    secrets = load_secrets()
    if secrets["username"] and secrets["password"]:
        log.info("Configuring CHAP authentication for iSCSI login to %s", iqn)
        run_cmd([
            "iscsiadm", "-m", "node", "-T", iqn, "-p", portal,
            "-o", "update", "-n", "node.session.auth.authmethod", "-v", "CHAP"
        ])
        run_cmd([
            "iscsiadm", "-m", "node", "-T", iqn, "-p", portal,
            "-o", "update", "-n", "node.session.auth.username", "-v", secrets["username"]
        ], sensitive={secrets["username"]})
        run_cmd([
            "iscsiadm", "-m", "node", "-T", iqn, "-p", portal,
            "-o", "update", "-n", "node.session.auth.password", "-v", secrets["password"]
        ], sensitive={secrets["password"]})

    run_cmd(["iscsiadm", "-m", "node", "-T", iqn, "-p", portal, "--login"])
    run_cmd([
        "iscsiadm", "-m", "node", "-T", iqn, "-p", portal,
        "-o", "update", "-n", "node.startup", "-v", "automatic"
    ])

    device = _find_session_device(iqn)
    if device:
        try:
            size = device_size_bytes(device)
            log.info("Logged in. Device: %s (%s)", device, human_size(size))
        except Exception:
            log.info("Logged in. Device: %s", device)
    else:
        log.info("Logged in to %s. Active device could not be resolved immediately.", iqn)

    _record_login_state(state, host, port, iqn, portal, device)


def _record_login_state(state: dict, host: str, port: int, iqn: str, portal: str, device: str | None) -> None:
    sessions_state = state.setdefault("sessions", [])
    entry = {"host": host, "port": port, "iqn": iqn, "portal": portal, "device": device}
    sessions_state = [s for s in sessions_state if s.get("iqn") != iqn]
    sessions_state.append(entry)
    state["sessions"] = sessions_state
    save_state(state)

    cfg = load_config()
    sessions_cfg = cfg.setdefault("initiator", {}).setdefault("sessions", [])
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

    state = load_state()
    sessions_state = state.get("sessions", [])
    state["sessions"] = [
        s for s in sessions_state if not (s.get("iqn") == iqn and s.get("host") == host)
    ]
    save_state(state)

    cfg = load_config()
    sessions = cfg.get("initiator", {}).get("sessions", [])
    cfg.setdefault("initiator", {})["sessions"] = [
        s for s in sessions if not (s.get("iqn") == iqn and s.get("host") == host)
    ]
    save_config(cfg)
    log.info("Logged out from %s", iqn)


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

    state = load_state()
    for s in state.get("sessions", []):
        dev = s.get("device")
        if dev and Path(dev).exists():
            try:
                size = human_size(device_size_bytes(dev))
                print(f"Config: {s['iqn']} -> {dev} ({size})")
            except CLIError:
                print(f"Config: {s['iqn']} -> {dev}")
