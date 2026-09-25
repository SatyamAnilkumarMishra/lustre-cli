"""Module 7 — Teardown and cleanup with state tracking and logging."""

from __future__ import annotations

from lustre_cli import deploy, initiator, target
from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd
from lustre_cli.state import load_state, save_state

log = get_logger()


def cmd_teardown(wipe: bool = False) -> None:
    require_root()
    check_tools("general")
    cfg = load_config()
    state = load_state()

    log.info("Starting teardown (clients -> OST -> MDT -> MGS)")
    try:
        deploy.cmd_unmount()
    except CLIError as exc:
        log.warning("Unmount failed during teardown: %s", exc)

    sessions = state.get("sessions", [])
    for s in sessions:
        try:
            initiator.cmd_logout(s["host"], s["iqn"], s.get("port", 3260))
        except CLIError as exc:
            log.warning("Logout %s failed during teardown: %s", s.get("iqn"), exc)

    if wipe:
        _wipe_devices(cfg)

    log.info("Teardown complete.")


def cmd_reset_hard(yes: bool = False) -> None:
    require_root()
    cfg = load_config()
    state = load_state()

    from lustre_cli.utils import is_dry_run
    if not yes and not is_dry_run():
        targets = state.get("targets", [])
        sessions = state.get("sessions", [])
        devices = []
        lustre = cfg.get("lustre", {})
        for key in ("mgs_device", "mdt_device"):
            if lustre.get(key):
                devices.append(lustre[key])
        devices.extend(lustre.get("ost_devices", []))

        print("WARNING: You are about to perform a hard reset!")
        print("This will destroy all data on the following devices:")
        for dev in devices:
            print(f"  - {dev}")
        print("This will delete the following iSCSI targets:")
        for t in targets:
            print(f"  - {t['iqn']}")
        print(f"This will log out and delete {len(sessions)} active initiator sessions.")
        
        val = input("Are you absolutely sure you want to proceed? [y/N]: ")
        if val.lower() not in ("y", "yes"):
            raise CLIError("Operation cancelled.")

    cmd_teardown(wipe=True)

    for t in list(state.get("targets", [])):
        try:
            target.cmd_delete(iqn=t["iqn"])
        except CLIError as exc:
            log.warning("Target delete %s failed: %s", t.get("iqn"), exc)

    run_cmd(["iscsiadm", "-m", "node", "--op", "delete"], check=False)
    run_cmd(["targetcli", "clearconfig", "confirm=true"], check=False)
    run_cmd(["targetcli", "saveconfig"], check=False)

    # Clear state & config
    state["targets"] = []
    state["sessions"] = []
    state["formatted"] = {}
    state["mounted"] = {}
    save_state(state)

    cfg["targets"] = []
    cfg.setdefault("initiator", {})["sessions"] = []
    cfg["lustre"]["ost_devices"] = []
    save_config(cfg)
    
    log.info("Hard reset complete. Config cleared; targets and sessions removed.")


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
            log.info("Wiped signatures on %s", dev)
