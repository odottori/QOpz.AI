from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class _Signal(TypedDict):
    name: str
    status: str
    detail: str


class HistoryReadinessOut(TypedDict):
    profile: str
    window_days: int
    target_days: int
    days_observed: int
    days_remaining: int
    target_events: int
    events_observed: int
    events_remaining: int
    event_breakdown: Dict[str, int]
    quality_completeness: float
    quality_target: float
    quality_gap: float
    compliance_violations_window: int
    pace_events_per_day: float
    eta_days: Optional[int]
    eta_date_utc: Optional[str]
    blockers: List[str]
    ready: bool
    score_pct: float


class IbkrStatusOut(TypedDict):
    ok: bool
    connected: bool
    host: str
    port: Optional[int]
    client_id: Optional[int]
    source_system: str
    connected_at: Optional[str]
    ports_probed: List[int]
    message: str


class IbkrAccountPositionOut(TypedDict):
    symbol: str
    sec_type: str
    expiry: Optional[str]
    strike: Optional[float]
    right: Optional[str]
    quantity: float
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float


class IbkrAccountOut(TypedDict):
    ok: bool
    connected: bool
    source_system: str
    account_id: Optional[str]
    net_liquidation: Optional[float]
    realized_pnl: Optional[float]
    unrealized_pnl: Optional[float]
    buying_power: Optional[float]
    positions: List[IbkrAccountPositionOut]
    message: str


class RegimeCurrentOut(TypedDict):
    ok: bool
    regime: str
    n_recent: int
    regime_counts: Dict[str, int]
    regime_pct: Dict[str, float]
    last_scan_ts: Optional[str]
    source: str


class SystemStatusOut(TypedDict):
    ok: bool
    timestamp_utc: str
    api_online: bool
    kill_switch_active: bool
    data_mode: str
    kelly_enabled: bool
    ibkr_connected: bool
    ibkr_port: Optional[int]
    ibkr_source_system: str
    ibkr_connected_at: Optional[str]
    execution_config_ready: bool
    n_closed_trades: int
    regime: str
    signals: List[_Signal]
    history_readiness: HistoryReadinessOut


class EquityPointOut(TypedDict):
    date: str
    equity: float


class EquityHistoryOut(TypedDict):
    ok: bool
    profile: str
    n_points: int
    latest_equity: Optional[float]
    initial_equity: Optional[float]
    min_date: Optional[str]
    max_date: Optional[str]
    points: List[EquityPointOut]


class ExitCandidateOut(TypedDict):
    symbol: str
    expiry: Optional[str]
    strike: Optional[float]
    right: Optional[str]
    quantity: float
    avg_cost: float
    market_price: Optional[float]
    unrealized_pnl: Optional[float]
    exit_score: int
    exit_reasons: List[str]
    source: str


class _ExitThresholds(TypedDict):
    theta_decay_pct: float
    loss_limit_pct: float
    time_stop_dte: int


class ExitCandidatesOut(TypedDict):
    ok: bool
    source: str
    today: str
    n_total: int
    n_flagged: int
    candidates: List[ExitCandidateOut]
    thresholds: _ExitThresholds


class PreviewRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    strategy: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)


class EquitySnapshotRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    asof_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    equity: float
    note: str = Field(default="")
    trigger: str = Field(default="manual", pattern="^(auto|manual)$")


class TradeJournalRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    symbol: str = Field(..., min_length=1)
    strategy: str = Field(..., min_length=1)
    entry_ts_utc: Optional[str] = None
    exit_ts_utc: Optional[str] = None
    strikes: Optional[list[float]] = None
    regime_at_entry: Optional[str] = None
    score_at_entry: Optional[float] = None
    kelly_fraction: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float
    pnl_pct: Optional[float] = None
    slippage_ticks: Optional[float] = None
    violations: int = Field(default=0, ge=0)
    note: str = Field(default="")
    trigger: str = Field(default="manual", pattern="^(auto|manual)$")


class PreviewResponse(BaseModel):
    confirm_token: str
    preview: Dict[str, Any]


class ConfirmRequest(BaseModel):
    confirm_token: str
    operator: str = Field(default="operator")
    decision: str = Field(..., pattern="^(APPROVE|REJECT)$")
    payload: Dict[str, Any] = Field(default_factory=dict)


class OpportunityDecisionRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    batch_id: Optional[str] = None
    symbol: str = Field(..., min_length=1)
    strategy: Optional[str] = None
    score: Optional[float] = None
    regime: Optional[str] = None
    scanner_name: Optional[str] = None
    source: Optional[str] = None
    decision: str = Field(..., pattern="^(APPROVE|REJECT|MODIFY)$")
    confidence: int = Field(..., ge=1, le=5)
    note: str = Field(default="")


class UniverseScanRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    symbols: Optional[list[str]] = None
    regime: str = Field(default="NORMAL")
    top_n: int = Field(default=8, ge=1, le=50)
    source: str = Field(default="auto")
    scanner_name: Optional[str] = None
    settings_path: Optional[str] = None


class ScanFullRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    regime: str = Field(default="NORMAL")
    symbols: list[str] = Field(default_factory=list)
    top_n: int = Field(default=5, ge=1, le=50)
    account_size: float = Field(default=10_000.0, gt=0)
    min_score: float = Field(default=60.0, ge=0.0, le=100.0)
    signal_map: Optional[Dict[str, str]] = None
    signal_pct_map: Optional[Dict[str, float]] = None
    use_cache: bool = Field(default=True)


class DemoPipelineAutoRequest(BaseModel):
    profile: str = Field(default="paper", min_length=1)
    symbols: Optional[list[str]] = None
    settings_path: Optional[str] = None
    fetch_limit: int = Field(default=12, ge=1, le=100)
    top_n: int = Field(default=8, ge=1, le=50)
    regime: str = Field(default="NORMAL")
    extract_backend: str = Field(default="json-pass")
    auto_scan: bool = Field(default=True)


class NarratorTtsRequest(BaseModel):
    action: str = Field(..., pattern="^(play|pause|stop)$")
    text: str = Field(default="")


class AiPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=12000)


class AiChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str = Field(..., min_length=1, max_length=12000)


class AiChatRequest(BaseModel):
    messages: list[AiChatMessage] = Field(default_factory=list)
    prompt: Optional[str] = None


class KillSwitchRequest(BaseModel):
    action: str = Field(..., description="'activate' oppure 'deactivate'")


class ObserverSwitchRequest(BaseModel):
    action: str = Field(..., description="'on' oppure 'off' (alias: yes/no, activate/deactivate)")
    notify_telegram: bool = Field(default=True, description="Invia conferma su Telegram")
    telegram_chat_id: Optional[str] = Field(default=None, description="Override chat id telegram")
    source: str = Field(default="operator_ui")


class IbwrServiceRequest(BaseModel):
    action: str = Field(..., description="'on', 'off', 'status' (alias: start/stop)")
    notify_telegram: bool = Field(default=False, description="Invia conferma su Telegram")
    telegram_chat_id: Optional[str] = Field(default=None, description="Override chat id telegram")
    source: str = Field(default="operator_ui")


class WheelNewRequest(BaseModel):
    symbol: str = Field(..., description="Underlying symbol, e.g. IWM")
    profile: str = Field("dev")
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class WheelTransitionRequest(BaseModel):
    event_type: str = Field(..., description="open_csp | expire_csp | assign | open_cc | expire_cc | call_away")
    profile: str = Field("dev")
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strike: Optional[float] = None
    expiry: Optional[str] = None
    premium: Optional[float] = None
    shares: int = 100


class SessionRunRequest(BaseModel):
    type: str = Field(default="morning", pattern="^(morning|eod)$")
    profile: str = Field(default="paper")
    force: bool = Field(default=False, description="Esegui anche se non è giorno di trading")


class SessionLogRequest(BaseModel):
    profile: str = Field(default="paper")
    session_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    session_type: str = Field(..., pattern="^(morning|eod)$")
    regime: Optional[str] = None
    equity: Optional[float] = None
    n_symbols: Optional[int] = None
    errors: Optional[list[str]] = None
    trigger: str = Field(default="auto", pattern="^(auto|manual)$")
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    steps: Optional[dict] = None  # dettagli di ogni step della sessione
