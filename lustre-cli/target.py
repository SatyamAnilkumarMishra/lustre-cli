"""Module 1 — iSCSI target setup via targetcli with CHAP and state tracking."""

from __future__ import annotations

from pathlib import Path

from lustre_cli.config import load_config, save_config, load_secrets
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd
from lustre_cli.state import load_state, save_state

import unicodedata
from typing import Any

log = get_logger()


def validate_safe_param(val: Any, name: str) -> None:
    s = str(val)
    for c in s:
        if c in ("\n", "\r") or unicodedata.category(c).startswith("C"):
            raise CLIError(f"Security validation failed: Control characters detected in targetcli parameter '{name}'.")


def get_local_initiator_iqn() -> str:
    path = Path("/etc/iscsi/initiatorname.iscsi")
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("InitiatorName="):
                    return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return ""


def _iqn_for_lun(cfg: dict, lun: int) -> str:
    prefix = cfg["iscsi"]["target_iqn_prefix"].rstrip(".")
    return f"{prefix}:lun{lun}"


def _targetcli_batch(commands: list[str], sensitive: set[str] | None = None) -> None:
    script = "\n".join(commands)
    run_cmd(["targetcli"], input_text=script + "\n", sensitive=sensitive)


def cmd_create(
    device: str,
    lun: int,
    portal_ip: str | None = None,
    portal_port: int | None = None,
    backstore_type: str = "block",
) -> None:
    require_root()
    check_tools("target")
    cfg = load_config()
    state = load_state()

    device_path = Path(device)
    if not device_path.exists():
        raise CLIError(f"Block device not found: {device}")

    ip = portal_ip or cfg["iscsi"]["portal_ip"]
    port = portal_port or cfg["iscsi"]["portal_port"]
    iqn = _iqn_for_lun(cfg, lun)
    bs_name = f"bs_lun{lun}"
    tpg = f"/iscsi/{iqn}/tpg1"
    portal = f"{tpg}/portals/{ip}:{port}"

    validate_safe_param(device, "device")
    validate_safe_param(lun, "lun")
    validate_safe_param(ip, "portal_ip")
    validate_safe_param(port, "portal_port")
    validate_safe_param(backstore_type, "backstore_type")
    validate_safe_param(iqn, "iqn")
    validate_safe_param(bs_name, "backstore_name")

    if backstore_type not in ("block", "fileio"):
        raise CLIError("backstore_type must be 'block' or 'fileio'")

    # Check if target is already created (idempotency)
    targets_state = state.setdefault("targets", [])
    if any(t["iqn"] == iqn for t in targets_state):
        check_res = run_cmd(["targetcli", "ls", f"/iscsi/{iqn}"], check=False, capture=True)
        if check_res.returncode == 0:
            log.info("Target %s already exists and is active. Skipping create.", iqn)
            return

    cmds = [
        f"/backstores/{backstore_type} create name={bs_name} {device}",
        f"/iscsi create {iqn}",
        f"{tpg}/luns create /backstores/{backstore_type}/{bs_name}",
        f"{portal} create {ip} {port}" if ip != "0.0.0.0" else f"{portal} create",
    ]

    # Support iSCSI CHAP Authentication
    secrets = load_secrets()
    if secrets["username"] and secrets["password"]:
        init_iqn = cfg["iscsi"].get("initiator_iqn") or get_local_initiator_iqn()
        if not init_iqn:
            raise CLIError(
                "CHAP authentication is enabled but initiator IQN is not set and could not be auto-detected."
            )
        log.info("Configuring CHAP authentication for initiator IQN: %s", init_iqn)
        cmds.extend([
            f"{tpg}/set attribute authentication=1",
            f"{tpg}/set attribute generate_node_acls=0",
            f"{tpg}/acls create {init_iqn}",
            f"{tpg}/acls/{init_iqn} set auth userid={secrets['username']}",
            f"{tpg}/acls/{init_iqn} set auth password={secrets['password']}",
        ])
    else:
        cmds.extend([
            f"{tpg}/set attribute authentication=0",
            f"{tpg}/set attribute generate_node_acls=1",
        ])

    cmds.append("saveconfig")
    log.info("Creating iSCSI target %s on %s:%s for %s", iqn, ip, port, device)
    
    sens = {secrets["password"]} if secrets["password"] else None
    _targetcli_batch(cmds, sensitive=sens)

    entry = {
        "iqn": iqn,
        "lun": lun,
        "device": device,
        "portal_ip": ip,
        "portal_port": port,
        "backstore": bs_name,
    }
    targets_state = [t for t in targets_state if t.get("iqn") != iqn]
    targets_state.append(entry)
    state["targets"] = targets_state
    save_state(state)

    # Save to standard config file too
    cfg_targets = cfg.setdefault("targets", [])
    cfg_targets = [t for t in cfg_targets if t.get("iqn") != iqn]
    cfg_targets.append(entry)
    cfg["targets"] = cfg_targets
    save_config(cfg)

    log.info("Target created: %s (Device: %s Portal: %s:%s)", iqn, device, ip, port)


def cmd_list() -> None:
    check_tools("target")
    result = run_cmd(["targetcli", "ls", "/iscsi"], capture=True, check=False)
    print(result.stdout or "(no iSCSI targets)")
    state = load_state()
    saved = state.get("targets", [])
    if saved:
        print("\nConfigured in lustre-cli:")
        for t in saved:
            print(f"  {t['iqn']}  lun={t['lun']}  dev={t['device']}")


def cmd_delete(iqn: str | None = None, lun: int | None = None) -> None:
    require_root()
    check_tools("target")
    cfg = load_config()
    state = load_state()

    targets = state.get("targets", [])
    to_remove = []
    for t in targets:
        if iqn and t["iqn"] != iqn:
            continue
        if lun is not None and t["lun"] != lun:
            continue
        to_remove.append(t)

    if not to_remove:
        if iqn:
            # Try to force delete targetcli target directly
            iqn_path = f"/iscsi/{iqn}"
            _targetcli_batch([f"{iqn_path} delete", "saveconfig"])
            log.info("Deleted target %s (not in state)", iqn)
            return
        raise CLIError("No matching target found. Specify --iqn or --lun.")

    for t in to_remove:
        iqn_path = f"/iscsi/{t['iqn']}"
        bs = t.get("backstore", "")
        cmds = [f"{iqn_path} delete"]
        if bs:
            cmds.append(f"/backstores/block delete {bs}")
        cmds.append("saveconfig")
        _targetcli_batch(cmds)
        log.info("Deleted target %s", t["iqn"])

    # Update state and config
    state["targets"] = [t for t in targets if t not in to_remove]
    save_state(state)

    cfg["targets"] = [t for t in cfg.get("targets", []) if t["iqn"] not in [r["iqn"] for r in to_remove]]
    save_config(cfg)


def persist_config() -> None:
    """Persist targetcli config."""
    require_root()
    run_cmd(["targetcli", "saveconfig"])
    for path in ("/etc/target/saveconfig.json", "/etc/target/saveconfig.json.bak"):
        if Path(path).exists():
            log.info("Target config saved to %s", path)
            return
    log.info("targetcli saveconfig completed")
