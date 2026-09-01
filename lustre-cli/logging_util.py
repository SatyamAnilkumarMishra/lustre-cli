"""Central logging setup supporting standard formats, file logs, and console levels."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from lustre_cli.config import load_config

_LOGGER: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    # Default fallback setup
    logger = logging.getLogger("lustre-cli")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    _LOGGER = logger
    return _LOGGER


def setup_logging(level_name: str | None = None) -> logging.Logger:
    global _LOGGER
    cfg = load_config()
    
    # 1. Resolve log level
    lvl = level_name or cfg.get("logging", {}).get("level", "INFO")
    level = getattr(logging, lvl.upper(), logging.INFO)

    # 2. Get/create logger
    logger = logging.getLogger("lustre-cli")
    logger.setLevel(level)
    logger.handlers.clear()

    # 3. Formatter
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 4. Console handler (always active)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # 5. File handler (optional)
    log_file_path = cfg.get("logging", {}).get("file")
    if log_file_path:
        log_file = Path(log_file_path)
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            logger.warning("Cannot write to log file %s; console only", log_file)

    _LOGGER = logger
    return logger
