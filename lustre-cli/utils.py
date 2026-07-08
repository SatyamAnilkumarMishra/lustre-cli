"""Shared subprocess helpers and exit handling."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Sequence

from lustre_cli.logging_util import get_logger


class CLIError(Exception):
    """User-facing CLI error with exit code."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def require_root() -> None:
    # FIXED: Clean, standard attribute tracking using top-level explicit imports
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise CLIError("This operation requires root privileges. Run with sudo.", 77)


def run_cmd(
    args: Sequence[str],
    *,
    check: bool = True,
    capture: bool = False,
    input_text: str | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    if not args:
        raise CLIError("Empty command sequence provided to runtime engine.")

    log = get_logger()
    log.debug("Running: %s", " ".join(args))
    
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
        raise CLIError(f"Command timed out: {' '.join(args)}") from exc

    if check and result.returncode != 0:
        # FIXED: Safeguard against uncaptured stream instances producing blank lines
        err = (result.stderr or result.stdout or "").strip()
        if not err and not capture:
            err = "[Console output streamed directly to terminal standard error]"
            
        raise CLIError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n{err}".strip(),
            result.returncode or 1,
        )
    return result


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def device_size_bytes(path: str) -> int:
    result = run_cmd(["blockdev", "--getsize64", path], capture=True)
    return int(result.stdout.strip())


def human_size(num_bytes: int | float) -> str:
    # FIXED: Strip float decoration from low-level absolute byte readouts
    if num_bytes < 1024:
        return f"{int(num_bytes)} B"
        
    for unit in ("KB", "MB", "GB", "TB"):
        num_bytes /= 1024
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
            
    return f"{num_bytes:.2f} PB"


def die(message: str, code: int = 1) -> None:
    log = get_logger()
    log.error(message)
    print(message, file=sys.stderr)
    sys.exit(code)
