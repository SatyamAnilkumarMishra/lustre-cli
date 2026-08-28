"""Module 3 — Lustre filesystem deployment with state tracking and rollbacks."""

from __future__ import annotations

import os
from pathlib import Path

from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd, tool_available
from lustre_cli.state import load_state, save_state, mark_formatted, mark_mounted

log = get_logger()


def _load_modules() -> None:
    for mod in ("libcfs", "lnet", "lustre"):
        run_cmd(["modprobe", mod], check=False)


def _configure_lnet(cfg: dict) -> None:
    lnet = cfg["lustre"]["lnet"]
    interfaces = lnet.get("interfaces") or []
    if not tool_available("lnetctl"):
        log.warning("lnetctl not available; skipping LNet configuration")
        return
    run_cmd(["lnetctl", "net", "del", "--net", "tcp"], check=False)
    if interfaces:
        for iface in interfaces:
            run_cmd(["lnetctl", "net", "add", "--net", "tcp", "--if", iface])
    else:
        run_cmd(["lnetctl", "lnet", "configure", "--all"], check=False)
    run_cmd(["lnetctl", "lnet", "up"], check=False)


def is_device_formatted_lustre(device: str) -> bool:
    from lustre_cli.utils import is_dry_run
    if is_dry_run():
        return False
    # Run blkid to check filesystem type
    res = run_cmd(["blkid", "-o", "value", "-s", "TYPE", device], check=False, capture=True)
    return "lustre" in res.stdout.strip().lower()


def cmd_format(
    mgs_device: str | None = None,
    mdt_device: str | None = None,
    ost_devices: list[str] | None = None,
    mgsnode: str | None = None,
    fsname: str | None = None,
    force: bool = False,
    yes: bool = False,
) -> None:
    require_root()
    check_tools("deploy")
    cfg = load_config()
    state = load_state()

    lustre = cfg["lustre"]
    mgs_dev = mgs_device or lustre.get("mgs_device")
    mdt_dev = mdt_device or lustre.get("mdt_device")
    osts = ost_devices or lustre.get("ost_devices") or []
    mgs_node = mgsnode or lustre.get("mgsnode")
    name = fsname or lustre["fsname"]

    if not mgs_dev:
        raise CLIError("MGS device required (--mgs-device or config lustre.mgs_device)")
    if not mdt_dev:
        raise CLIError("MDT device required")
    if not osts:
        raise CLIError("At least one OST device required")
    if not mgs_node:
        raise CLIError("MGS node required (--mgsnode or config lustre.mgsnode, e.g. 10.0.0.1@tcp)")

    _validate_devices([mgs_dev, mdt_dev, *osts])

    from lustre_cli.utils import is_dry_run
    if force and not yes and not is_dry_run():
        print("WARNING: Reformat (--force) requested. This will permanently destroy data on target devices!")
        print("Devices to be reformatted:")
        print(f"  - MGS: {mgs_dev}")
        print(f"  - MDT: {mdt_dev}")
        for o in osts:
            print(f"  - OST: {o}")
        val = input("Are you absolutely sure you want to format these devices? [y/N]: ")
        if val.lower() not in ("y", "yes"):
            raise CLIError("Operation cancelled.")
