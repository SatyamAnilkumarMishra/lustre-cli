"""Module 6 — Failure and misconfiguration simulation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lustre_cli.config import load_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd

log = get_logger()

REMEDIATION = {
    "ost_offline": "Restore OST: verify iSCSI session, remount OST, run 'lctl dl' to confirm.",
    "bad_mgs": "Verify lustre.mgsnode IP and LNet connectivity (lnetctl net show).",
    "format_exists": "Use --force with deploy format or wipefs device before reformat.",
    "login_fail": "Check target IQN, firewall (tcp/3260), and target ACLs.",
    "network_drop": "Restore network, restart iscsi/session, verify with initiator status.",
}


def _log_fault(event: str, detail: str, remediation_key: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    msg = f"[FAULT {ts}] {event}: {detail}"
    remedy = REMEDIATION.get(remediation_key, "Review logs and configuration.")
    log.error("%s | Remediation: %s", msg, remedy)
    print(msg)
    print(f"Remediation: {remedy}")


def cmd_simulate_ost_failure(ost_index: int = 0) -> None:
    require_root()
    check_tools("deploy")
    cfg = load_config()
    ost_base = cfg["lustre"]["mount"]["ost_base"]
    ost_mp = f"{ost_base}{ost_index:04d}"
    if not Path(ost_mp).exists():
        _log_fault("ost_failure", f"OST mount {ost_mp} not found", "ost_offline")
        raise CLIError(f"OST mount not found: {ost_mp}")

    # FIXED: Added capture=True so stderr is actually read upon unmount failures
    result = run_cmd(["umount", ost_mp], check=False, capture=True)
    if result.returncode == 0:
        _log_fault("ost_failure", f"Unmounted OST {ost_index} at {ost_mp}", "ost_offline")
        print("Observe client behavior: lfs df, writes to client mount.")
        run_cmd(["lfs", "df", "-h"], check=False)
    else:
        err = (result.stderr or "").strip()
        _log_fault("ost_failure", f"Unmount failed: {err}", "ost_offline")


def cmd_simulate_bad_config() -> None:
    require_root()
    cfg = load_config()
    lustre = cfg["lustre"]
    mdt_dev = lustre.get("mdt_device")
    if not mdt_dev:
        _log_fault("bad_config", "No MDT device in config", "bad_mgs")
        raise CLIError("Configure MDT device before simulating bad MGS config")

    bad_mgsnode = "192.0.2.254@tcp"  # TEST-NET-1, should be unreachable
    fake_mp = "/mnt/lustre/fault-test-mdt"
    Path(fake_mp).mkdir(parents=True, exist_ok=True)
    
    # FIXED: Replaced forward slash with mandatory colon separator for valid mount syntax
    result = run_cmd(
        ["mount", "-t", "lustre", f"{bad_mgsnode}:/{lustre['fsname']}/MDT0000", fake_mp],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "mount failed").strip()
        _log_fault("bad_config", f"Expected mount failure: {err}", "bad_mgs")
    else:
        run_cmd(["umount", fake_mp], check=False)
        _log_fault("bad_config", "Mount unexpectedly succeeded", "bad_mgs")

    # Already formatted device
    if mdt_dev and Path(mdt_dev).exists():
        fmt = run_cmd(
            ["mkfs.lustre", "--mdt", f"--mgsnode={lustre.get('mgsnode', '127.0.0.1@tcp')}", mdt_dev],
            check=False,
            capture=True,
        )
        if fmt.returncode != 0:
            _log_fault("format_exists", (fmt.stderr or "mkfs failed").strip(), "format_exists")
        else:
            _log_fault("format_exists", "mkfs succeeded (device may have been empty)", "format_exists")


def cmd_simulate_network_drop(host: str | None = None, iqn: str | None = None) -> None:
    require_root()
    check_tools("initiator")
    cfg = load_config()
    sessions = cfg.get("initiator", {}).get("sessions", [])
    if not sessions and not (host and iqn):
        raise CLIError("No initiator sessions in config. Login first or pass --host and --iqn.")

    session = sessions[0] if sessions else {"host": host, "iqn": iqn, "port": 3260}
    portal = f"{session['host']}:{session.get('port', 3260)}"
    wrong_iqn = session["iqn"] + "-INVALID"

    result = run_cmd(
        ["iscsiadm", "-m", "node", "-T", wrong_iqn, "-p", portal, "--login"],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "login failed").strip()
        _log_fault("network_drop", f"Wrong IQN login failed (expected): {err}", "login_fail")
    else:
        run_cmd(["iscsiadm", "-m", "node", "-T", wrong_iqn, "-p", portal, "--logout"], check=False)

    # Simulate unreachable portal
    bad_portal = "192.0.2.1:3260"
    disc = run_cmd(
        ["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", bad_portal],
        check=False,
        capture=True,
    )
    if disc.returncode != 0:
        # FIXED: Wrapped disc.stderr in a None-safe fallback guard before calling .strip()
        err_msg = (disc.stderr or "").strip()
        _log_fault("network_drop", f"Discovery to {bad_portal} failed: {err_msg}", "network_drop")
