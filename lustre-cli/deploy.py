"""Module 3 — Lustre filesystem deployment."""

from __future__ import annotations

import os
from pathlib import Path

from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd, tool_available

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


def cmd_format(
    mgs_device: str | None = None,
    mdt_device: str | None = None,
    ost_devices: list[str] | None = None,
    mgsnode: str | None = None,
    fsname: str | None = None,
    force: bool = False,
) -> None:
    require_root()
    check_tools("deploy")
    cfg = load_config()
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

    _load_modules()
    _configure_lnet(cfg)

    force_flag = ["--force"] if force else []
    mgsnode_arg = f"--mgsnode={mgs_node}"

    log.info("Formatting MGS on %s", mgs_dev)
    run_cmd(
        ["mkfs.lustre", "--mgs", f"--fsname={name}", "--reformat", *force_flag, mgs_dev]
    )

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

    for idx, ost_dev in enumerate(osts):
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

    lustre["mgs_device"] = mgs_dev
    lustre["mdt_device"] = mdt_dev
    lustre["ost_devices"] = osts
    lustre["mgsnode"] = mgs_node
    lustre["fsname"] = name
    save_config(cfg)
    print(f"Lustre filesystem '{name}' formatted (MGS, MDT, {len(osts)} OST(s)).")


def _validate_devices(devices: list[str]) -> None:
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

    if lustre.get("mgs_device"):
        _mount(lustre["mgs_device"], mgs_mp, ["-t", "lustre"])
    if lustre.get("mdt_device"):
        _mount(lustre["mdt_device"], mdt_mp, ["-t", "lustre"])
    for idx, ost_dev in enumerate(osts):
        ost_mp = f"{ost_base}{idx:04d}"
        Path(ost_mp).mkdir(parents=True, exist_ok=True)
        _mount(ost_dev, ost_mp, ["-t", "lustre"])

    # Client mount aggregates namespace
    _mount(client_spec, client_mp, ["-t", "lustre", "-o", "user_xattr"])

    cfg.setdefault("deploy", {})["mounted"] = True
    save_config(cfg)
    print("Lustre components mounted.")
    print(f"  Client mount: {client_mp}")


def _mount(device_or_spec: str, mountpoint: str, extra_opts: list[str]) -> None:
    if _is_mounted(mountpoint):
        log.info("%s already mounted", mountpoint)
        return
    args = ["mount"] + extra_opts + [device_or_spec, mountpoint]
    run_cmd(args)


def _is_mounted(path: str) -> bool:
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

    cfg.setdefault("deploy", {})["mounted"] = False
    save_config(cfg)
    print("Lustre components unmounted.")


def _umount(path: str) -> None:
    if Path(path).exists() and _is_mounted(path):
        run_cmd(["umount", path], check=False)
