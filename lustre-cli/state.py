"""State tracking for lustre-cli."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_FILE_PATH = Path("/var/lib/lustre-cli/state.json")
FALLBACK_STATE_FILE_PATH = Path("~/.lustre-cli/state.json").expanduser()


def get_state_file() -> Path:
    try:
        STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        return STATE_FILE_PATH
    except OSError:
        # Fallback to home dir
        FALLBACK_STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        return FALLBACK_STATE_FILE_PATH


def load_state() -> dict[str, Any]:
    path = get_state_file()
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {
        "targets": [],       # list of target dicts: {"iqn": str, "lun": int, "device": str, "portal": str}
        "sessions": [],      # list of initiator session dicts: {"iqn": str, "portal": str, "device": str}
        "formatted": {},     # {"mgs": "/dev/sdb", "mdt": "/dev/sdc", "osts": ["/dev/sdd"]}
        "mounted": {},       # {"mgs": bool, "mdt": bool, "osts": [bool], "client": bool}
    }


def save_state(state: dict[str, Any]) -> None:
    from lustre_cli.utils import is_dry_run
    if is_dry_run():
        return

    path = get_state_file()
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except Exception:
        # If we cannot save, we at least don't crash
        pass


def update_state(key: str, val: Any) -> None:
    state = load_state()
    state[key] = val
    save_state(state)


def mark_formatted(mgs: str | None = None, mdt: str | None = None, osts: list[str] | None = None) -> None:
    state = load_state()
    formatted = state.setdefault("formatted", {})
    if mgs:
        formatted["mgs"] = mgs
    if mdt:
        formatted["mdt"] = mdt
    if osts:
        formatted["osts"] = osts
    save_state(state)


def mark_mounted(mgs: bool | None = None, mdt: bool | None = None, osts: list[bool] | None = None, client: bool | None = None) -> None:
    state = load_state()
    mounted = state.setdefault("mounted", {})
    if mgs is not None:
        mounted["mgs"] = mgs
    if mdt is not None:
        mounted["mdt"] = mdt
    if osts is not None:
        mounted["osts"] = osts
    if client is not None:
        mounted["client"] = client
    save_state(state)
