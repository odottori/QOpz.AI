# Planner Model (PT1..PT4 + Milestone Enforcement)

## Objective
Create a single, enforceable planning model so every chat/agent works only on the assigned step and within declared scope.

## Source of truth
- Plan: `planner/master_plan.json`
- Active lock: `planner/active_step.json`
- Runtime state: `.qoaistate.json`

## Model levels
1. Primary targets: `PT1_MICRO`, `PT2_SMALL`, `PT3_MEDIUM`, `PT4_ADVANCED`
2. Secondary milestones: `R0..R5`
3. Executable steps: `F*`, `D2.*`

## Enforcement workflow
```powershell
py tools/planner_guard.py start --step-id F6-T2 --owner codex --note "work item"
py tools/planner_guard.py check --check-target index
py tools/run_gates.py --skip-manifest --skip-certify
```

## Scope policy
Each step maps to a `scope_profile` (`F1..F6`, `D2`, `PLAN`).
Only files matching that profile (plus always-allowed state files) are accepted.

## Status and monitoring
```powershell
py scripts/planner_status.py --format md
py scripts/project_status.py --format md
py tools/release_status.py --format md
```

## Operational notes
- If scope check fails: stop and fix scope or change active step.
- Use `planner_guard clear` to release the active lock.
- Keep state updates centralized when possible.


## Addendum demo-data (nuovo blocco)
Step pianificati:
- `F1-T5`: capture pagine demo (deferred) con dedup/freshness
- `F1-T6`: estrazione con Ollama qwen2.5 in JSON schema-fisso
- `F1-T7`: build dataset pulito (CSV/Parquet)
- `F1-T8`: retention+cap disco+audit report
- `F2-T5`: run backtest sul dataset costruito

Milestone collegata:
- `R1B_DEMO_DATA_PIPELINE` (soglia `dev`)
