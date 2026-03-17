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

_BOOL_ICON = {True: "✅", False: "❌", "post_qualification": "⚠️ post-qual", "post_gate_N50": "⚠️ N≥50"}


def _load_plan() -> dict:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def _fmt_cap(cap_lo: int, cap_hi: int | None) -> str:
    if cap_hi:
        return f"€{cap_lo:,}–€{cap_hi:,}".replace(",", ".")
    return f"€{cap_lo:,}+".replace(",", ".")


def _render_md(plan: dict) -> str:
    go = plan["principles"]["go_nogo"]
    tier_up = plan["principles"]["tier_upgrade"]

    lines: List[str] = []
    lines.append("## Appendice Z — Roadmap GO/NO-GO (Release per moduli)")
    lines.append("")

    # ── Gate GO/NO-GO ─────────────────────────────────────────────────────────
    lines.append("### Gate GO/NO-GO (paper → decisione live)")
    lines.append(f"- Sharpe paper ≥ **{go['paper_sharpe_min']}** (min **{go['paper_min_trades']}** trade)")
    lines.append(f"- Max DD paper < **{int(go['paper_maxdd_max']*100)}%** (in qualsiasi periodo)")
    lines.append("- Violazioni regole (sizing/stop/no-trade): **ZERO**")
    lines.append("")

    # ── Gate upgrade Tier ─────────────────────────────────────────────────────
    lines.append("### Gate upgrade Tier (OOS)")
    lines.append(
        f"- Sharpe OOS > **{tier_up['oos_sharpe_min']}** · "
        f"Max DD < **{int(tier_up['oos_maxdd_max']*100)}%** · Violazioni **ZERO**"
    )
    lines.append("")

    # ── Milestone per modulo ──────────────────────────────────────────────────
    lines.append("### Milestone per modulo")
    lines.append("| Milestone | Soglia | Step richiesti |")
    lines.append("|---|---|---|")
    for m in plan.get("milestones", []):
        req = ", ".join(m.get("required_steps", []))
        lines.append(f"| {m['id']} — {m['name']} | {m.get('release_threshold','-')} | {req} |")
    lines.append("")

    # ── Capital tiers (scope funzionale) ──────────────────────────────────────
    lines.append("### Capital tiers (scope funzionale)")
    lines.append("| Tier | Strategie | Target | Max posizioni |")
    lines.append("|---|---|---:|---:|")
    for k, v in plan["capital_tiers"].items():
        strat = ", ".join(v["strategies"])
        lo, hi = v["target_monthly_return_pct"]
        mp_lo, mp_hi = v["max_positions"]
        cap = _fmt_cap(v["capital_range_eur"][0], v["capital_range_eur"][1])
        lines.append(f"| {k} ({cap}) | {strat} | {lo}–{hi}%/mese | {mp_lo}–{mp_hi} |")
    lines.append("")

    # ── Tier Feature Matrix ───────────────────────────────────────────────────
    tfm = plan.get("tier_feature_matrix", {})
    if tfm:
        lines.append("### Tier Feature Matrix")
        lines.append(
            "> Il `capital_tier` (determinato dal capitale) definisce il tetto massimo disponibile. "
            "L'`active_mode` è la modalità operativa scelta dall'operatore (`active_mode ≤ capital_tier`)."
        )
        lines.append("")

        # ML & Sizing table
        lines.append("#### Stack tecnico per tier")
        lines.append("| Tier | Capitale | Milestone req. | XGBoost | HMM | Corr.Det. | Sizing | Kelly | TWAP/VWAP | Hedge |")
        lines.append("|---|---|---|:---:|:---:|:---:|---|:---:|:---:|:---:|")
        for k, v in tfm.items():
            ml = v["ml_stack"]
            cap = _fmt_cap(v["capital_range_eur"][0], v["capital_range_eur"][1])
            xgb  = _BOOL_ICON.get(ml["xgboost"], str(ml["xgboost"]))
            hmm  = _BOOL_ICON.get(ml["hmm_ensemble"], str(ml["hmm_ensemble"]))
            corr = _BOOL_ICON.get(ml["correlation_detector"], str(ml["correlation_detector"]))
            kelly = _BOOL_ICON.get(v["kelly_enabled"], str(v["kelly_enabled"]))
            twap  = _BOOL_ICON.get(v["twap_vwap"], str(v["twap_vwap"]))
            hedge = _BOOL_ICON.get(v["hedge_active"], str(v["hedge_active"]))
            lines.append(
                f"| **{k}** | {cap} | {v['milestone_prerequisite']} "
                f"| {xgb} | {hmm} | {corr} "
                f"| {v['sizing_policy']} | {kelly} | {twap} | {hedge} |"
            )
        lines.append("")

        # Strategies & UI table
        lines.append("#### Strategie e UI per tier")
        lines.append("| Tier | Strategie | Sottostanti | UI features |")
        lines.append("|---|---|---|---|")
        for k, v in tfm.items():
            strat = ", ".join(v["strategies"])
            under = ", ".join(v["underlyings"])
            ui = ", ".join(v["ui_features"])
            lines.append(f"| **{k}** | {strat} | {under} | {ui} |")
        lines.append("")

        # Upgrade gates table
        lines.append("#### Gate di upgrade tier")
        lines.append("| Tier → | Min trade | Sharpe OOS | Max DD | Kelly req. | Data mode |")
        lines.append("|---|---:|---:|---:|:---:|---|")
        for k, v in tfm.items():
            gate = v.get("upgrade_gate")
            if gate is None:
                lines.append(f"| **{k}** | — | — | — | — | — (tier finale) |")
            else:
                kelly_r = "✅" if gate.get("kelly_active_required") else "—"
                lines.append(
                    f"| **{k}** | {gate['min_closed_trades']} "
                    f"| ≥{gate['oos_sharpe_min']} | <{gate['max_dd_pct']}% "
                    f"| {kelly_r} | {gate['data_mode_required']} |"
                )
        lines.append("")

    lines.append(
        "_Generato automaticamente; modificare `config/release_plan_go_nogo.json` "
        "e rieseguire `py tools/hf_release_plan_go_nogo.py`._"
    )
    return "\n".join(lines)


def _upsert_block(text: str, block: str) -> str:
    if BEGIN in text and END in text:
        pre = text.split(BEGIN)[0]
        post = text.split(END)[1]
        return pre + BEGIN + "\n" + block + "\n" + END + post
    sep = "\n\n" if not text.endswith("\n") else "\n"
    return text + sep + BEGIN + "\n" + block + "\n" + END + "\n"


def main() -> int:
    plan = _load_plan()
    # update timestamp
    plan["generated_ts_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    PLAN.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    block = _render_md(plan)
    orig = APPENDIX.read_text(encoding="utf-8")
    new = _upsert_block(orig, block)
    if new != orig:
        APPENDIX.write_text(new, encoding="utf-8")
    ts = plan["generated_ts_utc"]
    print(f"OK HF_RELEASE_PLAN updated canonici appendix ts_utc={ts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
