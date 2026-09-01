"""Module for multi-node SSH orchestration using paramiko with safety validation and strict key checking."""

from __future__ import annotations

import os
import sys
import shlex
from pathlib import Path
from lustre_cli.config import load_config
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError

log = get_logger()


def _build_remote_cmd(argv: list[str], user: str) -> str:
    """Builds a shlex-quoted command string from argv."""
    cmd_parts = []
    executable = argv[0]
    if executable.endswith(".py"):
        cmd_parts.append(shlex.quote(sys.executable))
        cmd_parts.append(shlex.quote(executable))
    else:
        cmd_parts.append("lustre-cli")

    # Filter out --local and --continue-on-error (if present)
    skip_next = False
    for arg in argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg == "--local" or arg == "--continue-on-error":
            continue
        cmd_parts.append(shlex.quote(arg))

    remote_cmd = " ".join(cmd_parts)
    if user != "root":
        remote_cmd = f"sudo {remote_cmd}"
    return remote_cmd


def run_command_on_hosts(argv: list[str]) -> bool:
    """Orchestrates the current command to remote hosts if configured.

    Returns:
        True if the command was orchestrated to remote hosts, False otherwise.
    """
    # Prevent infinite loop on remote host
    if os.environ.get("LUSTRE_CLI_ORCHESTRATED") == "1":
        return False

    cfg = load_config()
    hosts = cfg.get("orchestration", {}).get("hosts") or []
    if not hosts:
        return False

    import paramiko

    user = cfg.get("orchestration", {}).get("user", "root")
    key_filename = cfg.get("orchestration", {}).get("key_filename")
    strict = cfg.get("orchestration", {}).get("strict_host_key_checking", True)
    continue_on_error = "--continue-on-error" in argv or cfg.get("orchestration", {}).get("continue_on_error", False)

    log.info("Multi-node orchestration active. Target hosts: %s", ", ".join(hosts))

    remote_cmd = _build_remote_cmd(argv, user)

    succeeded = []
    failed = []
    not_attempted = list(hosts)

    for host in hosts:
        not_attempted.remove(host)
        log.info("Connecting to %s@%s...", user, host)
        
        ssh = paramiko.SSHClient()
        
        # Load system and user known_hosts
        ssh.load_system_host_keys()
        user_hosts = Path("~/.ssh/known_hosts").expanduser()
        if user_hosts.is_file():
            try:
                ssh.load_host_keys(str(user_hosts))
            except Exception as exc:
                log.warning("Failed to load user known_hosts from %s: %s", user_hosts, exc)

        # Set strict key checking policy
        if strict:
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            log.warning("WARNING: strict_host_key_checking is disabled! Insecure AutoAddPolicy in use.")
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(
                hostname=host,
                username=user,
                key_filename=key_filename,
                timeout=10,
            )
            log.info("[%s] Executing: %s", host, remote_cmd)
            
            # Pass LUSTRE_CLI_ORCHESTRATED=1 to avoid loops
            stdin, stdout, stderr = ssh.exec_command(
                f"export LUSTRE_CLI_ORCHESTRATED=1; {remote_cmd}"
            )
            
            exit_code = stdout.channel.recv_exit_status()
            out_str = stdout.read().decode("utf-8").strip()
            err_str = stderr.read().decode("utf-8").strip()

            if exit_code != 0:
                log.error("[%s] Failed with exit code %d", host, exit_code)
                if out_str:
                    log.error("[%s] Stdout:\n%s", host, out_str)
                if err_str:
                    log.error("[%s] Stderr:\n%s", host, err_str)
                raise CLIError(f"Remote command failed on {host} (code {exit_code})")
            
            log.info("[%s] Command succeeded.", host)
            if out_str:
                log.info("[%s] Output:\n%s", host, out_str)
            succeeded.append(host)
        except Exception as exc:
            failed.append(host)
            log.error("[%s] Connection or execution error: %s", host, exc)
            if not continue_on_error:
                summary_msg = (
                    f"Orchestration failed partway. "
                    f"Succeeded: {', '.join(succeeded) or 'none'} | "
                    f"Failed: {', '.join(failed)} | "
                    f"Not attempted: {', '.join(not_attempted) or 'none'}"
                )
                log.error(summary_msg)
                raise CLIError(summary_msg)
        finally:
            ssh.close()

    if failed:
        summary_msg = (
            f"Orchestration completed with errors. "
            f"Succeeded: {', '.join(succeeded) or 'none'} | "
            f"Failed: {', '.join(failed)}"
        )
        log.error(summary_msg)
        raise CLIError(summary_msg)

    log.info("Multi-node orchestration completed successfully on all hosts.")
    return True
