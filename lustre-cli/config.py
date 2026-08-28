"""Configuration load/save and environment overrides."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("/etc/lustre-cli/config.yaml")
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml.example"

DEFAULTS: dict[str, Any] = {
    "iscsi": {
        "portal_ip": "0.0.0.0",
        "portal_port": 3260,
        "target_iqn_prefix": "iqn.2024-05.com.lustre-cli",
        "initiator_iqn": "",
    },
    "lustre": {
        "fsname": "lustrefs",
        "mgsnode": "",
        "mgs_device": "",
        "mdt_device": "",
        "ost_devices": [],
        "mount": {
            "mgs": "/mnt/lustre/mgs",
            "mdt": "/mnt/lustre/mdt",
            "ost_base": "/mnt/lustre/ost",
            "client": "/mnt/lustre/client",
        },
        "lnet": {
            "net": "tcp",
            "interfaces": [],
        },
    },
    "benchmark": {
        "output_dir": "/var/lib/lustre-cli/benchmarks",
        "fio_runtime_sec": 30,
    },
    "logging": {
        "file": "/var/log/lustre-cli.log",
        "level": "INFO",
    },
    "orchestration": {
        "hosts": [],
        "user": "root",
        "key_filename": None,
    },
    "targets": [],
    "initiator": {
        "sessions": [],
    },
}

_CONFIG_PATH_OVERRIDE: Path | None = None


def set_config_path(path: str) -> None:
    global _CONFIG_PATH_OVERRIDE
    _CONFIG_PATH_OVERRIDE = Path(path)


def config_path() -> Path:
    if _CONFIG_PATH_OVERRIDE is not None:
        return _CONFIG_PATH_OVERRIDE
    return Path(os.environ.get("LUSTRE_CLI_CONFIG", str(DEFAULT_CONFIG_PATH)))


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or config_path()
    data = deepcopy(DEFAULTS)
    if cfg_path.is_file():
        with cfg_path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        _deep_merge(data, loaded)

    # Apply environment variable overrides
    _apply_env_overrides(data)
    return data


def save_config(data: dict[str, Any], path: Path | None = None) -> Path:
    from lustre_cli.utils import is_dry_run
    if is_dry_run():
        return path or config_path()

    cfg_path = path or config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
    return cfg_path


def load_secrets() -> dict[str, str]:
    # 1. Environment variables
    user = os.environ.get("ISCSI_CHAP_USERNAME")
    password = os.environ.get("ISCSI_CHAP_PASSWORD")
    if user and password:
        return {"username": user, "password": password}

    # 2. File next to config file, or /etc/lustre-cli/secrets.yaml
    cfg_path = config_path()
    paths_to_check = [
        cfg_path.parent / "secrets.yaml",
        Path("/etc/lustre-cli/secrets.yaml"),
    ]
    for path in paths_to_check:
        if path.is_file():
            import sys
            import stat
            if not sys.platform.startswith("win32"):
                # Lazy import: logging_util imports config at module level, so a
                # top-level import here would create a circular import.
                from lustre_cli.logging_util import get_logger
                log = get_logger()
                try:
                    mode = path.stat().st_mode
                    if (mode & 0o077) != 0:
                        log.warning(
                            "WARNING: Secrets file %s has overly permissive permissions (%o). "
                            "It should be restricted to chmod 600.",
                            path, stat.S_IMODE(mode)
                        )
                except Exception as exc:
                    log.warning("Failed to check secrets file permissions: %s", exc)

            try:
                with path.open(encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                user = data.get("iscsi", {}).get("chap_username")
                password = data.get("iscsi", {}).get("chap_password")
                if user and password:
                    return {"username": user, "password": password}
            except Exception:
                pass

    return {"username": "", "password": ""}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
