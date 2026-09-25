"""Shared subprocess helpers and exit handling."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Sequence

from lustre_cli.logging_util import get_logger

log = get_logger()

_DRY_RUN = False


def set_dry_run(val: bool) -> None:
    global _DRY_RUN
    _DRY_RUN = val


def is_dry_run() -> bool:
    return _DRY_RUN


class CLIError(Exception):
    """User-facing CLI error with exit code."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def require_root() -> None:
    if is_dry_run():
        return
    if hasattr(os := __import__("os"), "geteuid") and os.geteuid() != 0:
        raise CLIError("This operation requires root privileges. Run with sudo.", 77)


def run_cmd(
    args: Sequence[str],
    *,
    check: bool = True,
    capture: bool = False,
    input_text: str | None = None,
    timeout: int | None = None,
    sensitive: set[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd_str = " ".join(args)
    cmd_str_logged = cmd_str
    if sensitive:
        for val in sensitive:
            if val:
                cmd_str_logged = cmd_str_logged.replace(val, "***REDACTED***")

    if is_dry_run():
        log.info("[DRY-RUN] Would run: %s", cmd_str_logged)
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=0,
            stdout="[DRY-RUN] stdout",
            stderr="[DRY-RUN] stderr",
        )

    log.debug("Running: %s", cmd_str_logged)
    try:
        result = subprocess.run(
            list(args),
            check=False,
            capture_output=capture,
            text=True,
            input=input_text,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CLIError(f"Command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CLIError(f"Command timed out: {cmd_str_logged}") from exc

    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        if sensitive:
            for val in sensitive:
                if val:
                    err = err.replace(val, "***REDACTED***")
        raise CLIError(
            f"Command failed ({result.returncode}): {cmd_str_logged}\n{err}",
            result.returncode or 1,
        )
    return result


def tool_available(name: str) -> bool:
    if is_dry_run():
        return True
    return shutil.which(name) is not None


def device_size_bytes(path: str) -> int:
    if is_dry_run():
        return 2147483648  # mock 2 GB
    result = run_cmd(["blockdev", "--getsize64", path], capture=True)
    return int(result.stdout.strip())


def human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def die(message: str, code: int = 1) -> None:
    log.error(message)
    sys.exit(code)
