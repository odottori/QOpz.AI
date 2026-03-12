from __future__ import annotations


def adaptive_fixed_fractional(*, regime: str, base_fraction: float = 0.01, n_closed_trades: int = 0) -> float:
    """F4 addendum: pre-Kelly sizing for track-record < 50 trades.

    NORMAL=1.0x, CAUTION=0.5x, SHOCK=0.0x.
    For >=50 trades the function returns base_fraction unchanged (Kelly may take over elsewhere).
    """
    b = float(base_fraction)
    if b < 0:
        raise ValueError("base_fraction must be >= 0")

    if int(n_closed_trades) >= 50:
        return b

    reg = str(regime or "").strip().upper()
    if reg == "SHOCK":
        return 0.0
    if reg == "CAUTION":
        return b * 0.5
    return b


def kelly_allowed(*, data_mode: str, n_closed_trades: int) -> bool:
    mode = str(data_mode or "").strip().upper()
    return mode == "VENDOR_REAL_CHAIN" and int(n_closed_trades) >= 50
