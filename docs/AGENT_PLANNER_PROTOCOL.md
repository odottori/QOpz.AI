# Agent Planner Protocol

Use this protocol as hard rule for every coding action.

## 1) Read status first
```powershell
py scripts/planner_status.py --format line
```

## 2) Work only on active step
- Use only `planner/active_step.json`.
- No edits outside that step scope.

## 3) Mandatory pre-commit checks
```powershell
py tools/planner_guard.py check --check-target index
py tools/run_gates.py --skip-manifest --skip-certify
```

## 4) Hard stop conditions
- Scope violation => STOP
- Missing active lock => STOP
- Step already completed => STOP

## 5) Lock management
```powershell
py tools/planner_guard.py start --step-id F6-T2 --owner codex
py tools/planner_guard.py clear
```

Do not mark steps complete without evidence (tests/gates/report).

## 6) Demo data rule (F1-T5..F2-T5)
- No dump massivo di pagine: usare dedup, freshness skip e retention cap.
- Estrazione LLM ammessa solo con validatore JSON deterministico prima dell'uso nel motore test.
