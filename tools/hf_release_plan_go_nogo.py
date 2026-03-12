from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
APPENDIX = ROOT / ".canonici" / "04_APPENDICI.md"
PLAN = ROOT / "config" / "release_plan_go_nogo.json"

BEGIN = "<!-- BEGIN GO_NOGO_RELEASE_PLAN -->"
END = "<!-- END GO_NOGO_RELEASE_PLAN -->"


def _load_plan() -> dict:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def _render_md(plan: dict) -> str:
    go = plan["principles"]["go_nogo"]
    tier = plan["principles"]["tier_upgrade"]

    lines: List[str] = []
    lines.append("## Appendice Z — Roadmap GO/NO-GO (Release per moduli)")
    lines.append("")
    lines.append("### Gate GO/NO-GO (paper → decisione live)")
    lines.append(f"- Sharpe paper ≥ **{go['paper_sharpe_min']}** (min **{go['paper_min_trades']}** trade)")
    lines.append(f"- Max DD paper < **{int(go['paper_maxdd_max']*100)}%** (in qualsiasi periodo)")
    lines.append("- Violazioni regole (sizing/stop/no-trade): **ZERO**")
    lines.append("")
    lines.append("### Gate upgrade Tier (OOS)")
    lines.append(f"- Sharpe OOS > **{tier['oos_sharpe_min']}** · Max DD < **{int(tier['oos_maxdd_max']*100)}%** · Violazioni **ZERO**")
    lines.append("")
    lines.append("### Milestone per modulo")
    lines.append("| Milestone | Soglia | Step richiesti |")
    lines.append("|---|---|---|")
    for m in plan.get("milestones", []):
        req = ", ".join(m.get("required_steps", []))
        lines.append(f"| {m['id']} — {m['name']} | {m.get('release_threshold','-')} | {req} |")
    lines.append("")
    lines.append("### Capital tiers (scope funzionale)")
    lines.append("| Tier | Strategie | Target | Max posizioni |")
    lines.append("|---|---|---:|---:|")
    for k,v in plan["capital_tiers"].items():
        strat = ", ".join(v["strategies"])
        lo,hi = v["target_monthly_return_pct"]
        mp_lo, mp_hi = v["max_positions"]
        cap_lo, cap_hi = v["capital_range_eur"]
        cap = f"€{cap_lo:,}–€{cap_hi:,}".replace(",", ".") if cap_hi else f"€{cap_lo:,}+".replace(",", ".")
        lines.append(f"| {k} ({cap}) | {strat} | {lo}–{hi}%/mese | {mp_lo}–{mp_hi} |")
    lines.append("")
    lines.append("_Generato automaticamente; modificare `config/release_plan_go_nogo.json` e rieseguire `py tools/hf_release_plan_go_nogo.py`._")
    return "\n".join(lines)


def _upsert_block(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        pre = text.split(BEGIN)[0]
        post = text.split(END)[1]
        return pre + BEGIN + "\n" + block + "\n" + END + post
    # append at end
    sep = "\n\n" if not text.endswith("\n") else "\n"
    return text + sep + BEGIN + "\n" + block + "\n" + END + "\n"


def main() -> int:
    plan = _load_plan()
    block = _render_md(plan)
    orig = APPENDIX.read_text(encoding="utf-8")
    new = _upsert_block(orig, block)
    if new != orig:
        APPENDIX.write_text(new, encoding="utf-8")
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    print(f"OK HF_RELEASE_PLAN updated canonici appendix ts_utc={ts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
