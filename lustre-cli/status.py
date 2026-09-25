"""Module for top-level system status and observability reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lustre_cli.config import load_config
from lustre_cli.logging_util import get_logger
from lustre_cli.state import load_state
from lustre_cli.utils import run_cmd, human_size

log = get_logger()


def _is_mounted(path: str) -> bool:
    from lustre_cli.utils import is_dry_run
    if is_dry_run():
        return False
    res = run_cmd(["findmnt", "-n", path], check=False, capture=True)
    return res.returncode == 0


def cmd_status(as_json: bool = False) -> None:
    cfg = load_config()
    state = load_state()

    status_data: dict[str, Any] = {}

    # 1. iSCSI Sessions
    active_sessions = []
    sess_res = run_cmd(["iscsiadm", "-m", "session"], check=False, capture=True)
    if sess_res.returncode == 0:
        for line in sess_res.stdout.splitlines():
            line = line.strip()
            if line:
                active_sessions.append(line)
    status_data["iscsi_sessions"] = {
        "active": active_sessions,
        "configured": state.get("sessions", []),
    }

    # 2. Lustre Mounts
    mounts = cfg["lustre"]["mount"]
    osts = cfg["lustre"].get("ost_devices", [])
    mgs_mp = mounts["mgs"]
    mdt_mp = mounts["mdt"]
    ost_base = mounts["ost_base"]
    client_mp = mounts["client"]

    ost_mounts = []
    for idx in range(len(osts)):
        mp = f"{ost_base}{idx:04d}"
        ost_mounts.append({"mountpoint": mp, "mounted": _is_mounted(mp)})

    status_data["lustre_mounts"] = {
        "mgs": {"mountpoint": mgs_mp, "mounted": _is_mounted(mgs_mp)},
        "mdt": {"mountpoint": mdt_mp, "mounted": _is_mounted(mdt_mp)},
        "osts": ost_mounts,
        "client": {"mountpoint": client_mp, "mounted": _is_mounted(client_mp)},
    }

    # 3. Disk / Device Health
    disks = []
    lsblk = run_cmd(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT"], check=False, capture=True)
    if lsblk.returncode == 0:
        try:
            disks_info = json.loads(lsblk.stdout)
            disks = disks_info.get("blockdevices", [])
        except Exception:
            pass
    status_data["disks"] = disks

    # 4. Last Benchmark Results
    benchmark_report = None
    last_report_path = cfg.get("benchmark", {}).get("last_report")
    if last_report_path and Path(last_report_path).is_file():
        try:
            benchmark_report = json.loads(Path(last_report_path).read_text(encoding="utf-8"))
        except Exception:
            pass
    status_data["last_benchmark"] = {
        "report_path": last_report_path,
        "results": benchmark_report,
    }

    # 5. Last Validation State (from state file)
    status_data["last_validation"] = {
        "formatted": state.get("formatted", {}),
        "mounted_state": state.get("mounted", {}),
    }

    if as_json:
        print(json.dumps(status_data, indent=2))
        return

    # Print a nice human readable format
    print("====================================================")
    print("               LUSTRE-CLI STATUS REPORT             ")
    print("====================================================")
    
    print("\n[iSCSI initiator sessions]")
    if active_sessions:
        for s in active_sessions:
            print(f"  * {s}")
    else:
        print("  No active iSCSI initiator sessions found.")

    print("\n[Lustre Mountpoints]")
    print(f"  MGS ({mgs_mp}): {'MOUNTED' if status_data['lustre_mounts']['mgs']['mounted'] else 'NOT MOUNTED'}")
    print(f"  MDT ({mdt_mp}): {'MOUNTED' if status_data['lustre_mounts']['mdt']['mounted'] else 'NOT MOUNTED'}")
    for idx, ost in enumerate(ost_mounts):
        print(f"  OST {idx:02d} ({ost['mountpoint']}): {'MOUNTED' if ost['mounted'] else 'NOT MOUNTED'}")
    print(f"  Client ({client_mp}): {'MOUNTED' if status_data['lustre_mounts']['client']['mounted'] else 'NOT MOUNTED'}")

    print("\n[Last Benchmark Report]")
    if last_report_path:
        print(f"  Path: {last_report_path}")
        if benchmark_report:
            from lustre_cli.benchmark import _print_table
            _print_table(benchmark_report)
    else:
        print("  No benchmark reports found.")

    print("\n[Validation/Deployment State]")
    print(f"  Formatted: {state.get('formatted', {})}")
    print(f"  Mounted tracked state: {state.get('mounted', {})}")
    print("====================================================")
