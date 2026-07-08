"""Module 5 — Performance benchmarking with fio."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lustre_cli.config import load_config, save_config
from lustre_cli.deps import check_tools, check_tools_optional
from lustre_cli.logging_util import get_logger
from lustre_cli.utils import CLIError, require_root, run_cmd, tool_available

log = get_logger()


def _output_dir() -> Path:
    cfg = load_config()
    out = Path(cfg["benchmark"]["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    return out


def _client_mount() -> Path:
    cfg = load_config()
    return Path(cfg["lustre"]["mount"]["client"])


def cmd_run(
    runtime: int | None = None,
    stripe_counts: list[int] | None = None,
    use_dd_fallback: bool = False,
) -> None:
    require_root()
    cfg = load_config()
    mp = _client_mount()
    if not mp.is_dir():
        raise CLIError(f"Mount point missing: {mp}")

    runtime_sec = runtime or cfg["benchmark"].get("fio_runtime_sec", 30)
    ost_count = len(cfg["lustre"].get("ost_devices", [])) or 1
    stripes = stripe_counts or [1, ost_count]

    if use_dd_fallback or not tool_available("fio"):
        results = _run_dd_benchmark(mp, stripes)
    else:
        check_tools("benchmark")
        results = _run_fio_benchmark(mp, runtime_sec, stripes)

    out_dir = _output_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = out_dir / f"benchmark_{ts}.json"
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    cfg.setdefault("benchmark", {})["last_report"] = str(report_path)
    save_config(cfg)
    _print_table(results)
    print(f"\nReport saved: {report_path}")


def _run_fio_benchmark(mp: Path, runtime: int, stripes: list[int]) -> list[dict]:
    results = []
    for stripe in stripes:
        testfile = mp / f"fio-stripe{stripe}.dat"
        if stripe > 1:
            run_cmd(["lfs", "setstripe", "-c", str(stripe), str(testfile)], check=False)
        for rw in ("read", "write"):
            for pattern in ("read", "randread") if rw == "read" else ("write", "randwrite"):
                job = f"{pattern}_stripe{stripe}"
                fio_json = mp.parent / f".fio_{job}.json"
                run_cmd(
                    [
                        "fio",
                        "--name=lustre_cli",
                        f"--filename={testfile}",
                        f"--rw={pattern}",
                        "--bs=1M",
                        "--iodepth=32",
                        "--numjobs=1",
                        f"--runtime={runtime}",
                        "--time_based",
                        "--group_reporting",
                        "--output-format=json",
                        f"--output={fio_json}",
                    ],
                    check=False,
                )
                if fio_json.exists():
                    data = json.loads(fio_json.read_text(encoding="utf-8"))
                    metrics = _parse_fio_json(data, job, stripe)
                    results.append(metrics)
                    fio_json.unlink(missing_ok=True)
        
        # Clean up the large benchmark test file from the Lustre target array
        testfile.unlink(missing_ok=True)
    return results


def _parse_fio_json(data: dict, job: str, stripe: int) -> dict:
    jobs = data.get("jobs", [])
    j = jobs[0] if jobs else {}
    rw = "read" if "read" in job else "write"
    
    # Extract metrics out of nested read or write dictionary
    rw_stats = j.get(rw, {})
    
    # fio JSON reports 'bw' natively in KB/s
    bw_kbs = rw_stats.get("bw", 0)
    iops = rw_stats.get("iops", 0)
    lat_ns = rw_stats.get("clat_ns", {}).get("mean", 0)
    
    return {
        "job": job,
        "stripe_count": stripe,
        "throughput_mbps": round(bw_kbs / 1024, 2),  # Convert KB/s to MB/s
        "iops": round(iops, 2),
        "latency_ms": round(lat_ns / 1e6, 3) if lat_ns else 0,  # Convert ns to ms
        "tool": "fio",
    }


def _run_dd_benchmark(mp: Path, stripes: list[int]) -> list[dict]:
    import time

    results = []
    block_mb = 64
    for stripe in stripes:
        testfile = mp / f"dd-stripe{stripe}.dat"
        if stripe > 1:
            run_cmd(["lfs", "setstripe", "-c", str(stripe), str(testfile)], check=False)

        start = time.perf_counter()
        run_cmd(
            ["dd", "bs=1M", f"count={block_mb}", "if=/dev/zero", f"of={testfile}", "status=none"],
            check=False,
        )
        write_elapsed = max(time.perf_counter() - start, 0.001)
        results.append(
            {
                "job": f"seqwrite_stripe{stripe}",
                "stripe_count": stripe,
                "throughput_mbps": round(block_mb / write_elapsed, 2),
                "iops": 0,
                "latency_ms": 0,
                "tool": "dd",
            }
        )

        start = time.perf_counter()
        run_cmd(
            ["dd", "bs=1M", f"count={block_mb}", f"if={testfile}", "of=/dev/null", "status=none"],
            check=False,
        )
        read_elapsed = max(time.perf_counter() - start, 0.001)
        results.append(
            {
                "job": f"seqread_stripe{stripe}",
                "stripe_count": stripe,
                "throughput_mbps": round(block_mb / read_elapsed, 2),
                "iops": 0,
                "latency_ms": 0,
                "tool": "dd",
            }
        )
        
        # Clean up the dd storage footprint asset
        testfile.unlink(missing_ok=True)
    return results


def _print_table(results: list[dict]) -> None:
    headers = ("Job", "Stripes", "MB/s", "IOPS", "Latency(ms)", "Tool")
    rows = [
        (
            r["job"],
            str(r["stripe_count"]),
            str(r["throughput_mbps"]),
            str(r["iops"]),
            str(r["latency_ms"]),
            r["tool"],
        )
        for r in results
    ]
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 2 * (len(headers) - 1)))
    for row in rows:
        print(fmt.format(*row))


def cmd_report(path: str | None = None) -> None:
    cfg = load_config()
    report = path or cfg.get("benchmark", {}).get("last_report")
    if not report or not Path(report).exists():
        raise CLIError("No benchmark report found. Run 'lustre-cli benchmark run' first.")
    data = json.loads(Path(report).read_text(encoding="utf-8"))
    if isinstance(data, list):
        _print_table(data)
    else:
        print(json.dumps(data, indent=2))
    print(f"\nSource: {report}")
