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
7. Standard operativo: validare sempre in ambiente protetto isolato prima del rilascio:
   - `py tools/opz_protected_validate.py --setup`
8. Mantenere Git e VM allineati:
   - `py scripts/repo_sync_status.py --format json --no-fetch`
   - VM dry-run (se `OPZ_VM_API_BASE` + `OPZ_API_TOKEN` sono configurati):
     `py tools/opz_protected_validate.py --venv-name .venv_protected`

## Hard rules
- If scope check fails: STOP.
- If active lock missing: STOP.
- If active step is already completed: STOP.
- No manual edits to planner state files when a tool exists.
- No step completion without evidence.
- Nessun rilascio codice senza pass in ambiente protetto (`opz_protected_validate`).

## Lock commands
- Set active lock:
  - `py tools/planner_guard.py start --step-id <STEP_ID> --owner <owner>`
- Set active maintenance lock (quando `next_step=COMPLETE`):
  - `py tools/planner_guard.py start-maint --base-profile F6 --paths <path_glob...> --owner <owner> --note "<note>"`
- List maintenance locks:
  - `py tools/planner_guard.py list-maint --only-active`
- Close maintenance lock:
  - `py tools/planner_guard.py close-maint --step-id <MNT_STEP_ID>`
- Clear active lock:
  - `py tools/planner_guard.py clear`
- Planner status:
  - `py scripts/planner_status.py --format line`
