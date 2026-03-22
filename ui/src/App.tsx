import React, { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

type ReleaseStatusResponse = { format: string; content: string };
type GateStatus = { pass: boolean; reasons: string[] };
type PreviewResponse = { confirm_token: string; preview: unknown };
type PaperSummaryResponse = {
  profile: string;
  window_days: number;
  as_of_date: string;
  equity_points: number;
  trades: number;
  sharpe_annualized: number | null;
  max_drawdown: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  avg_slippage_ticks: number | null;
  compliance_violations: number;
  pnl_cumulative?: number | null;
  gates: {
    go_nogo: GateStatus;
    f6_t1_acceptance: GateStatus;
    f6_t2_journal_complete: GateStatus & {
      completeness_ratio: number;
      required_missing: Record<string, number>;
    };
    window: { start_date: string; end_date: string };
    data_points: {
      equity_snapshots: number;
      trade_journal: number;
      compliance_events: number;
      trade_violation_sum: number;
    };
  };
};

type LastActionsResponse = {
  limit: number;
  paper_snapshots: Array<{
    snapshot_id: string;
    ts_utc: string;
    asof_date: string;
    equity: number | null;
    note: string;
    profile: string;
    trigger: string;
  }>;
  paper_trades: Array<{
    trade_id: string;
    ts_utc: string;
    symbol: string;
    strategy: string;
    pnl: number | null;
    pnl_pct: number | null;
    slippage_ticks: number | null;
    violations: number;
    note: string;
    profile: string;
    entry_ts_utc: string;
    exit_ts_utc: string;
    strikes_json: string;
    regime_at_entry: string;
    score_at_entry: number | null;
    kelly_fraction: number | null;
    exit_reason: string;
    trigger: string;
  }>;
  execution_previews: Array<{
    confirm_token: string | null;
    ts_unix: number | null;
    symbol: string | null;
    strategy: string | null;
  }>;
  execution_confirms: Array<{
    confirm_token: string | null;
    ts_unix: number | null;
    operator: string | null;
    decision: string | null;
  }>;
  opportunity_decisions: Array<{
    ts_utc: string;
    batch_id: string;
    symbol: string;
    strategy: string;
    score: number | null;
    regime: string;
    scanner_name: string;
    source: string;
    decision: string;
    confidence: number;
    note: string;
    profile: string;
  }>;
};

type UniverseScanItem = {
  rank: number;
  symbol: string;
  strategy: string;
  score: number;
  iv_rank: number;
  spread_pct: number;
  volume: number;
  open_interest: number;
  regime_fit: number;
  liquidity_score: number;
};

type UniverseLatestResponse = {
  has_data?: boolean;
  batch_id: string | null;
  profile: string | null;
  regime: string | null;
  top_n: number;
  universe_size: number;
  created_at_utc: string;
  source?: string | null;
  scanner_name?: string;
  ibkr_settings_path?: string;
  ibkr_settings_exists?: boolean;
  market_rows_available?: number;
  filter_fallback?: boolean;
  items: UniverseScanItem[];
};

type UniverseScannerDef = {
  scanner_name: string;
  scan_code: string;
  display_name: string;
  location_text: string;
  filters: Record<string, string>;
};

type UniverseIbkrContext = {
  source: string;
  settings_path: string;
  settings_exists: boolean;
  symbols: string[];
  quote_symbol_count: number;
  pages: string[];
  scanners: UniverseScannerDef[];
};

type UniverseFieldSource = "api" | "ocr" | "none";
type UniverseRowSource = "api" | "ocr" | "mixed" | "none";
type UniverseProvenanceRow = {
  tab: "titoli" | "indici" | "opzioni" | "ciclo" | "palinsesto";
  symbol: string;
  source: UniverseRowSource;
  field_sources: Record<string, UniverseFieldSource>;
  last: number | null;
  bid: number | null;
  ask: number | null;
  vs_pct: number | null;
  vi_pct: number | null;
  delta: number | null;
};

type UniverseProvenanceResponse = {
  generated_at_utc: string;
  batch_id?: string | null;
  symbol_scope?: string;
  api_rows: number;
  ocr_rows: number;
  rows: UniverseProvenanceRow[];
};
type DemoPipelineAutoResponse = {
  ok: boolean;
  profile: string;
  regime: string;
  ibkr_settings_path?: string | null;
  fetch?: { captured?: number; failed?: number };
  capture?: { captured?: number; duplicates?: number; skipped_fresh?: number };
  extract?: { valid?: number; needs_review?: number; errors?: number };
  dataset?: { records?: number; csv_path?: string };
  scan?: UniverseLatestResponse | null;
};

// ── ROC3: Opportunity Scanner (scan_full) ────────────────────────────────────
type ScanScoreBreakdown = { vol_edge: number; liquidity: number; risk_reward: number; regime_align: number };
type ScanFullCandidate = {
  symbol: string; strategy: string; score: number; score_breakdown: ScanScoreBreakdown;
  expiry: string; dte: number; strikes: number[]; delta: number; iv: number;
  iv_zscore_30: number | null; iv_zscore_60: number | null; iv_interp: string | null;
  expected_move: number | null; signal_vs_em_ratio: number | null;
  spread_pct: number; open_interest: number; volume: number;
  max_loss: number; max_loss_pct: number; breakeven: number; breakeven_pct: number;
  credit_or_debit: number; sizing_suggested: number; kelly_fraction: number | null;
  events_flag: string | null; human_review_required: boolean;
  stress_base: number; stress_shock: number;
  data_quality: string; source: string; underlying_price: number;
};
type ScanFullResponse = {
  ok: boolean; batch_id: string; profile: string; regime: string; data_mode: string;
  events_source: string;  // "ibkr_live" | "yfinance" | "events_map" | "none"
  scan_ts: string; symbols_scanned: number; symbols_with_chain: number;
  filtered_count: number; cache_used: boolean; cache_age_hours: number | null;
  ranking_suspended: boolean; suspension_reason: string | null;
  candidates: ScanFullCandidate[];
};
type SignalLifecycleItem = {
  symbol: string; strategy: string;
  state: "NEW" | "CONFIRMED" | "DEAD";
  n_confirmed: number;
  first_seen: string; last_seen: string;
  score: number; spread_pct: number | null; source: string | null;
};
type SignalLifecycleResponse = {
  ok: boolean; profile: string; generated_at: string;
  scan_dates: string[]; signals: SignalLifecycleItem[];
};
type IbkrStatusResponse = {
  ok: boolean; connected: boolean; host: string; port: number | null;
  client_id: number; source_system: string; connected_at: string | null;
  ports_probed: number[]; message: string;
};
type SystemSignal = { name: string; status: "OK" | "WARN" | "ALERT" | "DISABLED"; detail: string };
type HistoryReadinessResponse = {
  profile: string;
  window_days: number;
  target_days: number;
  days_observed: number;
  days_remaining: number;
  target_events: number;
  events_observed: number;
  events_remaining: number;
  event_breakdown: { equity_snapshots: number; paper_trades: number; opportunity_decisions: number };
  quality_completeness: number;
  quality_target: number;
  quality_gap: number;
  compliance_violations_window: number;
  pace_events_per_day: number;
  eta_days: number | null;
  eta_date_utc: string | null;
  blockers: string[];
  ready: boolean;
  score_pct: number;
};
type SystemStatusResponse = {
  ok: boolean; timestamp_utc: string; api_online: boolean;
  kill_switch_active: boolean; data_mode: string; kelly_enabled: boolean;
  ibkr_connected: boolean; ibkr_port: number | null; ibkr_source_system: string;
  ibkr_connected_at: string | null; execution_config_ready: boolean;
  n_closed_trades: number; regime: string; signals: SystemSignal[];
  history_readiness: HistoryReadinessResponse;
};
type RegimeCurrentResponse = {
  ok: boolean; regime: string;
  regime_counts: { NORMAL: number; CAUTION: number; SHOCK: number };
  regime_pct: { NORMAL: number; CAUTION: number; SHOCK: number };
  last_scan_ts: string | null; n_recent: number; source: string;
};
type EquityPoint = { date: string; equity: number };
type EquityHistoryResponse = {
  ok: boolean; profile: string; n_points: number;
  latest_equity: number | null; initial_equity: number | null;
  min_date: string | null; max_date: string | null;
  points: EquityPoint[];
};
type IbkrAccountPosition = {
  symbol: string; sec_type: string; expiry: string | null; strike: number | null;
  right: string | null; quantity: number; avg_cost: number;
  market_price: number; market_value: number;
  unrealized_pnl: number; realized_pnl: number;
};
type IbkrAccountResponse = {
  ok: boolean; connected: boolean; source_system: string;
  account_id: string | null; net_liquidation: number | null;
  realized_pnl: number | null; unrealized_pnl: number | null;
  buying_power: number | null; positions: IbkrAccountPosition[];
  message: string;
};
type SysLogRecord = { ts: string; level: string; name: string; msg: string; };
type SysLogResponse = { ok: boolean; n: number; records: SysLogRecord[]; };
type ActivityEvent = {
  ts: string; source: string; type: string;
  symbol?: string | null; detail: string;
  severity: "ok" | "warn" | "error" | "meta" | "data" | "neutral";
};
type ActivityStreamResponse = {
  ok: boolean; profile: string; n: number;
  events: ActivityEvent[]; as_of: string | null;
};
type ExitCandidate = {
  symbol: string; expiry: string | null; strike: number | null; right: string | null;
  quantity: number; avg_cost: number; market_price: number | null;
  unrealized_pnl: number | null; exit_score: number; exit_reasons: string[];
  source: string;
};
type ExitCandidatesResponse = {
  ok: boolean; source: string; today: string;
  n_total: number; n_flagged: number;
  candidates: ExitCandidate[];
  thresholds: { theta_decay_pct: number; loss_limit_pct: number; time_stop_dte: number };
};
type EvReportResponse = {
  ok: boolean; profile: string; window_days: number; generated_at: string;
  total_candidates: number; total_tracked: number; data_mode: string;
  score_distribution: { below_70: number; score_70_80: number; score_80_plus: number };
  strategies: Record<string, number>; regimes: Record<string, number>;
  human_review_required: number; events_flagged: number;
};

// ── Tier info ─────────────────────────────────────────────────────────────────
type TierName = "MICRO" | "SMALL" | "MEDIUM" | "ADVANCED";
type TierFeatures = {
  bull_put: boolean; iron_condor: boolean; wheel: boolean;
  pmcc_calendar: boolean; hedge_active: boolean; ratio_spread: boolean;
  delta_overlay: boolean; kelly_enabled: boolean; twap_vwap: boolean;
  multi_underlying: boolean;
};
type TierDetail = { capital: string; strategies: string[]; max_positions: number; };
type BlockVis = { visible: boolean; interactive: boolean; gate: string; reason: string | null };
type BlockVisibility = Record<string, BlockVis>;

type TierResponse = {
  ok: boolean; profile: string;
  capital_tier: TierName; active_mode: TierName;
  regime: string;
  features: TierFeatures;
  features_validated: TierFeatures;
  features_available: TierFeatures;
  tier_detail: TierDetail;
  next_tier: TierName | null;
  next_capital_tier: TierName | null;
  next_operational_tier: TierName | null;
  block_visibility: BlockVisibility;
  data_gate: { ok: boolean; data_mode: string; n_closed: number };
  kill_switch_active: boolean;
};

// ── ROC35: Wheel positions ────────────────────────────────────────────────────
type WheelState = "IDLE" | "OPEN_CSP" | "ASSIGNED" | "OPEN_CC" | "CLOSED";
type WheelPosition = {
  position_id: string;
  symbol: string;
  state: WheelState;
  csp_strike: number | null;
  csp_expiry: string | null;
  cc_strike: number | null;
  cc_expiry: string | null;
  total_premium_collected: number;
  unrealized_cost_basis: number | null;
  cycle_count: number;
  opened_at: string;
  updated_at: string;
};
type WheelPositionsResponse = {
  ok: boolean;
  profile: string;
  n: number;
  positions: WheelPosition[];
};

type NarratorTutorialResponse = {
  path: string;
  exists: boolean;
  content: string;
  lines: number;
};

type NarratorTtsResponse = {
  ok: boolean;
  action: "play" | "pause" | "stop";
  command: string;
  returncode: number;
  stdout: string;
  stderr: string;
};
type AiChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

type AiChatResponse = {
  ok: boolean;
  model: string;
  reply: string;
  messages: AiChatMessage[];
  stdout: string;
  stderr: string;
  returncode: number;
  duration_ms: number;
};
type AiPromptLegacyResponse = {
  ok: boolean;
  model: string;
  prompt: string;
  response: string;
  stdout: string;
  stderr: string;
  returncode: number;
  duration_ms: number;
};

type ControlStatusResponse = {
  ok: boolean;
  timestamp_utc: string;
  observer: { state: string; kill_switch_active: boolean; reason: string };
  ibwr: { service_state?: string; reason?: string; ts_utc?: string };
  ibkr: { connected: boolean; port: number | null; source_system: string | null; connected_at: string | null };
  vm: { services: Record<string, unknown>; control_plane_ok: boolean; control_plane_error: string | null };
  regime: string | null;
  data_mode: string | null;
  history_readiness: unknown;
};

type IbwrServiceResponse = {
  ok: boolean;
  requested_action: string;
  applied_action: string;
  service_state: string;
  reason: string;
  ts_utc?: string;
  kill_switch_active?: boolean;
  kill_switch_forced?: boolean;
  telegram_notified?: boolean;
  telegram_error?: string | null;
  message?: string;
};

type CenterPhase = "ante" | "op" | "post";
type AnteSubTab = "dati" | "analisi" | "briefing";
type OpSubTab = "trading" | "wheel" | "metriche" | "backtest";
type PostSubTab = "chiusura" | "report";
type UniverseSubTab = "titoli" | "indici" | "opzioni" | "ciclo" | "palinsesto";
type MarkdownTable = { headers: string[]; rows: string[][] };
type ReleaseMdView = { before: string; table: MarkdownTable | null; after: string };
// In production (Docker/nginx) usa URL relativo — nginx fa proxy.
// In dev locale: VITE_API_BASE=http://localhost:8765 in .env.local
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
/** Profilo attivo — unico punto di modifica per dev/paper/live */
const ACTIVE_PROFILE = (import.meta.env.VITE_PROFILE as string | undefined) ?? "paper";

// ── Tooltip dictionary (30+ voci) ─────────────────────────────────────────
const TOOLTIPS: Record<string, string> = {
  // Topbar
  regime_normal: "Il mercato è stabile. Il sistema può operare a piena capacità con sizing al 100%.",
  regime_caution: "Il mercato è in tensione. Sizing ridotto al 50%, solo spread stretti e filtro direzionale attivo.",
  regime_shock: "Evento di mercato estremo. Tutti i nuovi trade sono bloccati. Sizing 0%.",
  regime_offline: "Stato regime non disponibile. Il sistema non ha ricevuto dati recenti dal classificatore.",
  ibkr_connected: "Connesso a Interactive Brokers. I dati di mercato e le opzioni chain arrivano in tempo reale.",
  ibkr_disconnected: "Non connesso a Interactive Brokers. Il sistema usa dati storici da yfinance come alternativa.",
  data_mode_synthetic: "I dati usati sono sintetici (simulati). I risultati non sono reali e Kelly è disabilitato.",
  data_mode_real: "I dati provengono da fonti reali. Kelly può essere abilitato se hai almeno 50 operazioni chiuse.",
  stale: "Alcuni aggiornamenti non sono riusciti. I dati mostrati potrebbero non essere aggiornati.",

  // Metriche principali
  trades: "Numero totale di operazioni registrate nel journal. Ogni trade chiuso aumenta questo contatore.",
  sharpe: "Rapporto tra rendimento medio e rischio. Sopra 0.6 il sistema considera i risultati sufficienti per passare al trading reale.",
  max_dd: "La perdita massima dal picco del portafoglio. Deve restare sotto il 15% per superare la verifica finale.",
  win_rate: "Percentuale di operazioni chiuse in profitto. Sopra il 50% indica una strategia redditizia.",
  profit_factor: "Rapporto tra profitti totali e perdite totali. Sopra 1.0 significa che guadagni più di quanto perdi.",
  compliance: "Numero di violazioni delle regole operative (es. ordini fuori finestra, sizing eccessivo).",
  tier: "Livello operativo attuale basato sul capitale disponibile. Determina quali strategie sono accessibili.",

  // Kelly
  kelly_sizing: "Formula che calcola la percentuale ottimale del capitale da rischiare per operazione. Bloccato finché non hai 50 operazioni su dati reali.",
  kelly_half: "Dimensionamento Half-Kelly: metà del valore teorico ottimale, per ridurre la volatilità del portafoglio.",
  avg_slippage: "Differenza media tra il prezzo atteso e quello eseguito, in tick. Più basso è meglio.",

  // Gate
  go_nogo: "Verifica complessiva che determina se il sistema è pronto per avanzare alla fase successiva.",
  f6_t1: "Gate che verifica il completamento accettabile della pipeline di accettazione delle operazioni.",
  f6_t2: "Gate che verifica la completezza del journal di trading. Tutti i campi obbligatori devono essere compilati.",
  f6_t2_ratio: "Percentuale di completezza del journal: quanti campi obbligatori sono stati compilati correttamente.",

  // Equity & Drawdown
  equity_curve: "L'andamento del valore del portafoglio nel tempo. Una curva crescente indica una strategia profittevole.",
  drawdown_gauge: "Indicatore visivo della perdita massima attuale rispetto al limite operativo del 20%.",

  // History Readiness
  history_readiness: "Verifica se il sistema ha accumulato abbastanza dati storici per essere certificato per il trading reale.",
  history_window: "Finestra temporale analizzata per la verifica di idoneità, espressa in giorni.",
  history_days: "Giorni di dati effettivamente coperti rispetto all'obiettivo richiesto dal sistema.",
  history_events: "Numero di eventi registrati (snapshot equity, trade, decisioni) rispetto all'obiettivo.",
  history_quality: "Completezza del journal: percentuale di campi obbligatori compilati correttamente.",
  history_violations: "Numero di violazioni delle regole operative nella finestra analizzata. Zero è l'obiettivo.",
  history_eta: "Stima del tempo mancante per raggiungere il numero di dati sufficiente per la certificazione.",

  // Paper countdown
  paper_countdown: "Operazioni chiuse su 50 richieste. Raggiunte 50 su dati reali, il sistema verifica se sei pronto per il trading reale.",

  // Universe Scanner
  score_composito: "Punteggio da 0 a 1 basato su 4 pilastri: liquidità, timing, struttura e allineamento al regime.",
  ivr: "Rango di volatilità implicita: percentile rispetto all'ultimo anno. Sopra 20 il premio venduto è interessante.",
  oi: "Open Interest: numero di contratti aperti. Misura la liquidità dell'opzione sul mercato.",
  dte: "Giorni alla scadenza dell'opzione. Il sistema accetta solo opzioni con scadenza tra 14 e 60 giorni.",
  spread_pct: "Costo dello spread denaro/lettera in percentuale del prezzo. Più basso significa meno costoso da eseguire.",
  source_api: "Il dato proviene direttamente dall'API di Interactive Brokers (qualità alta).",
  source_ocr: "Il dato è stato estratto tramite riconoscimento ottico da uno screenshot di TWS (qualità media).",
  source_mixed: "Il dato combina fonti API e OCR. Verificare la coerenza prima di operare.",
  source_none: "Nessuna fonte disponibile per questo simbolo. Il dato non è affidabile.",

  // Opportunity Scanner
  score_opp: "Punteggio composito 0–100 basato su 4 pilastri. Sopra 75 il candidato è considerato di alta qualità.",
  ivz_30: "Z-score della volatilità implicita a 30 giorni: quanto è sopra o sotto la media storica.",
  em_pct: "Expected Move: variazione percentuale attesa dal mercato entro la scadenza dell'opzione.",
  vol_edge: "Vantaggio di volatilità: misura quanto la volatilità implicita supera quella realizzata.",
  liquidity_score: "Punteggio di liquidità basato su Open Interest, volume e spread denaro/lettera.",
  risk_reward: "Rapporto tra premio incassato e perdita massima possibile. Più alto è, meglio è.",
  regime_align: "Misura quanto la strategia si adatta al regime di mercato corrente (NORMAL/CAUTION/SHOCK).",
  events_flag: "Segnale di eventi societari imminenti (earnings, dividendi) che aumentano il rischio.",

  // Regime Matrix
  regime_matrix_sizing: "Moltiplicatore applicato al sizing calcolato da Kelly in base al regime di mercato corrente.",
  regime_matrix_hedge: "Indica se la copertura del portafoglio è attiva, monitorata o disattivata.",

  // Wheel states
  state_idle: "Nessuna posizione aperta per questo sottostante.",
  state_open_csp: "Cash Secured Put aperta: hai venduto il diritto di comprare azioni a un prezzo prefissato.",
  state_assigned: "La Put è stata esercitata: hai acquistato le azioni al prezzo dello strike.",
  state_open_cc: "Covered Call aperta: hai venduto il diritto di acquistare le azioni che già possiedi.",
  state_closed: "Ciclo completato: tutte le posizioni sono state chiuse.",

  // Pipeline
  pipe_data: "Raccolta dati di mercato da fonti esterne (yfinance, IBKR, FRED).",
  pipe_ivr: "Calcolo del rango di volatilità implicita per ogni sottostante del portafoglio.",
  pipe_regime: "Classificazione del regime di mercato corrente (NORMAL, CAUTION o SHOCK).",
  pipe_score: "Calcolo del punteggio composito per i candidati all'operazione.",
  pipe_kelly: "Calcolo del dimensionamento ottimale tramite la formula di Kelly. Richiede dati reali e 50 trade.",
};

// ── Tooltip component ──────────────────────────────────────────────────────
function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  if (!text) return <>{children}</>;

  return (
    <span
      ref={wrapRef}
      className={`tt-wrap${open ? " tt-open" : ""}`}
      onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
    >
      {children}
      <span className="tt-box">{text}</span>
    </span>
  );
}

function fmtPct(v: number | null): string {
  if (v === null) return "-";
  return `${(v * 100).toFixed(2)}%`;
}

function fmtNum(v: number | null): string {
  if (v === null) return "-";
  return Number.isFinite(v) ? v.toFixed(3) : String(v);
}

function fmtTs(iso: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function fmtUnix(ts: number | null): string {
  if (!Number.isFinite(ts ?? NaN)) return "-";
  const d = new Date((ts as number) * 1000);
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function shortToken(token: string | null): string {
  if (!token) return "-";
  if (token.length <= 12) return token;
  return `${token.slice(0, 6)}...${token.slice(-4)}`;
}

function sanitizeSignalDetail(detail: string, status: SystemSignal["status"]): string {
  const raw = (detail ?? "").trim();
  if (!raw) return "-";
  const token = status.toUpperCase();
  if (raw.toUpperCase() === token) return "-";
  const cleaned = raw.replace(new RegExp(`(?:\\s*[|:/\\-—–]?\\s*)${token}$`, "i"), "").trim();
  return cleaned || raw;
}

function sevClassForSignalStatus(status: SystemSignal["status"]): string {
  if (status === "OK") return "sev-ok";
  if (status === "WARN") return "sev-warn";
  if (status === "ALERT") return "sev-error";
  return "sev-neutral";
}

function sevClassForRegime(regime: string | null | undefined): string {
  if (regime === "NORMAL") return "sev-ok";
  if (regime === "CAUTION") return "sev-warn";
  if (regime === "SHOCK") return "sev-error";
  return "sev-neutral";
}

type UiHealth = "ok" | "warn" | "alert" | "neutral";

function healthToDotClass(h: UiHealth): string {
  if (h === "ok") return "dot-green";
  if (h === "warn") return "dot-amber";
  if (h === "alert") return "dot-red";
  return "dot-gray";
}

function healthToBadgeClass(h: UiHealth): string {
  if (h === "ok") return "ok";
  if (h === "warn") return "warn";
  if (h === "alert") return "alert";
  return "neutral";
}

function healthToSevClass(h: UiHealth): string {
  if (h === "ok") return "sev-ok";
  if (h === "warn") return "sev-warn";
  if (h === "alert") return "sev-error";
  return "sev-neutral";
}

function GateBadge({ pass }: { pass: boolean }) {
  return <span className={`gate-badge ${pass ? "ok" : "ko"}`}>{pass ? "PASS" : "FAIL"}</span>;
}

// ── ROC10: pure-SVG equity sparkline ──────────────────────────────────────
function EqSparkline({ points, w = 260, h = 52 }: {
  points: EquityPoint[]; w?: number; h?: number;
}) {
  if (points.length < 2) {
    return (
      <svg width={w} height={h} style={{ display: "block" }}>
        <text x={w / 2} y={h / 2} textAnchor="middle" fill="#444" fontSize={11}>
          {points.length === 0 ? "Nessun dato equity" : "Solo 1 punto — aggiungi snapshot"}
        </text>
      </svg>
    );
  }

  const vals = points.map((p) => p.equity);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const range = maxV - minV || 1;
  const pad = 4;
  const iw = w - pad * 2;
  const ih = h - pad * 2;

  const xs = points.map((_, i) => pad + (i / (points.length - 1)) * iw);
  const ys = vals.map((v) => pad + ih - ((v - minV) / range) * ih);

  const polyline = xs.map((x, i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  // Fill area under curve
  const areaPath =
    `M${xs[0].toFixed(1)},${(h - pad).toFixed(1)} ` +
    xs.map((x, i) => `L${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ") +
    ` L${xs[xs.length - 1].toFixed(1)},${(h - pad).toFixed(1)} Z`;

  const pnl = vals[vals.length - 1] - vals[0];
  const lineColor = pnl >= 0 ? "#4ade80" : "#f87171";

  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity={0.25} />
          <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      {/* Gridline at 0% = initial */}
      <line
        x1={pad} y1={ys[0].toFixed(1)} x2={w - pad} y2={ys[0].toFixed(1)}
        stroke="#333" strokeDasharray="3,3" strokeWidth={1}
      />
      {/* Area fill */}
      <path d={areaPath} fill="url(#eq-fill)" />
      {/* Line */}
      <polyline points={polyline} fill="none" stroke={lineColor} strokeWidth={1.8} strokeLinejoin="round" />
      {/* Last point dot */}
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r={3} fill={lineColor} />
    </svg>
  );
}

function parseFiniteInput(raw: string, field: string): { ok: true; value: number } | { ok: false; message: string } {
  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value)) {
    return { ok: false, message: `${field}: valore numerico non valido.` };
  }
  return { ok: true, value };
}

function parseIntInput(raw: string, field: string): { ok: true; value: number } | { ok: false; message: string } {
  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value)) {
    return { ok: false, message: `${field}: intero non valido.` };
  }
  return { ok: true, value };
}

function splitPipeRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((x) => x.trim());
}

function isMdSeparator(line: string): boolean {
  return /^[\s|\-:]+$/.test(line) && line.includes("-");
}

function parseReleaseMd(md: string): ReleaseMdView {
  const src = (md || "").replace(/\r\n/g, "\n");
  const lines = src.split("\n");

  for (let i = 0; i + 1 < lines.length; i += 1) {
    const headerLine = lines[i];
    const separatorLine = lines[i + 1];
    if (!headerLine.includes("|") || !isMdSeparator(separatorLine)) {
      continue;
    }

    let end = i + 2;
    while (end < lines.length && lines[end].includes("|")) {
      end += 1;
    }

    const headers = splitPipeRow(headerLine);
    if (headers.length === 0) {
      continue;
    }

    const rows = lines
      .slice(i + 2, end)
      .filter((row) => row.trim().length > 0)
      .map((row) => {
        const cells = splitPipeRow(row);
        while (cells.length < headers.length) {
          cells.push("");
        }
        return cells.slice(0, headers.length);
      });

    return {
      before: lines.slice(0, i).join("\n").trim(),
      table: { headers, rows },
      after: lines.slice(end).join("\n").trim(),
    };
  }

  return { before: src.trim(), table: null, after: "" };
}

export default function App() {
  const [stateJson, setStateJson] = useState<unknown>(null);
  const [releaseMd, setReleaseMd] = useState<string>("");
  const [paperSummary, setPaperSummary] = useState<PaperSummaryResponse | null>(null);
  const [lastActions, setLastActions] = useState<LastActionsResponse | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [centerPhase, setCenterPhase] = useState<CenterPhase>("ante");
  const [anteSubTab, setAnteSubTab] = useState<AnteSubTab>("dati");
  const [opSubTab, setOpSubTab] = useState<OpSubTab>("trading");
  const [postSubTab, setPostSubTab] = useState<PostSubTab>("chiusura");
  const [clockText, setClockText] = useState<string>("");
  const [universeLatest, setUniverseLatest] = useState<UniverseLatestResponse | null>(null);
  const [universeSymbols, setUniverseSymbols] = useState<string>("SPY,QQQ,IWM,AAPL,MSFT,NVDA,AMZN,META,TSLA,AMD");
  const [universeTopN, setUniverseTopN] = useState<string>("6");
  const [universeRegime, setUniverseRegime] = useState<"NORMAL" | "CAUTION" | "SHOCK">("NORMAL");
  const [universeSource, setUniverseSource] = useState<"auto" | "manual" | "ibkr_settings">("ibkr_settings");
  const [ibkrContext, setIbkrContext] = useState<UniverseIbkrContext | null>(null);
  const [universeScannerName, setUniverseScannerName] = useState<string>("");
  const [universeSettingsPath, setUniverseSettingsPath] = useState<string>("");
  const [universeSubTab, setUniverseSubTab] = useState<UniverseSubTab>("titoli");
  const [universeProvenance, setUniverseProvenance] = useState<UniverseProvenanceResponse | null>(null);
  const [oppScanResult, setOppScanResult] = useState<ScanFullResponse | null>(null);
  const [oppScanBusy, setOppScanBusy] = useState<boolean>(false);
  const [briefingBusy, setBriefingBusy] = useState<boolean>(false);
  const [briefingList, setBriefingList] = useState<string[]>([]);
  const [briefingListIdx, setBriefingListIdx] = useState<number>(0);
  const [briefingPlaying, setBriefingPlaying] = useState<boolean>(false);
  const [briefingAutoOpen, setBriefingAutoOpen] = useState<boolean>(false);
  const [briefingAutoPlay, setBriefingAutoPlay] = useState<boolean>(false);
  const briefingAudioRef = useRef<HTMLAudioElement | null>(null);
  const [oppScanSymbols, setOppScanSymbols] = useState<string>("SPY,QQQ,AAPL,MSFT,NVDA");
  const [oppScanRegime, setOppScanRegime] = useState<"NORMAL" | "CAUTION" | "SHOCK">("NORMAL");
  const [oppScanTopN, setOppScanTopN] = useState<string>("5");
  const [oppScanAccountSize, setOppScanAccountSize] = useState<string>("10000");
  const [selectedScanKey, setSelectedScanKey] = useState<string>("");
  const [evReport, setEvReport] = useState<EvReportResponse | null>(null);
  const [ibkrStatus, setIbkrStatus] = useState<IbkrStatusResponse | null>(null);
  const [ibkrChecking, setIbkrChecking] = useState<boolean>(false);
  const [ibkrAccount, setIbkrAccount] = useState<IbkrAccountResponse | null>(null);
  const [ibkrAccountLoading, setIbkrAccountLoading] = useState<boolean>(false);
  const [storicoTrades, setStoricoTrades] = useState<any[]>([]);
  const [storicoSummary, setStoricoSummary] = useState<any>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  const [storicoFrom, setStoricoFrom] = useState<string>("");
  const [storicoTo, setStoricoTo] = useState<string>("");
  const [posOutcomeFilter, setPosOutcomeFilter] = useState<"tutti"|"positivi"|"negativi"|"aperti">("tutti");
  const [posStrategyFilter, setPosStrategyFilter] = useState<string>("tutte");
  const [sysStatus, setSysStatus] = useState<SystemStatusResponse | null>(null);
  const [regimeCurrent, setRegimeCurrent] = useState<RegimeCurrentResponse | null>(null);
  const [equityHistory, setEquityHistory] = useState<EquityHistoryResponse | null>(null);
  const [exitCandidates, setExitCandidates] = useState<ExitCandidatesResponse | null>(null);
  const [activityStream, setActivityStream] = useState<ActivityStreamResponse | null>(null);
  const [activityOpen, setActivityOpen] = useState<boolean>(true);
  const [sysLog, setSysLog] = useState<SysLogRecord[]>([]);
  const [sysLogOpen, setSysLogOpen] = useState<boolean>(true);
  const [scanConfigOpen, setScanConfigOpen] = useState<boolean>(false);
  const sysLogRef = React.useRef<HTMLDivElement>(null);
  const [wheelPositions, setWheelPositions] = useState<WheelPositionsResponse | null>(null);
  const [wheelFetchedAt, setWheelFetchedAt] = useState<number | null>(null);
  const [tierInfo, setTierInfo] = useState<TierResponse | null>(null);


  const [symbol, setSymbol] = useState("IWM");
  const [strategy, setStrategy] = useState("BULL_PUT");
  const [payload, setPayload] = useState<string>('{"legs": []}');
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewSignature, setPreviewSignature] = useState<string | null>(null);
  const [confirmDecision, setConfirmDecision] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [confirmArmed, setConfirmArmed] = useState<boolean>(false);
  const confirmArmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [sysStatusFetchedAt, setSysStatusFetchedAt] = useState<number | null>(null);
  const [ibkrAccountFetchedAt, setIbkrAccountFetchedAt] = useState<number | null>(null);
  const [exitCandidatesFetchedAt, setExitCandidatesFetchedAt] = useState<number | null>(null);
  const [fetchErrors, setFetchErrors] = useState<Set<string>>(new Set());
  const [aiDrawerOpen, setAiDrawerOpen] = useState<boolean>(false);
  const [opExecOpen, setOpExecOpen] = useState<boolean>(false);
  const [execWindowOpen, setExecWindowOpen] = useState<boolean>(false);  // collassato di default
  const [dumpOpen, setDumpOpen] = useState<boolean>(false);              // DUMP block collassato di default
  const [scoreFilter, setScoreFilter] = useState<"all"|"high"|"mid"|"low">("all"); // filtro segnali per soglia score
  const [segnaliStrategyFilter, setSegnaliStrategyFilter] = useState<string>("tutte");
  const [segnaliFrom, setSegnaliFrom] = useState<string>("");
  const [segnaliTo, setSegnaliTo] = useState<string>("");
  const [segnaliFiltersOpen, setSegnaliFiltersOpen] = useState(false);
  const [posFiltersOpen, setPosFiltersOpen] = useState(false);
  const [signalLifecycle, setSignalLifecycle] = useState<SignalLifecycleResponse | null>(null);
  const [lifecycleLoading, setLifecycleLoading] = useState(false);
  const [lifecycleFilter, setLifecycleFilter] = useState<"all"|"new"|"confirmed"|"dead">("all");
  const [kpiExpanded, setKpiExpanded] = useState<string|null>(null); // blocco KPI espanso nel tab TRADING
  const [pinnedKpis, setPinnedKpis] = useState<string[]>([]);        // KPI bloccati nella colonna destra
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [leftKellyOpen, setLeftKellyOpen] = useState<boolean>(false);
  const [leftPhaseOpen, setLeftPhaseOpen] = useState<boolean>(false);
  const [leftExecWindowOpen, setLeftExecWindowOpen] = useState<boolean>(false);
  const [leftPipelineGroupOpen, setLeftPipelineGroupOpen] = useState<boolean>(true);
  const [leftOperationsOpen, setLeftOperationsOpen] = useState<boolean>(true);
  const [leftLiveStatusOpen, setLeftLiveStatusOpen] = useState<boolean>(false);
  const [leftPipelineDataOpen, setLeftPipelineDataOpen] = useState<boolean>(true);
  const [leftPipelineProgressOpen, setLeftPipelineProgressOpen] = useState<boolean>(true);
  const [leftDataHealthOpen, setLeftDataHealthOpen] = useState<boolean>(false);
  const [leftDevelopmentOpen, setLeftDevelopmentOpen] = useState<boolean>(false);
  const [slideDataPipelineOpen, setSlideDataPipelineOpen] = useState<boolean>(false);
  const [slideDataRecordsOpen, setSlideDataRecordsOpen] = useState<boolean>(false);
  const [slideDataModeOpen, setSlideDataModeOpen] = useState<boolean>(false);
  const [slideDataLatencyOpen, setSlideDataLatencyOpen] = useState<boolean>(false);
  const [controlStatus, setControlStatus] = useState<ControlStatusResponse | null>(null);
  const [ibwrBusy, setIbwrBusy] = useState<boolean>(false);
  const [narratorTutorial, setNarratorTutorial] = useState<NarratorTutorialResponse | null>(null);
  const [narratorBusy, setNarratorBusy] = useState<boolean>(false);
  const [narratorVoiceState, setNarratorVoiceState] = useState<"idle" | "playing" | "paused">("idle");
  const [narratorQuery, setNarratorQuery] = useState<string>("");
  const [narratorMatches, setNarratorMatches] = useState<number[]>([]);
  const [narratorMatchIdx, setNarratorMatchIdx] = useState<number>(-1);
  const narratorBoxRef = useRef<HTMLTextAreaElement | null>(null);
  const [aiPrompt, setAiPrompt] = useState<string>("");
  const [aiMessages, setAiMessages] = useState<AiChatMessage[]>([]);
  const [aiBusy, setAiBusy] = useState<boolean>(false);
  const [sessionStatus, setSessionStatus] = useState<{
    enabled: boolean; running: boolean;
    last_morning: string | null; last_eod: string | null;
    next_morning: string | null; next_eod: string | null;
  } | null>(null);

  type SessionLogEntry = {
    log_id: string; session_date: string; session_type: string;
    regime: string | null; equity: number | null; n_symbols: number | null;
    errors: string[]; steps: Record<string, unknown>;
    trigger: string; started_at: string | null; finished_at: string | null;
  };
  const [sessionLogs, setSessionLogs] = useState<SessionLogEntry[]>([]);
  const [sessionLogOpen, setSessionLogOpen] = useState(false);

  const parsedPayload = useMemo(() => {
    try {
      const parsed = JSON.parse(payload);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
      return parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [payload]);

  const payloadJsonError = parsedPayload === null;
  const executionSignature = useMemo(() => {
    if (!parsedPayload) return null;
    return JSON.stringify({ symbol: symbol.trim(), strategy: strategy.trim(), payload: parsedPayload });
  }, [symbol, strategy, parsedPayload]);
  const previewDirty = Boolean(preview && previewSignature && executionSignature && previewSignature !== executionSignature);
  const aiTranscript = useMemo(() => {
    if (aiMessages.length === 0) {
      return "Nessuna conversazione AI. Inserisci un prompt e premi INVIA.";
    }
    return aiMessages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => `${m.role === "user" ? "YOU" : "AI"}: ${m.content}`)
      .join("\n\n");
  }, [aiMessages]);

  const tutorialText = useMemo(() => {
    const content = narratorTutorial?.content ?? "";
    return content.replace(/\r\n/g, "\n");
  }, [narratorTutorial]);



  useEffect(() => {
    const q = narratorQuery.trim().toLowerCase();
    if (!q) {
      setNarratorMatches([]);
      setNarratorMatchIdx(-1);
      return;
    }
    const hay = tutorialText.toLowerCase();
    const found: number[] = [];
    let from = 0;
    while (from < hay.length) {
      const hit = hay.indexOf(q, from);
      if (hit < 0) break;
      found.push(hit);
      from = hit + Math.max(1, q.length);
      if (found.length >= 500) break;
    }
    setNarratorMatches(found);
    setNarratorMatchIdx(found.length > 0 ? 0 : -1);
  }, [narratorQuery, tutorialText]);


  const focusNarratorRange = (start: number, end: number) => {
    const el = narratorBoxRef.current;
    if (!el) return;
    const safeStart = Math.max(0, Math.min(start, tutorialText.length));
    const safeEnd = Math.max(safeStart, Math.min(end, tutorialText.length));
    el.focus();
    el.setSelectionRange(safeStart, safeEnd);
    const ratio = tutorialText.length > 0 ? safeStart / tutorialText.length : 0;
    el.scrollTop = Math.max(0, (el.scrollHeight - el.clientHeight) * ratio);
  };


  useEffect(() => {
    if (narratorMatchIdx < 0 || narratorMatchIdx >= narratorMatches.length) return;
    const q = narratorQuery.trim();
    if (!q) return;
    const start = narratorMatches[narratorMatchIdx];
    focusNarratorRange(start, start + q.length);
  }, [narratorMatchIdx, narratorMatches, narratorQuery]);

  const moveNarratorMatch = (step: number) => {
    if (narratorMatches.length === 0) return;
    setNarratorMatchIdx((prev) => {
      const base = prev < 0 ? 0 : prev;
      return (base + step + narratorMatches.length) % narratorMatches.length;
    });
  };


  const buildNarratorPlayText = (): string => {
    const el = narratorBoxRef.current;
    if (el) {
      const s = Math.max(0, Math.min(el.selectionStart ?? 0, tutorialText.length));
      const e = Math.max(0, Math.min(el.selectionEnd ?? 0, tutorialText.length));
      if (e > s) {
        const selected = tutorialText.slice(s, e).trim();
        if (selected) return selected;
      }
    }

    if (narratorMatchIdx >= 0 && narratorMatchIdx < narratorMatches.length) {
      const pos = narratorMatches[narratorMatchIdx];
      const qLen = Math.max(1, narratorQuery.trim().length);
      const from = Math.max(0, pos - 140);
      const to = Math.min(tutorialText.length, pos + qLen + 140);
      return tutorialText.slice(from, to).trim();
    }
    return tutorialText.slice(0, 5000).trim();
  };

  async function doNarratorTts(action: "play" | "pause" | "stop") {
    if (action === "play" && !tutorialText.trim()) {
      setError("Tutorial narratore vuoto o non disponibile.");
      setMessage("");
      return;
    }
    setNarratorBusy(true);
    setError("");
    try {
      const body = { action, text: action === "play" ? buildNarratorPlayText() : "" };
      const out = await apiJson<NarratorTtsResponse>(`${API_BASE}/opz/narrator/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!out.ok) {
        throw new Error(out.stderr || out.stdout || `qwenTTS ${action} failed`);
      }
      if (action === "play") setNarratorVoiceState("playing");
      if (action === "pause") setNarratorVoiceState("paused");
      if (action === "stop") setNarratorVoiceState("idle");
      setMessage(out.stdout || `qwenTTS ${action}: OK`);
    } catch (e) {
      setError(String(e));
      setMessage("");
    } finally {
      setNarratorBusy(false);
    }
  }

  async function doAiPrompt() {
    const prompt = aiPrompt.trim();
    if (!prompt) {
      setError("Prompt AI vuoto.");
      setMessage("");
      return;
    }

    const outboundMessages: AiChatMessage[] = [
      ...aiMessages.filter((m) => m.role === "user" || m.role === "assistant").slice(-16),
      { role: "user", content: prompt },
    ];

    setAiBusy(true);
    setError("");
    try {
      try {
        const out = await apiJson<AiChatResponse>(`${API_BASE}/opz/ai/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: outboundMessages }),
        });
        if (!out.ok) {
          throw new Error(out.stderr || out.stdout || "AI chat failed");
        }
        const reply = (out.reply || out.stdout || "").trim() || "(nessuna risposta)";
        const returned = Array.isArray(out.messages) ? out.messages.filter((m) => m.role === "user" || m.role === "assistant") : [];
        setAiMessages(returned.length > 0 ? returned : [...outboundMessages, { role: "assistant", content: reply }]);
        setAiPrompt("");
        setMessage(`AI risposta pronta (${out.model}, ${out.duration_ms}ms).`);
        return;
      } catch {
        const outLegacy = await apiJson<AiPromptLegacyResponse>(`${API_BASE}/opz/ai/prompt`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt }),
        });
        if (!outLegacy.ok) {
          throw new Error(outLegacy.stderr || outLegacy.stdout || "AI prompt failed");
        }
        const replyLegacy = (outLegacy.response || outLegacy.stdout || "").trim() || "(nessuna risposta)";
        setAiMessages([...outboundMessages, { role: "assistant", content: replyLegacy }]);
        setAiPrompt("");
        setMessage(`AI risposta pronta (${outLegacy.model}, ${outLegacy.duration_ms}ms).`);
      }
    } catch (e) {
      setError(String(e));
      setMessage("");
    } finally {
      setAiBusy(false);
    }
  }
  async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
    const res = await fetch(url, init);
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`${res.status} ${res.statusText} ${body}`.trim());
    }
    return res.json() as Promise<T>;
  }

  function provenanceQuery(overrides?: { batchId?: string | null; settingsPath?: string; regime?: string }): string {
    const qp = new URLSearchParams();
    const batchId = overrides?.batchId ?? universeLatest?.batch_id ?? null;
    const settingsPath = (overrides?.settingsPath ?? universeLatest?.ibkr_settings_path ?? universeSettingsPath).trim();
    const regime = overrides?.regime ?? universeRegime;
    if (batchId) qp.set("batch_id", batchId);
    if (settingsPath) qp.set("settings_path", settingsPath);
    qp.set("regime", regime);
    const q = qp.toString();
    return q ? `?${q}` : "";
  }

  async function refreshUniverseProvenance(overrides?: { batchId?: string | null; settingsPath?: string; regime?: string }): Promise<void> {
    const out = await apiJson<UniverseProvenanceResponse>(`${API_BASE}/opz/universe/provenance${provenanceQuery(overrides)}`);
    setUniverseProvenance(out);
  }

  async function doAutoDemoPipeline(silent = false) {
    const parsedTop = parseIntInput(universeTopN, "Top N");
    const topN = parsedTop.ok ? Math.max(1, Math.min(50, parsedTop.value)) : 8;
    if (!silent) {
      setBusy(true);
      setError("");
      setMessage("AUTO PIPELINE: acquisizione IBKR + estrazione + dataset + scan...");
    }
    try {
      const symbols = universeSymbols
        .split(/[\s,;]+/)
        .map((x) => x.trim().toUpperCase())
        .filter((x) => x.length > 0);
      const out = await apiJson<DemoPipelineAutoResponse>(`${API_BASE}/opz/demo_pipeline/auto`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: "paper",
          symbols: symbols.length > 0 ? symbols : undefined,
          settings_path: universeSettingsPath.trim() || undefined,
          fetch_limit: Math.max(8, Math.min(40, symbols.length || 12)),
          top_n: topN,
          regime: universeRegime,
          extract_backend: "json-pass",
          auto_scan: true,
        }),
      });
      if (out.scan) {
        setUniverseLatest({ ...out.scan, has_data: true });
      }
      await refreshUniverseProvenance({
        batchId: out.scan?.batch_id ?? null,
        settingsPath: out.ibkr_settings_path || universeSettingsPath,
        regime: universeRegime,
      }).catch(() => undefined);
      const fetched = out.fetch?.captured ?? 0;
      const extracted = out.extract?.valid ?? 0;
      const ds = out.dataset?.records ?? 0;
      setMessage(`AUTO PIPELINE OK: fetch=${fetched}, extract_valid=${extracted}, dataset_records=${ds}.`);
    } catch (e) {
      setError(String(e));
      setMessage("");
    } finally {
      if (!silent) setBusy(false);
    }
  }

    async function refreshAll() {
    setBusy(true);
    setError("");
    try {
      const ctxQuery = universeSettingsPath.trim()
        ? `?settings_path=${encodeURIComponent(universeSettingsPath.trim())}`
        : "";
      // Promise.allSettled: un endpoint lento/down non blocca gli altri
      const settled = await Promise.allSettled([
        apiJson<unknown>(`${API_BASE}/opz/state`),
        apiJson<ReleaseStatusResponse>(`${API_BASE}/opz/release_status`),
        apiJson<PaperSummaryResponse>(`${API_BASE}/opz/paper/summary?profile=${ACTIVE_PROFILE}&window_days=60`),
        apiJson<LastActionsResponse>(`${API_BASE}/opz/last_actions?limit=8`),
        apiJson<UniverseLatestResponse>(`${API_BASE}/opz/universe/latest`),
        apiJson<UniverseIbkrContext>(`${API_BASE}/opz/universe/ibkr_context${ctxQuery}`),
        apiJson<NarratorTutorialResponse>(`${API_BASE}/opz/narrator/tutorial`),
      ]);
      const ok = <T,>(r: PromiseSettledResult<T>): T | null =>
        r.status === "fulfilled" ? r.value : null;
      const [s, rs, ps, la, ul, ic, nt] = settled.map(ok) as [
        unknown, ReleaseStatusResponse | null, PaperSummaryResponse | null,
        LastActionsResponse | null, UniverseLatestResponse | null,
        UniverseIbkrContext | null, NarratorTutorialResponse | null,
      ];
      const up = await apiJson<UniverseProvenanceResponse>(
        `${API_BASE}/opz/universe/provenance${provenanceQuery({
          batchId: ul?.batch_id ?? null,
          settingsPath: ul?.ibkr_settings_path || universeSettingsPath,
          regime: ul?.regime ?? universeRegime,
        })}`
      ).catch(() => null);
      if (s !== null) setStateJson(s);
      if (rs !== null) setReleaseMd(rs.content || "");
      if (ps !== null) setPaperSummary(ps);
      if (la !== null) setLastActions(la);
      if (ul !== null) setUniverseLatest(ul);
      if (ic !== null) setIbkrContext(ic);
      if (nt !== null) setNarratorTutorial(nt);
      setUniverseProvenance(up);
      void doFetchEquityHistory();
      void doFetchSysStatus();
      void doFetchRegimeCurrent();
      void doFetchExitCandidates();
      void doFetchActivityStream();
      void doFetchSysLog();
      void doFetchWheelPositions();
      void doFetchTier();
      void doFetchBriefingList();
      void doFetchControlStatus();
      void doFetchLifecycle();
      if (!universeScannerName && ic?.scanners && ic.scanners.length > 0) {
        setUniverseScannerName(ic.scanners[0].scanner_name);
      }
      if (!universeSymbols.trim() && ic?.symbols && ic.symbols.length > 0) {
        setUniverseSymbols(ic.symbols.slice(0, 40).join(","));
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doPreview() {
    const s = symbol.trim();
    const st = strategy.trim();
    if (!s || !st) {
      setError("Symbol e Strategy sono obbligatori.");
      setMessage("");
      return;
    }
    if (!parsedPayload) {
      setError("Payload JSON non valido o non-oggetto.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = { symbol: s, strategy: st, payload: parsedPayload };
      const j = await apiJson<PreviewResponse>(`${API_BASE}/opz/execution/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setPreview(j);
      setPreviewSignature(executionSignature);
      setMessage("Preview created.");
      await refreshAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doConfirm() {
    if (!preview) return;
    if (!executionSignature || !previewSignature || previewSignature !== executionSignature) {
      setError("Payload/symbol/strategy changed after preview. Create a new Preview before Confirm.");
      setMessage("");
      return;
    }

    // Double-click protection: first click arms, second click sends
    if (!confirmArmed) {
      setConfirmArmed(true);
      setMessage("Clicca CONFIRM di nuovo per inviare l'ordine.");
      if (confirmArmTimerRef.current) clearTimeout(confirmArmTimerRef.current);
      confirmArmTimerRef.current = setTimeout(() => {
        setConfirmArmed(false);
        setMessage("");
      }, 5000);
      return;
    }

    // Second click — disarm and proceed
    setConfirmArmed(false);
    if (confirmArmTimerRef.current) { clearTimeout(confirmArmTimerRef.current); confirmArmTimerRef.current = null; }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = {
        confirm_token: preview.confirm_token,
        operator: "operator",
        decision: confirmDecision,
        payload: { symbol: symbol.trim(), strategy: strategy.trim(), payload: parsedPayload },
      };
      const confirmResult = await apiJson<{ ok: boolean; trade_id?: string }>(`${API_BASE}/opz/execution/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      // If operator selected a scan candidate, mark it as EXECUTED
      if (selectedItemId && confirmDecision === "APPROVE") {
        const tradeId = confirmResult?.trade_id ?? undefined;
        void apiJson(`${API_BASE}/opz/universe/scan_item/${selectedItemId}/status`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "EXECUTED", trade_id: tradeId ?? null }),
        }).catch(() => {/* non-critical */});
        setSelectedItemId(null);
      }
      setMessage("Confirm sent.");
      setPreview(null);
      setPreviewSignature(null);
      await refreshAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

    async function doUniverseScan() {
    const parsedTop = parseIntInput(universeTopN, "Top N");
    if (!parsedTop.ok || parsedTop.value < 1 || parsedTop.value > 50) {
      setError("Top N deve essere un intero tra 1 e 50.");
      setMessage("");
      return;
    }

    const symbols = universeSymbols
      .split(/[\s,;]+/)
      .map((x) => x.trim().toUpperCase())
      .filter((x) => x.length > 0);

    if (universeSource === "manual" && symbols.length === 0) {
      setError("In source=manual devi indicare almeno un symbol.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body: Record<string, unknown> = {
        profile: "paper",
        regime: universeRegime,
        top_n: parsedTop.value,
        source: universeSource,
      };
      if (universeSource === "manual") {
        body.symbols = symbols;
      }
      if (universeScannerName.trim()) {
        body.scanner_name = universeScannerName.trim();
      }
      if (universeSettingsPath.trim()) {
        body.settings_path = universeSettingsPath.trim();
      }

      const out = await apiJson<UniverseLatestResponse>(`${API_BASE}/opz/universe/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setUniverseLatest({ ...out, has_data: true });
      await refreshUniverseProvenance({
        batchId: out.batch_id ?? null,
        settingsPath: universeSettingsPath,
        regime: out.regime ?? universeRegime,
      }).catch(() => undefined);
      const rows = out.market_rows_available ?? 0;
      setMessage(`Universe scan complete: shortlist=${out.items.length}, market_rows=${rows}.`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }




  async function doScanFull() {
    const syms = oppScanSymbols.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
    if (!syms.length) { setError("Inserisci almeno un simbolo per lo scan."); setMessage(""); return; }
    const topN = parseInt(oppScanTopN) || 5;
    const acct = parseFloat(oppScanAccountSize);
    if (!Number.isFinite(acct) || acct <= 0) { setError("Account size non valido."); setMessage(""); return; }
    setOppScanBusy(true); setError(""); setMessage("");
    try {
      const res = await apiJson<ScanFullResponse>(`${API_BASE}/opz/opportunity/scan_full`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: "paper", regime: oppScanRegime, symbols: syms, top_n: topN, account_size: acct, use_cache: true }),
      });
      setOppScanResult(res);
      if (res.candidates.length > 0) setSelectedScanKey(`${res.candidates[0].symbol}::${res.candidates[0].strategy}::${res.candidates[0].expiry}`);
      setMessage(res.ranking_suspended
        ? `Scan sospeso: ${res.suspension_reason ?? "regime SHOCK"}.`
        : `Scan OK — ${res.candidates.length} candidati (batch ${res.batch_id}).`);
    } catch (e) { setError(String(e)); setMessage(""); }
    finally { setOppScanBusy(false); }
  }

  async function doLoadEvReport() {
    try {
      const r = await apiJson<EvReportResponse>(`${API_BASE}/opz/opportunity/ev_report?profile=${ACTIVE_PROFILE}&window_days=30`);
      setEvReport(r);
      setMessage(`EV report caricato: ${r.total_candidates} candidati (30gg).`);
    } catch (e) { setError(String(e)); }
  }

  async function doCheckIbkr(tryConnect = false) {
    setIbkrChecking(true);
    try {
      let r = await apiJson<IbkrStatusResponse>(
        `${API_BASE}/opz/ibkr/status?try_connect=${tryConnect}`
      );
      // Auto-recovery: se il poll passivo vede disconnected, tenta una reconnessione.
      if (!r.connected && !tryConnect) {
        r = await apiJson<IbkrStatusResponse>(
          `${API_BASE}/opz/ibkr/status?try_connect=true`
        );
      }
      setIbkrStatus(r);
      setMessage(r.message);
      // Aggiorna account solo se connesso
      if (r.connected) void doFetchIbkrAccount();
    } catch (e) { setError(String(e)); }
    finally { setIbkrChecking(false); }
  }

  function _agoLabel(fetchedAt: number | null): string {
    if (fetchedAt === null) return "—";
    const s = Math.round((Date.now() - fetchedAt) / 1000);
    if (s < 60) return `${s}s fa`;
    return `${Math.floor(s / 60)}m${s % 60}s fa`;
  }

  async function doFetchIbkrAccount() {
    setIbkrAccountLoading(true);
    try {
      const r = await apiJson<IbkrAccountResponse>(`${API_BASE}/opz/ibkr/account`);
      setIbkrAccount(r);
      setIbkrAccountFetchedAt(Date.now());
    } catch (e) { /* silenzioso: account non critico */ }
    finally { setIbkrAccountLoading(false); }
  }

  async function doFetchStorico() {
    setStoricoLoading(true);
    try {
      const [actData, sumData] = await Promise.all([
        apiJson<any>(`${API_BASE}/opz/last-actions?limit=500`),
        apiJson<any>(`${API_BASE}/opz/paper/summary?profile=paper&window_days=365`),
      ]);
      setStoricoTrades(actData.paper_trades ?? []);
      setStoricoSummary(sumData);
    } catch (e) { /* silenzioso */ }
    finally { setStoricoLoading(false); }
  }

  async function doFetchLifecycle() {
    setLifecycleLoading(true);
    try {
      const data = await apiJson<SignalLifecycleResponse>(`${API_BASE}/opz/signals/lifecycle?profile=paper&lookback=5`);
      setSignalLifecycle(data);
    } catch (e) { /* silenzioso */ }
    finally { setLifecycleLoading(false); }
  }

  function clearFetchErr(key: string) {
    setFetchErrors(prev => { const s = new Set(prev); s.delete(key); return s; });
  }
  function markFetchErr(key: string) {
    setFetchErrors(prev => new Set(prev).add(key));
  }

  async function doFetchSysStatus() {
    try {
      const r = await apiJson<SystemStatusResponse>(`${API_BASE}/opz/system/status`);
      setSysStatus(r);
      setSysStatusFetchedAt(Date.now());
      clearFetchErr("sysStatus");
    } catch (e) { markFetchErr("sysStatus"); }
  }

  async function doFetchRegimeCurrent() {
    try {
      const r = await apiJson<RegimeCurrentResponse>(`${API_BASE}/opz/regime/current?window=30`);
      setRegimeCurrent(r);
      clearFetchErr("regime");
    } catch (e) { markFetchErr("regime"); }
  }

  async function doFetchEquityHistory() {
    try {
      const url = `${API_BASE}/opz/paper/equity_history?profile=${ACTIVE_PROFILE}&limit=60`;
      const r = await apiJson<EquityHistoryResponse>(url);
      setEquityHistory(r);
      clearFetchErr("equity");
    } catch (e) { markFetchErr("equity"); }
  }


  async function doFetchExitCandidates() {
    try {
      const r = await apiJson<ExitCandidatesResponse>(`${API_BASE}/opz/opportunity/exit_candidates?min_score=1&top_n=5`);
      setExitCandidates(r);
      setExitCandidatesFetchedAt(Date.now());
      clearFetchErr("exitCandidates");
    } catch (e) { markFetchErr("exitCandidates"); }
  }

  async function doFetchActivityStream() {
    try {
      const r = await apiJson<ActivityStreamResponse>(`${API_BASE}/opz/activity/stream?n=30`);
      setActivityStream(r);
    } catch { /* non critico */ }
  }

  async function doFetchSysLog() {
    try {
      const r = await apiJson<SysLogResponse>(`${API_BASE}/opz/system/log?n=150`);
      setSysLog(r.records ?? []);
      // auto-scroll al fondo
      setTimeout(() => {
        if (sysLogRef.current) sysLogRef.current.scrollTop = sysLogRef.current.scrollHeight;
      }, 50);
    } catch { /* non critico */ }
  }

  async function doFetchSessionStatus() {
    try {
      const r = await apiJson<typeof sessionStatus>(`${API_BASE}/opz/session/status`);
      setSessionStatus(r);
    } catch { /* non critico */ }
  }

  async function doFetchSessionLogs() {
    try {
      const r = await apiJson<{ logs: SessionLogEntry[] }>(`${API_BASE}/opz/session/logs?profile=${ACTIVE_PROFILE}&limit=60`);
      setSessionLogs(r.logs ?? []);
    } catch { /* non critico */ }
  }

  async function doFetchControlStatus() {
    try {
      const r = await apiJson<ControlStatusResponse>(`${API_BASE}/opz/control/status`);
      setControlStatus(r);
      clearFetchErr("controlStatus");
    } catch {
      markFetchErr("controlStatus");
    }
  }

  async function doIbwrService(action: "status" | "on" | "off") {
    setIbwrBusy(true);
    try {
      const r = await apiJson<IbwrServiceResponse>(`${API_BASE}/opz/ibwr/service`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, notify_telegram: false, source: "operator_ui" }),
      });
      setMessage(r.message || `IBWR ${action.toUpperCase()} -> ${r.service_state}`);
      await doFetchControlStatus();
    } catch (e) {
      setError(String(e));
      setMessage("");
    } finally {
      setIbwrBusy(false);
    }
  }

  async function doRunSession(type: "morning" | "eod") {
    try {
      await apiJson(`${API_BASE}/opz/session/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, profile: ACTIVE_PROFILE }),
      });
      void doFetchSessionStatus();
    } catch { /* non critico */ }
  }

  async function doFetchWheelPositions() {
    try {
      const r = await apiJson<WheelPositionsResponse>(`${API_BASE}/opz/wheel/positions?profile=${ACTIVE_PROFILE}`);
      setWheelPositions(r);
      setWheelFetchedAt(Date.now());
      clearFetchErr("wheel");
    } catch (e) { markFetchErr("wheel"); }
  }

  async function doFetchTier(currentRegime?: string) {
    const reg = currentRegime ?? regimeCurrent?.regime ?? "NORMAL";
    try {
      const r = await apiJson<TierResponse>(`${API_BASE}/opz/tier?profile=${ACTIVE_PROFILE}&regime=${reg}`);
      setTierInfo(r);
      clearFetchErr("tier");
    } catch (e) { markFetchErr("tier"); }
  }

  async function doFetchBriefingList() {
    try {
      const list = await apiJson<string[]>(`${API_BASE}/opz/briefing/list`);
      setBriefingList(list);
      setBriefingListIdx(0);
    } catch {
      setBriefingList([]);
      setBriefingListIdx(0);
    }
  }

  async function doBriefingGenerate() {
    setBriefingBusy(true);
    setMessage("Generazione briefing in corso... (30-60s)");
    try {
      const r = await apiJson<{ ok: boolean; stderr?: string }>(`${API_BASE}/opz/briefing/generate`, { method: "POST" });
      if (r.ok) {
        setMessage("Briefing generato.");
        await doFetchBriefingList();
        if (briefingAutoOpen) setAiDrawerOpen(true);
        if (briefingAutoPlay && briefingAudioRef.current) {
          briefingAudioRef.current.src = `${API_BASE}/opz/briefing/latest`;
          briefingAudioRef.current.load();
          void briefingAudioRef.current.play();
        }
      } else {
        setError(`Briefing fallito: ${r.stderr ?? "errore sconosciuto"}`);
      }
    } catch (e) { setError(String(e)); }
    finally { setBriefingBusy(false); }
  }

  const briefingSelected = briefingList[briefingListIdx];
  const briefingAudioSrc = briefingSelected
    ? `${API_BASE}/opz/briefing/file/${encodeURIComponent(briefingSelected)}`
    : `${API_BASE}/opz/briefing/latest`;

  const briefingLabel = (() => {
    const name = briefingList[briefingListIdx] ?? "";
    const m = name.match(/briefing_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/);
    if (!m) return "Ultimo briefing";
    return `${m[3]}/${m[2]}/${m[1]}  ${m[4]}:${m[5]}`;
  })();

  function doBriefingPlay() {
    const el = briefingAudioRef.current;
    if (!el) return;
    if (briefingList.length === 0) {
      setError("Nessun briefing disponibile. Premi GENERA.");
      return;
    }
    el.src = briefingAudioSrc;
    el.load();
    void el.play().catch((err) => {
      setError(`Play briefing fallito: ${String(err)}`);
    });
  }

  function doBriefingStop() {
    const el = briefingAudioRef.current;
    if (!el) return;
    el.pause();
    el.currentTime = 0;
    setBriefingPlaying(false);
  }

  function doBriefingPrev() {
    setBriefingListIdx(i => Math.min(i + 1, Math.max(0, briefingList.length - 1)));
    setBriefingPlaying(false);
  }

  function doBriefingNext() {
    setBriefingListIdx(i => Math.max(i - 1, 0));
    setBriefingPlaying(false);
  }

  async function doKillSwitch() {
    const ksActive = sysStatus?.kill_switch_active ?? false;
    const action = ksActive ? "deactivate" : "activate";
    const msg = ksActive
      ? "DISATTIVARE il Kill Switch?\nL'esecuzione ordini verrà ri-abilitata."
      : "ATTIVARE il Kill Switch?\nTutti gli ordini saranno BLOCCATI immediatamente.";
    if (!window.confirm(msg)) return;
    setBusy(true);
    setError("");
    try {
      await apiJson(`${API_BASE}/opz/execution/kill_switch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      setMessage(ksActive ? "Kill switch disattivato." : "🛑 KILL SWITCH ATTIVATO — esecuzione bloccata.");
      await doFetchSysStatus();
    } catch (e) {
      setError(`Kill switch fallito: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  const goGate = paperSummary?.gates.go_nogo;
  const f6Gate = paperSummary?.gates.f6_t1_acceptance;
  const f6t2Gate = paperSummary?.gates.f6_t2_journal_complete;
  const historyReadiness = sysStatus?.history_readiness ?? null;
  const historyEtaLabel = useMemo(() => {
    if (!historyReadiness) return "n/d";
    if (historyReadiness.ready) return "Pronto ora";
    if (historyReadiness.eta_days === null) return "ETA non stimabile";
    if (historyReadiness.eta_days === 0) return "Pronto oggi";
    return `${historyReadiness.eta_days}g (stima)`;
  }, [historyReadiness]);
  const historyStatusClass = historyReadiness?.ready
    ? "history-ready"
    : (historyReadiness?.score_pct ?? 0) >= 70
      ? "history-building"
      : "history-critical";
  const stateObj = stateJson && typeof stateJson === "object" ? (stateJson as Record<string, unknown>) : null;
  const nextStep = typeof stateObj?.next_step === "string" ? stateObj.next_step : "-";
  const progressObj = stateObj?.progress && typeof stateObj.progress === "object" ? (stateObj.progress as Record<string, unknown>) : null;
  const plannerComplete = nextStep === "COMPLETE";
  const phaseProgress = plannerComplete
    ? { f1: 100, f2: 100, f3: 100, f4: 100 }
    : { f1: 100, f2: 85, f3: 40, f4: 0 };
  const blockedCount = Array.isArray(progressObj?.blocked_steps) ? progressObj.blocked_steps.length : 0;
  const universeItems = universeLatest?.items ?? [];
  const ibkrScanners = ibkrContext?.scanners ?? [];
  const selectedScanner = ibkrScanners.find((x) => x.scanner_name === universeScannerName) ?? ibkrScanners[0] ?? null;
  const selectedScannerFilters = selectedScanner ? Object.entries(selectedScanner.filters ?? {}) : [];
  const provenanceRows = universeProvenance?.rows ?? [];

  const fallbackRows = (symbols: string[], tab: UniverseSubTab): UniverseProvenanceRow[] =>
    symbols.map((symbol) => ({
      tab,
      symbol,
      source: "api",
      field_sources: {},
      last: null,
      bid: null,
      ask: null,
      vs_pct: null,
      vi_pct: null,
      delta: null,
    }));

  const rowsByTab = {
    titoli: provenanceRows.filter((r) => r.tab === "titoli"),
    indici: provenanceRows.filter((r) => r.tab === "indici"),
    opzioni: provenanceRows.filter((r) => r.tab === "opzioni"),
    ciclo: provenanceRows.filter((r) => r.tab === "ciclo"),
    palinsesto: provenanceRows.filter((r) => r.tab === "palinsesto"),
  };const sourceRank: Record<UniverseRowSource, number> = { none: 0, api: 1, ocr: 2, mixed: 3 };
  const rowSourceBySymbol = new Map<string, UniverseRowSource>();
  for (const row of provenanceRows) {
    const sym = row.symbol.toUpperCase();
    const cur = rowSourceBySymbol.get(sym) ?? "none";
    if (sourceRank[row.source] > sourceRank[cur]) rowSourceBySymbol.set(sym, row.source);
  }

  const opzioniRows = universeItems;
  const opportunityReady = universeItems.filter((x) => x.score >= 0.55).length;
  const scanCandidates: ScanFullCandidate[] = oppScanResult?.candidates ?? [];
  const premarketUsesScanFull = scanCandidates.length > 0;
  const premarketShortlistCount = premarketUsesScanFull ? scanCandidates.length : universeItems.length;
  const premarketReadyCount = premarketUsesScanFull
    ? scanCandidates.filter((c) => c.score >= 75).length
    : universeItems.filter((x) => x.score >= 0.55).length;
  const premarketTopScorePct = premarketUsesScanFull
    ? (scanCandidates[0]?.score ?? null)
    : (universeItems[0] ? (universeItems[0].score * 100) : null);
  const premarketRegime = regimeCurrent?.regime ?? universeLatest?.regime ?? "UNKNOWN";
  const premarketScanAt = oppScanResult?.scan_ts ?? regimeCurrent?.last_scan_ts ?? universeLatest?.created_at_utc ?? null;
  const premarketSource = premarketUsesScanFull ? "scan_full" : (universeLatest?.source ?? "universe_latest");
  const pipelineRecords = universeLatest?.market_rows_available ?? 0;
  const pipelineBatch = universeLatest?.batch_id ?? "N/D";
  const pipelineLatencyState = fetchErrors.size > 0 ? "STALE" : "FRESH";
  const pipelineReadinessLine = historyReadiness
    ? `${historyReadiness.days_observed}/${historyReadiness.target_days} giorni · ${(historyReadiness.quality_completeness * 100).toFixed(1)}% qualita`
    : "N/D";
  const premarketRows = premarketUsesScanFull
    ? scanCandidates.map((c, i) => ({
      rank: i + 1,
      symbol: c.symbol,
      strategy: c.strategy,
      scorePct: c.score,
      spreadPct: c.spread_pct * 100,
      ivRankPct: null as number | null,
      source: c.source ?? premarketSource,
    }))
    : universeItems.map((u) => ({
      rank: u.rank,
      symbol: u.symbol,
      strategy: u.strategy,
      scorePct: u.score * 100,
      spreadPct: u.spread_pct * 100,
      ivRankPct: u.iv_rank * 100,
      source: premarketSource,
    }));
  const premarketPrimary =
    scanCandidates.find((c) => `${c.symbol}::${c.strategy}::${c.expiry}` === selectedScanKey) ?? scanCandidates[0] ?? null;
  const premarketUniversePrimary = universeItems[0] ?? null;
  const toTen = (value: number | null | undefined): number | null => {
    if (value === null || value === undefined || !Number.isFinite(value)) return null;
    const v = Number(value);
    if (v <= 1) return Math.max(0, Math.min(10, v * 10));
    if (v <= 10) return Math.max(0, Math.min(10, v));
    if (v <= 100) return Math.max(0, Math.min(10, v / 10));
    return 10;
  };
  const clampTen = (value: number): number => Math.max(0, Math.min(10, value));
  const preP1 = premarketPrimary
    ? toTen(premarketPrimary.score_breakdown.vol_edge)
    : premarketUniversePrimary
      ? toTen(premarketUniversePrimary.iv_rank)
      : null;
  const preP2 = premarketPrimary
    ? toTen(premarketPrimary.score_breakdown.liquidity)
    : premarketUniversePrimary
      ? clampTen(10 - (premarketUniversePrimary.spread_pct * 100))
      : null;
  const preP3 = premarketPrimary
    ? toTen(premarketPrimary.score_breakdown.risk_reward)
    : premarketUniversePrimary
      ? toTen(premarketUniversePrimary.score)
      : null;
  const preP4 = premarketPrimary
    ? toTen(premarketPrimary.score_breakdown.regime_align)
    : premarketUniversePrimary
      ? toTen(premarketUniversePrimary.regime_fit)
      : null;
  const preFinal = premarketPrimary
    ? toTen(premarketPrimary.score)
    : premarketUniversePrimary
      ? toTen(premarketUniversePrimary.score)
      : null;
  const selectedScanCandidate: ScanFullCandidate | null =
    scanCandidates.find((c) => `${c.symbol}::${c.strategy}::${c.expiry}` === selectedScanKey) ?? scanCandidates[0] ?? null;
  const nonOptionsRows = universeSubTab === "opzioni" ? [] : rowsByTab[universeSubTab as Exclude<UniverseSubTab, "opzioni">];
  const sourceBadgeClass = (source: UniverseRowSource): string => (
    source === "mixed" ? "source-mixed" : source === "ocr" ? "source-ocr" : source === "api" ? "source-api" : "source-none"
  );
  const fieldClass = (source: UniverseFieldSource | undefined): string => (
    source === "ocr" ? "field-ocr" : source === "api" ? "field-api" : ""
  );

  const apiOnline = Boolean(!error && stateJson && paperSummary);
  const hasPaperData = Boolean((paperSummary?.equity_points ?? 0) > 0 || (paperSummary?.trades ?? 0) > 0);
  const executionConfigReady = Boolean(symbol.trim() && strategy.trim() && parsedPayload && !payloadJsonError);

  const regimeView = useMemo(() => {
    if (!apiOnline) return { cls: "regime-shock", text: "OFFLINE" };
    // Fonte autorevole: regime corrente da /opz/regime/current
    const live = regimeCurrent?.regime;
    if (live === "NORMAL")  return { cls: "regime-normal",  text: "NORMAL" };
    if (live === "CAUTION") return { cls: "regime-caution", text: "CAUTION" };
    if (live === "SHOCK")   return { cls: "regime-shock",   text: "SHOCK" };
    // Fallback: nessun dato regime ancora disponibile
    if (hasPaperData) return { cls: "regime-caution", text: "CAUTION" };
    return { cls: "regime-offline", text: "UNKNOWN" };
  }, [apiOnline, regimeCurrent?.regime, hasPaperData]);

  const kellyHalf = useMemo(() => {
    const p = paperSummary?.win_rate;
    const b = paperSummary?.profit_factor;
    if (p === null || p === undefined || b === null || b === undefined || b <= 0) return null;
    const full = p - (1 - p) / b;
    return Math.max(0, Math.min(0.25, full / 2));
  }, [paperSummary?.win_rate, paperSummary?.profit_factor]);

  const signalToHealth = (status: SystemSignal["status"]): UiHealth => {
    if (status === "OK") return "ok";
    if (status === "WARN") return "warn";
    if (status === "ALERT") return "alert";
    return "neutral";
  };
  const maxHealth = (...vals: UiHealth[]): UiHealth => {
    if (vals.includes("alert")) return "alert";
    if (vals.includes("warn")) return "warn";
    if (vals.includes("ok")) return "ok";
    return "neutral";
  };

  const dataModeUpper = String(sysStatus?.data_mode ?? "").toUpperCase();
  const hasRealData = apiOnline && !dataModeUpper.includes("SYNTH");
  const feedStale = fetchErrors.size > 0;
  const yfinanceHealth: UiHealth = !apiOnline ? "neutral" : feedStale ? "warn" : dataModeUpper.includes("SYNTH") ? "neutral" : "ok";
  const yfinanceLabel = !apiOnline ? "N/D" : feedStale ? "STALE" : dataModeUpper.includes("SYNTH") ? "SYNTH" : "OK";
  const fredHealth: UiHealth = !apiOnline ? "neutral" : fetchErrors.has("regime") ? "warn" : "ok";
  const fredLabel = !apiOnline ? "N/D" : fetchErrors.has("regime") ? "STALE" : "OK";
  const oratsHealth: UiHealth = "neutral";
  const oratsLabel = "N/D";
  const pipelineFeedHealth = !apiOnline ? "neutral" : maxHealth(yfinanceHealth, fredHealth);
  const pipelineFeedLabel = !apiOnline ? "N/D" : pipelineFeedHealth === "ok" ? "OK" : pipelineFeedHealth === "warn" ? "WARN" : pipelineFeedHealth === "alert" ? "ALERT" : "N/D";

  const ddValue = paperSummary?.max_drawdown;
  const ddHealth: UiHealth = !apiOnline ? "neutral" : ddValue == null ? "neutral" : ddValue >= 0.15 ? "alert" : ddValue >= 0.10 ? "warn" : "ok";
  const ddLabel = !apiOnline ? "N/D" : ddValue == null ? "N/D" : `${(ddValue * 100).toFixed(1)}%`;
  const varSignal = (sysStatus?.signals ?? []).find((s) => /var|cvar/i.test(s.name));
  const varHealth: UiHealth = !apiOnline ? "neutral" : varSignal ? signalToHealth(varSignal.status) : "neutral";
  const varLabel = !apiOnline ? "N/D" : varSignal ? varSignal.status : "N/D";
  const tailHedgeOn = Boolean(tierInfo?.features?.hedge_active);
  const tailHedgeHealth: UiHealth = !apiOnline ? "neutral" : tailHedgeOn ? "ok" : "neutral";
  const tailHedgeLabel = !apiOnline ? "N/D" : tailHedgeOn ? "ON" : "OFF";

  const dataQtyPct = historyReadiness
    ? Math.min(
      100,
      Math.round(
        50 * (historyReadiness.days_observed / Math.max(1, historyReadiness.target_days)) +
        50 * (historyReadiness.events_observed / Math.max(1, historyReadiness.target_events))
      )
    )
    : null;
  const dataQualityPct = historyReadiness ? Math.round(historyReadiness.quality_completeness * 100) : null;
  const localRecords = (paperSummary?.equity_points ?? 0) + (paperSummary?.trades ?? 0);
  const localDbHealth: UiHealth = !apiOnline ? "neutral" : localRecords > 0 ? "ok" : "neutral";
  const ingestHealth: UiHealth = !apiOnline ? "neutral" : fetchErrors.size > 0 ? "warn" : "ok";
  const ingestLabel = !apiOnline ? "N/D" : fetchErrors.size > 0 ? `${fetchErrors.size} err` : "OK";
  const qtyHealth: UiHealth = !apiOnline ? "neutral" : dataQtyPct === null ? "neutral" : dataQtyPct >= 80 ? "ok" : dataQtyPct >= 50 ? "warn" : "alert";
  const qualityHealth: UiHealth = !apiOnline ? "neutral" : dataQualityPct === null ? "neutral" : dataQualityPct >= 95 ? "ok" : dataQualityPct >= 80 ? "warn" : "alert";
  const dataHealthOverall: UiHealth = !apiOnline ? "neutral" : maxHealth(qtyHealth, qualityHealth, ingestHealth);
  const dataHealthLabel = !apiOnline ? "N/D" : dataHealthOverall === "ok" ? "OK" : dataHealthOverall === "warn" ? "WARN" : dataHealthOverall === "alert" ? "ALERT" : "N/D";
  const pipelineCriticality = !apiOnline ? null : fetchErrors.size + (historyReadiness?.blockers.length ?? 0);
  const pipelineCriticalityHealth: UiHealth = !apiOnline ? "neutral" : (pipelineCriticality ?? 0) > 2 ? "alert" : (pipelineCriticality ?? 0) > 0 ? "warn" : "ok";
  const pipelineStateHealth: UiHealth = !apiOnline ? "neutral" : maxHealth(ingestHealth, pipelineCriticalityHealth, (regimeCurrent?.n_recent ?? 0) > 0 ? "ok" : "warn");
  const pipelineStateLabel = !apiOnline ? "N/D" : pipelineStateHealth === "ok" ? "STABLE" : pipelineStateHealth === "warn" ? "DEGRADED" : "CRITICAL";
  const significanceScore = !apiOnline
    ? null
    : Math.round(
      0.4 * Math.min(100, localRecords * 2) +
      0.3 * (dataQtyPct ?? 0) +
      0.3 * (dataQualityPct ?? 0)
    );
  const significanceHealth: UiHealth = !apiOnline ? "neutral" : significanceScore === null ? "neutral" : significanceScore >= 80 ? "ok" : significanceScore >= 50 ? "warn" : "alert";
  const significanceLabel = !apiOnline
    ? "N/D"
    : significanceScore === null
      ? "N/D"
      : significanceScore >= 80
        ? `HIGH ${significanceScore}%`
        : significanceScore >= 50
          ? `MED ${significanceScore}%`
          : `LOW ${significanceScore}%`;
  const ibwrState = String(controlStatus?.ibwr?.service_state ?? "N/D").toUpperCase();
  const ibwrHealth: UiHealth = !apiOnline ? "neutral" : ibwrState === "ON" ? "ok" : ibwrState === "OFF" ? "warn" : "neutral";
  const stepDataHealth: UiHealth = !apiOnline
    ? "neutral"
    : !hasRealData
      ? "warn"
      : maxHealth(pipelineStateHealth, dataHealthOverall);
  const stepDataStatusLabel = !apiOnline
    ? "OFFLINE"
    : !hasRealData
      ? "SYNTH"
      : stepDataHealth === "ok"
        ? "OK"
        : stepDataHealth === "warn"
          ? "WARN"
          : "ALERT";
  const stepDataSummary = `pipeline ${pipelineStateLabel} · rec ${pipelineRecords.toLocaleString("it-IT")} · mode ${dataModeUpper || "N/D"} · readiness ${pipelineReadinessLine}`;
  const stepDataHint = !apiOnline
    ? "API offline: feed non raggiungibile"
    : !hasRealData
      ? "Data mode sintetico: blocco in monitoraggio"
      : "Feed reale attivo: blocco operativo";

  useEffect(() => {
    if (!message && !error) return;
    const timeout = error ? 30000 : 10000; // errori visibili 30s, info 10s
    const id = window.setTimeout(() => {
      setMessage("");
      setError("");
    }, timeout);
    return () => window.clearTimeout(id);
  }, [message, error]);

  useEffect(() => {
    const init = async () => {
      await refreshAll();
    };
    void init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const tick = () => {
      const t = new Date().toLocaleString("sv-SE", { hour12: false, timeZone: "America/New_York" }).replace("T", " ");
      setClockText(`${t} EST`);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  // On mount: connessione IBKR + fetch iniziale di tutti i dati
  useEffect(() => {
    void doCheckIbkr(true);
    void doFetchIbkrAccount();
    void doFetchSysStatus();
    void doFetchRegimeCurrent();
    void doFetchEquityHistory();
    void doFetchExitCandidates();
    void doFetchActivityStream();
    void doFetchSessionStatus();
    void doFetchSessionLogs();
    void doFetchControlStatus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Heartbeat ogni 5 minuti — solo status leggeri (nessun dato daily ridondante)
  useEffect(() => {
    const id = window.setInterval(() => {
      void doCheckIbkr(false);   // TCP probe IBG — rileva disconnessioni
      void doFetchSysStatus();   // 1 query DuckDB — kill switch, kelly, data_mode
      void doFetchSessionStatus(); // stato scheduler sessioni
      void doFetchControlStatus(); // observer + ibwr + control plane
      void doFetchActivityStream(); // activity stream — refresh ogni 5 min
      void doFetchSysLog();         // system log — refresh ogni 5 min
    }, 5 * 60_000);
    return () => window.clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Refresh syslog ogni 30s — log è leggero e utile per debug in tempo reale
  useEffect(() => {
    if (!apiOnline) return;
    const id = window.setInterval(() => void doFetchSysLog(), 30_000);
    return () => window.clearInterval(id);
  }, [apiOnline]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch tier when regime changes — block_visibility depends on regime
  useEffect(() => {
    if (regimeCurrent?.regime) void doFetchTier(regimeCurrent.regime);
  }, [regimeCurrent?.regime]); // eslint-disable-line react-hooks/exhaustive-deps

  // Helper: read block visibility for a block key (safe default = fully visible/interactive)
  function blk(key: string): BlockVis {
    return tierInfo?.block_visibility?.[key]
      ?? { visible: true, interactive: true, gate: "unknown", reason: null };
  }

  const releaseView = useMemo(() => parseReleaseMd(releaseMd), [releaseMd]);
  const ddPct = (paperSummary?.max_drawdown ?? 0) * 100;
  const ddFill = Math.max(0, Math.min(100, (ddPct / 20) * 100));

  // ── ROC16: Dynamic AUTOMATION PIPELINE states ─────────────────────────────
  const pipeHasRegime  = (regimeCurrent?.n_recent ?? 0) > 0;
  const pipeHasScore   = pipeHasRegime; // scan run implies scoring happened
  const pipeKellyReady = sysStatus?.kelly_enabled === true;
  const pipeRegimeStep = pipeHasRegime ? "done" : "wait";
  const pipeScoreStep  = pipeHasScore  ? "run"  : "wait"; // 'run' = pulsing = active scoring
  const pipeKellyStep  = pipeKellyReady ? "done" : "wait";
  const wheelAvailable = tierInfo?.features_available?.wheel ?? false;
  const wheelValidated =
    (paperSummary?.trades ?? 0) >= 50 &&
    (paperSummary?.sharpe_annualized ?? 0) >= 0.6 &&
    (paperSummary?.compliance_violations ?? 0) === 0;
  const wheelWarning = wheelAvailable && !wheelValidated ? "Strategia non validata sul track record." : null;
  // ── ROC16: High-urgency exit signal ───────────────────────────────────────
  const urgentExits = (exitCandidates?.candidates ?? []).filter(c => c.exit_score >= 5);
  const hasUrgentExit = urgentExits.length > 0;

  const phaseKey: string = centerPhase === "ante"
    ? `ante-${anteSubTab}`
    : centerPhase === "op"
      ? `op-${opSubTab}`
      : `post-${postSubTab}`;
  const phaseTemplate = (() => {
    const baseScanTs = premarketScanAt ? fmtTs(premarketScanAt) : "N/D";
    if (phaseKey === "ante-dati") {
      return {
        step: "STEP 1-2 - DATI",
        title: "Ingest e Consolidamento",
        subtitle: `Ultimo aggiornamento: ${baseScanTs}`,
        kpis: [
          { label: "Pipeline", value: pipelineStateLabel, tone: healthToSevClass(pipelineStateHealth), sub: "stato ingest" },
          { label: "Data mode", value: dataModeUpper || "N/D", tone: hasRealData ? "sev-ok" : "sev-neutral", sub: "fonte dati" },
          { label: "Base locale", value: `${localRecords} rec`, tone: healthToSevClass(localDbHealth), sub: "duckdb + journal" },
          { label: "History", value: historyReadiness ? `${historyReadiness.score_pct.toFixed(1)}%` : "N/D", tone: historyReadiness?.ready ? "sev-ok" : "sev-warn", sub: "readiness" },
        ],
        screenTitle: "ingest_pipeline.log",
        screenLines: [
          `feed: ${pipelineFeedLabel}`,
          `yfinance/cboe: ${yfinanceLabel} | fred: ${fredLabel} | orats: ${oratsLabel}`,
          `data_mode: ${dataModeUpper || "N/D"}`,
          `base_locale_records: ${localRecords}`,
          `history_readiness: ${historyReadiness ? `${historyReadiness.days_observed}/${historyReadiness.target_days} giorni` : "N/D"}`,
        ],
      };
    }
    if (phaseKey === "ante-analisi") {
      return {
        step: "STEP 3-4 - ANALISI",
        title: "Risultato Scoring Pre-Market",
        subtitle: `Regime ${premarketRegime} - shortlist ${premarketShortlistCount}`,
        kpis: [
          { label: "Regime", value: premarketRegime, tone: sevClassForRegime(premarketRegime), sub: `${regimeCurrent?.n_recent ?? 0} sample` },
          { label: "Top score", value: premarketTopScorePct === null ? "N/D" : `${premarketTopScorePct.toFixed(1)}/100`, tone: premarketTopScorePct !== null && premarketTopScorePct >= 75 ? "sev-ok" : "sev-warn", sub: "candidato #1" },
          { label: "Shortlist", value: `${premarketShortlistCount}`, tone: "sev-data", sub: `pronti ${premarketReadyCount}` },
          { label: "Source", value: premarketSource, tone: "sev-meta", sub: `scan ${baseScanTs}` },
        ],
        screenTitle: "scoring_engine.py",
        screenLines: [
          `regime: ${premarketRegime}`,
          `source: ${premarketSource}`,
          `shortlist: ${premarketShortlistCount}`,
          `ready: ${premarketReadyCount}`,
          `top_score: ${premarketTopScorePct === null ? "N/D" : premarketTopScorePct.toFixed(1)}`,
        ],
      };
    }
    if (phaseKey === "ante-briefing") {
      return {
        step: "STEP 5 - BRIEFING",
        title: "Briefing Operativo",
        subtitle: briefingLabel,
        kpis: [
          { label: "Audio", value: briefingPlaying ? "PLAYING" : "STOP", tone: briefingPlaying ? "sev-ok" : "sev-neutral", sub: "player unificato" },
          { label: "Archivio", value: `${briefingList.length}`, tone: briefingList.length > 0 ? "sev-ok" : "sev-neutral", sub: "file briefing" },
          { label: "Auto-open", value: briefingAutoOpen ? "ON" : "OFF", tone: briefingAutoOpen ? "sev-data" : "sev-neutral", sub: "drawer ai" },
          { label: "Auto-play", value: briefingAutoPlay ? "ON" : "OFF", tone: briefingAutoPlay ? "sev-data" : "sev-neutral", sub: "narratore" },
        ],
        screenTitle: "briefing_runner.log",
        screenLines: [
          `api: ${apiOnline ? "ONLINE" : "OFFLINE"}`,
          `current: ${briefingLabel}`,
          `files: ${briefingList.length}`,
          `auto_open: ${briefingAutoOpen ? "on" : "off"}`,
          `auto_play: ${briefingAutoPlay ? "on" : "off"}`,
        ],
      };
    }
    if (phaseKey === "op-trading") {
      return {
        step: "STEP 6-15 - TRADING",
        title: "Execution e Monitoraggio",
        subtitle: "Flusso operativo in sessione",
        kpis: [
          { label: "Go/No-Go", value: goGate ? (goGate.pass ? "GO" : "NO-GO") : "N/D", tone: goGate?.pass ? "sev-ok" : "sev-error", sub: "gate operativo" },
          { label: "Kill switch", value: sysStatus?.kill_switch_active ? "ON" : "OFF", tone: sysStatus?.kill_switch_active ? "sev-error" : "sev-ok", sub: "controllo rischio" },
          { label: "Trades", value: `${sysStatus?.n_closed_trades ?? 0}`, tone: "sev-data", sub: "completati" },
          { label: "Exit flag", value: `${urgentExits.length}`, tone: urgentExits.length > 0 ? "sev-warn" : "sev-neutral", sub: "alta urgenza" },
        ],
        screenTitle: "execution_window.log",
        screenLines: [
          `window: 10:00-11:30 EST`,
          `avoid: 09:30-09:45 | 15:30-16:00`,
          `kill_switch: ${sysStatus?.kill_switch_active ? "active" : "off"}`,
          `urgent_exits: ${urgentExits.length}`,
          `closed_trades: ${sysStatus?.n_closed_trades ?? 0}`,
        ],
      };
    }
    if (phaseKey === "op-wheel") {
      return {
        step: "STEP 16-20 - WHEEL",
        title: "Ciclo Wheel",
        subtitle: "Stato macchina e capitale dedicato",
        kpis: [
          { label: "Disponibilita", value: wheelAvailable ? "ENABLED" : "LOCKED", tone: wheelAvailable ? "sev-ok" : "sev-warn", sub: wheelWarning ?? "feature gate" },
          { label: "Posizioni", value: `${wheelPositions?.positions?.length ?? 0}`, tone: "sev-data", sub: "attive" },
          { label: "Tier", value: tierInfo?.active_mode ?? "N/D", tone: "sev-data", sub: "capital mode" },
          { label: "Kelly", value: blk("kelly_sizing").visible ? "LIVE" : "LOCK", tone: blk("kelly_sizing").visible ? "sev-ok" : "sev-neutral", sub: "sizing gate" },
        ],
        screenTitle: "wheel_state_machine.log",
        screenLines: [
          `tier: ${tierInfo?.active_mode ?? "N/D"}`,
          `wheel_enabled: ${wheelAvailable ? "yes" : "no"}`,
          `active_positions: ${wheelPositions?.positions?.length ?? 0}`,
          `warning: ${wheelWarning ?? "none"}`,
          `kelly: ${blk("kelly_sizing").visible ? "live" : "lock"}`,
        ],
      };
    }
    if (phaseKey === "op-metriche") {
      return {
        step: "STEP 21-22 - METRICHE",
        title: "Portfolio Metrics",
        subtitle: "Snapshot operativo consolidato",
        kpis: [
          { label: "Win rate", value: fmtPct(paperSummary?.win_rate ?? null), tone: "sev-data", sub: "paper summary" },
          { label: "Sharpe", value: fmtNum(paperSummary?.sharpe_annualized ?? null), tone: "sev-data", sub: "annualizzato" },
          { label: "Max DD", value: fmtPct(paperSummary?.max_drawdown ?? null), tone: ddHealth === "alert" ? "sev-error" : ddHealth === "warn" ? "sev-warn" : "sev-ok", sub: "rischio" },
          { label: "Net Liq", value: ibkrAccount?.net_liquidation != null ? `€${ibkrAccount.net_liquidation.toLocaleString("it-IT", { minimumFractionDigits: 0 })}` : "N/D", tone: "sev-ok", sub: "conto ibkr" },
        ],
        screenTitle: "portfolio_agg.log",
        screenLines: [
          `trades: ${paperSummary?.trades ?? 0}`,
          `win_rate: ${fmtPct(paperSummary?.win_rate ?? null)}`,
          `sharpe: ${fmtNum(paperSummary?.sharpe_annualized ?? null)}`,
          `max_dd: ${fmtPct(paperSummary?.max_drawdown ?? null)}`,
          `net_liq: ${ibkrAccount?.net_liquidation ?? "N/D"}`,
        ],
      };
    }
    if (phaseKey === "op-backtest") {
      return {
        step: "BACKTEST",
        title: "Paper Closed + WFA Storico",
        subtitle: "Valutazione segnali e coerenza operativa",
        kpis: [
          { label: "Trade chiusi", value: `${paperSummary?.trades ?? 0}`, tone: "sev-data", sub: "journal paper" },
          { label: "History", value: historyReadiness ? `${historyReadiness.score_pct.toFixed(1)}%` : "N/D", tone: historyReadiness?.ready ? "sev-ok" : "sev-warn", sub: "copertura dati" },
          { label: "Violazioni", value: `${paperSummary?.compliance_violations ?? 0}`, tone: (paperSummary?.compliance_violations ?? 0) > 0 ? "sev-warn" : "sev-ok", sub: "compliance" },
          { label: "Profit factor", value: fmtNum(paperSummary?.profit_factor ?? null), tone: "sev-data", sub: "qualita edge" },
        ],
        screenTitle: "backtest_audit.log",
        screenLines: [
          `closed_trades: ${paperSummary?.trades ?? 0}`,
          `history_ready: ${historyReadiness?.ready ? "yes" : "no"}`,
          `history_score: ${historyReadiness ? `${historyReadiness.score_pct.toFixed(1)}%` : "N/D"}`,
          `profit_factor: ${fmtNum(paperSummary?.profit_factor ?? null)}`,
          `compliance_violations: ${paperSummary?.compliance_violations ?? 0}`,
        ],
      };
    }
    if (phaseKey === "post-chiusura") {
      return {
        step: "STEP 23 - CHIUSURA",
        title: "Sessione EOD",
        subtitle: "Chiusura e stato scheduler",
        kpis: [
          { label: "Scheduler", value: sessionStatus?.enabled ? "ON" : "OFF", tone: sessionStatus?.enabled ? "sev-ok" : "sev-neutral", sub: "session engine" },
          { label: "Running", value: sessionStatus?.running ? "YES" : "NO", tone: sessionStatus?.running ? "sev-warn" : "sev-ok", sub: "stato sessione" },
          { label: "Last morning", value: sessionStatus?.last_morning ? sessionStatus.last_morning.slice(0, 16) : "N/D", tone: "sev-meta", sub: "UTC" },
          { label: "Last EOD", value: sessionStatus?.last_eod ? sessionStatus.last_eod.slice(0, 16) : "N/D", tone: "sev-meta", sub: "UTC" },
        ],
        screenTitle: "session_logs.eod",
        screenLines: [
          `scheduler: ${sessionStatus?.enabled ? "on" : "off"}`,
          `running: ${sessionStatus?.running ? "yes" : "no"}`,
          `last_morning: ${sessionStatus?.last_morning ?? "N/D"}`,
          `last_eod: ${sessionStatus?.last_eod ?? "N/D"}`,
          `next_eod: ${sessionStatus?.next_eod ?? "N/D"}`,
        ],
      };
    }
    return {
      step: "STEP 24 - REPORT",
      title: "Consolidamento Report",
      subtitle: "Esito giornata e stato release",
      kpis: [
        { label: "P&L cumulato", value: fmtNum(paperSummary?.pnl_cumulative ?? null), tone: (paperSummary?.pnl_cumulative ?? 0) >= 0 ? "sev-ok" : "sev-error", sub: "paper" },
        { label: "Trades", value: `${paperSummary?.trades ?? 0}`, tone: "sev-data", sub: "totali" },
        { label: "Release note", value: releaseMd ? "PRESENTE" : "N/D", tone: releaseMd ? "sev-ok" : "sev-neutral", sub: "status doc" },
        { label: "Data agg", value: paperSummary?.as_of_date ?? "N/D", tone: "sev-meta", sub: "snapshot" },
      ],
      screenTitle: "report_eod.log",
      screenLines: [
        `pnl_cumulative: ${fmtNum(paperSummary?.pnl_cumulative ?? null)}`,
        `trades: ${paperSummary?.trades ?? 0}`,
        `as_of_date: ${paperSummary?.as_of_date ?? "N/D"}`,
        `release_loaded: ${releaseMd ? "yes" : "no"}`,
      ],
    };
  })();

  // Web Audio beep: triggered once when urgentExits count transitions 0→>0
  const prevUrgentCount = useRef(0);
  useEffect(() => {
    const cur = urgentExits.length;
    if (cur > prevUrgentCount.current && cur > 0) {
      // Audio beep
      let ctx: AudioContext | null = null;
      try {
        ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.type = "sine"; osc.frequency.value = 660;
        gain.gain.setValueAtTime(0.25, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
        osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.35);
        osc.onended = () => ctx!.close();
      } catch { ctx?.close(); /* browser may block before first user interaction */ }
      // Visual flash — red overlay 300ms
      const flash = document.createElement("div");
      flash.style.cssText = "position:fixed;inset:0;background:rgba(255,48,48,0.28);pointer-events:none;z-index:10000;transition:opacity 0.3s";
      document.body.appendChild(flash);
      setTimeout(() => { flash.style.opacity = "0"; setTimeout(() => flash.remove(), 300); }, 300);
    }
    prevUrgentCount.current = cur;
  }, [urgentExits.length]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="terminal-app">
      <header className="topbar">
        <div className="logo">QuantOPTION<span className="logo-ai">.AI</span></div>
        <div className="topbar-center">
          <Tooltip text={TOOLTIPS[`regime_${regimeView.text.toLowerCase()}`] ?? ""}>
            <span className={`regime-pill ${regimeView.cls}`}>REGIME: {regimeView.text}</span>
          </Tooltip>
          {apiOnline && <span className="top-mini">XGBoost: {(stateObj as any)?.model_scores?.xgboost ?? "—"}</span>}
          {apiOnline && <span className="top-mini">HMM P(shock): {(stateObj as any)?.model_scores?.hmm_p_shock ?? "—"}</span>}
          <span className="top-mini">Sizing: {regimeView.text === "NORMAL" ? "100%" : regimeView.text === "CAUTION" ? "50%" : regimeView.text === "SHOCK" ? "0%" : "—"}</span>
        </div>
        <div className="topbar-right">
          {fetchErrors.size > 0 && (
            <Tooltip text={TOOLTIPS.stale}>
              <span style={{ color: "#f97316", fontSize: "0.7rem" }} title={`Fetch falliti: ${Array.from(fetchErrors).join(", ")}`}>
                ⚠ {fetchErrors.size} stale
              </span>
            </Tooltip>
          )}
          <span className="clock">{clockText}</span>
          <Tooltip text={apiOnline ? TOOLTIPS.ibkr_connected : TOOLTIPS.ibkr_disconnected}>
            <span className={`live-pill ${apiOnline ? "online" : "offline"}`}>{apiOnline ? "API LIVE" : "API DOWN"}</span>
          </Tooltip>
          <button className="btn btn-primary" onClick={refreshAll} disabled={busy}>{busy ? "REFRESHING" : "REFRESH"}</button>
          <a className="btn btn-ghost" href={`${API_BASE}/guide`} target="_blank" rel="noreferrer">GUIDA</a>
          <a className="btn btn-ghost" href={`${API_BASE}/health`} target="_blank" rel="noreferrer">API /HEALTH</a>
          <button
            className={`btn ${(sysStatus?.kill_switch_active) ? "btn-warning" : "btn-danger"}`}
            onClick={doKillSwitch}
            disabled={busy}
            title={(sysStatus?.kill_switch_active) ? "Kill switch ATTIVO — clicca per disattivare" : "Attiva kill switch — blocca tutti gli ordini"}
          >{(sysStatus?.kill_switch_active) ? "🛑 KS ATTIVO" : "KILL SWITCH"}</button>
        </div>
      </header>

            <div className="terminal-main">
        <aside className="leftnav">
          <div className="nav-section left-ops-section left-dev-group">
            <div className="left-grouphead" onClick={() => setLeftDevelopmentOpen((v) => !v)} role="button" tabIndex={0}>
              <span className="left-grouphead-title"><span className="group-arrow">{leftDevelopmentOpen ? "▾" : "▸"}</span>AVANZAMENTO</span>
            </div>
            {leftDevelopmentOpen && (
              <>
                <div className="left-subhead" onClick={() => setLeftPipelineProgressOpen((v) => !v)} role="button" tabIndex={0}>
                  <span>{leftPipelineProgressOpen ? "▾" : "▸"} MILESTONE</span>
                  <span className="sev-data">{phaseProgress.f1}%/{phaseProgress.f2}%/{phaseProgress.f3}%/{phaseProgress.f4}%</span>
                </div>
                {leftPipelineProgressOpen && (
                  <div className="dev-phase-stack">
                    <div className="phase-row"><span>F1 Pipeline</span><b className={phaseProgress.f1 === 100 ? "ok" : "warn"}>{phaseProgress.f1}%</b></div>
                    <div className="phase-bar"><span style={{ width: `${phaseProgress.f1}%` }} /></div>
                    <div className="phase-row"><span>F2 Regime</span><b className={phaseProgress.f2 === 100 ? "ok" : "warn"}>{phaseProgress.f2}%</b></div>
                    <div className="phase-bar"><span style={{ width: `${phaseProgress.f2}%` }} /></div>
                    <div className="phase-row"><span>F3 Paper</span><b className={phaseProgress.f3 === 100 ? "ok" : phaseProgress.f3 > 0 ? "warn" : "dim"}>{phaseProgress.f3}%</b></div>
                    <div className="phase-bar"><span style={{ width: `${phaseProgress.f3}%` }} /></div>
                    <div className="phase-row"><span>F4 Scoring</span><b className={phaseProgress.f4 === 100 ? "ok" : phaseProgress.f4 > 0 ? "warn" : "dim"}>{phaseProgress.f4}%</b></div>
                    <div className="phase-bar"><span style={{ width: `${phaseProgress.f4}%` }} /></div>
                  </div>
                )}
                <div className="left-subhead left-subhead-inline" onClick={() => setLeftPhaseOpen((v) => !v)} role="button" tabIndex={0}>
                  <span>{leftPhaseOpen ? "▾" : "▸"} STEP ATTIVO</span>
                  <span className="sev-data">{nextStep}</span>
                </div>
                {leftPhaseOpen && (
                  <div className="left-subbody">
                    <div className="left-kpi-row"><span>Step bloccati</span><b className="sev-data">{blockedCount}</b></div>
                    <div className="left-kpi-row"><span>Equity points</span><b className="sev-data">{paperSummary?.equity_points ?? 0}</b></div>
                    <div className="left-kpi-row"><span>Trade journal</span><b className="sev-data">{paperSummary?.trades ?? 0}</b></div>
                    <div className="left-kpi-row"><span>Aggiornato</span><b className="sev-meta">{paperSummary?.as_of_date ?? "-"}</b></div>
                  </div>
                )}
                {/* ── SESSIONI AUTO ── */}
                <div className="left-subhead left-subhead-inline"
                  onClick={() => setSessionLogOpen(v => !v)} role="button" tabIndex={0} style={{cursor:"pointer", marginTop:4}}>
                  <span className="sev-meta" style={{fontSize:"0.6rem"}}>
                    <span style={{marginRight:4}}>{sessionLogOpen ? "▾" : "▸"}</span>SESSIONI AUTO
                  </span>
                  <span style={{display:"flex", gap:4, alignItems:"center"}}>
                    <span className={sessionStatus?.enabled ? "sev-ok" : "sev-neutral"} style={{fontSize:"0.6rem"}}>
                      {sessionStatus?.enabled ? "ON" : "OFF"}
                    </span>
                    {sessionLogs.some(l => l.errors.length > 0) && <span className="sev-error" style={{fontSize:"0.58rem"}}>ERR</span>}
                  </span>
                </div>
                <div className="left-subbody">
                  <div className="left-kpi-row"><span>Prossima</span><b className="sev-meta" style={{fontSize:"0.6rem"}}>
                    {sessionStatus?.next_morning ? sessionStatus.next_morning.slice(0,16).replace("T"," ") : "—"}
                  </b></div>
                </div>
                {sessionLogOpen && (() => {
                  // Raggruppa per data (max 30 giorni)
                  const byDay: Record<string, SessionLogEntry[]> = {};
                  sessionLogs.forEach(l => {
                    const d = l.session_date ?? l.started_at?.slice(0,10) ?? "?";
                    if (!byDay[d]) byDay[d] = [];
                    byDay[d].push(l);
                  });
                  const days = Object.keys(byDay).sort().reverse().slice(0, 30);
                  if (days.length === 0) return (
                    <div style={{fontSize:"0.6rem", color:"var(--dim)", padding:"4px 6px"}}>Nessuna sessione registrata</div>
                  );
                  return (
                    <div style={{maxHeight:320, overflowY:"auto"}}>
                      {days.map(day => {
                        const sessions = byDay[day];
                        const allErrors = sessions.flatMap(s => s.errors ?? []);
                        const morning = sessions.find(s => s.session_type === "morning");
                        const eod = sessions.find(s => s.session_type === "eod");
                        return (
                          <div key={day} style={{borderTop:"1px solid var(--border)", paddingTop:4, marginTop:4}}>
                            {/* Header giorno */}
                            <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:3}}>
                              <span style={{fontSize:"0.62rem", fontWeight:600, color:"var(--text)"}}>{day}</span>
                              {allErrors.length > 0
                                ? <span className="sev-error" style={{fontSize:"0.55rem"}}>{allErrors.length} err</span>
                                : <span className="sev-ok" style={{fontSize:"0.55rem"}}>✓</span>}
                            </div>
                            {/* Blocco PROCESSI */}
                            <div style={{fontSize:"0.58rem", color:"var(--dim)", marginBottom:2, textTransform:"uppercase", letterSpacing:"0.03em"}}>Processi</div>
                            {[morning, eod].map((sess, si) => sess && (
                              <div key={si} style={{marginBottom:4, paddingLeft:6, borderLeft:"2px solid var(--border)"}}>
                                <div style={{fontSize:"0.6rem", color:"var(--dim)", marginBottom:2}}>
                                  {sess.session_type.toUpperCase()} · {sess.started_at?.slice(11,16) ?? "?"} → {sess.finished_at?.slice(11,16) ?? "?"}
                                  {sess.regime && <span style={{marginLeft:4}} className={sess.regime==="NORMAL"?"sev-ok":sess.regime==="CAUTION"?"sev-warn":"sev-error"}>{sess.regime}</span>}
                                </div>
                                {Object.entries(sess.steps ?? {}).map(([stepName, stepData]) => {
                                  const sd = stepData as Record<string, unknown>;
                                  const ok = sd.ok !== false;
                                  return (
                                    <div key={stepName} style={{display:"flex", justifyContent:"space-between", alignItems:"center", fontSize:"0.58rem", padding:"1px 0"}}>
                                      <span style={{color: ok ? "var(--text)" : "var(--error)"}}>{ok ? "✓" : "✗"} {stepName}</span>
                                      <span style={{color:"var(--dim)"}}>
                                        {sd.candidates != null ? `${sd.candidates} cand` :
                                         sd.universe_size != null ? `${sd.universe_size} sym` :
                                         sd.count != null ? String(sd.count) :
                                         sd.regime != null ? String(sd.regime) : ""}
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>
                            ))}
                            {/* Blocco ERRORI */}
                            {allErrors.length > 0 && (
                              <>
                                <div style={{fontSize:"0.58rem", color:"var(--error)", marginTop:3, marginBottom:2, textTransform:"uppercase", letterSpacing:"0.03em"}}>Errori</div>
                                <div style={{paddingLeft:6, borderLeft:"2px solid var(--error)"}}>
                                  {allErrors.map((e, ei) => (
                                    <div key={ei} style={{fontSize:"0.57rem", color:"var(--error)", padding:"1px 0", wordBreak:"break-word"}}>· {e}</div>
                                  ))}
                                </div>
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
              </>
            )}
          </div>
          {/* SYSTEM LOG */}
          <div className="nav-section syslog-section">
            <div className="left-grouphead syslog-header" onClick={() => setSysLogOpen(v => !v)} role="button" tabIndex={0}>
              <span className="left-grouphead-title">
                <span className="group-arrow">{sysLogOpen ? "▾" : "▸"}</span>SYSTEM LOG
              </span>
              <span style={{display:"flex", gap:5, alignItems:"center"}}>
                {sysLog.some(r => r.level === "ERROR") && <span className="sev-error" style={{fontSize:"0.58rem"}}>ERR</span>}
                {sysLog.some(r => r.level === "WARNING") && <span className="sev-warn" style={{fontSize:"0.58rem"}}>WARN</span>}
                <span className="sev-meta" style={{fontSize:"0.58rem"}}>{sysLog.length}</span>
              </span>
            </div>
            {sysLogOpen && (
              <>
                <div className="syslog-feed" ref={sysLogRef}>
                  {sysLog.length === 0 && (
                    <div className="syslog-empty">{apiOnline ? "In attesa di eventi..." : "API offline"}</div>
                  )}
                  {sysLog.map((r, i) => (
                    <div key={i} className={`syslog-row syslog-${r.level.toLowerCase()}`}>
                      <span className="syslog-ts">{r.ts}</span>
                      <span className="syslog-lvl">{r.level.slice(0,1)}</span>
                      <span className="syslog-name">{r.name}</span>
                      <span className="syslog-msg">{r.msg}</span>
                    </div>
                  ))}
                </div>
                <div className="syslog-toolbar">
                  <button className="btn btn-ghost syslog-btn" disabled={!apiOnline}
                    onClick={() => void doFetchSysLog()}>⟳ aggiorna</button>
                  <button className="btn btn-ghost syslog-btn"
                    onClick={() => {
                      const txt = sysLog.map(r => `${r.ts} [${r.level}] ${r.name}: ${r.msg}`).join("\n");
                      const a = document.createElement("a");
                      a.href = URL.createObjectURL(new Blob([txt], {type:"text/plain"}));
                      a.download = `syslog_${new Date().toISOString().slice(0,19).replace(/:/g,"-")}.txt`;
                      a.click();
                    }}>⬇ salva</button>
                  <button className="btn btn-ghost syslog-btn"
                    onClick={() => setSysLog([])}>✕ pulisci</button>
                </div>
              </>
            )}
          </div>
        </aside><section className="centerpane">
          <div className="metrics-row">
            <div className="metric-box"><div className="metric-label"><Tooltip text={TOOLTIPS.trades}>TRADES</Tooltip></div><div className="metric-val">{paperSummary?.trades ?? "-"}</div></div>
            <div className="metric-box"><div className="metric-label"><Tooltip text={TOOLTIPS.sharpe}>SHARPE</Tooltip></div><div className="metric-val">{fmtNum(paperSummary?.sharpe_annualized ?? null)}</div></div>
            <div className="metric-box"><div className="metric-label"><Tooltip text={TOOLTIPS.max_dd}>MAX DD</Tooltip></div><div className="metric-val amber">{fmtPct(paperSummary?.max_drawdown ?? null)}</div></div>
            <div className="metric-box"><div className="metric-label"><Tooltip text={TOOLTIPS.win_rate}>WIN RATE</Tooltip></div><div className="metric-val">{fmtPct(paperSummary?.win_rate ?? null)}</div></div>
            <div className="metric-box"><div className="metric-label"><Tooltip text={TOOLTIPS.compliance}>COMPLIANCE</Tooltip></div><div className="metric-val red">{paperSummary?.compliance_violations ?? "-"}</div></div>
            {tierInfo && (() => {
              const tierColor: Record<string, string> = {
                MICRO: "#60a5fa", SMALL: "#a78bfa", MEDIUM: "#4ade80", ADVANCED: "#f97316",
              };
              const col = tierColor[tierInfo.active_mode] ?? "#888";
              return (
                <div className="metric-box" style={{ borderLeft: `3px solid ${col}` }}>
                  <div className="metric-label" style={{ color: col }}><Tooltip text={TOOLTIPS.tier}>TIER</Tooltip></div>
                  <div className="metric-val" style={{ color: col, fontSize: "0.9rem" }}>{tierInfo.active_mode}</div>
                  <div style={{ fontSize: "0.6rem", color: "#555", marginTop: 2 }}>{tierInfo.tier_detail.capital}</div>
                </div>
              );
            })()}
          </div>

          {/* ── SHOCK banner — ALWAYS_VISIBLE, collapses trading UI ── */}
          {regimeView.text === "SHOCK" && (
            <div style={{
              background: "#3b0000", border: "1px solid #ef4444", borderRadius: 4,
              padding: "8px 14px", marginBottom: 6, display: "flex", alignItems: "center", gap: 10,
            }}>
              <span style={{ color: "#ef4444", fontWeight: 700, fontSize: "0.85rem" }}>🛑 REGIME SHOCK</span>
              <span style={{ color: "#fca5a5", fontSize: "0.75rem" }}>
                Trading sospeso — tutti i pannelli operativi sono in sola lettura.
                Solo monitoring, kill switch e risk panel rimangono attivi.
              </span>
            </div>
          )}

          {/* ── CAUTION banner ── */}
          {regimeView.text === "CAUTION" && (
            <div style={{
              background: "#2c1a00", border: "1px solid #f59e0b", borderRadius: 4,
              padding: "6px 14px", marginBottom: 6, display: "flex", alignItems: "center", gap: 10,
            }}>
              <span style={{ color: "#f59e0b", fontWeight: 700, fontSize: "0.8rem" }}>⚠ REGIME CAUTION</span>
              <span style={{ color: "#fcd34d", fontSize: "0.7rem" }}>
                Sizing 50% — solo spread stretti con filtro direzionale. Nuovi condor sospesi.
              </span>
            </div>
          )}

          <div className="tabs phase-tabs">
            <button className={`tab ${centerPhase === "ante" ? "active" : ""}`} onClick={() => setCenterPhase("ante")}>ANTE</button>
            <button className={`tab ${centerPhase === "op" ? "active" : ""}`} onClick={() => setCenterPhase("op")}>OP</button>
            <button className={`tab ${centerPhase === "post" ? "active" : ""}`} onClick={() => setCenterPhase("post")}>POST</button>
          </div>
          {centerPhase === "ante" && (
            <div className="tabs subtabs">
              <button className={`tab ${anteSubTab === "dati" ? "active" : ""}`} onClick={() => setAnteSubTab("dati")}>DATI</button>
              <button className={`tab ${anteSubTab === "analisi" ? "active" : ""}`} onClick={() => setAnteSubTab("analisi")}>ANALISI</button>
              <button className={`tab ${anteSubTab === "briefing" ? "active" : ""}`} onClick={() => setAnteSubTab("briefing")}>BRIEFING</button>
            </div>
          )}
          {centerPhase === "op" && (
            <div className="tabs subtabs">
              <button className={`tab ${opSubTab === "trading" ? "active" : ""}`} onClick={() => setOpSubTab("trading")}>TRADING</button>
              <button className={`tab ${opSubTab === "wheel" ? "active" : ""}`} onClick={() => setOpSubTab("wheel")}>WHEEL</button>
              <button className={`tab ${opSubTab === "metriche" ? "active" : ""}`} onClick={() => setOpSubTab("metriche")}>METRICHE</button>
              <button className={`tab ${opSubTab === "backtest" ? "active" : ""}`} onClick={() => setOpSubTab("backtest")}>BACKTEST</button>
            </div>
          )}
          {centerPhase === "post" && (
            <div className="tabs subtabs">
              <button className={`tab ${postSubTab === "chiusura" ? "active" : ""}`} onClick={() => setPostSubTab("chiusura")}>CHIUSURA</button>
              <button className={`tab ${postSubTab === "report" ? "active" : ""}`} onClick={() => setPostSubTab("report")}>REPORT</button>
            </div>
          )}
          {/* ══════════════════════════════════════════════════════════════
               LIFECYCLE PANELS — ANTE / OP / POST  (dati reali, no mock)
              ══════════════════════════════════════════════════════════════ */}

          {/* ── ANTE / DATI ── Steps 1-2: Ingest + Consolidamento ──────── */}
          {centerPhase === "ante" && anteSubTab === "dati" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 1–2 — DATI</span>
                <span className="lc-step-title">Ingest e Consolidamento</span>
                {premarketScanAt && <span className="lc-step-sub">Aggiornato: {fmtTs(premarketScanAt)}</span>}
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Stato pipeline</div>
                  <div className="lc-kpi-grid">
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Pipeline</div>
                      <div className={`lc-kpi-value ${healthToSevClass(pipelineStateHealth)}`}>{pipelineStateLabel}</div>
                      <div className="lc-kpi-sub">ingest + regime</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Data Mode</div>
                      <div className={`lc-kpi-value ${hasRealData ? "sev-ok" : "sev-neutral"}`} style={{fontSize:"0.75rem"}}>{dataModeUpper || "N/D"}</div>
                      <div className="lc-kpi-sub">fonte dati</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Record locali</div>
                      <div className={`lc-kpi-value ${healthToSevClass(localDbHealth)}`}>{localRecords.toLocaleString("it-IT")}</div>
                      <div className="lc-kpi-sub">DuckDB + journal</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">History</div>
                      <div className={`lc-kpi-value ${historyReadiness?.ready ? "sev-ok" : "sev-warn"}`}>
                        {historyReadiness ? `${historyReadiness.score_pct.toFixed(0)}%` : "N/D"}
                      </div>
                      <div className="lc-kpi-sub">{historyReadiness ? `${historyReadiness.days_observed}/${historyReadiness.target_days}g` : "—"}</div>
                    </div>
                  </div>
                  {historyReadiness && (
                    <div className="lc-progress-wrap">
                      <div className="lc-panel-title" style={{marginTop:12}}>Readiness → Kelly gate (50 trade / 50 giorni)</div>
                      <div className="lc-progress-track">
                        <div className={`lc-progress-fill ${historyReadiness.ready ? "ok" : "warn"}`}
                          style={{width:`${Math.min(100, historyReadiness.score_pct)}%`}}/>
                      </div>
                      <div className="lc-progress-labels">
                        <span>{historyReadiness.days_observed}g osservati · {historyReadiness.events_observed} eventi</span>
                        <span>{historyReadiness.ready ? "✓ PRONTO" : historyEtaLabel}</span>
                      </div>
                      {historyReadiness.blockers.length > 0 && historyReadiness.blockers.map((b, i) => (
                        <div key={i} style={{fontSize:"0.6rem", color:"var(--amber)", marginTop:3}}>⚠ {b}</div>
                      ))}
                    </div>
                  )}
                  <div className="lc-kpi-grid" style={{marginTop:12}}>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Trade chiusi</div>
                      <div className="lc-kpi-value sev-data">{paperSummary?.trades ?? 0}</div>
                      <div className="lc-kpi-sub">su 50 per Kelly</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Kelly gate</div>
                      <div className={`lc-kpi-value ${sysStatus?.kelly_enabled ? "sev-ok" : "sev-warn"}`} style={{fontSize:"0.7rem"}}>
                        {sysStatus?.kelly_enabled ? "ABILITATO" : "DISABILITATO"}
                      </div>
                      <div className="lc-kpi-sub">{sysStatus?.kelly_enabled ? "sizing attivo" : `mancano ${Math.max(0, 50 - (sysStatus?.n_closed_trades ?? 0))} trade`}</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">P&L cumulato</div>
                      <div className={`lc-kpi-value ${(paperSummary?.pnl_cumulative ?? 0) >= 0 ? "sev-ok" : "sev-error"}`}>
                        {paperSummary?.pnl_cumulative != null ? `€${paperSummary.pnl_cumulative.toFixed(0)}` : "N/D"}
                      </div>
                      <div className="lc-kpi-sub">da inizio paper</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Violations</div>
                      <div className={`lc-kpi-value ${(paperSummary?.compliance_violations ?? 0) > 0 ? "sev-warn" : "sev-ok"}`}>
                        {paperSummary?.compliance_violations ?? 0}
                      </div>
                      <div className="lc-kpi-sub">compliance</div>
                    </div>
                  </div>
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">ingest_pipeline.log</span>
                  </div>
                  <div className="lc-screen-body">
                    <div className="lc-screen-row"><span className="lc-dim">feed_status</span><span className={pipelineFeedHealth === "ok" ? "sev-ok" : "sev-warn"}>{pipelineFeedLabel}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">yfinance/cboe</span><span className={healthToSevClass(yfinanceHealth)}>{yfinanceLabel}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">fred</span><span className={healthToSevClass(fredHealth)}>{fredLabel}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">orats</span><span className="sev-neutral">{oratsLabel}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">ibwr</span><span className={healthToSevClass(ibwrHealth)}>{ibwrState}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">data_mode</span><span className={hasRealData ? "sev-ok" : "sev-neutral"}>{dataModeUpper || "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">records_locali</span><span className="sev-data">{localRecords.toLocaleString("it-IT")}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">equity_snapshots</span><span className="sev-data">{paperSummary?.gates.data_points.equity_snapshots ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">trade_journal</span><span className="sev-data">{paperSummary?.gates.data_points.trade_journal ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">opportunity_log</span><span className="sev-data">{paperSummary?.gates.data_points.compliance_events ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">readiness_pct</span><span className={historyReadiness?.ready ? "sev-ok" : "sev-warn"}>{historyReadiness ? `${historyReadiness.score_pct.toFixed(1)}%` : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">kelly_gate</span><span className={sysStatus?.kelly_enabled ? "sev-ok" : "sev-warn"}>{sysStatus?.kelly_enabled ? "ABILITATO" : `LOCK (${sysStatus?.n_closed_trades ?? 0}/50)`}</span></div>
                    <div className="lc-action-bar">
                      <button className="btn btn-primary" onClick={() => void doAutoDemoPipeline()} disabled={busy || !apiOnline}>
                        {busy ? "..." : "▶ Avvia pipeline"}
                      </button>
                      <button className="btn btn-ghost" onClick={refreshAll} disabled={busy}>⟳</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── ANTE / ANALISI ── Steps 3-4: Regime + Scoring ──────────── */}
          {centerPhase === "ante" && anteSubTab === "analisi" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 3–4 — ANALISI</span>
                <span className="lc-step-title">Regime e Scoring Pre-Market</span>
                {premarketScanAt && <span className="lc-step-sub">{fmtTs(premarketScanAt)} · {premarketShortlistCount} segnali</span>}
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Regime di mercato</div>
                  <div className={`lc-regime-big ${premarketRegime.toLowerCase() === "normal" ? "normal" : premarketRegime.toLowerCase() === "caution" ? "caution" : premarketRegime.toLowerCase() === "shock" ? "shock" : "unknown"}`}>
                    {premarketRegime}
                  </div>
                  <div style={{fontSize:"0.62rem", color:"var(--dim)", marginBottom:12}}>
                    {regimeCurrent?.n_recent ?? 0} sessioni analizzate · sizing {premarketRegime === "NORMAL" ? "100%" : premarketRegime === "CAUTION" ? "50%" : premarketRegime === "SHOCK" ? "0%" : "—"}
                  </div>
                  <div className="lc-kpi-grid">
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Shortlist</div>
                      <div className="lc-kpi-value sev-data">{premarketShortlistCount}</div>
                      <div className="lc-kpi-sub">pronti: {premarketReadyCount}</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Top score</div>
                      <div className={`lc-kpi-value ${premarketTopScorePct !== null && premarketTopScorePct >= 65 ? "sev-ok" : "sev-warn"}`}>
                        {premarketTopScorePct !== null ? `${premarketTopScorePct.toFixed(0)}/100` : "N/D"}
                      </div>
                      <div className="lc-kpi-sub">candidato #1</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">P1 Vol edge</div>
                      <div className={`lc-kpi-value ${preP1 !== null && preP1 >= 6.5 ? "sev-ok" : "sev-warn"}`}>{preP1 !== null ? preP1.toFixed(1) : "—"}</div>
                      <div className="lc-kpi-sub">IVR / premium</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">P2 Liquidità</div>
                      <div className={`lc-kpi-value ${preP2 !== null && preP2 >= 6.5 ? "sev-ok" : "sev-warn"}`}>{preP2 !== null ? preP2.toFixed(1) : "—"}</div>
                      <div className="lc-kpi-sub">OI / spread</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">P3 Risk/reward</div>
                      <div className={`lc-kpi-value ${preP3 !== null && preP3 >= 6.5 ? "sev-ok" : "sev-warn"}`}>{preP3 !== null ? preP3.toFixed(1) : "—"}</div>
                      <div className="lc-kpi-sub">payoff struttura</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">P4 Regime align</div>
                      <div className={`lc-kpi-value ${preP4 !== null && preP4 >= 6.5 ? "sev-ok" : "sev-warn"}`}>{preP4 !== null ? preP4.toFixed(1) : "—"}</div>
                      <div className="lc-kpi-sub">coerenza regime</div>
                    </div>
                  </div>
                  {premarketRows.length > 0 && (
                    <div style={{marginTop:14}}>
                      <div className="lc-panel-title">Top candidati</div>
                      {premarketRows.slice(0, 5).map((c, i) => (
                        <div key={i} className="lc-candidate-row">
                          <span className="lc-candidate-rank">#{i + 1}</span>
                          <span className="lc-candidate-sym">{c.symbol} <span style={{color:"var(--dim)", fontSize:"0.62rem"}}>{c.strategy}</span></span>
                          {c.scorePct !== undefined && <span className={`lc-candidate-score ${c.scorePct >= 65 ? "sev-ok" : c.scorePct >= 50 ? "sev-warn" : "sev-error"}`}>{c.scorePct.toFixed(0)}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">regime_engine + scoring_engine</span>
                  </div>
                  <div className="lc-screen-body">
                    <div className="lc-screen-row"><span className="lc-dim">regime</span><span className={sevClassForRegime(premarketRegime)}>{premarketRegime}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">n_sessioni</span><span className="sev-data">{regimeCurrent?.n_recent ?? "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">source</span><span className="sev-meta">{premarketSource}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">universe_size</span><span className="sev-data">{universeLatest?.universe_size ?? "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">shortlist</span><span className="sev-data">{premarketShortlistCount}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">ready</span><span className="sev-data">{premarketReadyCount}</span></div>
                    {premarketPrimary && <>
                      <div className="lc-screen-section">
                        <div className="lc-screen-row"><span className="lc-dim">— rank #1 —</span><span className="sev-ok">{premarketPrimary.symbol}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">score</span><span className="sev-ok">{premarketPrimary.score.toFixed(1)}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">P1_vol</span><span>{(toTen(premarketPrimary.score_breakdown.vol_edge) ?? 0).toFixed(1)}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">P2_liq</span><span>{(toTen(premarketPrimary.score_breakdown.liquidity) ?? 0).toFixed(1)}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">P3_rr</span><span>{(toTen(premarketPrimary.score_breakdown.risk_reward) ?? 0).toFixed(1)}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">P4_reg</span><span>{(toTen(premarketPrimary.score_breakdown.regime_align) ?? 0).toFixed(1)}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">dte</span><span>{premarketPrimary.dte}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">spread_pct</span><span className={premarketPrimary.spread_pct < 0.05 ? "sev-ok" : "sev-warn"}>{(premarketPrimary.spread_pct * 100).toFixed(1)}%</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">max_loss_pct</span><span className={premarketPrimary.max_loss_pct < 0.3 ? "sev-ok" : "sev-warn"}>{(premarketPrimary.max_loss_pct * 100).toFixed(1)}%</span></div>
                      </div>
                    </>}
                    {/* Parametri scan — collassabile */}
                    <div style={{marginTop:10, borderTop:"1px solid var(--border)", paddingTop:8}}>
                      <div
                        style={{display:"flex", justifyContent:"space-between", alignItems:"center", cursor:"pointer", fontSize:"0.62rem", color:"var(--dim)", userSelect:"none"}}
                        onClick={() => setScanConfigOpen(v => !v)}
                        role="button" tabIndex={0}
                      >
                        <span>{scanConfigOpen ? "▾" : "▸"} parametri scan manuale</span>
                        {!scanConfigOpen && <span className="sev-meta" style={{fontSize:"0.58rem"}}>regime={universeRegime} · top {universeTopN}</span>}
                      </div>
                      {scanConfigOpen && (
                        <div style={{marginTop:8, display:"flex", flexDirection:"column", gap:6}}>
                          <div style={{display:"flex", gap:8, alignItems:"center"}}>
                            <span style={{fontSize:"0.62rem", color:"var(--dim)", width:60}}>Regime</span>
                            <select value={universeRegime} onChange={e => setUniverseRegime(e.target.value as "NORMAL"|"CAUTION"|"SHOCK")}
                              style={{background:"var(--p1)", color:"var(--text)", border:"1px solid var(--border)", fontSize:"0.65rem", padding:"2px 4px", flex:1}}>
                              <option value="NORMAL">NORMAL</option>
                              <option value="CAUTION">CAUTION</option>
                              <option value="SHOCK">SHOCK</option>
                            </select>
                          </div>
                          <div style={{display:"flex", gap:8, alignItems:"center"}}>
                            <span style={{fontSize:"0.62rem", color:"var(--dim)", width:60}}>Top N</span>
                            <input value={universeTopN} onChange={e => setUniverseTopN(e.target.value)}
                              style={{background:"var(--p1)", color:"var(--text)", border:"1px solid var(--border)", fontSize:"0.65rem", padding:"2px 4px", flex:1, width:40}} />
                          </div>
                          <div style={{display:"flex", gap:8, alignItems:"center"}}>
                            <span style={{fontSize:"0.62rem", color:"var(--dim)", width:60}}>Source</span>
                            <select value={universeSource} onChange={e => setUniverseSource(e.target.value as "auto"|"manual"|"ibkr_settings")}
                              style={{background:"var(--p1)", color:"var(--text)", border:"1px solid var(--border)", fontSize:"0.65rem", padding:"2px 4px", flex:1}}>
                              <option value="ibkr_settings">ibkr_settings</option>
                              <option value="auto">auto</option>
                              <option value="manual">manual</option>
                            </select>
                          </div>
                          {universeSource === "manual" && (
                            <div style={{display:"flex", gap:8, alignItems:"center"}}>
                              <span style={{fontSize:"0.62rem", color:"var(--dim)", width:60}}>Symbols</span>
                              <input value={universeSymbols} onChange={e => setUniverseSymbols(e.target.value)}
                                placeholder="SPY,QQQ,AAPL,..."
                                style={{background:"var(--p1)", color:"var(--text)", border:"1px solid var(--border)", fontSize:"0.65rem", padding:"2px 4px", flex:1}} />
                            </div>
                          )}
                          <div style={{fontSize:"0.58rem", color:"var(--dim)", marginTop:2}}>
                            batch: {universeLatest?.batch_id?.slice(0,8) ?? "—"} · size: {universeLatest?.universe_size ?? "N/D"} · {universeLatest?.created_at_utc ? fmtTs(universeLatest.created_at_utc) : "mai"}
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="lc-action-bar">
                      <button className="btn btn-primary" onClick={() => void doScanFull()} disabled={oppScanBusy}>
                        {oppScanBusy ? "⏳ scan..." : "▶ Scan completo"}
                      </button>
                      <button className="btn btn-ghost" onClick={refreshAll} disabled={busy}>⟳</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── ANTE / BRIEFING ── Step 5: Checklist + Narratore ────────── */}
          {centerPhase === "ante" && anteSubTab === "briefing" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 5 — BRIEFING</span>
                <span className="lc-step-title">Operatore pronto all'apertura</span>
                <span className="lc-step-sub">10 min prima del mercato</span>
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Checklist apertura</div>
                  <ul className="lc-checklist">
                    <li className={`lc-check-item ${sessionStatus?.enabled ? "pass" : "fail"}`}>
                      <span className="lc-check-icon">{sessionStatus?.enabled ? "✅" : "❌"}</span>
                      <span className="lc-check-name">Scheduler sessioni</span>
                      <span className="lc-check-val">{sessionStatus?.enabled ? "ON" : "OFF"}</span>
                    </li>
                    <li className={`lc-check-item ${ibkrStatus?.connected ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{ibkrStatus?.connected ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">Connessione IBKR</span>
                      <span className="lc-check-val">{ibkrStatus?.connected ? `LIVE ${ibkrStatus.source_system}` : "DISCONNESSO"}</span>
                    </li>
                    <li className={`lc-check-item ${ibwrState === "ON" ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{ibwrState === "ON" ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">Observer Telegram</span>
                      <span className="lc-check-val">{ibwrState}</span>
                    </li>
                    <li className={`lc-check-item ${briefingList.length > 0 ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{briefingList.length > 0 ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">Briefing disponibile</span>
                      <span className="lc-check-val">{briefingList.length > 0 ? `${briefingList.length} file` : "nessuno"}</span>
                    </li>
                    <li className={`lc-check-item ${premarketRegime === "NORMAL" ? "pass" : premarketRegime === "CAUTION" ? "warn" : "fail"}`}>
                      <span className="lc-check-icon">{premarketRegime === "NORMAL" ? "✅" : premarketRegime === "CAUTION" ? "⚠️" : "🛑"}</span>
                      <span className="lc-check-name">Regime del giorno</span>
                      <span className="lc-check-val">{premarketRegime} · sizing {premarketRegime === "NORMAL" ? "100%" : premarketRegime === "CAUTION" ? "50%" : "0%"}</span>
                    </li>
                    <li className={`lc-check-item ${goGate?.pass ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{goGate?.pass ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">Gate Go/No-Go</span>
                      <span className="lc-check-val">{goGate?.pass ? "PASS" : "FAIL"}</span>
                    </li>
                    <li className={`lc-check-item ${!(sysStatus?.kill_switch_active) ? "pass" : "fail"}`}>
                      <span className="lc-check-icon">{sysStatus?.kill_switch_active ? "🛑" : "✅"}</span>
                      <span className="lc-check-name">Kill switch</span>
                      <span className="lc-check-val">{sysStatus?.kill_switch_active ? "ATTIVO — blocca ordini" : "OFF"}</span>
                    </li>
                  </ul>
                  <div style={{marginTop:14}}>
                    <div className="lc-panel-title">Posizioni aperte</div>
                    <div className="lc-kpi-grid">
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Exit urgenti</div>
                        <div className={`lc-kpi-value ${urgentExits.length > 0 ? "sev-warn" : "sev-ok"}`}>{urgentExits.length}</div>
                        <div className="lc-kpi-sub">score ≥ 5</div>
                      </div>
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Wheel posizioni</div>
                        <div className="lc-kpi-value sev-data">{wheelPositions?.positions?.length ?? 0}</div>
                        <div className="lc-kpi-sub">attive</div>
                      </div>
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Net Liq</div>
                        <div className="lc-kpi-value sev-ok">
                          {ibkrAccount?.net_liquidation != null ? `€${ibkrAccount.net_liquidation.toLocaleString("it-IT", {maximumFractionDigits:0})}` : "N/D"}
                        </div>
                        <div className="lc-kpi-sub">conto IBKR</div>
                      </div>
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Segnali pronti</div>
                        <div className={`lc-kpi-value ${premarketReadyCount > 0 ? "sev-ok" : "sev-neutral"}`}>{premarketReadyCount}</div>
                        <div className="lc-kpi-sub">da presentare</div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">WAR ROOM — apertura sessione</span>
                  </div>
                  <div className="lc-screen-body">
                    <div className="lc-screen-row"><span className="lc-dim">scheduler</span><span className={sessionStatus?.enabled ? "sev-ok" : "sev-warn"}>{sessionStatus?.enabled ? "ON" : "OFF"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">ibkr</span><span className={ibkrStatus?.connected ? "sev-ok" : "sev-warn"}>{ibkrStatus?.connected ? "LIVE" : "OFFLINE"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">regime</span><span className={sevClassForRegime(premarketRegime)}>{premarketRegime}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">segnali_pronti</span><span className="sev-data">{premarketReadyCount}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">kill_switch</span><span className={sysStatus?.kill_switch_active ? "sev-error" : "sev-ok"}>{sysStatus?.kill_switch_active ? "ACTIVE" : "off"}</span></div>
                    {sessionStatus?.next_morning && <div className="lc-screen-row"><span className="lc-dim">next_morning</span><span className="sev-meta">{sessionStatus.next_morning.replace("T"," ").slice(0,16)}</span></div>}
                    {sessionStatus?.last_morning && <div className="lc-screen-row"><span className="lc-dim">last_morning</span><span className="sev-meta">{sessionStatus.last_morning.replace("T"," ").slice(0,16)}</span></div>}
                    <div className="lc-screen-section">
                      <div className="lc-screen-row"><span className="lc-dim">NARRATORE</span><span className={briefingPlaying ? "sev-ok" : "sev-neutral"}>{briefingPlaying ? "▶ PLAYING" : "■ STOP"}</span></div>
                      <div className="lc-screen-row"><span className="lc-dim">track</span><span className="sev-meta" style={{fontSize:"0.6rem", maxWidth:"120px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{briefingLabel}</span></div>
                      <div className="lc-screen-row"><span className="lc-dim">archivio</span><span className="sev-data">{briefingList.length} file</span></div>
                    </div>
                    <div className="lc-action-bar">
                      <button className="btn btn-primary"
                        onClick={briefingPlaying ? doBriefingStop : doBriefingPlay}
                        disabled={!apiOnline || (!briefingPlaying && briefingList.length === 0)}>
                        {briefingPlaying ? "■ STOP" : "▶ PLAY"}
                      </button>
                      <button className="btn btn-ghost" onClick={() => void doBriefingGenerate()} disabled={briefingBusy || !apiOnline}>
                        {briefingBusy ? "..." : "⊕ Genera"}
                      </button>
                      <button className="btn btn-ghost" onClick={() => void doRunSession("morning")} disabled={sessionStatus?.running || !apiOnline}>
                        ▶ Morning
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── OP / TRADING ── Steps 6-15: Candidati + Execution + Exit ── */}
          {centerPhase === "op" && opSubTab === "trading" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 6–15 — TRADING</span>
              </div>
              {/* ══ KPI BAR — blocchi operativi, cliccabili + pinnabili ══ */}
              {(() => {
                const kpiToggle = (id: string) => setKpiExpanded(v => v === id ? null : id);
                const kpiPin = (id: string, e: React.MouseEvent) => {
                  e.stopPropagation();
                  setPinnedKpis(v => v.includes(id) ? v.filter(x => x !== id) : [...v, id]);
                };
                const kpiCard = (
                  id: string,
                  label: string,
                  value: React.ReactNode,
                  sub: string,
                  subTooltip: string,
                  accent: string,
                  detail: React.ReactNode | null,
                  compact?: boolean,   // versione compatta per colonna destra
                ) => {
                  const open = !compact && kpiExpanded === id;
                  const pinned = pinnedKpis.includes(id);
                  return (
                    <div key={id} onClick={() => !compact && detail && kpiToggle(id)}
                      style={{
                        background:"var(--p2)", border:`1px solid ${open ? accent + "55" : pinned && !compact ? accent + "33" : "var(--border)"}`,
                        borderRadius:4, padding: compact ? "6px 8px" : "7px 10px",
                        width:"100%", boxSizing:"border-box",
                        cursor: detail && !compact ? "pointer" : "default",
                        transition:"border-color 0.15s",
                        position:"relative",
                      }}>
                      {/* Pin icon — top-right */}
                      {!compact && (
                        <span onClick={e => kpiPin(id, e)}
                          title={pinned ? "Rimuovi da Posizioni ▶" : "Fissa in Posizioni ▶"}
                          style={{
                            position:"absolute", top:4, right:6,
                            fontSize:"0.65rem", cursor:"pointer",
                            color: pinned ? accent : "#555",
                            userSelect:"none",
                            transition:"color 0.15s",
                          }}
                          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = pinned ? "#fff" : accent; }}
                          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = pinned ? accent : "#555"; }}>
                          {pinned ? "◆" : "◇"}
                        </span>
                      )}
                      {compact && (
                        <span onClick={e => kpiPin(id, e)}
                          title="Rimuovi dalla colonna destra"
                          style={{float:"right", fontSize:"0.6rem", cursor:"pointer", color:"#888", userSelect:"none"}}>
                          ✕
                        </span>
                      )}
                      <div style={{fontSize: compact ? "0.55rem" : "0.58rem", color:"#777", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:2}}>{label}</div>
                      <div style={{fontSize: compact ? "0.85rem" : "1rem", fontWeight:700, color: accent, lineHeight:1.1, marginBottom:2}}>{value}</div>
                      <div style={{fontSize:"0.58rem", color:"#777"}} title={subTooltip}>
                        {sub}
                        {!compact && detail ? <span style={{marginLeft:4, color:"#777"}}>{open ? "▲" : "▼"}</span> : null}
                      </div>
                      {open && detail && (
                        <div onClick={e => e.stopPropagation()}
                          style={{marginTop:8, paddingTop:8, borderTop:"1px solid #222", fontSize:"0.65rem", color:"var(--dim)"}}>
                          {detail}
                        </div>
                      )}
                    </div>
                  );
                };
                // Definizioni KPI — usate sia nella barra che nella colonna destra (pinned)
                const kpiDefs: Array<{id:string, label:string, value:React.ReactNode, sub:string, subTooltip:string, accent:string, detail:React.ReactNode|null}> = [
                  {
                    id:"gate", label:"Gate Go/No-Go",
                    value: goGate?.pass ? "GO ✓" : "NO-GO",
                    sub:"accesso mercato", subTooltip:"Autorizzazione sistema ad operare. FAIL blocca nuovi ordini.",
                    accent: goGate?.pass ? "#4ade80" : "#f87171",
                    detail: goGate && !goGate.pass && goGate.reasons.length > 0
                      ? <>{goGate.reasons.map((r,i) => <div key={i}>· {r}</div>)}</>
                      : goGate?.pass ? <div style={{color:"#4ade80"}}>Tutti i controlli superati</div> : null,
                  },
                  {
                    id:"regime", label:"Regime · Sizing",
                    value: premarketRegime ?? "—",
                    sub: premarketRegime === "NORMAL" ? "sizing 100%" : premarketRegime === "CAUTION" ? "sizing 50%" : premarketRegime === "SHOCK" ? "sizing 0%" : "—",
                    subTooltip:"Stato di mercato rilevato dal classificatore HMM. CAUTION dimezza il sizing. SHOCK blocca tutto.",
                    accent: premarketRegime === "NORMAL" ? "#4ade80" : premarketRegime === "CAUTION" ? "#fbbf24" : "#f87171",
                    detail:<><div>NORMAL → sizing 100%, tutte le strategie</div><div>CAUTION → sizing 50%, solo spread stretti</div><div>SHOCK → sizing 0%, nessun nuovo trade</div></>,
                  },
                  {
                    id:"finestra", label:"Finestra operativa",
                    value:"10:00–11:30",
                    sub:"evita 09:30–09:45", subTooltip:"Fascia oraria ottimale per esecuzione (EST). Evitare i primi 15 min per spread più ampi.",
                    accent:"#a78bfa",
                    detail:<><div>Fascia ottimale: 10:00–11:30 EST</div><div>Evitare: 09:30–09:45 (apertura)</div><div>Seconda finestra: 14:00–15:00 EST</div></>,
                  },
                  {
                    id:"exits", label:"Exit urgenti",
                    value: urgentExits.length,
                    sub: urgentExits.length > 0 ? "attenzione richiesta" : "nessuna azione",
                    subTooltip:"Posizioni che superano la soglia di score di uscita (≥5). Richiedono revisione immediata.",
                    accent: urgentExits.length > 0 ? "#fbbf24" : "#4ade80",
                    detail: urgentExits.length > 0
                      ? <>{urgentExits.map((c,i) => <div key={i}>{c.symbol} {c.right ?? ""} {c.strike ?? ""} — score {c.exit_score}</div>)}</>
                      : null,
                  },
                  {
                    id:"trades", label:"Trades chiusi",
                    value: sysStatus?.n_closed_trades ?? 0,
                    sub:"paper journal", subTooltip:"Operazioni chiuse nel journal paper trading. Soglia Kelly: 50 trade.",
                    accent:"#60a5fa",
                    detail:<><div>Kelly gate: {(sysStatus?.n_closed_trades ?? 0) >= 50 ? "✓ sbloccato" : `✗ mancano ${50 - (sysStatus?.n_closed_trades ?? 0)} trade`}</div><div style={{marginTop:4}}>Per dettagli → tab METRICHE</div></>,
                  },
                ];
                // KPI bar: 2-column grid aligned with lc-body (1fr 1fr, gap:12)
                // Each column = inner grid of 3 slots; empty slots = faded placeholder
                const SLOTS = 3, GROUPS = 2, PER_ROW = SLOTS * GROUPS;
                const nRows = Math.max(1, Math.ceil(kpiDefs.length / PER_ROW));
                const kpiGroups: React.ReactNode[] = [];
                for (let row = 0; row < nRows; row++) {
                  for (let g = 0; g < GROUPS; g++) {
                    const base = row * PER_ROW + g * SLOTS;
                    const isLastGroup = g === GROUPS - 1;
                    kpiGroups.push(
                      <div key={`g${row}-${g}`} style={{
                        display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:6,
                        borderRight: isLastGroup ? "none" : "1px solid var(--border)",
                      }}>
                        {Array.from({length: SLOTS}).map((_, s) => {
                          const k = kpiDefs[base + s];
                          if (k) return kpiCard(k.id, k.label, k.value, k.sub, k.subTooltip, k.accent, k.detail);
                          return <div key={`ph${base+s}`} style={{
                            border:"1px dashed #2a2a2a",
                            borderRadius:4, minHeight:52,
                          }} />;
                        })}
                      </div>
                    );
                  }
                }
                return (
                  <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, padding:"8px 0 6px", borderBottom:"1px solid var(--border)"}}>
                    {kpiGroups}
                  </div>
                );
              })()}

              <div className="lc-body">
                <div className="lc-panel" style={{overflowY:"auto"}}>
                  {/* ── Segnali candidati ── */}
                  {/* Header segnali + tasti filtro score */}
                  <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:6}}>
                    <span className="lc-panel-title" style={{margin:0}}>
                      SEGNALI — filtri duri + score
                      <span style={{fontWeight:400, marginLeft:8, fontSize:"0.68rem"}}>
                        <span style={{color:"#888"}} title="Totale candidati">({premarketRows.length}</span>
                        <span style={{color:"#777", margin:"0 2px"}}>·</span>
                        <span style={{color:"#4ade80"}} title="Score ≥65 — ottimi">{premarketRows.filter(c => (c.scorePct ?? 0) >= 65).length}</span>
                        <span style={{color:"#777", margin:"0 2px"}}>·</span>
                        <span style={{color:"#fbbf24"}} title="Score 50–64 — usabili">{premarketRows.filter(c => (c.scorePct ?? 0) >= 50 && (c.scorePct ?? 0) < 65).length}</span>
                        <span style={{color:"#777", margin:"0 2px"}}>·</span>
                        <span style={{color:"#f87171"}} title="Score <50 — insufficienti">{premarketRows.filter(c => (c.scorePct ?? 0) < 50).length}</span>
                        <span style={{color:"#888"}}>)</span>
                      </span>
                    </span>
                    <button className="btn btn-ghost" style={{fontSize:"0.6rem", padding:"1px 6px"}} onClick={refreshAll} disabled={busy}>⟳</button>
                  </div>
                  {/* ── Filtri SEGNALI — collassabili ── */}
                  {(() => {
                    const lcItems = signalLifecycle?.signals ?? [];
                    const lcCounts = {
                      all: lcItems.length,
                      new: lcItems.filter(s => s.state === "NEW").length,
                      confirmed: lcItems.filter(s => s.state === "CONFIRMED").length,
                      dead: lcItems.filter(s => s.state === "DEAD").length,
                    };
                    const KNOWN = ["WHEEL","BULL_PUT","IRON_CONDOR","CALENDAR","PMCC_CALENDAR","HEDGE_ACTIVE"];
                    const extra = Array.from(new Set(
                      premarketRows.map(c => c.strategy).filter((s): s is string => !!s && !KNOWN.includes(s))
                    )).sort();
                    const strategies = ["tutte", ...KNOWN, ...extra];
                    const stratCount = (s: string) => s === "tutte" ? premarketRows.length
                      : premarketRows.filter(c => c.strategy === s).length;
                    const activeCount =
                      (lifecycleFilter !== "all" ? 1 : 0) +
                      (scoreFilter !== "all" ? 1 : 0) +
                      (segnaliStrategyFilter !== "tutte" ? 1 : 0) +
                      ((segnaliFrom || segnaliTo) ? 1 : 0);
                    const filterBtnStyle = (active: boolean, color: string, hasData = true) => ({
                      fontSize:"0.6rem" as const, padding:"2px 7px", borderRadius:3,
                      cursor: hasData ? "pointer" as const : "default" as const,
                      border:`1px solid ${active ? color : hasData ? "#3d3d3d" : "#252525"}`,
                      background: active ? `${color}22` : "transparent",
                      color: active ? color : hasData ? "#888" : "#3a3a3a",
                      fontWeight: active ? 600 : 400,
                      transition:"all 0.15s",
                    });
                    return (
                      <div style={{marginBottom:6}}>
                        {/* header collassabile */}
                        <div style={{
                          display:"flex", alignItems:"center", gap:5, cursor:"pointer",
                          padding:"3px 0", borderBottom:"1px solid #1e1e1e", marginBottom: segnaliFiltersOpen ? 6 : 0,
                        }} onClick={() => setSegnaliFiltersOpen(v => !v)}>
                          <span style={{fontSize:"0.62rem", color:"#888"}}>🔍</span>
                          <span style={{
                            fontSize:"0.56rem", textTransform:"uppercase", letterSpacing:"0.06em", flex:1,
                            color: activeCount > 0 ? "#60a5fa" : "#555",
                            fontWeight: activeCount > 0 ? 600 : 400,
                          }}>
                            FILTRI{activeCount > 0 ? ` · ${activeCount} attiv${activeCount === 1 ? "o" : "i"}` : ""}
                          </span>
                          <span style={{fontSize:"0.5rem", color:"#777"}}>{segnaliFiltersOpen ? "▾" : "▸"}</span>
                        </div>

                        {segnaliFiltersOpen && (<>
                          {/* stato lifecycle */}
                          <div style={{display:"flex", alignItems:"center", gap:4, marginBottom:4, flexWrap:"wrap"}}>
                            <span style={{fontSize:"0.5rem", color:"#888", textTransform:"uppercase",
                              letterSpacing:"0.06em", minWidth:32, flexShrink:0}}>stato:</span>
                            {([
                              {id:"all" as const,       label:"TUTTI",     color:"#888"},
                              {id:"new" as const,       label:"NEW",       color:"#4ade80"},
                              {id:"confirmed" as const, label:"CONFIRMED", color:"#60a5fa"},
                              {id:"dead" as const,      label:"DEAD",      color:"#f87171"},
                            ]).map(({id, label, color}) => {
                              const n = lcCounts[id];
                              return (
                                <button key={id} onClick={() => setLifecycleFilter(id)}
                                  style={filterBtnStyle(lifecycleFilter === id, color, id === "all" || n > 0)}>
                                  {label} <span style={{opacity:0.7}}>({n})</span>
                                </button>
                              );
                            })}
                            {lifecycleLoading && <span style={{fontSize:"0.5rem", color:"var(--dim)", marginLeft:4}}>…</span>}
                            {signalLifecycle?.scan_dates?.length && (
                              <span style={{fontSize:"0.48rem", color:"#888", marginLeft:"auto"}}
                                title={`Batch: ${signalLifecycle.scan_dates.join(", ")}`}>
                                {signalLifecycle.scan_dates.length} scan
                              </span>
                            )}
                          </div>

                          {/* score */}
                          <div style={{display:"flex", alignItems:"center", gap:4, marginBottom:4, flexWrap:"wrap"}}>
                            <span style={{fontSize:"0.5rem", color:"#888", textTransform:"uppercase",
                              letterSpacing:"0.06em", minWidth:32, flexShrink:0}}>score:</span>
                            {(["all","high","mid","low"] as const).map(f => {
                              const label = {all:"TUTTO", high:"≥65", mid:"50–64", low:"<50"}[f];
                              const color = {all:"#888", high:"#4ade80", mid:"#fbbf24", low:"#f87171"}[f];
                              const count = f === "all" ? premarketRows.length
                                : f === "high" ? premarketRows.filter(c => (c.scorePct ?? 0) >= 65).length
                                : f === "mid"  ? premarketRows.filter(c => (c.scorePct ?? 0) >= 50 && (c.scorePct ?? 0) < 65).length
                                : premarketRows.filter(c => (c.scorePct ?? 0) < 50).length;
                              return (
                                <button key={f} onClick={() => setScoreFilter(f)}
                                  style={filterBtnStyle(scoreFilter === f, color)}>
                                  {label} <span style={{opacity:0.7}}>({count})</span>
                                </button>
                              );
                            })}
                          </div>

                          {/* strategia */}
                          <div style={{display:"flex", alignItems:"center", gap:4, marginBottom:4, flexWrap:"wrap"}}>
                            <span style={{fontSize:"0.5rem", color:"#888", textTransform:"uppercase",
                              letterSpacing:"0.06em", minWidth:32, flexShrink:0}}>str:</span>
                            {strategies.map(s => {
                              const n = stratCount(s);
                              const hasData = s === "tutte" || n > 0;
                              return (
                                <button key={s} onClick={() => setSegnaliStrategyFilter(s)}
                                  style={filterBtnStyle(segnaliStrategyFilter === s, "#60a5fa", hasData)}>
                                  {s === "tutte" ? "TUTTE" : s}
                                  {s !== "tutte" && <span style={{opacity:0.5, marginLeft:2}}>({n})</span>}
                                </button>
                              );
                            })}
                          </div>

                          {/* data scan (freschezza batch) */}
                          <div style={{display:"flex", alignItems:"center", gap:4, marginBottom:4, flexWrap:"wrap"}}>
                            <span style={{fontSize:"0.5rem", color:"#888", textTransform:"uppercase",
                              letterSpacing:"0.06em", minWidth:32, flexShrink:0}}>scan:</span>
                            <span style={{fontSize:"0.55rem", color:"var(--dim)"}}>dal</span>
                            <input type="date" value={segnaliFrom} onChange={e => setSegnaliFrom(e.target.value)}
                              style={{fontSize:"0.58rem", background:"var(--p2)", color:"var(--text)",
                                border:"1px solid var(--border)", borderRadius:2, padding:"1px 3px", width:96}} />
                            <span style={{fontSize:"0.55rem", color:"var(--dim)"}}>al</span>
                            <input type="date" value={segnaliTo} onChange={e => setSegnaliTo(e.target.value)}
                              style={{fontSize:"0.58rem", background:"var(--p2)", color:"var(--text)",
                                border:"1px solid var(--border)", borderRadius:2, padding:"1px 3px", width:96}} />
                            {(segnaliFrom || segnaliTo) && (
                              <button className="btn btn-ghost" style={{fontSize:"0.55rem", padding:"0 4px"}}
                                onClick={() => { setSegnaliFrom(""); setSegnaliTo(""); }}>✕</button>
                            )}
                          </div>
                        </>)}
                      </div>
                    );
                  })()}

                  {/* ── Metrics strip SEGNALI ── */}
                  {(() => {
                    const total = premarketRows.length;
                    const avgScore = total > 0
                      ? premarketRows.reduce((s, c) => s + (c.scorePct ?? 0), 0) / total
                      : null;
                    const lc = signalLifecycle?.signals ?? [];
                    const nNew  = lc.filter(s => s.state === "NEW").length;
                    const nConf = lc.filter(s => s.state === "CONFIRMED").length;
                    const nDead = lc.filter(s => s.state === "DEAD").length;
                    const mc = (label: string, val: string, col: string, tip?: string) => (
                      <div key={label} title={tip} style={{
                        flex:"1 1 0", minWidth:44, height:44, background:"var(--p2)",
                        border:`1px solid ${col}28`, borderRadius:3,
                        display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:2,
                      }}>
                        <div style={{fontSize:"0.46rem", color:"#888", textTransform:"uppercase", letterSpacing:"0.05em", lineHeight:1, whiteSpace:"nowrap"}}>{label}</div>
                        <div style={{fontSize:"0.76rem", fontWeight:700, color:col, lineHeight:1}}>{val}</div>
                      </div>
                    );
                    return (
                      <div style={{display:"flex", gap:4, marginBottom:8}}>
                        {mc("totali", total > 0 ? String(total) : "—", "#888", "Segnali nell'ultimo scan")}
                        {mc("score medio", avgScore != null ? `${avgScore.toFixed(0)}%` : "—", avgScore != null && avgScore >= 65 ? "#4ade80" : avgScore != null && avgScore >= 50 ? "#fbbf24" : "#f87171", "Score medio dei segnali filtrati")}
                        {mc("NEW", nNew > 0 ? String(nNew) : "—", "#4ade80", "Segnali nuovi (solo nell'ultimo scan)")}
                        {mc("CONF.", nConf > 0 ? String(nConf) : "—", "#60a5fa", "Segnali confermati (≥2 scan consecutivi)")}
                        {mc("DEAD", nDead > 0 ? String(nDead) : "—", "#f87171", "Segnali scomparsi dall'ultimo scan")}
                        {[0,1,2].map(i => <div key={`ph${i}`} style={{flex:"1 1 0", minWidth:44, height:44, border:"1px dashed #252525", borderRadius:3}} />)}
                      </div>
                    );
                  })()}

                  {/* ── Tabella segnali — sempre visibile ── */}
                  {(() => {
                    // freschezza: se date impostate, verifica che premarketScanAt sia nel range
                    const scanDate = premarketScanAt?.slice(0, 10) ?? null;
                    const scanOutOfRange = !!(
                      (segnaliFrom && scanDate && scanDate < segnaliFrom) ||
                      (segnaliTo   && scanDate && scanDate > segnaliTo)
                    );
                    // mappa lifecycle per (symbol+strategy)
                    const lcMap = new Map<string, SignalLifecycleItem>();
                    (signalLifecycle?.signals ?? []).forEach(s => lcMap.set(`${s.symbol}|${s.strategy}`, s));
                    // applica score + strategia + lifecycle
                    const liveRows = scanOutOfRange ? [] : premarketRows.filter(c => {
                      const scoreOk =
                        scoreFilter === "all"  ? true :
                        scoreFilter === "high" ? (c.scorePct ?? 0) >= 65 :
                        scoreFilter === "mid"  ? (c.scorePct ?? 0) >= 50 && (c.scorePct ?? 0) < 65 :
                        (c.scorePct ?? 0) < 50;
                      const stratOk = segnaliStrategyFilter === "tutte" || c.strategy === segnaliStrategyFilter;
                      const lc = lcMap.get(`${c.symbol}|${c.strategy}`);
                      const lcOk = lifecycleFilter === "all" || lifecycleFilter === "dead" ? true
                        : lifecycleFilter === "new"       ? lc?.state === "NEW"
                        : lifecycleFilter === "confirmed" ? lc?.state === "CONFIRMED"
                        : true;
                      return scoreOk && stratOk && lcOk;
                    });
                    // righe DEAD (dal lifecycle, assenti dall'ultimo scan)
                    const deadRows: SignalLifecycleItem[] = (lifecycleFilter === "all" || lifecycleFilter === "dead")
                      ? (signalLifecycle?.signals ?? []).filter(s =>
                          s.state === "DEAD" &&
                          (segnaliStrategyFilter === "tutte" || s.strategy === segnaliStrategyFilter)
                        )
                      : [];
                    const totalRows = liveRows.length + deadRows.length;
                    // messaggio vuoto
                    const emptyMsg = busy ? "Caricamento…"
                      : scanOutOfRange ? `scan del ${scanDate ?? "?"} fuori dal periodo selezionato`
                      : totalRows === 0 && premarketRows.length === 0 ? "nessun segnale — esegui scan dalla tab ANALISI"
                      : "nessun segnale per i filtri selezionati";
                    // badge stato
                    const lcBadge = (sym: string, str: string) => {
                      const lc = lcMap.get(`${sym}|${str}`);
                      if (!lc) return null;
                      const col = lc.state === "NEW" ? "#4ade80" : lc.state === "CONFIRMED" ? "#60a5fa" : "#f87171";
                      const label = lc.state === "CONFIRMED" ? `×${lc.n_confirmed}` : lc.state;
                      return (
                        <span style={{fontSize:"0.5rem", color:col, border:`1px solid ${col}30`,
                          borderRadius:2, padding:"0 3px", whiteSpace:"nowrap"}}
                          title={`${lc.state} — visto dal ${lc.first_seen}`}>
                          {label}
                        </span>
                      );
                    };
                    const csvSegnali = () => {
                      const cols = ["#","Simbolo","Strategia","Score","Spread%","IVR%","Stato","Prima vista"];
                      const body = [
                        ...liveRows.map((c, i) => {
                          const lc = lcMap.get(`${c.symbol}|${c.strategy}`);
                          return [i+1, c.symbol, c.strategy, c.scorePct?.toFixed(0)??"", c.spreadPct?.toFixed(1)??"", c.ivRankPct?.toFixed(0)??"", lc?.state??"", lc?.first_seen??""].join(",");
                        }),
                        ...deadRows.map(d => ["—",d.symbol,d.strategy,d.score.toFixed(0),d.spread_pct?.toFixed(1)??"","","DEAD",d.first_seen].join(",")),
                      ];
                      const blob = new Blob([[cols.join(","), ...body].join("\n")], {type:"text/csv"});
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a"); a.href=url;
                      a.download=`segnali_${new Date().toISOString().slice(0,10)}.csv`; a.click();
                      URL.revokeObjectURL(url);
                    };
                    return (
                      <>
                      <div style={{overflowX:"auto", maxHeight:220, overflowY:"auto"}}>
                        <table style={{width:"100%", fontSize:"0.68rem", borderCollapse:"collapse"}}>
                          <thead>
                            <tr style={{color:"#888", borderBottom:"1px solid #444"}}>
                              <th style={{textAlign:"left", padding:"2px 4px"}}>#</th>
                              <th style={{textAlign:"left", padding:"2px 4px"}}>Sym</th>
                              <th style={{textAlign:"left", padding:"2px 4px"}}
                                title="Struttura operativa — passa il mouse sulla riga per i dettagli">Str</th>
                              <th style={{textAlign:"right", padding:"2px 4px"}}
                                title="Score composito 0–100 (volatilità · liquidità · R/R · regime). Min operativo: 50">Score</th>
                              <th style={{textAlign:"right", padding:"2px 4px"}}
                                title="Spread bid-ask % del mid. Soglia dura ≤10%">Spr%</th>
                              <th style={{textAlign:"right", padding:"2px 4px"}}
                                title="IV Rank percentile. Soglia dura ≥20">IVR%</th>
                              <th style={{textAlign:"left", padding:"2px 4px"}}>Stato</th>
                              <th style={{padding:"2px 4px"}}></th>
                            </tr>
                          </thead>
                          <tbody>
                            {totalRows === 0 ? (
                              <tr><td colSpan={8} style={{padding:"8px 4px", color:"#888", fontSize:"0.7rem"}}>
                                {emptyMsg}
                              </td></tr>
                            ) : (<>
                              {liveRows.map((c, i) => {
                                const isSelected = selectedItemId != null && (c as any).item_id != null
                                  && selectedItemId === (c as any).item_id;
                                const stratTip: Record<string, string> = {
                                  BULL_PUT:      "Bull Put Spread · vendi put strike basso + compri put strike alto",
                                  IRON_CONDOR:   "Iron Condor · bull put + bear call · profitto in range",
                                  CALENDAR:      "Calendar Spread · decadimento temporale differenziale",
                                  WHEEL:         "Wheel · put venduta → assegnazione → call venduta",
                                  PMCC_CALENDAR: "Poor Man's Covered Call · LEAP + call mensile breve",
                                  HEDGE_ACTIVE:  "Copertura attiva · protezione direzionale portafoglio",
                                };
                                return (
                                  <tr key={i} style={{borderBottom:"1px solid #222",
                                    background: isSelected ? "rgba(74,222,128,0.08)" : undefined}}>
                                    <td style={{padding:"2px 4px", color:"#888"}}>#{i+1}</td>
                                    <td style={{padding:"2px 4px", fontWeight:600}}>{c.symbol}</td>
                                    <td style={{padding:"2px 4px", color:"#888"}}
                                      title={stratTip[c.strategy ?? ""] ?? c.strategy ?? ""}>{c.strategy}</td>
                                    <td style={{padding:"2px 4px", textAlign:"right"}}>
                                      {c.scorePct !== undefined ? (
                                        <span className={c.scorePct >= 65 ? "sev-ok" : c.scorePct >= 50 ? "sev-warn" : "sev-error"}
                                          title={`${c.scorePct.toFixed(0)}/100 — min operativo 50`}>
                                          {c.scorePct.toFixed(0)}<span style={{color:"var(--dim)", fontSize:"0.55rem"}}>/100</span>
                                        </span>
                                      ) : "—"}
                                    </td>
                                    <td style={{padding:"2px 4px", textAlign:"right",
                                      color:c.spreadPct == null || c.spreadPct === 0 ? "var(--dim)" : "#888"}}>
                                      {c.spreadPct != null && c.spreadPct > 0
                                        ? c.spreadPct.toFixed(1)
                                        : <span title="Dato non acquisito">—</span>}
                                    </td>
                                    <td style={{padding:"2px 4px", textAlign:"right",
                                      color:c.ivRankPct == null || c.ivRankPct === 0 ? "var(--dim)" : "#888"}}>
                                      {c.ivRankPct != null && c.ivRankPct > 0
                                        ? c.ivRankPct.toFixed(0)
                                        : <span title="Dato non acquisito">—</span>}
                                    </td>
                                    <td style={{padding:"2px 4px"}}>{lcBadge(c.symbol ?? "", c.strategy ?? "")}</td>
                                    <td style={{padding:"2px 2px"}}>
                                      {(c.spreadPct == null || c.spreadPct === 0 || c.ivRankPct == null || c.ivRankPct === 0) ? (
                                        <span title="Dati incompleti — aggiorna scan"
                                          style={{fontSize:"0.6rem", color:"var(--amber)", padding:"1px 6px"}}>⚠</span>
                                      ) : (
                                        <button className="btn btn-ghost"
                                          style={{fontSize:"0.6rem", padding:"1px 6px", whiteSpace:"nowrap"}}
                                          onClick={() => {
                                            setSymbol(c.symbol ?? "");
                                            setStrategy(c.strategy ?? "BULL_PUT");
                                            setPayload(JSON.stringify({symbol:c.symbol, strategy:c.strategy, legs:[]}, null, 2));
                                            setSelectedItemId((c as any).item_id ?? null);
                                            setOpExecOpen(true);
                                          }}>→ ESEGUI</button>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                              {deadRows.map((d, i) => (
                                <tr key={`dead-${i}`} style={{borderBottom:"1px solid #1a1a1a", opacity:0.45}}>
                                  <td style={{padding:"2px 4px", color:"#777"}}>—</td>
                                  <td style={{padding:"2px 4px", color:"#777", fontWeight:600}}>{d.symbol}</td>
                                  <td style={{padding:"2px 4px", color:"#888"}}>{d.strategy}</td>
                                  <td style={{padding:"2px 4px", textAlign:"right", color:"#888"}}>
                                    {d.score > 0 ? d.score.toFixed(0) : "—"}
                                  </td>
                                  <td style={{padding:"2px 4px", textAlign:"right", color:"#888"}}>
                                    {d.spread_pct != null ? d.spread_pct.toFixed(1) : "—"}
                                  </td>
                                  <td style={{padding:"2px 4px", textAlign:"right", color:"#888"}}>—</td>
                                  <td style={{padding:"2px 4px"}}>
                                    <span style={{fontSize:"0.5rem", color:"#f87171", border:"1px solid #f8717130",
                                      borderRadius:2, padding:"0 3px"}}
                                      title={`Scomparso il ${d.last_seen} — era presente dal ${d.first_seen}`}>
                                      DEAD
                                    </span>
                                  </td>
                                  <td style={{padding:"2px 4px"}}></td>
                                </tr>
                              ))}
                            </>)}
                          </tbody>
                        </table>
                      </div>
                      <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginTop:6}}>
                        <button className="btn btn-ghost" style={{fontSize:"0.55rem", padding:"1px 5px"}}
                          onClick={csvSegnali} title="Scarica CSV dei segnali filtrati">⬇ CSV</button>
                        <span style={{fontSize:"0.58rem", color:"var(--dim)"}}
                          title="Spread% e IVR% vuoti = mercati chiusi o scan non ancora aggiornato.">
                          {premarketScanAt
                            ? `scan: ${premarketScanAt.slice(0,10)} · Spr%/IVR% vuoti = mercati chiusi`
                            : "⚠ scan non ancora eseguito"}
                        </span>
                      </div>
                      </>
                    );
                  })()}

                </div>

                {/* ── Colonna destra — stesso pattern strutturale di SEGNALI ── */}
                <div className="lc-panel" style={{overflowY:"auto"}}>
                  {/* blocchi pinnati — strip compatta */}
                  {pinnedKpis.length > 0 && (() => {
                    const pinnedData: Record<string, {label:string, value:React.ReactNode, sub:string, accent:string}> = {
                      gate:     { label:"Gate Go/No-Go", value: goGate?.pass ? "GO ✓" : "NO-GO",   sub:"accesso mercato",  accent: goGate?.pass ? "#4ade80" : "#f87171" },
                      regime:   { label:"Regime · Sizing", value: premarketRegime ?? "—",          sub: premarketRegime === "NORMAL" ? "100%" : premarketRegime === "CAUTION" ? "50%" : premarketRegime === "SHOCK" ? "0%" : "—",  accent: premarketRegime === "NORMAL" ? "#4ade80" : premarketRegime === "CAUTION" ? "#fbbf24" : "#f87171" },
                      exits:    { label:"Exit urgenti",  value: urgentExits.length,                sub: urgentExits.length > 0 ? "⚠ attenzione" : "ok",  accent: urgentExits.length > 0 ? "#fbbf24" : "#4ade80" },
                      trades:   { label:"Trades chiusi", value: sysStatus?.n_closed_trades ?? 0,  sub:"paper journal",    accent:"#60a5fa" },
                      finestra: { label:"Finestra",      value:"10:00–11:30",                      sub:"evita 09:30–09:45", accent:"#a78bfa" },
                    };
                    return (
                      <div style={{display:"flex", flexDirection:"column", gap:4, marginBottom:10, paddingBottom:10, borderBottom:"1px solid var(--border)"}}>
                        {pinnedKpis.map(id => {
                          const d = pinnedData[id];
                          if (!d) return null;
                          return (
                            <div key={id} style={{background:"var(--p2)", border:`1px solid ${d.accent}22`,
                              borderRadius:3, padding:"5px 8px", display:"flex", alignItems:"center", gap:8}}>
                              <div style={{flex:1, minWidth:0}}>
                                <div style={{fontSize:"0.55rem", color:"#777", textTransform:"uppercase", letterSpacing:"0.05em"}}>{d.label}</div>
                                <div style={{fontSize:"0.9rem", fontWeight:700, color:d.accent, lineHeight:1.1}}>{d.value}</div>
                                <div style={{fontSize:"0.55rem", color:"#888"}}>{d.sub}</div>
                              </div>
                              <span onClick={() => setPinnedKpis(v => v.filter(x => x !== id))}
                                title="Rimuovi"
                                style={{fontSize:"0.65rem", color:"#777", cursor:"pointer", padding:"2px 4px", userSelect:"none"}}
                                onMouseEnter={e => (e.currentTarget.style.color = "#888")}
                                onMouseLeave={e => (e.currentTarget.style.color = "#555")}>✕</span>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}

                  {/* ── Titolo ── */}
                  <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:6}}>
                    <div style={{display:"flex", flexDirection:"column", gap:2, minWidth:0}}>
                      <span className="lc-panel-title" style={{margin:0}}>
                        POSIZIONI
                        {/* contatori assoluti — INDIPENDENTI dai filtri */}
                        {(() => {
                          const chiusi = storicoTrades.filter(t => !!t.exit_ts_utc);
                          const tot  = chiusi.length;
                          const pos  = chiusi.filter(t => (t.pnl ?? 0) >= 0).length;
                          const neg  = chiusi.filter(t => (t.pnl ?? 0) <  0).length;
                          const ape  = storicoTrades.filter(t => !t.exit_ts_utc).length;
                          const live = ibkrAccount?.positions.length ?? 0;
                          return (
                            <span style={{fontWeight:400, marginLeft:6, fontSize:"0.65rem"}}>
                              <span style={{color:"#777"}}>(</span>
                              <span style={{color:"#999"}} title="Totale trades chiusi (lifetime)">{tot}</span>
                              <span style={{color:"#777"}}>/</span>
                              <span style={{color:"#4ade80"}} title="Trades chiusi positivi (lifetime)">{pos}</span>
                              <span style={{color:"#777"}}>/</span>
                              <span style={{color:"#f87171"}} title="Trades chiusi negativi (lifetime)">{neg}</span>
                              <span style={{color:"#777"}}>/</span>
                              <span style={{color:"#fbbf24"}} title="Trades ancora aperti nel journal">{ape}</span>
                              <span style={{color:"#777"}}>)</span>
                            </span>
                          );
                        })()}
                      </span>
                    </div>
                    <button className="btn btn-ghost" style={{fontSize:"0.6rem", padding:"1px 6px", marginTop:2}}
                      disabled={storicoLoading || ibkrAccountLoading}
                      onClick={() => { void doFetchStorico(); void doFetchIbkrAccount(); }}>
                      {(storicoLoading || ibkrAccountLoading) ? "…" : "⟳"}
                    </button>
                  </div>

                  {/* ── Filtri POSIZIONI — collassabili ── */}
                  {(() => {
                    const KNOWN: string[] = ["WHEEL","BULL_PUT","IRON_CONDOR","CALENDAR","PMCC_CALENDAR","HEDGE_ACTIVE"];
                    const extra = Array.from(new Set(
                      storicoTrades.map(t => t.strategy).filter((s): s is string => !!s && !KNOWN.includes(s))
                    )).sort();
                    const strategies = ["tutte", ...KNOWN, ...extra];
                    const byDateBase = storicoTrades.filter(t => {
                      if (posOutcomeFilter === "aperti") return !t.exit_ts_utc;
                      const d = t.exit_ts_utc?.slice(0,10);
                      return d != null && (!storicoFrom || d >= storicoFrom) && (!storicoTo || d <= storicoTo)
                        && (posOutcomeFilter === "positivi" ? (t.pnl ?? 0) >= 0 : true)
                        && (posOutcomeFilter === "negativi" ? (t.pnl ?? 0) <  0 : true);
                    });
                    const outcomeColors = {tutti:"#888", positivi:"#4ade80", negativi:"#f87171", aperti:"#fbbf24"};
                    const outcomeCounts: Record<"tutti"|"positivi"|"negativi"|"aperti", number> = {
                      tutti:    storicoTrades.filter(t => { const d = t.exit_ts_utc?.slice(0,10); return d != null && (!storicoFrom||d>=storicoFrom) && (!storicoTo||d<=storicoTo); }).length,
                      positivi: storicoTrades.filter(t => { const d = t.exit_ts_utc?.slice(0,10); return d != null && (!storicoFrom||d>=storicoFrom) && (!storicoTo||d<=storicoTo) && (t.pnl??0)>=0; }).length,
                      negativi: storicoTrades.filter(t => { const d = t.exit_ts_utc?.slice(0,10); return d != null && (!storicoFrom||d>=storicoFrom) && (!storicoTo||d<=storicoTo) && (t.pnl??0)<0; }).length,
                      aperti:   storicoTrades.filter(t => !t.exit_ts_utc).length,
                    };
                    const activeCount =
                      (posOutcomeFilter !== "tutti" ? 1 : 0) +
                      (posStrategyFilter !== "tutte" ? 1 : 0) +
                      ((storicoFrom || storicoTo) ? 1 : 0);
                    const fbs = (active: boolean, color: string, hasData = true) => ({
                      fontSize:"0.6rem" as const, padding:"2px 7px", borderRadius:3,
                      cursor: hasData ? "pointer" as const : "default" as const,
                      border:`1px solid ${active ? color : hasData ? "#3d3d3d" : "#252525"}`,
                      background: active ? `${color}22` : "transparent",
                      color: active ? color : hasData ? "#888" : "#3a3a3a",
                      fontWeight: active ? 600 : 400,
                      transition:"all 0.15s",
                    });
                    return (
                      <div style={{marginBottom:6}}>
                        <div style={{
                          display:"flex", alignItems:"center", gap:5, cursor:"pointer",
                          padding:"3px 0", borderBottom:"1px solid #1e1e1e", marginBottom: posFiltersOpen ? 6 : 0,
                        }} onClick={() => setPosFiltersOpen(v => !v)}>
                          <span style={{fontSize:"0.62rem", color:"#888"}}>🔍</span>
                          <span style={{
                            fontSize:"0.56rem", textTransform:"uppercase", letterSpacing:"0.06em", flex:1,
                            color: activeCount > 0 ? "#60a5fa" : "#555",
                            fontWeight: activeCount > 0 ? 600 : 400,
                          }}>
                            FILTRI{activeCount > 0 ? ` · ${activeCount} attiv${activeCount===1?"o":"i"}` : ""}
                          </span>
                          <span style={{fontSize:"0.5rem", color:"#777"}}>{posFiltersOpen ? "▾" : "▸"}</span>
                        </div>

                        {posFiltersOpen && (<>
                          {/* esito */}
                          <div style={{display:"flex", alignItems:"center", gap:4, marginBottom:4, flexWrap:"wrap"}}>
                            <span style={{fontSize:"0.5rem", color:"#888", textTransform:"uppercase",
                              letterSpacing:"0.06em", minWidth:32, flexShrink:0}}>esito:</span>
                            {(["tutti","positivi","negativi","aperti"] as const).map(f => (
                              <button key={f} onClick={() => setPosOutcomeFilter(f)}
                                style={fbs(posOutcomeFilter === f, outcomeColors[f])}>
                                {{tutti:"TUTTI",positivi:"POSITIVI",negativi:"NEGATIVI",aperti:"APERTI"}[f]}
                                {" "}<span style={{opacity:0.7}}>({outcomeCounts[f]})</span>
                              </button>
                            ))}
                          </div>

                          {/* data */}
                          <div style={{display:"flex", alignItems:"center", gap:4, marginBottom:4, flexWrap:"wrap"}}>
                            <span style={{fontSize:"0.5rem", color:"#888", textTransform:"uppercase",
                              letterSpacing:"0.06em", minWidth:32, flexShrink:0}}>data:</span>
                            <span style={{fontSize:"0.55rem", color:"var(--dim)"}}>dal</span>
                            <input type="date" value={storicoFrom} onChange={e => setStoricoFrom(e.target.value)}
                              style={{fontSize:"0.58rem", background:"var(--p2)", color:"var(--text)",
                                border:"1px solid var(--border)", borderRadius:2, padding:"1px 3px", width:96}} />
                            <span style={{fontSize:"0.55rem", color:"var(--dim)"}}>al</span>
                            <input type="date" value={storicoTo} onChange={e => setStoricoTo(e.target.value)}
                              style={{fontSize:"0.58rem", background:"var(--p2)", color:"var(--text)",
                                border:"1px solid var(--border)", borderRadius:2, padding:"1px 3px", width:96}} />
                            {(storicoFrom || storicoTo) && (
                              <button className="btn btn-ghost" style={{fontSize:"0.55rem", padding:"0 4px"}}
                                onClick={() => { setStoricoFrom(""); setStoricoTo(""); }}>✕</button>
                            )}
                          </div>

                          {/* strategia */}
                          <div style={{display:"flex", alignItems:"center", gap:4, marginBottom:4, flexWrap:"wrap"}}>
                            <span style={{fontSize:"0.5rem", color:"#888", textTransform:"uppercase",
                              letterSpacing:"0.06em", minWidth:32, flexShrink:0}}>str:</span>
                            {strategies.map(s => {
                              const n = s === "tutte" ? byDateBase.length : byDateBase.filter(t => t.strategy === s).length;
                              const hasData = s === "tutte" || n > 0;
                              return (
                                <button key={s} onClick={() => setPosStrategyFilter(s)}
                                  style={fbs(posStrategyFilter === s, "#60a5fa", hasData)}>
                                  {s === "tutte" ? "TUTTE" : s}
                                  {s !== "tutte" && <span style={{opacity:0.5, marginLeft:2}}>({n})</span>}
                                </button>
                              );
                            })}
                          </div>
                        </>)}
                      </div>
                    );
                  })()}

                  {/* ── Metrics strip ── */}
                  {(() => {
                    const chiusi = storicoTrades.filter(t => !!t.exit_ts_utc);
                    const nPos = chiusi.filter(t => (t.pnl ?? 0) >= 0).length;
                    const maxWin  = chiusi.length ? Math.max(...chiusi.map(t => t.pnl ?? 0)) : null;
                    const maxLoss = chiusi.length ? Math.min(...chiusi.map(t => t.pnl ?? 0)) : null;
                    const winPct  = chiusi.length > 0 ? nPos / chiusi.length * 100 : null;
                    const roi     = storicoSummary?.roi_pct ?? null;
                    const dd      = storicoSummary?.max_drawdown_pct ?? null;
                    const cassa   = ibkrAccount?.net_liquidation ?? null;
                    const brokerStatus = ibkrAccount
                      ? (ibkrAccount.connected ? "broker ON" : "broker OFF")
                      : null;
                    const mc = (label: string, val: string, col: string, tip?: string) => (
                      <div key={label} title={tip} style={{
                        flex:"1 1 0", minWidth:44, height:44, background:"var(--p2)",
                        border:`1px solid ${col}28`, borderRadius:3,
                        display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:2,
                      }}>
                        <div style={{fontSize:"0.46rem", color:"#888", textTransform:"uppercase", letterSpacing:"0.05em", lineHeight:1, whiteSpace:"nowrap"}}>{label}</div>
                        <div style={{fontSize:"0.76rem", fontWeight:700, color:col, lineHeight:1}}>{val}</div>
                      </div>
                    );
                    return (
                      <div style={{display:"flex", gap:4, marginBottom:8}}>
                        {mc("cassa", cassa != null ? `€${cassa.toLocaleString("it-IT",{maximumFractionDigits:0})}` : "—", "#888", brokerStatus ?? "Patrimonio netto broker")}
                        {mc("ROI", roi != null ? `${roi>=0?"+":""}${Number(roi).toFixed(1)}%` : "—", (roi??0)>=0?"#4ade80":"#f87171", "Rendimento totale journal")}
                        {mc("▼ maxDown", dd != null ? `${Number(dd).toFixed(1)}%` : "—", "#f87171", "Drawdown massimo dal picco")}
                        {mc("▲ maxWin", maxWin != null ? `+${maxWin.toFixed(0)}` : "—", "#4ade80", "Trade migliore (€)")}
                        {mc("▼ maxLoss", maxLoss != null ? `${maxLoss.toFixed(0)}` : "—", "#f87171", "Trade peggiore (€)")}
                        {mc("win%", winPct != null ? `${winPct.toFixed(0)}%` : "—", winPct != null && winPct>=50?"#4ade80":"#f87171", "Percentuale trade chiusi positivi")}
                        {[0,1].map(i => <div key={`ph${i}`} style={{flex:"1 1 0", minWidth:44, height:44, border:"1px dashed #252525", borderRadius:3}} />)}
                      </div>
                    );
                  })()}

                  {/* ── TABELLA ── applica tutti i filtri: esito + data + strategia ── */}
                  {(() => {
                    const filtered = storicoTrades.filter(t => {
                      // filtro esito
                      if (posOutcomeFilter === "aperti") {
                        if (t.exit_ts_utc) return false;
                      } else {
                        const exitDate = t.exit_ts_utc?.slice(0,10);
                        if (!exitDate) return false;
                        if (storicoFrom && exitDate < storicoFrom) return false;
                        if (storicoTo   && exitDate > storicoTo)   return false;
                        if (posOutcomeFilter === "positivi" && (t.pnl ?? 0) <  0) return false;
                        if (posOutcomeFilter === "negativi" && (t.pnl ?? 0) >= 0) return false;
                      }
                      // filtro strategia
                      if (posStrategyFilter !== "tutte" && t.strategy !== posStrategyFilter) return false;
                      return true;
                    });
                    const nTot   = filtered.length;
                    const nPos   = filtered.filter(t => (t.pnl ?? 0) >= 0).length;
                    const sumPnl = filtered.reduce((s, t) => s + (t.pnl ?? 0), 0);
                    const maxWin  = nTot ? Math.max(...filtered.map(t => t.pnl ?? 0)) : null;
                    const maxLoss = nTot ? Math.min(...filtered.map(t => t.pnl ?? 0)) : null;
                    const winRate = nTot > 0 ? (nPos / nTot * 100) : null;
                    const fmtPnl  = (v: number | null) => v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(0)}`;
                    const pill = (label: string, value: React.ReactNode, accent: string, tip?: string) => (
                      <div key={label} title={tip} style={{
                        flex:"1 1 auto", minWidth:54,
                        background:"var(--p2)", border:`1px solid ${accent}22`,
                        borderRadius:3, padding:"4px 6px",
                      }}>
                        <div style={{fontSize:"0.5rem", color:"#777", textTransform:"uppercase",
                          letterSpacing:"0.05em", lineHeight:1}}>{label}</div>
                        <div style={{fontSize:"0.8rem", fontWeight:700, color:accent, lineHeight:1.2}}>{value}</div>
                      </div>
                    );
                    return (
                      <div>
                        {nTot > 0 && (
                          <div style={{display:"flex", gap:5, marginBottom:8, flexWrap:"wrap",
                            paddingBottom:8, borderBottom:"1px solid #1e1e1e"}}>
                            {pill("P&L", fmtPnl(sumPnl), sumPnl >= 0 ? "#4ade80" : "#f87171", "PnL cumulato")}
                            {pill("win%", winRate != null ? winRate.toFixed(0)+"%" : "—",
                              winRate != null && winRate >= 50 ? "#4ade80" : "#fbbf24", "Win rate")}
                            {pill("▲ best", fmtPnl(maxWin), "#4ade80", "Trade migliore")}
                            {pill("▼ worst", fmtPnl(maxLoss), "#f87171", "Trade peggiore")}
                          </div>
                        )}
                        {/* tabella sempre visibile — header fissa, messaggio inline nel tbody */}
                        <div style={{overflowX:"auto", maxHeight:220, overflowY:"auto"}}>
                          <table style={{width:"100%", fontSize:"0.68rem", borderCollapse:"collapse"}}>
                            <thead>
                              <tr style={{color:"#888", borderBottom:"1px solid #444"}}>
                                <th style={{textAlign:"left", padding:"2px 4px"}}>#</th>
                                <th style={{textAlign:"left", padding:"2px 4px"}}>Sym</th>
                                <th style={{textAlign:"left", padding:"2px 4px"}}>Str</th>
                                <th style={{textAlign:"right", padding:"2px 4px"}} title="PnL realizzato">PnL</th>
                                <th style={{textAlign:"right", padding:"2px 4px"}} title="PnL %">%</th>
                                <th style={{textAlign:"left", padding:"2px 4px"}}>
                                  {posOutcomeFilter === "aperti" ? "Entrata" : "Uscita"}
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {storicoLoading ? (
                                <tr><td colSpan={6} style={{padding:"8px 4px", color:"var(--dim)", fontSize:"0.7rem"}}>
                                  Caricamento…
                                </td></tr>
                              ) : filtered.length === 0 ? (
                                <tr><td colSpan={6} style={{padding:"8px 4px", color:"#888", fontSize:"0.7rem"}}>
                                  {storicoTrades.length === 0
                                    ? "nessun trade nel journal — premi ⟳ per caricare"
                                    : "nessun trade per i filtri selezionati"}
                                </td></tr>
                              ) : (
                                filtered.map((t, i) => {
                                  const pnl    = t.pnl ?? null;
                                  const pnlPct = t.pnl_pct ?? null;
                                  const pnlCol = pnl == null ? "#666" : pnl >= 0 ? "#4ade80" : "#f87171";
                                  const dateVal = posOutcomeFilter === "aperti"
                                    ? (t.entry_ts_utc?.slice(0,10) ?? "—")
                                    : (t.exit_ts_utc?.slice(0,10)  ?? "—");
                                  return (
                                    <tr key={i} style={{borderBottom:"1px solid #222"}}>
                                      <td style={{padding:"2px 4px", color:"#888"}}>#{i+1}</td>
                                      <td style={{padding:"2px 4px", fontWeight:600}}>{t.symbol||"—"}</td>
                                      <td style={{padding:"2px 4px", color:"#888", fontSize:"0.62rem"}}>{t.strategy||"—"}</td>
                                      <td style={{padding:"2px 4px", textAlign:"right", color:pnlCol}}>
                                        {pnl != null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(0)}` : "—"}
                                      </td>
                                      <td style={{padding:"2px 4px", textAlign:"right", color:pnlCol, fontSize:"0.62rem"}}>
                                        {pnlPct != null ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(1)}%` : "—"}
                                      </td>
                                      <td style={{padding:"2px 4px", color:"#777", fontSize:"0.62rem"}}>{dateVal}</td>
                                    </tr>
                                  );
                                })
                              )}
                            </tbody>
                          </table>
                        </div>
                        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginTop:6}}>
                          <button className="btn btn-ghost" style={{fontSize:"0.55rem", padding:"1px 5px"}}
                            title="Scarica CSV dei trade filtrati"
                            onClick={() => {
                              const cols = ["#","Simbolo","Strategia","PnL","PnL%","Data"];
                              const body = filtered.map((t, i) => [
                                i+1, t.symbol??"", t.strategy??"",
                                (t.pnl??0).toFixed(2), (t.pnl_pct??0).toFixed(2),
                                (t.exit_ts_utc ?? t.entry_ts_utc)?.slice(0,10)??"",
                              ].join(","));
                              const blob = new Blob([[cols.join(","), ...body].join("\n")], {type:"text/csv"});
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement("a"); a.href=url;
                              a.download=`posizioni_${new Date().toISOString().slice(0,10)}.csv`; a.click();
                              URL.revokeObjectURL(url);
                            }}>⬇ CSV</button>
                          <span style={{fontSize:"0.58rem", color:"var(--dim)"}}
                            title="Storico trades da paper journal (DuckDB). Cassa e posizioni aperte da broker IBKR.">
                            source: paper journal · DuckDB
                          </span>
                        </div>
                      </div>
                    );
                  })()}
                </div>{/* fine colonna destra */}
              </div>{/* fine lc-body */}

              {/* ── DUMP — tecnico/dev, collassato di default ── */}
              <div style={{borderTop:"1px solid var(--border)"}}>
                <div style={{border:"1px solid #2a2a2a", borderRadius:3, overflow:"hidden"}}>
                  {/* Semaforino = marker visivo universale DUMP */}
                  <div style={{display:"flex", alignItems:"center", gap:5, padding:"4px 8px",
                    background:"#0d0d0d", cursor:"pointer",
                    borderBottom: dumpOpen ? "1px solid #2a2a2a" : "none"}}
                    onClick={() => setDumpOpen(o => !o)}>
                    <span style={{width:7, height:7, borderRadius:"50%", background:"#ef4444", display:"inline-block"}}/>
                    <span style={{width:7, height:7, borderRadius:"50%", background:"#eab308", display:"inline-block"}}/>
                    <span style={{width:7, height:7, borderRadius:"50%", background:"#22c55e", display:"inline-block"}}/>
                    <span style={{fontSize:"0.63rem", color:"#777", fontFamily:"monospace", marginLeft:4, letterSpacing:"0.05em"}}>DUMP</span>
                    <span style={{marginLeft:"auto", fontSize:"0.58rem", color:"#888"}}>{dumpOpen ? "▲" : "▼"}</span>
                  </div>
                  {dumpOpen && (
                    <div style={{padding:0}}>

                      {/* ─── Sezione 1: execution_window.log ─── */}
                      <div style={{borderBottom:"1px solid #1e1e1e"}}>
                        <div style={{display:"flex", alignItems:"center", gap:6, padding:"5px 10px", cursor:"pointer"}}
                          onClick={() => setExecWindowOpen(o => !o)}>
                          <span style={{fontSize:"0.65rem", color:"var(--dim)", userSelect:"none"}}>{execWindowOpen ? "▾" : "▸"}</span>
                          <span style={{fontSize:"0.65rem", color:"var(--dim)", fontFamily:"monospace"}}>execution_window.log</span>
                        </div>
                        {execWindowOpen && (
                          <div style={{padding:"6px 12px 10px"}}>
                            <div className="lc-screen-row"><span className="lc-dim">regime</span><span className={sevClassForRegime(premarketRegime)}>{premarketRegime}</span></div>
                            <div className="lc-screen-row"><span className="lc-dim">kill_switch</span><span className={sysStatus?.kill_switch_active ? "sev-error" : "sev-ok"}>{sysStatus?.kill_switch_active ? "ACTIVE 🛑" : "off"}</span></div>
                            <div className="lc-screen-row"><span className="lc-dim">go_nogo_gate</span><span className={goGate?.pass ? "sev-ok" : "sev-error"}>{goGate?.pass ? "PASS" : "FAIL"}</span></div>
                            <div className="lc-screen-row"><span className="lc-dim">kelly_enabled</span><span className={sysStatus?.kelly_enabled ? "sev-ok" : "sev-warn"}>{sysStatus?.kelly_enabled ? "yes" : "no"}</span></div>
                            <div className="lc-screen-row"><span className="lc-dim">sizing</span><span className={sevClassForRegime(premarketRegime)}>{premarketRegime === "NORMAL" ? "100%" : premarketRegime === "CAUTION" ? "50%" : "0%"}</span></div>
                            <div className="lc-screen-row"><span className="lc-dim">candidati</span><span className="sev-data">{premarketShortlistCount}</span></div>
                            <div className="lc-screen-row"><span className="lc-dim">exit_urgenti</span><span className={urgentExits.length > 0 ? "sev-warn" : "sev-ok"}>{urgentExits.length}</span></div>
                            <div className="lc-screen-row"><span className="lc-dim">trades_chiusi</span><span className="sev-data">{sysStatus?.n_closed_trades ?? 0}</span></div>
                            {goGate && !goGate.pass && goGate.reasons.length > 0 && (
                              <div className="lc-screen-section">
                                <div style={{color:"var(--amber)", fontSize:"0.6rem", marginBottom:4}}>motivi no-go:</div>
                                {goGate.reasons.map((r, i) => <div key={i} style={{fontSize:"0.6rem", color:"var(--dim)"}}>· {r}</div>)}
                              </div>
                            )}
                            <div style={{marginTop:8}}>
                              <button className="btn btn-ghost" style={{fontSize:"0.6rem"}} onClick={refreshAll} disabled={busy}>⟳ refresh</button>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* ─── Sezione 2: ESECUZIONE ORDINE ─── */}
                      <div>
                        <div style={{display:"flex", alignItems:"center", gap:6, padding:"5px 10px", cursor:"pointer"}}
                          onClick={() => setOpExecOpen(o => !o)}>
                          <span style={{fontSize:"0.65rem", color:"var(--dim)", userSelect:"none"}}>{opExecOpen ? "▾" : "▸"}</span>
                          <span style={{fontSize:"0.65rem", color:"var(--dim)", fontFamily:"monospace"}}>esecuzione_ordine</span>
                          {!opExecOpen && symbol && (
                            <span style={{fontSize:"0.6rem", color:"var(--muted)", marginLeft:4}}>{symbol} · {strategy}</span>
                          )}
                        </div>
                        {opExecOpen && (
                          <div style={{padding:"6px 12px 10px"}}>
                            {!blk("order_preview").interactive && blk("order_preview").reason && (
                              <div className="notice error" style={{marginBottom:6, fontSize:"0.7rem"}}>
                                🛑 {blk("order_preview").reason}
                              </div>
                            )}
                            <div className="form-grid" style={{fontSize:"0.72rem"}}>
                              <label>Symbol</label>
                              <input value={symbol} onChange={e => setSymbol(e.target.value)} disabled={!blk("order_preview").interactive} />
                              <label>Strategia</label>
                              <select value={strategy} onChange={e => setStrategy(e.target.value)} disabled={!blk("order_preview").interactive}
                                style={{background:"var(--panel)", color:"var(--text)", border:"1px solid var(--border)", padding:"2px 4px", fontSize:"0.72rem"}}>
                                <option value="BULL_PUT">BULL_PUT</option>
                                {(tierInfo?.features_available?.iron_condor ?? true) && <option value="IRON_CONDOR">IRON_CONDOR</option>}
                                {(tierInfo?.features_available?.wheel ?? true) && <option value="WHEEL">WHEEL</option>}
                                {(tierInfo?.features_available?.pmcc_calendar ?? false) && <option value="PMCC_CALENDAR">PMCC_CALENDAR</option>}
                                {(tierInfo?.features_available?.hedge_active ?? false) && <option value="HEDGE_ACTIVE">HEDGE_ACTIVE</option>}
                                {!["BULL_PUT","IRON_CONDOR","WHEEL","PMCC_CALENDAR","HEDGE_ACTIVE"].includes(strategy) && <option value={strategy}>{strategy}</option>}
                              </select>
                              <label>Payload JSON</label>
                              <textarea rows={4} value={payload} onChange={e => setPayload(e.target.value)} disabled={!blk("order_preview").interactive}
                                style={{fontSize:"0.68rem", fontFamily:"monospace"}} />
                            </div>
                            {payloadJsonError && <div className="notice error" style={{fontSize:"0.7rem"}}>Payload JSON non valido.</div>}
                            {previewDirty && <div className="notice error" style={{fontSize:"0.7rem"}}>Preview non allineata al payload.</div>}
                            <div className="actions" style={{marginTop:6}}>
                              <button className="btn btn-primary" onClick={() => void doPreview()}
                                disabled={busy || payloadJsonError || !blk("order_preview").interactive}>
                                {busy ? "..." : "▶ PREVIEW"}
                              </button>
                              <select value={confirmDecision} onChange={e => setConfirmDecision(e.target.value as "APPROVE" | "REJECT")}
                                disabled={!blk("order_confirm").interactive}
                                style={{background:"var(--panel)", color:"var(--text)", border:"1px solid var(--border)", padding:"2px 4px", fontSize:"0.72rem"}}>
                                <option value="APPROVE">APPROVE</option>
                                <option value="REJECT">REJECT</option>
                              </select>
                              <button
                                className={`btn ${confirmArmed ? "btn-warning" : "btn-danger"}`}
                                onClick={doConfirm}
                                disabled={busy || !preview || payloadJsonError || previewDirty || !blk("order_confirm").interactive}
                                title={confirmArmed ? "Clicca ancora per inviare" : "Prima conferma"}
                              >{confirmArmed ? "⚠ CONFERMA?" : "CONFIRM"}</button>
                            </div>
                            {preview && <pre className="console" style={{fontSize:"0.62rem", marginTop:6}}>{JSON.stringify(preview, null, 2)}</pre>}
                          </div>
                        )}
                      </div>

                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── OP / WHEEL ── Steps 16-20: State machine ─────────────────── */}
          {centerPhase === "op" && opSubTab === "wheel" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 16–20 — WHEEL</span>
                <span className="lc-step-title">Ciclo della Ruota</span>
                <span className="lc-step-sub">{wheelAvailable ? (wheelWarning ? "⚠ " + wheelWarning : "✓ Disponibile") : "🔒 Richiede tier SMALL"}</span>
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Stato macchina — 5 fasi</div>
                  <div className="lc-wheel-states">
                    {(["IDLE","OPEN_CSP","ASSIGNED","OPEN_CC","CLOSED"] as const).map(state => {
                      const activePositions = wheelPositions?.positions ?? [];
                      const isActive = activePositions.some((p: any) => p.state === state);
                      return (
                        <div key={state} className={`lc-wheel-state ${isActive ? "active" : ""}`}>
                          <div className={`lc-wheel-state-name ${isActive ? "sev-ok" : "sev-neutral"}`}>{state}</div>
                          <div className="lc-wheel-state-desc">
                            {state === "IDLE" ? "in attesa" : state === "OPEN_CSP" ? "put venduta" : state === "ASSIGNED" ? "azioni ricevute" : state === "OPEN_CC" ? "call venduta" : "ciclo ok"}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {(wheelPositions?.positions ?? []).length > 0 ? (
                    <div style={{marginTop:14}}>
                      <div className="lc-panel-title">Posizioni attive</div>
                      {(wheelPositions!.positions as any[]).map((p: any, i: number) => (
                        <div key={i} style={{background:"var(--p2)", border:"1px solid var(--border)", borderRadius:4, padding:"8px 10px", marginBottom:6}}>
                          <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:4}}>
                            <span style={{fontWeight:600, color:"var(--text)"}}>{p.symbol ?? "—"}</span>
                            <span className={`lc-badge ${p.state === "CLOSED" ? "ok" : p.state === "ASSIGNED" ? "warn" : "blue"}`}>{p.state ?? "—"}</span>
                          </div>
                          {p.csp_premium != null && <div className="lc-screen-row"><span className="lc-dim">CSP premium</span><span className="sev-ok">€{Number(p.csp_premium).toFixed(2)}</span></div>}
                          {p.cc_premium != null && <div className="lc-screen-row"><span className="lc-dim">CC premium</span><span className="sev-ok">€{Number(p.cc_premium).toFixed(2)}</span></div>}
                          {p.cycle_count != null && <div className="lc-screen-row"><span className="lc-dim">cicli</span><span className="sev-data">{p.cycle_count}</span></div>}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{marginTop:14}}>
                      <div className="lc-kpi-grid">
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Disponibilità</div>
                          <div className={`lc-kpi-value ${wheelAvailable ? "sev-ok" : "sev-warn"}`}>{wheelAvailable ? "ON" : "LOCK"}</div>
                          <div className="lc-kpi-sub">{tierInfo?.active_mode ?? "—"}</div>
                        </div>
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Posizioni</div>
                          <div className="lc-kpi-value sev-neutral">0</div>
                          <div className="lc-kpi-sub">nessuna aperta</div>
                        </div>
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Tier</div>
                          <div className="lc-kpi-value sev-data" style={{fontSize:"0.75rem"}}>{tierInfo?.active_mode ?? "N/D"}</div>
                          <div className="lc-kpi-sub">richiede SMALL</div>
                        </div>
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Kelly</div>
                          <div className={`lc-kpi-value ${blk("kelly_sizing").visible ? "sev-ok" : "sev-neutral"}`}>{blk("kelly_sizing").visible ? "LIVE" : "LOCK"}</div>
                          <div className="lc-kpi-sub">sizing gate</div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">wheel_state_machine.log</span>
                  </div>
                  <div className="lc-screen-body">
                    <div className="lc-screen-row"><span className="lc-dim">tier</span><span className="sev-data">{tierInfo?.active_mode ?? "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">wheel_enabled</span><span className={wheelAvailable ? "sev-ok" : "sev-warn"}>{wheelAvailable ? "yes" : "no"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">active_positions</span><span className="sev-data">{wheelPositions?.positions?.length ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">kelly</span><span className={sysStatus?.kelly_enabled ? "sev-ok" : "sev-warn"}>{sysStatus?.kelly_enabled ? "LIVE" : "LOCK"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">trades_validati</span><span className="sev-data">{paperSummary?.trades ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">sharpe_ann</span><span className="sev-data">{fmtNum(paperSummary?.sharpe_annualized ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">win_rate</span><span className="sev-data">{fmtPct(paperSummary?.win_rate ?? null)}</span></div>
                    {wheelWarning && <div style={{color:"var(--amber)", fontSize:"0.6rem", marginTop:6}}>⚠ {wheelWarning}</div>}
                    <div className="lc-action-bar" style={{marginTop:10}}>
                      <button className="btn btn-ghost" onClick={refreshAll} disabled={busy}>⟳ Aggiorna</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── OP / METRICHE ── Steps 21-22: Tier + Portfolio ───────────── */}
          {centerPhase === "op" && opSubTab === "metriche" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 21–22 — METRICHE</span>
                <span className="lc-step-title">Portfolio e Tier Roadmap</span>
                {paperSummary?.as_of_date && <span className="lc-step-sub">as of {paperSummary.as_of_date}</span>}
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Portfolio — snapshot operativo</div>
                  <div className="lc-kpi-grid">
                    <div className="lc-kpi-item full">
                      <div className="lc-kpi-label">Net Liquidation</div>
                      <div className="lc-kpi-value big sev-ok">
                        {ibkrAccount?.net_liquidation != null ? `€${ibkrAccount.net_liquidation.toLocaleString("it-IT", {maximumFractionDigits:0})}` : "N/D"}
                      </div>
                      <div className="lc-kpi-sub">conto IBKR · {_agoLabel(ibkrAccountFetchedAt)}</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Win rate</div>
                      <div className="lc-kpi-value sev-data">{fmtPct(paperSummary?.win_rate ?? null)}</div>
                      <div className="lc-kpi-sub">{paperSummary?.trades ?? 0} trade</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Sharpe ann.</div>
                      <div className={`lc-kpi-value ${(paperSummary?.sharpe_annualized ?? 0) >= 0.6 ? "sev-ok" : "sev-warn"}`}>
                        {fmtNum(paperSummary?.sharpe_annualized ?? null)}
                      </div>
                      <div className="lc-kpi-sub">soglia 0.6</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Max drawdown</div>
                      <div className={`lc-kpi-value ${ddHealth === "alert" ? "sev-error" : ddHealth === "warn" ? "sev-warn" : "sev-ok"}`}>
                        {fmtPct(paperSummary?.max_drawdown ?? null)}
                      </div>
                      <div className="lc-kpi-sub">limite 15%</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Profit factor</div>
                      <div className={`lc-kpi-value ${(paperSummary?.profit_factor ?? 0) >= 1.5 ? "sev-ok" : "sev-warn"}`}>
                        {fmtNum(paperSummary?.profit_factor ?? null)}
                      </div>
                      <div className="lc-kpi-sub">soglia 1.5</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Avg slippage</div>
                      <div className={`lc-kpi-value ${(paperSummary?.avg_slippage_ticks ?? 0) <= 2 ? "sev-ok" : "sev-warn"}`}>
                        {fmtNum(paperSummary?.avg_slippage_ticks ?? null)}
                      </div>
                      <div className="lc-kpi-sub">ticks</div>
                    </div>
                  </div>
                  <div style={{marginTop:14}}>
                    <div className="lc-panel-title">Tier roadmap</div>
                    {([
                      {name:"MICRO", range:"€1k–2k", req:"R0+R1+R1B+R2", active: tierInfo?.active_mode === "MICRO"},
                      {name:"SMALL", range:"€2k–5k", req:"+wheel validato", active: tierInfo?.active_mode === "SMALL"},
                      {name:"MEDIUM", range:"€5k+",  req:"+live enable",   active: tierInfo?.active_mode === "MEDIUM"},
                    ]).map(t => (
                      <div key={t.name} style={{display:"flex", alignItems:"center", gap:8, padding:"5px 0", borderBottom:"1px solid var(--border)"}}>
                        <span className={`lc-badge ${t.active ? "ok" : "dim"}`}>{t.name}</span>
                        <span style={{fontSize:"0.65rem", color:"var(--dim)", flex:1}}>{t.range} · {t.req}</span>
                        {t.active && <span style={{fontSize:"0.6rem", color:"var(--g1)"}}>← ATTIVO</span>}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">portfolio_agg.log</span>
                  </div>
                  <div className="lc-screen-body">
                    <EqSparkline points={equityHistory?.points ?? []} w={220} h={52} />
                    <div style={{height:8}}/>
                    <div className="lc-screen-row"><span className="lc-dim">trades</span><span className="sev-data">{paperSummary?.trades ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">win_rate</span><span className="sev-data">{fmtPct(paperSummary?.win_rate ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">sharpe</span><span className="sev-data">{fmtNum(paperSummary?.sharpe_annualized ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">max_dd</span><span className={ddHealth === "alert" ? "sev-error" : "sev-data"}>{fmtPct(paperSummary?.max_drawdown ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">profit_factor</span><span className="sev-data">{fmtNum(paperSummary?.profit_factor ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">compliance_v</span><span className={(paperSummary?.compliance_violations ?? 0) > 0 ? "sev-warn" : "sev-ok"}>{paperSummary?.compliance_violations ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">go_nogo</span><span className={goGate?.pass ? "sev-ok" : "sev-error"}>{goGate?.pass ? "PASS" : "FAIL"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">f6_t1</span><span className={f6Gate?.pass ? "sev-ok" : "sev-error"}>{f6Gate?.pass ? "PASS" : "FAIL"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">f6_t2_complete</span><span className={f6t2Gate?.pass ? "sev-ok" : "sev-warn"}>{f6t2Gate ? `${(f6t2Gate.completeness_ratio * 100).toFixed(0)}%` : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">net_liq</span><span className="sev-ok">{ibkrAccount?.net_liquidation != null ? `€${ibkrAccount.net_liquidation.toLocaleString("it-IT",{maximumFractionDigits:0})}` : "N/D"}</span></div>
                    <div className="lc-action-bar">
                      <button className="btn btn-ghost" onClick={() => void doFetchIbkrAccount()} disabled={ibkrAccountLoading || !apiOnline}>
                        {ibkrAccountLoading ? "..." : "⟳ IBKR account"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── OP / BACKTEST ── History readiness + WFA + closed trades ─── */}
          {centerPhase === "op" && opSubTab === "backtest" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">BACKTEST — STORICO</span>
                <span className="lc-step-title">Paper Closed Trades e WFA</span>
                {paperSummary?.as_of_date && <span className="lc-step-sub">as of {paperSummary.as_of_date}</span>}
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">History readiness — Kelly gate progress</div>
                  {historyReadiness ? (
                    <>
                      <div className="lc-kpi-grid">
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Score readiness</div>
                          <div className={`lc-kpi-value ${historyReadiness.ready ? "sev-ok" : "sev-warn"}`}>{historyReadiness.score_pct.toFixed(1)}%</div>
                          <div className="lc-kpi-sub">{historyReadiness.ready ? "PRONTO" : historyEtaLabel}</div>
                        </div>
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Giorni osservati</div>
                          <div className="lc-kpi-value sev-data">{historyReadiness.days_observed}</div>
                          <div className="lc-kpi-sub">su {historyReadiness.target_days} target</div>
                        </div>
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Trade chiusi</div>
                          <div className="lc-kpi-value sev-data">{paperSummary?.trades ?? 0}</div>
                          <div className="lc-kpi-sub">su 50 per Kelly</div>
                        </div>
                        <div className="lc-kpi-item">
                          <div className="lc-kpi-label">Qualità dati</div>
                          <div className={`lc-kpi-value ${(dataQualityPct ?? 0) >= 95 ? "sev-ok" : "sev-warn"}`}>{dataQualityPct !== null ? `${dataQualityPct}%` : "N/D"}</div>
                          <div className="lc-kpi-sub">soglia 95%</div>
                        </div>
                      </div>
                      <div className="lc-progress-wrap" style={{marginTop:12}}>
                        <div className="lc-panel-title">Completamento</div>
                        <div className="lc-progress-track">
                          <div className={`lc-progress-fill ${historyReadiness.ready ? "ok" : "warn"}`} style={{width:`${Math.min(100, historyReadiness.score_pct)}%`}}/>
                        </div>
                        <div className="lc-progress-labels">
                          <span>{historyReadiness.events_observed} / {historyReadiness.target_events} eventi</span>
                          <span>{historyReadiness.pace_events_per_day.toFixed(1)} ev/g</span>
                        </div>
                      </div>
                      <div style={{marginTop:12}}>
                        <div className="lc-panel-title">Breakdown eventi</div>
                        <div className="lc-screen-row"><span className="lc-dim">equity_snapshots</span><span className="sev-data">{historyReadiness.event_breakdown.equity_snapshots}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">paper_trades</span><span className="sev-data">{historyReadiness.event_breakdown.paper_trades}</span></div>
                        <div className="lc-screen-row"><span className="lc-dim">opportunity_decisions</span><span className="sev-data">{historyReadiness.event_breakdown.opportunity_decisions}</span></div>
                      </div>
                    </>
                  ) : (
                    <div style={{color:"var(--dim)", fontSize:"0.7rem"}}>History readiness non disponibile</div>
                  )}
                  <div style={{marginTop:14}}>
                    <div className="lc-panel-title">Metriche paper closed</div>
                    <div className="lc-kpi-grid">
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Sharpe ann.</div>
                        <div className={`lc-kpi-value ${(paperSummary?.sharpe_annualized ?? 0) >= 0.6 ? "sev-ok" : "sev-warn"}`}>{fmtNum(paperSummary?.sharpe_annualized ?? null)}</div>
                        <div className="lc-kpi-sub">soglia 0.6</div>
                      </div>
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Max drawdown</div>
                        <div className={`lc-kpi-value ${ddHealth === "alert" ? "sev-error" : ddHealth === "warn" ? "sev-warn" : "sev-ok"}`}>{fmtPct(paperSummary?.max_drawdown ?? null)}</div>
                        <div className="lc-kpi-sub">limite 15%</div>
                      </div>
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Profit factor</div>
                        <div className={`lc-kpi-value ${(paperSummary?.profit_factor ?? 0) >= 1.5 ? "sev-ok" : "sev-warn"}`}>{fmtNum(paperSummary?.profit_factor ?? null)}</div>
                        <div className="lc-kpi-sub">soglia 1.5</div>
                      </div>
                      <div className="lc-kpi-item">
                        <div className="lc-kpi-label">Violations</div>
                        <div className={`lc-kpi-value ${(paperSummary?.compliance_violations ?? 0) > 0 ? "sev-warn" : "sev-ok"}`}>{paperSummary?.compliance_violations ?? 0}</div>
                        <div className="lc-kpi-sub">compliance</div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">backtest_audit.log</span>
                  </div>
                  <div className="lc-screen-body">
                    <div className="lc-screen-row"><span className="lc-dim">history_ready</span><span className={historyReadiness?.ready ? "sev-ok" : "sev-warn"}>{historyReadiness?.ready ? "yes" : "no"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">score_pct</span><span className={historyReadiness?.ready ? "sev-ok" : "sev-warn"}>{historyReadiness ? `${historyReadiness.score_pct.toFixed(1)}%` : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">days_observed</span><span className="sev-data">{historyReadiness?.days_observed ?? "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">days_remaining</span><span className="sev-data">{historyReadiness?.days_remaining ?? "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">quality_completeness</span><span className="sev-data">{historyReadiness ? `${(historyReadiness.quality_completeness * 100).toFixed(1)}%` : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">closed_trades</span><span className="sev-data">{paperSummary?.trades ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">sharpe_ann</span><span className="sev-data">{fmtNum(paperSummary?.sharpe_annualized ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">max_drawdown</span><span className="sev-data">{fmtPct(paperSummary?.max_drawdown ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">profit_factor</span><span className="sev-data">{fmtNum(paperSummary?.profit_factor ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">win_rate</span><span className="sev-data">{fmtPct(paperSummary?.win_rate ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">window</span><span className="sev-meta">{paperSummary?.gates.window.start_date ?? "—"} → {paperSummary?.gates.window.end_date ?? "—"}</span></div>
                    {historyReadiness?.blockers && historyReadiness.blockers.length > 0 && (
                      <div className="lc-screen-section">
                        {historyReadiness.blockers.map((b, i) => <div key={i} style={{color:"var(--amber)", fontSize:"0.62rem"}}>⚠ {b}</div>)}
                      </div>
                    )}
                    <div className="lc-action-bar">
                      <button className="btn btn-ghost" onClick={refreshAll} disabled={busy}>⟳ Aggiorna</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── POST / CHIUSURA ── Step 23: EOD + Scheduler ──────────────── */}
          {centerPhase === "post" && postSubTab === "chiusura" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 23 — CHIUSURA</span>
                <span className="lc-step-title">Sessione EOD</span>
                <span className="lc-step-sub">{sessionStatus?.running ? "⟳ SESSIONE IN CORSO" : sessionStatus?.last_eod ? `Ultima EOD: ${sessionStatus.last_eod.slice(0,16).replace("T"," ")}` : "Nessuna EOD registrata"}</span>
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Checklist EOD</div>
                  <ul className="lc-checklist">
                    <li className={`lc-check-item ${sessionStatus?.enabled ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{sessionStatus?.enabled ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">Scheduler EOD</span>
                      <span className="lc-check-val">{sessionStatus?.enabled ? "ON" : "OFF"}</span>
                    </li>
                    <li className={`lc-check-item ${(paperSummary?.gates.data_points.equity_snapshots ?? 0) > 0 ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{(paperSummary?.gates.data_points.equity_snapshots ?? 0) > 0 ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">Equity snapshot</span>
                      <span className="lc-check-val">{paperSummary?.gates.data_points.equity_snapshots ?? 0} record</span>
                    </li>
                    <li className={`lc-check-item ${(paperSummary?.compliance_violations ?? 0) === 0 ? "pass" : "fail"}`}>
                      <span className="lc-check-icon">{(paperSummary?.compliance_violations ?? 0) === 0 ? "✅" : "❌"}</span>
                      <span className="lc-check-name">Compliance</span>
                      <span className="lc-check-val">{paperSummary?.compliance_violations ?? 0} violations</span>
                    </li>
                    <li className={`lc-check-item ${f6t2Gate?.pass ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{f6t2Gate?.pass ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">Journal completeness</span>
                      <span className="lc-check-val">{f6t2Gate ? `${(f6t2Gate.completeness_ratio * 100).toFixed(0)}%` : "N/D"}</span>
                    </li>
                    <li className={`lc-check-item ${!(sysStatus?.kill_switch_active) ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{sysStatus?.kill_switch_active ? "⚠️" : "✅"}</span>
                      <span className="lc-check-name">Kill switch</span>
                      <span className="lc-check-val">{sysStatus?.kill_switch_active ? "ATTIVO" : "off"}</span>
                    </li>
                  </ul>
                  <div className="lc-kpi-grid" style={{marginTop:14}}>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Scheduler</div>
                      <div className={`lc-kpi-value ${sessionStatus?.enabled ? "sev-ok" : "sev-neutral"}`}>{sessionStatus?.enabled ? "ON" : "OFF"}</div>
                      <div className="lc-kpi-sub">session engine</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Running</div>
                      <div className={`lc-kpi-value ${sessionStatus?.running ? "sev-warn" : "sev-ok"}`}>{sessionStatus?.running ? "YES" : "NO"}</div>
                      <div className="lc-kpi-sub">stato attuale</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Prossima morning</div>
                      <div className="lc-kpi-value sev-meta" style={{fontSize:"0.65rem"}}>{sessionStatus?.next_morning ? sessionStatus.next_morning.slice(0,16).replace("T"," ") : "N/D"}</div>
                      <div className="lc-kpi-sub">UTC</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Prossima EOD</div>
                      <div className="lc-kpi-value sev-meta" style={{fontSize:"0.65rem"}}>{sessionStatus?.next_eod ? sessionStatus.next_eod.slice(0,16).replace("T"," ") : "N/D"}</div>
                      <div className="lc-kpi-sub">UTC</div>
                    </div>
                  </div>
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">session_logs.eod</span>
                  </div>
                  <div className="lc-screen-body">
                    <div className="lc-screen-row"><span className="lc-dim">scheduler</span><span className={sessionStatus?.enabled ? "sev-ok" : "sev-warn"}>{sessionStatus?.enabled ? "on" : "off"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">running</span><span className={sessionStatus?.running ? "sev-warn" : "sev-ok"}>{sessionStatus?.running ? "yes" : "no"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">last_morning</span><span className="sev-meta">{sessionStatus?.last_morning ? sessionStatus.last_morning.slice(0,19).replace("T"," ") : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">last_eod</span><span className="sev-meta">{sessionStatus?.last_eod ? sessionStatus.last_eod.slice(0,19).replace("T"," ") : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">next_morning</span><span className="sev-meta">{sessionStatus?.next_morning ? sessionStatus.next_morning.slice(0,16).replace("T"," ") : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">next_eod</span><span className="sev-meta">{sessionStatus?.next_eod ? sessionStatus.next_eod.slice(0,16).replace("T"," ") : "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">equity_snapshots</span><span className="sev-data">{paperSummary?.gates.data_points.equity_snapshots ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">compliance_v</span><span className={(paperSummary?.compliance_violations ?? 0) > 0 ? "sev-warn" : "sev-ok"}>{paperSummary?.compliance_violations ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">journal_complete</span><span className={f6t2Gate?.pass ? "sev-ok" : "sev-warn"}>{f6t2Gate ? `${(f6t2Gate.completeness_ratio * 100).toFixed(0)}%` : "N/D"}</span></div>
                    <div className="lc-action-bar">
                      <button className="btn btn-primary" onClick={() => void doRunSession("eod")} disabled={sessionStatus?.running || !apiOnline}>
                        ▶ EOD manuale
                      </button>
                      <button className="btn btn-ghost" onClick={() => void doFetchSessionStatus()} disabled={busy}>⟳</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── POST / REPORT ── Step 24: Report + Gates + Release ───────── */}
          {centerPhase === "post" && postSubTab === "report" && (
            <div className="lifecycle-panel">
              <div className="lc-header">
                <span className="lc-step-label">STEP 24 — REPORT</span>
                <span className="lc-step-title">Consolidamento e Stato Release</span>
                {paperSummary?.as_of_date && <span className="lc-step-sub">as of {paperSummary.as_of_date} · window {paperSummary.window_days}g</span>}
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Gate di sistema</div>
                  <ul className="lc-checklist">
                    <li className={`lc-check-item ${goGate?.pass ? "pass" : "fail"}`}>
                      <span className="lc-check-icon">{goGate?.pass ? "✅" : "❌"}</span>
                      <span className="lc-check-name">Go/No-Go</span>
                      <span className="lc-check-val">{goGate?.pass ? "PASS" : "FAIL"}</span>
                    </li>
                    <li className={`lc-check-item ${f6Gate?.pass ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{f6Gate?.pass ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">F6-T1 Acceptance</span>
                      <span className="lc-check-val">{f6Gate?.pass ? "PASS" : "FAIL"}</span>
                    </li>
                    <li className={`lc-check-item ${f6t2Gate?.pass ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{f6t2Gate?.pass ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">F6-T2 Journal complete</span>
                      <span className="lc-check-val">{f6t2Gate ? `${(f6t2Gate.completeness_ratio * 100).toFixed(0)}%` : "N/D"}</span>
                    </li>
                    <li className={`lc-check-item ${historyReadiness?.ready ? "pass" : "warn"}`}>
                      <span className="lc-check-icon">{historyReadiness?.ready ? "✅" : "⚠️"}</span>
                      <span className="lc-check-name">History readiness</span>
                      <span className="lc-check-val">{historyReadiness ? `${historyReadiness.score_pct.toFixed(0)}% · ${historyEtaLabel}` : "N/D"}</span>
                    </li>
                  </ul>
                  <div className="lc-kpi-grid" style={{marginTop:14}}>
                    <div className="lc-kpi-item full">
                      <div className="lc-kpi-label">P&L cumulato</div>
                      <div className={`lc-kpi-value big ${(paperSummary?.pnl_cumulative ?? 0) >= 0 ? "sev-ok" : "sev-error"}`}>
                        {paperSummary?.pnl_cumulative != null ? `€${paperSummary.pnl_cumulative.toFixed(0)}` : "N/D"}
                      </div>
                      <div className="lc-kpi-sub">paper · {paperSummary?.trades ?? 0} trade · win rate {fmtPct(paperSummary?.win_rate ?? null)}</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Sharpe ann.</div>
                      <div className={`lc-kpi-value ${(paperSummary?.sharpe_annualized ?? 0) >= 0.6 ? "sev-ok" : "sev-warn"}`}>{fmtNum(paperSummary?.sharpe_annualized ?? null)}</div>
                      <div className="lc-kpi-sub">soglia 0.6</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Max DD</div>
                      <div className={`lc-kpi-value ${ddHealth === "alert" ? "sev-error" : ddHealth === "warn" ? "sev-warn" : "sev-ok"}`}>{fmtPct(paperSummary?.max_drawdown ?? null)}</div>
                      <div className="lc-kpi-sub">limite 15%</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Release note</div>
                      <div className={`lc-kpi-value ${releaseMd ? "sev-ok" : "sev-neutral"}`} style={{fontSize:"0.7rem"}}>{releaseMd ? "PRESENTE" : "N/D"}</div>
                      <div className="lc-kpi-sub">status doc</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">DATA_MODE</div>
                      <div className={`lc-kpi-value ${hasRealData ? "sev-ok" : "sev-neutral"}`} style={{fontSize:"0.68rem"}}>{dataModeUpper || "N/D"}</div>
                      <div className="lc-kpi-sub">watermark</div>
                    </div>
                  </div>
                  {f6t2Gate && Object.keys(f6t2Gate.required_missing ?? {}).length > 0 && (
                    <div style={{marginTop:12}}>
                      <div className="lc-panel-title" style={{color:"var(--amber)"}}>Campi journal mancanti</div>
                      {Object.entries(f6t2Gate.required_missing).filter(([,v]) => v > 0).map(([k, v]) => (
                        <div key={k} className="lc-screen-row"><span className="lc-dim">{k}</span><span className="sev-warn">{v} mancanti</span></div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">report_eod.log</span>
                  </div>
                  <div className="lc-screen-body">
                    <div className="lc-screen-row"><span className="lc-dim">profile</span><span className="sev-meta">{paperSummary?.profile ?? ACTIVE_PROFILE}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">as_of_date</span><span className="sev-meta">{paperSummary?.as_of_date ?? "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">window_days</span><span className="sev-meta">{paperSummary?.window_days ?? "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">trades</span><span className="sev-data">{paperSummary?.trades ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">equity_points</span><span className="sev-data">{paperSummary?.equity_points ?? 0}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">win_rate</span><span className="sev-data">{fmtPct(paperSummary?.win_rate ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">sharpe</span><span className="sev-data">{fmtNum(paperSummary?.sharpe_annualized ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">max_dd</span><span className="sev-data">{fmtPct(paperSummary?.max_drawdown ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">profit_factor</span><span className="sev-data">{fmtNum(paperSummary?.profit_factor ?? null)}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">data_mode</span><span className={hasRealData ? "sev-ok" : "sev-neutral"}>{dataModeUpper || "N/D"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">go_nogo</span><span className={goGate?.pass ? "sev-ok" : "sev-error"}>{goGate?.pass ? "PASS" : "FAIL"}</span></div>
                    <div className="lc-screen-row"><span className="lc-dim">f6_t2</span><span className={f6t2Gate?.pass ? "sev-ok" : "sev-warn"}>{f6t2Gate?.pass ? "PASS" : "FAIL"}</span></div>
                    {releaseMd && (
                      <div className="lc-screen-section" style={{marginTop:8}}>
                        <div style={{color:"var(--dim)", fontSize:"0.6rem", marginBottom:4}}>release_notes.md</div>
                        <div style={{color:"var(--text)", fontSize:"0.62rem", whiteSpace:"pre-wrap", maxHeight:80, overflow:"hidden"}}>
                          {releaseMd.slice(0, 200)}{releaseMd.length > 200 ? "…" : ""}
                        </div>
                      </div>
                    )}
                    <div className="lc-action-bar">
                      <button className="btn btn-ghost" onClick={() => void doLoadEvReport()} disabled={busy || !apiOnline}>
                        {busy ? "..." : "⟳ Reload report"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}



        </section>

        <aside className="rightpanel">
          <section className="rp-section">
            <div className="rp-title">KPI MONITOR</div>
            <div className="checklist-item"><span className="ci-label">trades</span><span className="sev-data">{paperSummary?.trades ?? "-"}</span></div>
            <div className="checklist-item"><span className="ci-label">sharpe</span><span className="sev-data">{fmtNum(paperSummary?.sharpe_annualized ?? null)}</span></div>
            <div className="checklist-item"><span className="ci-label">max dd</span><span className="sev-warn">{fmtPct(paperSummary?.max_drawdown ?? null)}</span></div>
            <div className="checklist-item"><span className="ci-label">win rate</span><span className="sev-data">{fmtPct(paperSummary?.win_rate ?? null)}</span></div>
            <div className="checklist-item"><span className="ci-label">compliance</span><span className={(paperSummary?.compliance_violations ?? 0) > 0 ? "sev-error" : "sev-ok"}>{paperSummary?.compliance_violations ?? "-"}</span></div>
            <div className="checklist-item"><span className="ci-label">tier</span><span className="sev-data">{tierInfo?.active_mode ?? "-"}</span></div>
          </section>
        </aside>

        <button
          type="button"
          className={`ai-drawer-handle ${aiDrawerOpen ? "open" : ""}`}
          onClick={() => setAiDrawerOpen((v) => !v)}
          aria-expanded={aiDrawerOpen}
          aria-controls="ai-drawer-panel"
          title={aiDrawerOpen ? "Chiudi pannello AI" : "Apri pannello AI"}
        >
          {aiDrawerOpen ? "AI CLOSE" : "AI OPEN"}
        </button>

        <aside id="ai-drawer-panel" className={`ai-drawer ${aiDrawerOpen ? "open" : ""}`} aria-hidden={!aiDrawerOpen}>
          <section className="ai-drawer-section">
            <div className="rp-title">NARRATORE</div>

            {/* elemento audio nascosto — controllato via ref */}
            <audio
              ref={briefingAudioRef}
              preload="none"
              onPlay={() => setBriefingPlaying(true)}
              onPause={() => setBriefingPlaying(false)}
              onEnded={() => setBriefingPlaying(false)}
              onError={() => setError("Riproduzione briefing fallita: audio non disponibile.")}
            />

            <div className="narrator-briefing-label dim">{briefingLabel}</div>

            <div className="sev-meta" style={{ fontSize: "0.68rem", margin: "4px 0 8px" }}>
              Controlli audio unificati nel WAR ROOM (barra briefing).
            </div>

            {/* ricerca nel tutorial */}
            <div className="narrator-search-block">
              <label className="narrator-search-label">
                <span className="icon-lens" aria-hidden="true" />
                Ricerca nel tutorial
              </label>
              <div className="narrator-search-row">
                <input
                  value={narratorQuery}
                  onChange={(e) => setNarratorQuery(e.target.value)}
                  placeholder="testo da cercare"
                  disabled={!tutorialText.trim()}
                />
                <button className="btn" onClick={() => moveNarratorMatch(-1)} disabled={narratorMatches.length === 0}>Prev</button>
                <button className="btn" onClick={() => moveNarratorMatch(1)} disabled={narratorMatches.length === 0}>Next</button>
              </div>
              <div className="dim narrator-hit">{narratorMatches.length > 0 ? `${narratorMatchIdx + 1}/${narratorMatches.length}` : "0/0"}</div>
            </div>

            <textarea
              ref={narratorBoxRef}
              className="narrator-textbox"
              value={tutorialText || `File non trovato: ${narratorTutorial?.path ?? "docs/TUTORIAL_APPLICAZIONE.md"}`}
              readOnly
            />
          </section>

          <section className="ai-drawer-section ai-chat-section">
            <div className="rp-title">AI CONTROL PANEL</div>
            <p className="dim ai-drawer-copy">
              Qwen via Ollama.
            </p>
            <textarea
              className="ai-response-box"
              value={aiTranscript}
              readOnly
            />
            <div className="ai-prompt-row">
              <input
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="Scrivi il prompt..."
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    if (!aiBusy) {
                      void doAiPrompt();
                    }
                  }
                }}
              />
              <button className="btn" onClick={() => setAiMessages([])} disabled={aiBusy || aiMessages.length === 0}>
                NUOVA CHAT
              </button>
              <button className="btn btn-primary" onClick={() => void doAiPrompt()} disabled={aiBusy || !aiPrompt.trim()}>
                {aiBusy ? "INVIO..." : "INVIA"}
              </button>
            </div>
          </section>
        </aside>
      </div>
      {(message || error) && <section className={`notice toast-notice ${error ? "error" : "ok"}`}>{error || message}</section>}
    </div>
  );
}
