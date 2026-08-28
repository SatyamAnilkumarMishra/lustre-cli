"""lustre-cli entry point."""

from __future__ import annotations

import argparse
import sys
import os

from lustre_cli import __version__
from lustre_cli import benchmark, deploy, fault, initiator, target, teardown, validate, status
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger, setup_logging
from lustre_cli.utils import CLIError, set_dry_run
from lustre_cli.config import set_config_path

log = get_logger()


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--config",
        help="Path to config YAML (default: /etc/lustre-cli/config.yaml or LUSTRE_CLI_CONFIG)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lustre-cli",
        description="iSCSI-backed Lustre storage management CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        help="Path to config YAML (default: /etc/lustre-cli/config.yaml or LUSTRE_CLI_CONFIG)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Print intended actions without executing them",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Shortcut for --log-level DEBUG",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run command locally, bypassing multi-node orchestration",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Automatic yes to prompts; assume yes to confirmation questions",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- target ---
    t = sub.add_parser("target", help="iSCSI target (storage server) management")
    ts = t.add_subparsers(dest="target_cmd", required=True)

    tc = ts.add_parser("create", help="Create iSCSI target for a block device")
    tc.add_argument("--device", "-d", required=True, help="Block device path e.g. /dev/sdb")
    tc.add_argument("--lun", type=int, required=True, help="LUN number")
    tc.add_argument("--portal-ip", help="Portal IP (default from config)")
    tc.add_argument("--portal-port", type=int, help="Portal port (default 3260)")
    tc.add_argument("--backstore", choices=["block", "fileio"], default="block")

    ts.add_parser("list", help="List iSCSI targets")

    td = ts.add_parser("delete", help="Delete iSCSI target")
    td.add_argument("--iqn", help="Target IQN")
    td.add_argument("--lun", type=int, help="LUN number")

    # --- initiator ---
    i = sub.add_parser("initiator", help="iSCSI initiator (client) management")
    isub = i.add_subparsers(dest="initiator_cmd", required=True)

    idisc = isub.add_parser("discover", help="Discover targets on portal")
    idisc.add_argument("--host", required=True, help="Target server IP")
    idisc.add_argument("--port", type=int, default=3260)

    ilogin = isub.add_parser("login", help="Login to target")
    ilogin.add_argument("--host", required=True)
    ilogin.add_argument("--iqn", required=True)
    ilogin.add_argument("--port", type=int, default=3260)

    ilogout = isub.add_parser("logout", help="Logout from target")
    ilogout.add_argument("--host", required=True)
    ilogout.add_argument("--iqn", required=True)
    ilogout.add_argument("--port", type=int, default=3260)

    isub.add_parser("status", help="Show initiator session status")

    # --- deploy ---
    d = sub.add_parser("deploy", help="Lustre filesystem deployment")
    ds = d.add_subparsers(dest="deploy_cmd", required=True)

    df = ds.add_parser("format", help="mkfs.lustre for MGS, MDT, OSTs")
    df.add_argument("--mgs-device")
    df.add_argument("--mdt-device")
    df.add_argument("--ost-device", action="append", dest="ost_devices")
    df.add_argument("--mgsnode", help="MGS node e.g. 10.0.0.1@tcp")
    df.add_argument("--fsname")
    df.add_argument("--force", action="store_true")

    ds.add_parser("mount", help="Mount Lustre components")
    ds.add_parser("status", help="Show Lustre deployment status")
    ds.add_parser("unmount", help="Unmount Lustre components")

    # --- validate ---
    v = sub.add_parser("validate", help="Filesystem validation tests")
    vs = v.add_subparsers(dest="validate_cmd", required=True)
    vs.add_parser("basic", help="Basic create/read/write test")
    vs.add_parser("stripe", help="Stripe configuration test")
    vs.add_parser("integrity", help="Checksum integrity and OST check")

    # --- benchmark ---
    b = sub.add_parser("benchmark", help="Performance benchmarks")
    bs = b.add_subparsers(dest="benchmark_cmd", required=True)
    br = bs.add_parser("run", help="Run fio/dd benchmarks")
    br.add_argument("--runtime", type=int, help="fio runtime seconds")
    br.add_argument("--stripe", type=int, action="append", dest="stripes")
    br.add_argument("--dd", action="store_true", help="Use dd instead of fio")
    brep = bs.add_parser("report", help="Display last benchmark report")
    brep.add_argument("--file", help="Report JSON path")

    # --- fault ---
    f = sub.add_parser("fault", help="Failure simulation")
    fs = f.add_subparsers(dest="fault_cmd", required=True)
    fost = fs.add_parser("simulate-ost-failure", help="Unmount an OST")
    fost.add_argument("--index", type=int, default=0)
    fs.add_parser("simulate-bad-config", help="Bad MGS and format-on-existing tests")
    fnet = fs.add_parser("simulate-network-drop", help="Failed login and discovery")
    fnet.add_argument("--host")
    fnet.add_argument("--iqn")

    # --- status (top level) ---
    st = sub.add_parser("status", help="Show overall deployment and system status")
    st.add_argument("--json", action="store_true", help="Output status in machine-readable JSON")

    # --- teardown ---
    sub.add_parser("teardown", help="Unmount Lustre and logout iSCSI")
    rh = sub.add_parser("reset", help="Full cleanup")
    rh.add_argument("--hard", action="store_true", help="Wipe devices and clear targets")

    sub.add_parser("check-deps", help="Verify required tools are installed")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Setup config file path if specified
    if args.config:
        set_config_path(args.config)

    # 2. Setup dry-run flag
    if args.dry_run:
        set_dry_run(True)

    # 3. Setup logging level
    log_level = "DEBUG" if args.verbose else args.log_level
    setup_logging(log_level)

    # 4. Remote orchestration
    if not args.local and args.command in (
        "deploy",
        "initiator",
        "teardown",
        "reset",
        "validate",
        "benchmark",
    ):
        from lustre_cli.orchestration import run_command_on_hosts
        try:
            # sys.argv is used if argv is None
            cmd_args = sys.argv if argv is None else argv
            if run_command_on_hosts(cmd_args):
                return 0
        except CLIError as exc:
            log.error(str(exc))
            return exc.exit_code

    try:
        return _dispatch(args)
    except CLIError as exc:
        log.error(str(exc))
        return exc.exit_code
    except Exception as exc:
        log.exception("Unexpected error occurred: %s", exc)
        return 1
