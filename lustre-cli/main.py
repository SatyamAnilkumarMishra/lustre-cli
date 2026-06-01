"""lustre-cli entry point."""

from __future__ import annotations

import argparse
import sys

from lustre_cli import __version__
from lustre_cli import benchmark, deploy, fault, initiator, target, teardown, validate
from lustre_cli.deps import check_tools
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError

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

    # --- teardown ---
    sub.add_parser("teardown", help="Unmount Lustre and logout iSCSI")
    rh = sub.add_parser("reset", help="Full cleanup")
    rh.add_argument("--hard", action="store_true", help="Wipe devices and clear targets")

    sub.add_parser("check-deps", help="Verify required tools are installed")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.config:
        import os
        os.environ["LUSTRE_CLI_CONFIG"] = args.config

    try:
        return _dispatch(args)
    except CLIError as exc:
        log.error(str(exc))
        print(str(exc), file=sys.stderr)
        return exc.exit_code


def _dispatch(args: argparse.Namespace) -> int:
    cmd = args.command

    if cmd == "check-deps":
        check_tools()
        print("All required tools are available.")
        return 0

    if cmd == "target":
        if args.target_cmd == "create":
            target.cmd_create(
                args.device, args.lun, args.portal_ip, args.portal_port, args.backstore
            )
        elif args.target_cmd == "list":
            target.cmd_list()
        elif args.target_cmd == "delete":
            target.cmd_delete(args.iqn, args.lun)
        return 0

    if cmd == "initiator":
        if args.initiator_cmd == "discover":
            initiator.cmd_discover(args.host, args.port)
        elif args.initiator_cmd == "login":
            initiator.cmd_login(args.host, args.iqn, args.port)
        elif args.initiator_cmd == "logout":
            initiator.cmd_logout(args.host, args.iqn, args.port)
        elif args.initiator_cmd == "status":
            initiator.cmd_status()
        return 0

    if cmd == "deploy":
        if args.deploy_cmd == "format":
            deploy.cmd_format(
                args.mgs_device,
                args.mdt_device,
                args.ost_devices,
                args.mgsnode,
                args.fsname,
                args.force,
            )
        elif args.deploy_cmd == "mount":
            deploy.cmd_mount()
        elif args.deploy_cmd == "status":
            deploy.cmd_status()
        elif args.deploy_cmd == "unmount":
            deploy.cmd_unmount()
        return 0

    if cmd == "validate":
        if args.validate_cmd == "basic":
            validate.cmd_basic()
        elif args.validate_cmd == "stripe":
            validate.cmd_stripe()
        elif args.validate_cmd == "integrity":
            validate.cmd_integrity()
        return 0

    if cmd == "benchmark":
        if args.benchmark_cmd == "run":
            benchmark.cmd_run(args.runtime, args.stripes, args.dd)
        elif args.benchmark_cmd == "report":
            benchmark.cmd_report(args.file)
        return 0

    if cmd == "fault":
        if args.fault_cmd == "simulate-ost-failure":
            fault.cmd_simulate_ost_failure(args.index)
        elif args.fault_cmd == "simulate-bad-config":
            fault.cmd_simulate_bad_config()
        elif args.fault_cmd == "simulate-network-drop":
            fault.cmd_simulate_network_drop(args.host, args.iqn)
        return 0

    if cmd == "teardown":
        teardown.cmd_teardown()
        return 0

    if cmd == "reset":
        if args.hard:
            teardown.cmd_reset_hard()
        else:
            teardown.cmd_teardown(wipe=True)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
