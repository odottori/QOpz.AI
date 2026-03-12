
# QuantOptionAI
# MASTER CONTROL FRAMEWORK
## Version 1.2
## Generated: 2026-02-26T09:45:00Z
## Classification: Controlled Architecture Document

---

# CONTROL DOMAIN 0 — Governance & Framework Integrity

## Objective
Ensure structural coherence, versioning discipline, and control traceability across all domains.

## Controls
QOAI-GOV-000: All Control Domains SHALL be uniquely identified.
QOAI-GOV-001: Control IDs MUST NOT be duplicated.
QOAI-GOV-002: Domain dependencies SHALL be documented.
QOAI-GOV-003: Version increment SHALL occur upon control modification.
QOAI-GOV-004: Destructive structural changes REQUIRE documented approval.
QOAI-GOV-005: This framework SHALL be included in every FULL release.

---

# CONTROL DOMAIN 1 — Pre-Operational Controls (Gate 0)

## Objective
Validate readiness before trading.

QOAI-G0-001: Profiles SHALL exist (dev/paper/live).
QOAI-G0-002: Storage SHALL be writable and schema marker present.
QOAI-G0-003: Dataset SHALL be deterministic.
QOAI-G0-004: Broker connectivity SHALL be validated.
QOAI-G0-005: Severity mapping MUST follow profile policy.
QOAI-G0-006: Reports (JSON, MD, SHA256) SHALL be generated.
QOAI-G0-007: Exit codes SHALL follow 0/2/10 policy.

---

# CONTROL DOMAIN 2 — Execution Controls

## Objective
Ensure deterministic and safe order execution.

### Controls
QOAI-EXE-001: Order payload SHALL be schema validated.  
QOAI-EXE-002: Order size MUST align with risk allocation.  
QOAI-EXE-003: Duplicate submission MUST NOT occur.  
QOAI-EXE-004: Broker ACK timeout SHALL be classified.  
QOAI-EXE-005: Order state reconciliation SHALL occur.  
QOAI-EXE-006: Client order IDs SHALL be unique per session.

### ### ID & Trace Conventions
- `PATCH_NOTES_D2_*` = patchpack lineage / release notes.
- `tests/test_d2_XX_*` = milestone test IDs (suite coverage), NOT chronological order.
- `.qoaistate.json` `progress.steps_completed` = operational timeline (source of truth).

Implementation Trace (as of 2026-02-26T19:00:10Z)
| Control | Canonical reference | Implementation anchors | Tests / evidence | Status |
|---|---|---|---|:---:|
| QOAI-EXE-001 | `.canonici/01_TECNICO.md` (execution protocol context) | `execution/order_schema.py` (`Order.validate`) | `py -m unittest -v` (Domain2 suite) | OK |
| QOAI-EXE-002 | `.canonici/00_MASTER.md` (risk allocation policy), `.canonici/01_TECNICO.md` | Boundary: sizing handled upstream; Domain2 validates quantity > 0 (`execution/order_schema.py`) | n/a (Domain2 only) | PARTIAL |
| QOAI-EXE-003 | `.canonici/01_TECNICO.md` §T6.2 (deterministic execution) | `execution/idempotency.py`, `execution/storage.py` (dedupe primitives), `execution/state_machine.py` | `tests/test_d2_5_orders_journal.py` (journal invariants) | OK |
| QOAI-EXE-004 | `.canonici/01_TECNICO.md` §T6.2 (2 min steps) | `execution/ack.py` (ACK/timeout), `execution/boundary_adapter.py` (paper/live Gate0 + journal trail), `scripts/submit_order.py` (paper/live controlled reject) | `tests/test_d2_9_ack_classification.py`, `tests/test_d2_11_adapter_boundary.py`, `tests/test_d2_12_paperlive_event_trail.py` | OK |
| QOAI-EXE-005 | `.canonici/02_TEST.md` (gate F3), `.canonici/01_TECNICO.md` | `execution/reconcile.py`, `scripts/reconcile_execution.py` | `tests/test_d2_5_orders_journal.py` (F3-T4 logging + queries) | OK |
| QOAI-EXE-006 | `.canonici/01_TECNICO.md` (run discipline) | `execution/client_id.py` (run_id-scoped client_order_id), `execution/storage.py` (journal) | Covered by Domain2 tests indirectly | OK |

---

# CONTROL DOMAIN 3 — Risk Controls

## Objective
Enforce exposure and capital limits.

QOAI-RSK-001: Position exposure SHALL not exceed threshold.
QOAI-RSK-002: Portfolio heat MUST remain under configured limit.
QOAI-RSK-003: Stop-loss SHALL be enforced automatically.
QOAI-RSK-004: Drawdown breach SHALL trigger kill-switch.
QOAI-RSK-005: Trade frequency caps SHALL be enforced.
QOAI-RSK-006: Capital allocation SHALL be bounded per strategy.

---

# CONTROL DOMAIN 4 — Data Integrity Controls

## Objective
Ensure correctness and prevent bias.

QOAI-DAT-001: No forward-looking leakage SHALL occur.
QOAI-DAT-002: Timestamp monotonicity SHALL be verified.
QOAI-DAT-003: Trading calendar gaps SHALL be classified.
QOAI-DAT-004: Schema markers SHALL match expected version.
QOAI-DAT-005: Backtest results SHALL be reproducible.
QOAI-DAT-006: Dataset integrity SHALL be checksum-validated.

---

# CONTROL DOMAIN 5 — Monitoring & Logging Controls

## Objective
Ensure runtime auditability.

QOAI-MON-001: All order events SHALL be logged.
QOAI-MON-002: Logs SHALL include timestamp and severity.
QOAI-MON-003: Rotation policy SHALL be enforced.
QOAI-MON-004: Critical errors SHALL trigger escalation.
QOAI-MON-005: Log retention SHALL follow defined policy.
QOAI-MON-006: Logs SHOULD be tamper-evident.

---

# CONTROL DOMAIN 6 — Release & Integrity Controls

## Objective
Guarantee release consistency and cryptographic integrity.

QOAI-REL-001: All files SHALL be included in MANIFEST.
QOAI-REL-002: REGISTRO_INTEGRITA SHALL match actual hashes.
QOAI-REL-003: Versioning SHALL be consistent across docs.
QOAI-REL-004: No orphan files SHALL exist.
QOAI-REL-005: FULL ZIP SHALL be reproducible.
QOAI-REL-006: Integrity verification SHALL pass before certification.

---

# INTER-DOMAIN DEPENDENCY MATRIX

## Dependency Classification
HARD  = Blocking dependency  
SOFT  = Advisory dependency  
CERT  = Required for release certification  
ESC   = Escalation chain  

| From \ To | D0 | D1 | D2 | D3 | D4 | D5 | D6 |
|------------|----|----|----|----|----|----|----|
| D0 Gov     | —  | HARD | HARD | HARD | HARD | HARD | HARD |
| D1 PreOp   | SOFT | —  | HARD | HARD | HARD | SOFT | CERT |
| D2 Exec    | SOFT | —  | —  | HARD | HARD | HARD | CERT |
| D3 Risk    | SOFT | —  | HARD | —  | HARD | HARD | CERT |
| D4 Data    | SOFT | HARD | HARD | HARD | —  | SOFT | CERT |
| D5 Mon     | SOFT | SOFT | HARD | HARD | SOFT | —  | CERT |
| D6 Release | HARD | HARD | HARD | HARD | HARD | HARD | —  |

---

# ESCALATION CHAINS

Broker Failure (Live):
D2 → D3 → D5 → D6

Data Integrity Breach:
D4 → D3 → D2 → D6

Manifest Mismatch:
D6 → D0

---

# CERTIFICATION CRITERIA

Release certification requires:
1. No HARD dependency violations.
2. All CERT dependencies satisfied.
3. All domain controls implemented.
4. Integrity registers consistent.
5. No governance breaches.

---

END OF DOCUMENT
