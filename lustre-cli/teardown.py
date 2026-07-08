"""Module 7 — Teardown and cleanup."""

from __future__ import annotations

from lustre_cli import deploy, initiator, target
from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd


def cmd_teardown(wipe: bool = False) -> None:
    require_root()
    check_tools("general")
    log = get_logger()
    cfg = load_config()

    log.info("Starting teardown (clients -> OST -> MDT -> MGS)")
    try:
        deploy.cmd_unmount()
    except CLIError as exc:
        log.warning("Unmount: %s", exc)

    # FIXED: Wipe block devices while iSCSI fabrics are still logged in and mapped
    if wipe:
        _wipe_devices(cfg)

    sessions = cfg.get("initiator", {}).get("sessions", [])
    for s in sessions:
        try:
            initiator.cmd_logout(s["host"], s["iqn"], s.get("port", 3260))
        except CLIError as exc:
            log.warning("Logout %s: %s", s.get("iqn"), exc)

    print("Teardown complete.")


def cmd_reset_hard() -> None:
    require_root()
    log = get_logger()
    
    # Snapshot target IQNs from current disk state before invoking subcommands
    initial_cfg = load_config()
    target_iqns = [t["iqn"] for t in initial_cfg.get("targets", []) if "iqn" in t]

    # Executes teardown (and wipes active target connections cleanly)
    cmd_teardown(wipe=True)

    # Clean target frameworks individually
    for iqn in target_iqns:
        try:
            target.cmd_delete(iqn=iqn)
        except CLIError as exc:
            log.warning("Target delete %s: %s", iqn, exc)

    # Execute absolute fallback fabric flushes
    run_cmd(["iscsiadm", "-m", "node", "--op", "delete"], check=False)
    run_cmd(["targetcli", "clearconfig", "confirm=true"], check=False)
    run_cmd(["targetcli", "saveconfig"], check=False)

    # FIXED: Reload config from disk to obtain current state updates before updating
    cfg = load_config()
    cfg["targets"] = []
    cfg.setdefault("initiator", {})["sessions"] = []
    cfg.setdefault("lustre", {})["ost_devices"] = []
    save_config(cfg)
    
    log.info("Hard reset completed")
    print("Hard reset complete. Config cleared; targets and sessions removed.")


def _wipe_devices(cfg: dict) -> None:
    log = get_logger()
    devices = []
    lustre = cfg.get("lustre", {})
    
    for key in ("mgs_device", "mdt_device"):
        if lustre.get(key):
            devices.append(lustre[key])
            
    devices.extend(lustre.get("ost_devices", []))
    for dev in devices:
        if dev:
            log.info("Wiping %s", dev)
            run_cmd(["wipefs", "-a", dev], check=False)
            print(f"Wiped signatures on {dev}")
