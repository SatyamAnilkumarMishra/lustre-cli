"""Dependency and privilege checks."""

from __future__ import annotations

from typing import Iterable

from lustre_cli.utils import CLIError, tool_available

# tool_name -> human description
TOOL_GROUPS: dict[str, list[tuple[str, str]]] = {
    "target": [
        ("targetcli", "targetcli (LIO iSCSI target)"),
    ],
    "initiator": [
        ("iscsiadm", "open-iscsi initiator"),
    ],
    "deploy": [
        ("mkfs.lustre", "Lustre mkfs"),
        ("mount.lustre", "Lustre mount helper"),
        ("lctl", "Lustre control"),
        ("lnetctl", "Lustre LNet control"),
        ("modprobe", "kernel module loader"),
    ],
    "validate": [
        ("lfs", "Lustre lfs utility"),
        ("lctl", "Lustre control"),
        ("md5sum", "checksum utility"),
    ],
    "benchmark": [
        ("fio", "Flexible I/O Tester"),
    ],
    "general": [
        ("lsblk", "block device listing"),
        ("wipefs", "filesystem signature wipe"),
    ],
}

ALL_TOOLS = {name for group in TOOL_GROUPS.values() for name, _ in group}


def check_tools(group: str | None = None) -> None:
    missing: list[str] = []
    if group and group in TOOL_GROUPS:
        tools = TOOL_GROUPS[group]
    else:
        tools = [(n, d) for g in TOOL_GROUPS.values() for n, d in g]

    seen: set[str] = set()
    for name, desc in tools:
        if name in seen:
            continue
        seen.add(name)
        if not tool_available(name):
            missing.append(f"{name} ({desc})")

    if missing:
        raise CLIError(
            "Missing required tools:\n  - " + "\n  - ".join(missing)
            + "\nInstall the corresponding packages and retry.",
            127,
        )


def check_tools_optional(names: Iterable[str]) -> list[str]:
    return [n for n in names if not tool_available(n)]
