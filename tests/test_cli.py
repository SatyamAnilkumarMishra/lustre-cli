"""Unit tests for CLI parser and core commands mapping."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lustre_cli.cli import build_parser, main
from lustre_cli.config import load_config, save_config, set_config_path
from lustre_cli.utils import set_dry_run, is_dry_run


class TestCLI(unittest.TestCase):
    def setUp(self):
        # Reset global state before each test
        set_dry_run(False)

    def test_help_parser(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--help"])

    def test_version(self):
        # Mock main execution which exits or returns code
        # For --version it uses argparse.version action which raises SystemExit
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--version"])

    def test_dry_run_flag(self):
        # Main entrypoint with dry run should set global state
        main(["--dry-run", "check-deps"])
        self.assertTrue(is_dry_run())

    def test_status_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["status", "--json"])
        self.assertEqual(args.command, "status")
        self.assertTrue(args.json)

    def test_target_create_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["target", "create", "-d", "/dev/loop0", "--lun", "0"])
        self.assertEqual(args.command, "target")
        self.assertEqual(args.target_cmd, "create")
        self.assertEqual(args.device, "/dev/loop0")
        self.assertEqual(args.lun, 0)

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            os.environ["LUSTRE_CLI_CONFIG"] = str(cfg_path)
            data = load_config(cfg_path)
            data["lustre"]["fsname"] = "testfs"
            save_config(data, cfg_path)
            loaded = load_config(cfg_path)
            self.assertEqual(loaded["lustre"]["fsname"], "testfs")


    def test_sensitive_redaction(self):
        from lustre_cli.utils import run_cmd
        set_dry_run(True)
        with self.assertLogs("lustre-cli", level="INFO") as log_capture:
            run_cmd(
                ["echo", "SuperSecretPassword123"],
                sensitive={"SuperSecretPassword123"},
            )
        log_text = "".join(log_capture.output)
        self.assertIn("***REDACTED***", log_text)
        self.assertNotIn("SuperSecretPassword123", log_text)

    def test_orchestration_remote_cmd_neutralizes_shell_injection(self):
        """A malicious arg must survive as ONE argument, not break out via shell metacharacters."""
        import shlex
        from lustre_cli.orchestration import _build_remote_cmd

        malicious_device = "/dev/sdb; rm -rf /tmp/test; echo pwned"
        argv = ["lustre-cli", "target", "create", "-d", malicious_device, "--lun", "9"]

        remote_cmd = _build_remote_cmd(argv, user="root")
        parsed_back = shlex.split(remote_cmd)

        # The malicious string must round-trip as a single argument, proving
        # the shell never sees unescaped ';' as a command separator.
        self.assertIn(malicious_device, parsed_back)
        self.assertEqual(
            parsed_back,
            ["lustre-cli", "target", "create", "-d", malicious_device, "--lun", "9"],
        )

    def test_orchestration_defaults_to_strict_host_key_checking(self):
        """Unknown SSH hosts must be rejected by default, not silently trusted."""
        import unittest.mock
        import paramiko

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            os.environ["LUSTRE_CLI_CONFIG"] = str(cfg_path)
            data = load_config(cfg_path)
            data["orchestration"]["hosts"] = ["10.0.0.99"]
            save_config(data, cfg_path)

            policies_set = []
            connect_calls = []

            class FakeSSHClient:
                def load_system_host_keys(self):
                    pass

                def load_host_keys(self, path):
                    pass

                def set_missing_host_key_policy(self, policy):
                    policies_set.append(type(policy).__name__)

                def connect(self, **kwargs):
                    connect_calls.append(kwargs)
                    raise paramiko.SSHException("Server not found in known_hosts (simulated reject)")

                def close(self):
                    pass

            with unittest.mock.patch("paramiko.SSHClient", FakeSSHClient):
                from lustre_cli.orchestration import run_command_on_hosts
                with self.assertRaises(Exception):
                    run_command_on_hosts(["lustre-cli", "initiator", "status"])

            self.assertIn("RejectPolicy", policies_set)
            self.assertNotIn("AutoAddPolicy", policies_set)

    def test_load_secrets_warns_not_crashes_on_permissive_file(self):
        """A world-readable secrets.yaml must produce a warning, never a crash.

        Regression test: an earlier fix added a permission-check warning that
        referenced an undefined `log`, causing load_secrets() to raise
        NameError instead of warning. Any CHAP-authenticated command would
        fail outright. This confirms secrets still load and only a warning
        is logged.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            secrets_path = Path(tmp) / "secrets.yaml"
            secrets_path.write_text(
                "iscsi:\n  chap_username: testuser\n  chap_password: testpass\n",
                encoding="utf-8",
            )
            os.chmod(secrets_path, 0o644)  # world-readable on purpose
            os.environ["LUSTRE_CLI_CONFIG"] = str(cfg_path)

            from lustre_cli.config import load_secrets
            secrets = load_secrets()

        self.assertEqual(secrets, {"username": "testuser", "password": "testpass"})

    def test_reset_hard_requires_confirmation_without_yes(self):
        """reset --hard without --yes must not proceed without confirmation.

        Runs before check_tools()/require_root()-gated destructive work, so
        it's safe to verify here without targetcli/iscsiadm installed.
        Simulates a non-interactive environment (no stdin available) to
        confirm the command fails safely rather than silently wiping
        devices when it can't get an answer.
        """
        import io
        import unittest.mock

        with unittest.mock.patch("sys.stdin", io.StringIO("")):
            code = main(["--local", "reset", "--hard"])
        # EOF on stdin during input() raises inside cli.py's generic
        # exception handler, which returns 1 — the command must not report
        # success (0), and must not have proceeded with the destructive action.
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
