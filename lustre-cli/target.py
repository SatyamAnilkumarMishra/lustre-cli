"""Module 1 — iSCSI target setup via targetcli."""

from __future__ import annotations

from pathlib import Path

from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd


def _iqn_for_lun(cfg: dict, lun: int) -> str:
    prefix = cfg["iscsi"]["target_iqn_prefix"].rstrip(".")
    return f"{prefix}:lun{lun}"


def _targetcli_batch(commands: list[str]) -> None:
    script = "\n".join(commands)
    run_cmd(["targetcli"], input_text=script + "\n")


def cmd_create(
    device: str,
    lun: int,
    portal_ip: str | None = None,
    portal_port: int | None = None,
    backstore_type: str = "block",
) -> None:
    require_root()
    check_tools("target")
    log = get_logger()
    cfg = load_config()
    
    device_path = Path(device)
    if not device_path.exists():
        raise CLIError(f"Block device not found: {device}")

    ip = portal_ip or cfg["iscsi"]["portal_ip"]
    port = portal_port or cfg["iscsi"]["portal_port"]
    iqn = _iqn_for_lun(cfg, lun)
    bs_name = f"bs_lun{lun}"
    tpg = f"/iscsi/{iqn}/tpg1"
    
    # FIXED: point to the parent collection node for portal creation context
    portals_dir = f"{tpg}/portals"

    if backstore_type not in ("block", "fileio"):
        raise CLIError("backstore_type must be 'block' or 'fileio'")

    cmds = [
        f"/backstores/{backstore_type} create name={bs_name} {device}",
        f"/iscsi create {iqn}",
        f"{tpg}/luns create /backstores/{backstore_type}/{bs_name}",
        # FIXED: run the create verb from the target-agnostic collection directory
        f"{portals_dir} create {ip} {port}" if ip != "0.0.0.0" else f"{portals_dir} create",
        f"{tpg}/set attribute authentication=0",
        f"{tpg}/set attribute generate_node_acls=1",
        "saveconfig",
    ]
    log.info("Creating iSCSI target %s on %s:%s for %s", iqn, ip, port, device)
    _targetcli_batch(cmds)

    # Clean up preexisting array indexes matching this LUN to preserve unique state mapping
    targets = cfg.setdefault("targets", [])
    cfg["targets"] = [t for t in targets if t.get("lun") != lun and t.get("iqn") != iqn]
    
    cfg["targets"].append(
        {
            "iqn": iqn,
            "lun": lun,
            "device": device,
            "portal_ip": ip,
            "portal_port": port,
            "backstore": bs_name,
            "backstore_type": backstore_type,  # FIXED: track type explicitly to handle safe teardown later
        }
    )
    save_config(cfg)
    print(f"Target created: {iqn}")
    print(f"  Device: {device}  Portal: {ip}:{port}")


def cmd_list() -> None:
    check_tools("target")
    result = run_cmd(["targetcli", "ls", "/iscsi"], capture=True, check=False)
    print(result.stdout or "(no iSCSI targets)")
    cfg = load_config()
    saved = cfg.get("targets", [])
    if saved:
        print("\nConfigured in lustre-cli:")
        for t in saved:
            print(f"  {t['iqn']}  lun={t['lun']}  dev={t['device']}")


def cmd_delete(iqn: str | None = None, lun: int | None = None) -> None:
    require_root()
    check_tools("target")
    log = get_logger()
    cfg = load_config()
    targets = cfg.get("targets", [])
    to_remove = []
    
    for t in targets:
        if iqn and t["iqn"] != iqn:
            continue
        if lun is not None and t["lun"] != lun:
            continue
        to_remove.append(t)

    if not to_remove:
        if iqn:
            iqn_path = f"/iscsi/{iqn}"
            _targetcli_batch([f"{iqn_path} delete", "saveconfig"])
            print(f"Deleted target {iqn} (not in config)")
            return
        raise CLIError("No matching target in config. Specify --iqn or --lun.")

    for t in to_remove:
        iqn_path = f"/iscsi/{t['iqn']}"
        bs = t.get("backstore", "")
        bs_type = t.get("backstore_type", "block")  # FIXED: Fallback safely but respect configuration type
        
        cmds = [f"{iqn_path} delete"]
        if bs:
            # FIXED: Target the explicit functional path node type
            cmds.append(f"/backstores/{bs_type} delete {bs}")
        cmds.append("saveconfig")
        _targetcli_batch(cmds)
        log.info("Deleted target %s", t["iqn"])
        print(f"Deleted: {t['iqn']}")

    cfg["targets"] = [t for t in targets if t not in to_remove]
    save_config(cfg)


def persist_config() -> None:
    """Persist targetcli config (also called on create/delete)."""
    require_root()
    log = get_logger()
    run_cmd(["targetcli", "saveconfig"])
    # RHEL/CentOS path hooks
    for path in ("/etc/target/saveconfig.json", "/etc/target/saveconfig.json.bak"):
        if Path(path).exists():
            log.info("Target config saved to %s", path)
            return
    log.info("targetcli saveconfig completed")
