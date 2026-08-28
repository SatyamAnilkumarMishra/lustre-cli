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

    _load_modules()
    _configure_lnet(cfg)

    force_flag = ["--force"] if force else []
    mgsnode_arg = f"--mgsnode={mgs_node}"

    formatted_in_this_run = []
    try:
        # Format MGS
        if not force and is_device_formatted_lustre(mgs_dev):
            log.info("MGS device %s already formatted. Skipping format.", mgs_dev)
        else:
            log.info("Formatting MGS on %s", mgs_dev)
            run_cmd(
                ["mkfs.lustre", "--mgs", f"--fsname={name}", "--reformat", *force_flag, mgs_dev]
            )
            formatted_in_this_run.append(mgs_dev)

        # Format MDT
        if not force and is_device_formatted_lustre(mdt_dev):
            log.info("MDT device %s already formatted. Skipping format.", mdt_dev)
        else:
            log.info("Formatting MDT on %s", mdt_dev)
            run_cmd(
                [
                    "mkfs.lustre",
                    "--mdt",
                    mgsnode_arg,
                    f"--fsname={name}",
                    "--index=0",
                    "--reformat",
                    *force_flag,
                    mdt_dev,
                ]
            )
            formatted_in_this_run.append(mdt_dev)

        # Format OSTs
        for idx, ost_dev in enumerate(osts):
            if not force and is_device_formatted_lustre(ost_dev):
                log.info("OST device %s already formatted. Skipping format.", ost_dev)
            else:
                log.info("Formatting OST %d on %s", idx, ost_dev)
                run_cmd(
                    [
                        "mkfs.lustre",
                        "--ost",
                        mgsnode_arg,
                        f"--fsname={name}",
                        f"--index={idx}",
                        "--reformat",
                        *force_flag,
                        ost_dev,
                    ]
                )
                formatted_in_this_run.append(ost_dev)

    except Exception as exc:
        log.error("Formatting failed. Rolling back formatted devices: %s", formatted_in_this_run)
        for dev in formatted_in_this_run:
            try:
                run_cmd(["wipefs", "-a", dev], check=False)
                log.info("Rolled back (wiped signature): %s", dev)
            except Exception as rollback_err:
                log.error("Failed to wipe signature of %s during rollback: %s", dev, rollback_err)
        raise CLIError(f"Deployment formatting failed: {exc}")

    # Save to state tracking
    mark_formatted(mgs=mgs_dev, mdt=mdt_dev, osts=osts)

    lustre["mgs_device"] = mgs_dev
    lustre["mdt_device"] = mdt_dev
    lustre["ost_devices"] = osts
    lustre["mgsnode"] = mgs_node
    lustre["fsname"] = name
    save_config(cfg)
    log.info("Lustre filesystem '%s' formatted successfully.", name)


def _validate_devices(devices: list[str]) -> None:
    from lustre_cli.utils import is_dry_run
    if is_dry_run():
        return
    for dev in devices:
        if not Path(dev).exists():
            raise CLIError(f"Device not found: {dev}")


def cmd_mount() -> None:
    require_root()
    check_tools("deploy")
    cfg = load_config()
    lustre = cfg["lustre"]
    mounts = lustre["mount"]
    mgsnode = lustre.get("mgsnode", "")
    fsname = lustre["fsname"]
    osts = lustre.get("ost_devices", [])

    _load_modules()
    _configure_lnet(cfg)

    mgs_mp = mounts["mgs"]
    mdt_mp = mounts["mdt"]
    ost_base = mounts["ost_base"]
    client_mp = mounts["client"]

    for mp in (mgs_mp, mdt_mp, ost_base, client_mp):
        Path(mp).mkdir(parents=True, exist_ok=True)

    mgs_spec = f"{mgsnode}/{fsname}/MGS"
    mdt_spec = f"{mgsnode}/{fsname}/MDT0000"
    client_spec = f"{mgsnode}/{fsname}"

    mounted_in_this_run = []
    try:
        # Mount MGS
        if lustre.get("mgs_device"):
            mgs_dev = lustre["mgs_device"]
            if _is_mounted(mgs_mp):
                log.info("%s already mounted. Skipping.", mgs_mp)
            else:
                _mount(mgs_dev, mgs_mp, ["-t", "lustre"])
                mounted_in_this_run.append(mgs_mp)

        # Mount MDT
        if lustre.get("mdt_device"):
            mdt_dev = lustre["mdt_device"]
            if _is_mounted(mdt_mp):
                log.info("%s already mounted. Skipping.", mdt_mp)
            else:
                _mount(mdt_dev, mdt_mp, ["-t", "lustre"])
                mounted_in_this_run.append(mdt_mp)

        # Mount OSTs
        for idx, ost_dev in enumerate(osts):
            ost_mp = f"{ost_base}{idx:04d}"
            Path(ost_mp).mkdir(parents=True, exist_ok=True)
            if _is_mounted(ost_mp):
                log.info("%s already mounted. Skipping.", ost_mp)
            else:
                _mount(ost_dev, ost_mp, ["-t", "lustre"])
                mounted_in_this_run.append(ost_mp)

        # Mount Client
        if _is_mounted(client_mp):
            log.info("%s already mounted. Skipping.", client_mp)
        else:
            _mount(client_spec, client_mp, ["-t", "lustre", "-o", "user_xattr"])
            mounted_in_this_run.append(client_mp)

    except Exception as exc:
        log.error("Mounting failed. Rolling back mounted points: %s", mounted_in_this_run)
        for mp in reversed(mounted_in_this_run):
            try:
                run_cmd(["umount", mp], check=False)
                log.info("Rolled back (unmounted): %s", mp)
            except Exception as rollback_err:
                log.error("Failed to unmount %s during rollback: %s", mp, rollback_err)
        raise CLIError(f"Deployment mounting failed: {exc}")

    # Track mounted state
    mark_mounted(
        mgs=_is_mounted(mgs_mp),
        mdt=_is_mounted(mdt_mp),
        osts=[_is_mounted(f"{ost_base}{i:04d}") for i in range(len(osts))],
        client=_is_mounted(client_mp)
    )

    cfg.setdefault("deploy", {})["mounted"] = True
    save_config(cfg)
    log.info("Lustre components mounted. Client mount: %s", client_mp)


def _mount(device_or_spec: str, mountpoint: str, extra_opts: list[str]) -> None:
    if _is_mounted(mountpoint):
        log.info("%s already mounted", mountpoint)
        return
    args = ["mount"] + extra_opts + [device_or_spec, mountpoint]
    run_cmd(args)


def _is_mounted(path: str) -> bool:
    from lustre_cli.utils import is_dry_run
    if is_dry_run():
        return False
    result = run_cmd(["findmnt", "-n", path], capture=True, check=False)
    return result.returncode == 0


def cmd_status() -> None:
    check_tools("deploy")
    print("=== mount points ===")
    run_cmd(["findmnt", "-t", "lustre"], check=False)
    print("\n=== lctl dl ===")
    run_cmd(["lctl", "dl"], check=False)
    print("\n=== lfs df ===")
    run_cmd(["lfs", "df", "-h"], check=False)


def cmd_unmount() -> None:
    require_root()
    cfg = load_config()
    mounts = cfg["lustre"]["mount"]
    client_mp = mounts["client"]
    ost_base = mounts["ost_base"]
    osts = cfg["lustre"].get("ost_devices", [])

    # Client first
    _umount(client_mp)
    for idx in range(len(osts) - 1, -1, -1):
        _umount(f"{ost_base}{idx:04d}")
    _umount(mounts["mdt"])
    _umount(mounts["mgs"])

    mark_mounted(mgs=False, mdt=False, osts=[False] * len(osts), client=False)

    cfg.setdefault("deploy", {})["mounted"] = False
    save_config(cfg)
    log.info("Lustre components unmounted.")


def _umount(path: str) -> None:
    if Path(path).exists() and _is_mounted(path):
        run_cmd(["umount", path], check=False)

