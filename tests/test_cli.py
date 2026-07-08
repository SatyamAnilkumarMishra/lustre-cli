"""CLI parser tests (no root or Lustre required)."""

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lustre_cli.config import load_config, save_config
from lustre_cli.main import build_parser, main


class TestCLI(unittest.TestCase):
    
    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('sys.stderr', new_callable=io.StringIO)
    def test_help_parser(self, mock_stderr, mock_stdout):
        parser = build_parser()
        with self.assertRaises(SystemExit) as cm:
            parser.parse_args(["--help"])
        
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("usage:", mock_stdout.getvalue().lower())

    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('sys.stderr', new_callable=io.StringIO)
    def test_version(self, mock_stderr, mock_stdout):
        # FIXED: Defensively handles both integer returns and standard sys.exit() exceptions
        try:
            code = main(["--version"])
            if code is not None:
                self.assertEqual(code, 0)
        except SystemExit as cm:
            self.assertEqual(cm.code, 0)
            
        # Ensure that something was actually written to output streams
        output = mock_stdout.getvalue().strip() or mock_stderr.getvalue().strip()
        self.assertTrue(len(output) > 0, "Version flag produced no console output")

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            
            with patch.dict(os.environ, {"LUSTRE_CLI_CONFIG": str(cfg_path)}):
                # Seed the file path explicitly first
                initial_data = {"lustre": {"fsname": "default"}}
                save_config(initial_data, cfg_path)
                
                # FIXED: Call load_config() without arguments to force it to read 
                # from the mocked os.environ["LUSTRE_CLI_CONFIG"] just like production code does
                data = load_config() 
                data["lustre"]["fsname"] = "testfs"
                save_config(data, cfg_path)
                
                loaded = load_config()
                self.assertEqual(loaded["lustre"]["fsname"], "testfs")


if __name__ == "__main__":
    unittest.main()
