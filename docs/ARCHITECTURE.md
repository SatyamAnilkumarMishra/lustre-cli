# Architecture: iSCSI + Lustre

## Overview

`lustre-cli` chains two layers:

1. **iSCSI** — presents remote block devices (LUNs) over TCP/IP.
2. **Lustre** — formats those block devices as MGS, MDT, and OST targets and exposes a single parallel filesystem namespace.

```
┌──────────────────── STORAGE SERVER ────────────────────┐
│  /dev/sdb, /dev/sdc, ...  (local disks or LVM)         │
│           │                                             │
│           ▼                                             │
│  targetcli: backstore → iSCSI target (IQN) → portal    │
│           │                              :3260/tcp    │
└───────────┼────────────────────────────────────────────┘
            │  iSCSI protocol
            ▼
┌──────────────────── LUSTRE CLIENT / OSS NODE ──────────┐
│  iscsiadm: discovery → login → /dev/sdX (SCSI disks)   │
│           │                                             │
│           ▼                                             │
│  mkfs.lustre:  MGS | MDT | OST0 | OST1 | ...           │
│           │                                             │
│           ▼                                             │
│  mount.lustre + LNet (tcp) → /mnt/lustre/client        │
└────────────────────────────────────────────────────────┘
```

## iSCSI layer

| Component | Role |
|-----------|------|
| **Target** (server) | Owns physical block devices; maps each to a LUN behind an IQN |
| **Initiator** (client) | Discovers targets, establishes session, kernel presents `/dev/sd*` |
| **Portal** | IP:port (default `3260`) where targets are advertised |

Block I/O from the client goes over the network as SCSI commands encapsulated in iSCSI PDUs. The client sees a **local block device** with no filesystem until Lustre formats it.

## Lustre layer

| Target | Device role | Purpose |
|--------|-------------|---------|
| **MGS** | Management | Stores filesystem configuration (which MDT/OST exist) |
| **MDT** | Metadata | Filenames, directories, permissions, striping policy |
| **OST** | Object storage | File data chunks (objects) |

All targets register with the **MGS** using `--mgsnode=<mgs-ip>@tcp`. Clients mount `mgsnode/fsname` to access the unified namespace.

**LNet** routes Lustre RPCs over configured networks (`lnetctl`). MGS, MDT, and OST must reach each other on the LNet NIDs.

## Data path

1. Application writes to `/mnt/lustre/client/foo`.
2. Lustre client splits metadata → MDT, data → OST(s) per striping.
3. OST issues block I/O to its backing device.
4. If that device is iSCSI-backed, I/O traverses the network to the storage server’s disk.

## Why combine iSCSI and Lustre?

- **iSCSI** centralizes disks on a SAN-like server without requiring Lustre on the storage box.
- **Lustre** adds parallel metadata + multiple OSTs for bandwidth and capacity scaling on compute nodes.
- This lab stack demonstrates: export disks → import on clients → build a parallel filesystem → validate, benchmark, and fault-test.

## lustre-cli responsibilities

| Phase | Tooling |
|-------|---------|
| Export | `targetcli` |
| Import | `iscsiadm` |
| Format/mount | `mkfs.lustre`, `mount.lustre`, `lnetctl` |
| Verify | `lfs`, `lctl` |
| Benchmark | `fio` / `dd` |
| State | `/etc/lustre-cli/config.yaml`, `/var/log/lustre-cli.log` |
