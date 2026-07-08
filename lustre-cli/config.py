"""Configuration load/save for /etc/lustre-cli/config.yaml."""

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
}


def config_path() -> Path:
    return Path(os.environ.get("LUSTRE_CLI_CONFIG", str(DEFAULT_CONFIG_PATH)))


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or config_path()
    data = deepcopy(DEFAULTS)
    if cfg_path.is_file():
        with cfg_path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            
        # Defensive Type Guard: Only merge if the file parses into a structured dictionary
        if isinstance(loaded, dict):
            _deep_merge(data, loaded)
    return data


def save_config(data: dict[str, Any], path: Path | None = None) -> Path:
    cfg_path = path or config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
    return cfg_path


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


