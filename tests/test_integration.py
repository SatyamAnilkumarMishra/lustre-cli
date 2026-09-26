"""Integration tests for lustre-cli single-machine lab loopback flow."""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

from lustre_cli.cli import main
from lustre_cli.config import load_config, save_config
from lustre_cli.utils import run_cmd

# Only run on Linux with root privileges AND the required system tools present.
# Checking is_linux_root alone is not enough: on a Linux root box without
# targetcli/iscsiadm/losetup/truncate installed, tests would hard-fail instead
# of skipping gracefully. Only run when everything needed is actually present.
_REQUIRED_TOOLS = ("targetcli", "iscsiadm", "losetup", "truncate")

is_linux_root = sys.platform.startswith("linux") and hasattr(os, "getuid") and os.getuid() == 0
_missing_tools = [t for t in _REQUIRED_TOOLS if shutil.which(t) is None] if is_linux_root else list(_REQUIRED_TOOLS)

if not is_linux_root:
    _skip_reason = "Requires Linux and root privileges"
elif _missing_tools:
    _skip_reason = f"Missing required system tools: {', '.join(_missing_tools)}"
else:
    _skip_reason = ""

_can_run = is_linux_root and not _missing_tools


@unittest.skipUnless(_can_run, _skip_reason)
class TestIntegration(unittest.TestCase):
    def setUp(self):
        # Create temp dir for images
        self.tmp_dir = Path("/tmp/lustre-cli-test-disks")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.disk_path = self.tmp_dir / "disk0.img"
        
        # 1. Truncate a dummy image file
        run_cmd(["truncate", "-s", "2G", str(self.disk_path)])
        
        # 2. Attach loop device
        res = run_cmd(["losetup", "-f", "--show", str(self.disk_path)], capture=True)
        self.loop_dev = res.stdout.strip()
        
    def tearDown(self):
        # Detach loop device
        run_cmd(["losetup", "-d", self.loop_dev], check=False)
        # Delete image
        if self.disk_path.exists():
            self.disk_path.unlink()
        if self.tmp_dir.exists():
            try:
                self.tmp_dir.rmdir()
            except Exception:
                pass

    def test_full_iscsi_flow(self):
        # We can test the target commands using our loopback device
        # 1. Create target
        code = main(["--local", "target", "create", "-d", self.loop_dev, "--lun", "9"])
        self.assertEqual(code, 0)
        
        # 2. List targets
        code = main(["--local", "target", "list"])
        self.assertEqual(code, 0)
        
        # 3. Clean up / Delete target
        code = main(["--local", "target", "delete", "--lun", "9"])
        self.assertEqual(code, 0)
        
    def test_teardown_and_reset(self):
        # Test teardown
        code = main(["--local", "teardown"])
        self.assertEqual(code, 0)

        # Test hard reset. --yes is required here: reset --hard now prompts
        # for interactive confirmation (by design, to prevent accidental data
        # loss), and this test verifies the reset logic itself, not the
        # prompt, so it opts in explicitly rather than blocking on stdin.
        code = main(["--local", "reset", "--hard", "--yes"])
        self.assertEqual(code, 0)
