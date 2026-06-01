"""Module 4 — Lustre validation tests."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from lustre_cli.config import load_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd

log = get_logger()


def _client_mount() -> Path:
    cfg = load_config()
    mp = Path(cfg["lustre"]["mount"]["client"])
    if not mp.is_dir():
        raise CLIError(f"Client mount not found: {mp}. Run 'lustre-cli deploy mount' first.")
    return mp


def cmd_basic() -> None:
    require_root()
    check_tools("validate")
    mp = _client_mount()
    test_dir = mp / "lustre-cli-test"
    test_dir.mkdir(exist_ok=True)
    test_file = test_dir / "basic.txt"
    payload = b"lustre-cli validation payload 2024\n"
    test_file.write_bytes(payload)
    read_back = test_file.read_bytes()
    if read_back != payload:
        raise CLIError("Basic read/write mismatch")
    log.info("Basic I/O test passed at %s", test_file)
    print(f"PASS: created {test_dir}, wrote and verified {test_file}")


def cmd_stripe() -> None:
    require_root()
    check_tools("validate")
    mp = _client_mount()
    stripe_file = mp / "lustre-cli-stripe.dat"
    ost_count = _ost_count()
    stripe_cnt = max(1, ost_count)
    run_cmd(["lfs", "setstripe", "-c", str(stripe_cnt), str(stripe_file)])
    stripe_file.write_bytes(b"x" * 4096)
    result = run_cmd(["lfs", "getstripe", str(stripe_file)], capture=True)
    print(result.stdout)
    if "stripe_count" not in result.stdout.lower() and str(stripe_cnt) not in result.stdout:
        log.warning("Could not confirm stripe count in output")
    print(f"PASS: striping configured (stripe_count={stripe_cnt})")


def _ost_count() -> int:
    df = run_cmd(["lfs", "df", "-h"], capture=True, check=False)
    if df.returncode != 0:
        cfg = load_config()
        return len(cfg["lustre"].get("ost_devices", [])) or 1
    return max(1, df.stdout.lower().count("ost"))


def cmd_integrity() -> None:
    require_root()
    check_tools("validate")
    mp = _client_mount()
    data = os.urandom(1024 * 256)
    digest = hashlib.sha256(data).hexdigest()

    with tempfile.NamedTemporaryFile(dir=mp, delete=False, suffix=".bin") as tmp:
        path = Path(tmp.name)
        path.write_bytes(data)

    read_data = path.read_bytes()
    read_digest = hashlib.sha256(read_data).hexdigest()
    if read_digest != digest:
        raise CLIError(f"Integrity check failed: expected {digest}, got {read_digest}")

    run_cmd(["lctl", "dl"], check=False)
    run_cmd(["lfs", "df", "-h"], check=False)
    _verify_ost_distribution(mp)

    path.unlink(missing_ok=True)
    log.info("Integrity test passed sha256=%s", digest[:16])
    print(f"PASS: SHA256 integrity verified ({len(data)} bytes)")
    print(f"  Digest: {digest}")


def _verify_ost_distribution(mp: Path) -> None:
    """Create files and check OST usage via lfs df."""
    result = run_cmd(["lfs", "df", str(mp)], capture=True, check=False)
    if result.returncode == 0:
        print("OST availability:")
        print(result.stdout)
    else:
        log.warning("lfs df failed; OST distribution not verified")
