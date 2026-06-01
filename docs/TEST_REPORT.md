# lustre-cli Test Report

**Date:** _______________  
**Tester:** _______________  
**Environment:** Ubuntu / RHEL _______ | Kernel _______  
**Nodes:** Target IP _______ | Client IP _______  

---

## 1. Dependency check

```bash
sudo lustre-cli check-deps
```

| Tool | Present |
|------|---------|
| targetcli | ☐ |
| iscsiadm | ☐ |
| mkfs.lustre | ☐ |
| lctl / lfs | ☐ |
| fio | ☐ |

**Result:** PASS / FAIL  
**Notes:**

---

## 2. Module 1 — iSCSI target

| Test | Command | Result | Notes |
|------|---------|--------|-------|
| Create LUN 0 | `target create -d /dev/sdb --lun 0` | | |
| Create LUN 1 | `target create -d /dev/sdc --lun 1` | | |
| List | `target list` | | |
| Persist reboot | Reboot server, `target list` | | |
| Delete | `target delete --lun 0` | | |

---

## 3. Module 2 — iSCSI initiator

| Test | Command | Result | Notes |
|------|---------|--------|-------|
| Discover | `initiator discover --host <IP>` | | |
| Login | `initiator login --host <IP> --iqn <IQN>` | | |
| Device size | `initiator status` / `blockdev --getsize64` | | |
| Logout | `initiator logout ...` | | |
| Bad IQN (fault) | See fault tests | | |

---

## 4. Module 3 — Lustre deploy

| Test | Command | Result | Notes |
|------|---------|--------|-------|
| Format | `deploy format ...` | | |
| Mount | `deploy mount` | | |
| Status | `deploy status` | | |
| `lctl dl` | All targets ONLINE | | |
| Unmount | `deploy unmount` | | |

---

## 5. Module 4 — Validation

| Test | Command | Result | Notes |
|------|---------|--------|-------|
| Basic I/O | `validate basic` | | |
| Striping | `validate stripe` | | |
| Integrity SHA256 | `validate integrity` | | |
| OST distribution | `lfs df` output | | |

---

## 6. Module 5 — Benchmark

```bash
sudo lustre-cli benchmark run
sudo lustre-cli benchmark report
```

| Job | Stripe count | MB/s | IOPS | Latency (ms) |
|-----|--------------|------|------|--------------|
| seqwrite_stripe1 | 1 | | | |
| seqread_stripe1 | 1 | | | |
| seqwrite_stripeN | N (all OSTs) | | | |
| seqread_stripeN | N | | | |

**Observation:** Parallelism gain from striping across OSTs: _______________

**Report file:** `/var/lib/lustre-cli/benchmarks/benchmark_*.json`

---

## 7. Module 6 — Fault simulation

| Scenario | Command | Expected | Actual | Remediation logged |
|----------|---------|----------|--------|-------------------|
| OST offline | `fault simulate-ost-failure` | Degraded FS / errors on write | | ☐ |
| Bad MGS IP | `fault simulate-bad-config` | Mount/mkfs failure | | ☐ |
| Re-format existing | (part of bad-config) | mkfs error | | ☐ |
| Wrong IQN | `fault simulate-network-drop` | Login failure | | ☐ |
| Unreachable portal | (part of network-drop) | Discovery failure | | ☐ |

---

## 8. Module 7 — Teardown

| Test | Command | Result |
|------|---------|--------|
| Teardown | `teardown` | |
| Hard reset | `reset --hard` | |
| Devices wiped | `wipefs` / clean `lsblk` | |

---

## Summary

| Area | Pass | Fail |
|------|------|------|
| iSCSI target | | |
| iSCSI initiator | | |
| Lustre deploy | | |
| Validation | | |
| Benchmark | | |
| Fault handling | | |
| Teardown | | |

**Overall:** PASS / FAIL  

**Issues / follow-ups:**
