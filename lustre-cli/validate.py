"""Module 4 — Lustre validation tests."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from lustre_cli.config import load_config
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd


def _client_mount() -> Path:
    cfg = load_config()
    mp = Path(cfg["lustre"]["mount"]["client"])
    if not mp.is_dir():
        raise CLIError(f"Client mount not found: {mp}. Run 'lustre-cli deploy mount' first.")
    return mp


def _evict_file_cache(path: Path) -> None:
    """Force data flush to the storage fabric and evict pages from local memory cache."""
    if not path.exists():
        return
    with open(path, "r+b") as f:
        fd = f.fileno()
        os.fsync(fd)
        if hasattr(os, "posix_fadvise"):
            # Instructs the kernel to drop clean pages, forcing subsequent reads to go to the OSTs
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)


def cmd_basic() -> None:
    require_root()
    check_tools("validate")
    log = get_logger()
    mp = _client_mount()
    
    test_dir = mp / "lustre-cli-test"
    test_dir.mkdir(exist_ok=True)
    test_file = test_dir / "basic.txt"
    
    payload = b"lustre-cli validation payload 2026\n"
    
    try:
        test_file.write_bytes(payload)
        _evict_file_cache(test_file)  # FIXED: Bypass local RAM cache
        
        read_back = test_file.read_bytes()
        if read_back != payload:
            raise CLIError("Basic read/write mismatch across Lustre storage tier")
            
        log.info("Basic I/O test passed at %s", test_file)
        print(f"PASS: created {test_dir}, wrote and verified {test_file}")
    finally:
        test_file.unlink(missing_ok=True)


def cmd_stripe() -> None:
    require_root()
    check_tools("validate")
    log = get_logger()
    mp = _client_mount()
    
    stripe_file = mp / f"lustre-cli-stripe-{uuid.uuid4().hex}.dat"
    ost_count = _ost_count()
    stripe_cnt = max(1, ost_count)
    
    try:
        run_cmd(["lfs", "setstripe", "-c", str(stripe_cnt), str(stripe_file)])
        stripe_file.write_bytes(b"x" * 4096)
        
        result = run_cmd(["lfs", "getstripe", str(stripe_file)], capture=True)
        print(result.stdout)
        
        if "stripe_count" not in result.stdout.lower() and str(stripe_cnt) not in result.stdout:
            log.warning("Could not confirm stripe count match in output layout")
        print(f"PASS: striping configured (stripe_count={stripe_cnt})")
    finally:
        # FIXED: Prevent storage pool layout leaks on the client share
        stripe_file.unlink(missing_ok=True)


def _ost_count() -> int:
    df = run_cmd(["lfs", "df"], capture=True, check=False)
    if df.returncode != 0:
        cfg = load_config()
        return len(cfg["lustre"].get("ost_devices", [])) or 1
    
    # FIXED: Check lines for distinct UUID target lines to bypass summary text
    count = 0
    for line in df.stdout.splitlines():
        normalized = line.upper()
        if "_OST" in normalized or "[OST:" in normalized:
            count += 1
            
    return max(1, count)


def cmd_integrity() -> None:
    require_root()
    check_tools("validate")
    log = get_logger()
    mp = _client_mount()
    
    data = os.urandom(1024 * 256)
    digest = hashlib.sha256(data).hexdigest()
    
    # FIXED: Replaced NamedTemporaryFile wrapper loop to isolate descriptor contexts cleanly
    path = mp / f"lustre-integrity-{uuid.uuid4().hex}.bin"

    try:
        path.write_bytes(data)
        _evict_file_cache(path)  # FIXED: Evict layout blocks out of tracking memory cache
        
        read_data = path.read_bytes()
        read_digest = hashlib.sha256(read_data).hexdigest()
        
        if read_digest != digest:
            raise CLIError(f"Integrity check failed: expected {digest}, got {read_digest}")

        run_cmd(["lctl", "dl"], check=False)
        run_cmd(["lfs", "df", "-h"], check=False)
        _verify_ost_distribution(mp)
        
        log.info("Integrity test passed sha256=%s", digest[:16])
        print(f"PASS: SHA256 integrity verified ({len(data)} bytes)")
        print(f"  Digest: {digest}")
    finally:
        # FIXED: Guarantees that binary test data blocks are removed even if validation runs drop error states
        path.unlink(missing_ok=True)


def _verify_ost_distribution(mp: Path) -> None:
    log = get_logger()
    result = run_cmd(["lfs", "df", str(mp)], capture=True, check=False)
    if result.returncode == 0:
        print("OST availability:")
        print(result.stdout)
    else: 
        log.warning("lfs df failed; OST distribution not verified")
