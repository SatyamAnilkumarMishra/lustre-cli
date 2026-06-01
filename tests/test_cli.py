"""CLI parser tests (no root or Lustre required)."""

import os
import tempfile
import unittest
from pathlib import Path

from lustre_cli.config import load_config, save_config
from lustre_cli.main import build_parser, main


class TestCLI(unittest.TestCase):
    def test_help_parser(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--help"])

    def test_version(self):
        code = main(["--version"])
        self.assertEqual(code, 0)

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            os.environ["LUSTRE_CLI_CONFIG"] = str(cfg_path)
            data = load_config(cfg_path)
            data["lustre"]["fsname"] = "testfs"
            save_config(data, cfg_path)
            loaded = load_config(cfg_path)
            self.assertEqual(loaded["lustre"]["fsname"], "testfs")


if __name__ == "__main__":
    unittest.main()
