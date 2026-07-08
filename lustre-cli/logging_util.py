"""Central logging to /var/log/lustre-cli.log."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOGGER: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    # FIXED: Insulate the logger from circular import paradoxes and config parsing crashes
    try:
        from lustre_cli.config import load_config
        cfg = load_config()
        log_file = Path(cfg.get("logging", {}).get("file", "/var/log/lustre-cli.log"))
        level_name = cfg.get("logging", {}).get("level", "INFO")
    except Exception:
        # Fall back cleanly to safe defaults if the config engine isn't bootstrapped yet
        log_file = Path("/var/log/lustre-cli.log")
        level_name = "INFO"

    logger = logging.getLogger("lustre-cli")
    logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    try:
        # Ensure parent directories exist before opening file streams
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        # FIXED: Changed to debug level to prevent annoying non-root users with 
        # permission warnings during harmless CLI commands.
        logger.debug("Cannot write log file %s; falling back to stderr only", log_file)

    _LOGGER = logger
    return logger
