"""Module 7 — Teardown and cleanup."""

from __future__ import annotations

from lustre_cli import deploy, initiator, target
from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd

log = get_logger()


def cmd_teardown(wipe: bool = False) -> None:
    require_root()
    check_tools("general")
    cfg = load_config()

    log.info("Starting teardown (clients -> OST -> MDT -> MGS)")
    try:
        deploy.cmd_unmount()
    except CLIError as exc:
        log.warning("Unmount: %s", exc)

    sessions = cfg.get("initiator", {}).get("sessions", [])
    for s in sessions:
        try:
            initiator.cmd_logout(s["host"], s["iqn"], s.get("port", 3260))
        except CLIError as exc:
            log.warning("Logout %s: %s", s.get("iqn"), exc)

    if wipe:
        _wipe_devices(cfg)

    print("Teardown complete.")


def cmd_reset_hard() -> None:
    require_root()
    cfg = load_config()

    cmd_teardown(wipe=True)

    for t in list(cfg.get("targets", [])):
        try:
            target.cmd_delete(iqn=t["iqn"])
        except CLIError as exc:
            log.warning("Target delete %s: %s", t.get("iqn"), exc)

    run_cmd(["iscsiadm", "-m", "node", "--op", "delete"], check=False)
    run_cmd(["targetcli", "clearconfig", "confirm=true"], check=False)
    run_cmd(["targetcli", "saveconfig"], check=False)

    cfg["targets"] = []
    cfg.setdefault("initiator", {})["sessions"] = []
    cfg["lustre"]["ost_devices"] = []
    save_config(cfg)
    log.info("Hard reset completed")
    print("Hard reset complete. Config cleared; targets and sessions removed.")


def _wipe_devices(cfg: dict) -> None:
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
