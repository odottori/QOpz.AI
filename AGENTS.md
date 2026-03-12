# AGENTS.md - Planner Enforcement (QuantOptionAI)

## Mandatory workflow
1. Read planner status:
   - `py scripts/planner_status.py --format md`
   - `py scripts/advancement_matrix.py --format md`
2. Work only on active step lock (`planner/active_step.json`).
3. Edit only files allowed by that step scope in `planner/master_plan.json`.
4. Before commit, stage files and run:
   - `py tools/planner_guard.py check --check-target index`
   - `py tools/run_gates.py --skip-manifest --skip-certify`
5. Mark completion only with evidence (tests/gates/report) and state tool updates.
6. Per step `F1-T5..F2-T5`, applicare dedup/freshness/retention e validazione JSON deterministica (no raw dump indiscriminato).

## Hard rules
- If scope check fails: STOP.
- If active lock missing: STOP.
- If active step is already completed: STOP.
- No manual edits to planner state files when a tool exists.
- No step completion without evidence.

## Lock commands
- Set active lock:
  - `py tools/planner_guard.py start --step-id <STEP_ID> --owner <owner>`
- Clear active lock:
  - `py tools/planner_guard.py clear`
- Planner status:
  - `py scripts/planner_status.py --format line`
