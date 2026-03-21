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
    ts_utc: string;
    asof_date: string;
    equity: number | null;
    note: string;
    profile: string;
    trigger: string;
  }>;
  paper_trades: Array<{
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

type TabKey = "warroom" | "premarket" | "pipeline" | "universe" | "opportunity" | "trades" | "regime" | "tests";
type CenterPhase = "ante" | "op" | "post" | "old";
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
  const [activeTab, setActiveTab] = useState<TabKey>("warroom");
  const [centerPhase, setCenterPhase] = useState<CenterPhase>("old");
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
  const [oppDecision, setOppDecision] = useState<"APPROVE" | "REJECT" | "MODIFY">("APPROVE");
  const [oppConfidence, setOppConfidence] = useState<string>("3");
  const [oppNote, setOppNote] = useState<string>("");
  const [selectedOpportunityKey, setSelectedOpportunityKey] = useState<string>("");
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
  const [sysStatus, setSysStatus] = useState<SystemStatusResponse | null>(null);
  const [regimeCurrent, setRegimeCurrent] = useState<RegimeCurrentResponse | null>(null);
  const [equityHistory, setEquityHistory] = useState<EquityHistoryResponse | null>(null);
  const [navDate, setNavDate] = useState<string>(""); // YYYY-MM-DD — vuoto = oggi
  const [exitCandidates, setExitCandidates] = useState<ExitCandidatesResponse | null>(null);
  const [activityStream, setActivityStream] = useState<ActivityStreamResponse | null>(null);
  const [activityOpen, setActivityOpen] = useState<boolean>(true);
  const [sysLog, setSysLog] = useState<SysLogRecord[]>([]);
  const [sysLogOpen, setSysLogOpen] = useState<boolean>(true);
  const sysLogRef = React.useRef<HTMLDivElement>(null);
  const [wheelPositions, setWheelPositions] = useState<WheelPositionsResponse | null>(null);
  const [wheelFetchedAt, setWheelFetchedAt] = useState<number | null>(null);
  const [tierInfo, setTierInfo] = useState<TierResponse | null>(null);

  const [snapDate, setSnapDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [snapEquity, setSnapEquity] = useState<string>("10000");
  const [snapNote, setSnapNote] = useState<string>("");

  const [tradeEntryTs, setTradeEntryTs] = useState<string>("");
  const [tradeExitTs, setTradeExitTs] = useState<string>("");
  const [tradeStrikes, setTradeStrikes] = useState<string>("");
  const [tradeRegime, setTradeRegime] = useState<string>("");
  const [tradeScore, setTradeScore] = useState<string>("");
  const [tradeKelly, setTradeKelly] = useState<string>("");
  const [tradeExitReason, setTradeExitReason] = useState<string>("");
  const [tradePnl, setTradePnl] = useState<string>("0");
  const [tradePnlPct, setTradePnlPct] = useState<string>("");
  const [tradeSlip, setTradeSlip] = useState<string>("");
  const [tradeViol, setTradeViol] = useState<string>("0");
  const [tradeNote, setTradeNote] = useState<string>("");

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
  const [warEquityOpen, setWarEquityOpen] = useState<boolean>(true);
  const [warSystemOpen, setWarSystemOpen] = useState<boolean>(true);
  const [warIbkrOpen, setWarIbkrOpen] = useState<boolean>(true);
  const [warDrawdownOpen, setWarDrawdownOpen] = useState<boolean>(false);
  const [warGateOpen, setWarGateOpen] = useState<boolean>(false);
  const [warHistoryOpen, setWarHistoryOpen] = useState<boolean>(false);
  const [warRegimeOpen, setWarRegimeOpen] = useState<boolean>(false);
  const [warPipelineOpen, setWarPipelineOpen] = useState<boolean>(false);
  const [warIbkrPositionsOpen, setWarIbkrPositionsOpen] = useState<boolean>(true);
  const [warIbkrExitOpen, setWarIbkrExitOpen] = useState<boolean>(true);
  const [warWheelOpen, setWarWheelOpen] = useState<boolean>(true);
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
  const [slideStepDataOpen, setSlideStepDataOpen] = useState<boolean>(true);
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
      await apiJson(`${API_BASE}/opz/execution/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setMessage("Confirm sent.");
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

  async function doAddSnapshot() {
    const eq = parseFiniteInput(snapEquity, "Equity");
    if (!eq.ok) {
      setError(eq.message);
      setMessage("");
      return;
    }
    if (eq.value <= 0) {
      setError("Equity deve essere > 0.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      await apiJson(`${API_BASE}/opz/paper/equity_snapshot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: "paper", asof_date: snapDate, equity: eq.value, note: snapNote }),
      });
      setMessage("Equity snapshot recorded.");
      await refreshAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doAddTrade() {
    const pnl = parseFiniteInput(tradePnl, "PnL");
    if (!pnl.ok) {
      setError(pnl.message);
      setMessage("");
      return;
    }
    const viol = parseIntInput(tradeViol, "Violations");
    if (!viol.ok || viol.value < 0) {
      setError("Violations deve essere un intero >= 0.");
      setMessage("");
      return;
    }

    const body: Record<string, unknown> = {
      profile: "paper",
      symbol: symbol.trim(),
      strategy: strategy.trim(),
      pnl: pnl.value,
      violations: viol.value,
      note: tradeNote,
    };

    if (tradeEntryTs.trim()) {
      const d = new Date(tradeEntryTs);
      if (Number.isNaN(d.getTime())) {
        setError("Entry TS UTC non valido.");
        setMessage("");
        return;
      }
      body.entry_ts_utc = d.toISOString();
    }
    if (tradeExitTs.trim()) {
      const d = new Date(tradeExitTs);
      if (Number.isNaN(d.getTime())) {
        setError("Exit TS UTC non valido.");
        setMessage("");
        return;
      }
      body.exit_ts_utc = d.toISOString();
    }
    if (tradeStrikes.trim()) {
      try {
        const arr = JSON.parse(tradeStrikes);
        if (!Array.isArray(arr) || arr.some((x) => !Number.isFinite(Number(x)))) throw new Error("invalid strikes array");
        body.strikes = arr.map((x) => Number(x));
      } catch {
        setError("Strikes deve essere un JSON array numerico, es: [185,180]");
        setMessage("");
        return;
      }
    }
    if (tradeRegime.trim()) body.regime_at_entry = tradeRegime.trim();
    if (tradeScore.trim()) {
      const score = parseFiniteInput(tradeScore, "Score at entry");
      if (!score.ok) {
        setError(score.message);
        setMessage("");
        return;
      }
      body.score_at_entry = score.value;
    }
    if (tradeKelly.trim()) {
      const kelly = parseFiniteInput(tradeKelly, "Kelly fraction");
      if (!kelly.ok || kelly.value < 0 || kelly.value > 1) {
        setError("Kelly fraction deve essere tra 0 e 1.");
        setMessage("");
        return;
      }
      body.kelly_fraction = kelly.value;
    }
    if (tradeExitReason.trim()) body.exit_reason = tradeExitReason.trim();
    if (tradePnlPct.trim()) {
      const pct = parseFiniteInput(tradePnlPct, "PnL %");
      if (!pct.ok) {
        setError(pct.message);
        setMessage("");
        return;
      }
      body.pnl_pct = pct.value;
    }
    if (tradeSlip.trim()) {
      const slip = parseFiniteInput(tradeSlip, "Slippage ticks");
      if (!slip.ok || slip.value < 0) {
        setError("Slippage ticks deve essere >= 0.");
        setMessage("");
        return;
      }
      body.slippage_ticks = slip.value;
    }

    if (!String(body.symbol).trim() || !String(body.strategy).trim()) {
      setError("Symbol e Strategy sono obbligatori anche per il trade journal.");
      setMessage("");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      await apiJson(`${API_BASE}/opz/paper/trade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setMessage("Paper trade recorded.");
      await refreshAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doOpportunityDecision() {
    // Priorità: candidato da scan_full; fallback: candidato da universe items
    const scanC = oppScanResult?.candidates.find((c) => `${c.symbol}::${c.strategy}::${c.expiry}` === selectedScanKey)
      ?? oppScanResult?.candidates[0] ?? null;
    const candidate = scanC ?? selectedOpportunity;
    if (!candidate) {
      setError("Nessun candidato disponibile per validazione Opportunity.");
      setMessage("");
      return;
    }
    const conf = parseIntInput(oppConfidence, "Confidence");
    if (!conf.ok || conf.value < 1 || conf.value > 5) {
      setError("Confidence deve essere un intero tra 1 e 5.");
      setMessage("");
      return;
    }

    const batchId = oppScanResult?.batch_id ?? universeLatest?.batch_id ?? undefined;
    const regime = oppScanResult?.regime ?? universeLatest?.regime ?? universeRegime;
    const source = oppScanResult ? "opportunity_scanner" : (universeLatest?.source ?? universeSource);

    setBusy(true);
    setError("");
    setMessage("");
    try {
      await apiJson(`${API_BASE}/opz/opportunity/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: "paper",
          batch_id: batchId,
          symbol: candidate.symbol,
          strategy: candidate.strategy,
          score: candidate.score,
          regime,
          scanner_name: universeLatest?.scanner_name ?? selectedScanner?.scanner_name ?? "",
          source,
          decision: oppDecision,
          confidence: conf.value,
          note: oppNote.trim(),
        }),
      });
      setMessage(
        `Opportunity logged: ${oppDecision} ${candidate.symbol} (score=${candidate.score.toFixed(2)}, conf=${conf.value}/5).`
      );
      await refreshAll();
    } catch (e) {
      setError(String(e));
      setMessage("");
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

  async function doFetchEquityHistory(asof?: string) {
    try {
      const dateParam = asof ?? navDate;
      const url = dateParam
        ? `${API_BASE}/opz/paper/equity_history?profile=${ACTIVE_PROFILE}&limit=60&asof_date=${dateParam}`
        : `${API_BASE}/opz/paper/equity_history?profile=${ACTIVE_PROFILE}&limit=60`;
      const r = await apiJson<EquityHistoryResponse>(url);
      setEquityHistory(r);
      clearFetchErr("equity");
    } catch (e) { markFetchErr("equity"); }
  }

  function shiftDate(days: number) {
    const base = navDate || new Date().toISOString().slice(0, 10);
    const d = new Date(base);
    d.setDate(d.getDate() + days);
    const next = d.toISOString().slice(0, 10);
    setNavDate(next);
    void doFetchEquityHistory(next);
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
  const opportunityKeyOf = (item: UniverseScanItem): string => `${item.rank}::${item.symbol}::${item.strategy}`;
  const opportunityTop = universeItems[0] ?? null;
  const selectedOpportunity = universeItems.find((x) => opportunityKeyOf(x) === selectedOpportunityKey) ?? opportunityTop;
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
  }, [apiOnline, goGate?.pass, hasPaperData]);

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
    if (!universeItems.length) {
      if (selectedOpportunityKey) setSelectedOpportunityKey("");
      return;
    }
    const hasSelection = universeItems.some((x) => opportunityKeyOf(x) === selectedOpportunityKey);
    if (!hasSelection) {
      setSelectedOpportunityKey(opportunityKeyOf(universeItems[0]));
    }
  }, [universeItems, selectedOpportunityKey]);

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

  const oldNavItems: Array<{ id: TabKey; label: string }> = [
    { id: "warroom", label: "WAR ROOM" },
    { id: "premarket", label: "PRE-MARKET SCORE" },
    { id: "universe", label: "UNIVERSE SCANNER" },
    { id: "opportunity", label: "OPPORTUNITY" },
    { id: "pipeline", label: "PIPELINE AUTO" },
    { id: "trades", label: "TRADE LOG" },
    { id: "regime", label: "REGIME MATRIX" },
    { id: "tests", label: "TEST SUITE" },
  ];
  const resolvedTab: TabKey = centerPhase === "old"
    ? activeTab
    : centerPhase === "ante"
      ? (anteSubTab === "dati" ? "premarket" : anteSubTab === "analisi" ? "opportunity" : "warroom")
      : centerPhase === "op"
        ? (opSubTab === "metriche" ? "regime" : opSubTab === "backtest" ? "trades" : "warroom")
        : (postSubTab === "report" ? "tests" : "warroom");
  const openOldTab = (tab: TabKey): void => {
    setCenterPhase("old");
    setActiveTab(tab);
  };
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
                <div className="left-subhead left-subhead-inline" style={{marginTop:4}}>
                  <span className="sev-meta" style={{fontSize:"0.6rem"}}>SESSIONI AUTO</span>
                  <span className={sessionStatus?.enabled ? "sev-ok" : "sev-neutral"} style={{fontSize:"0.6rem"}}>
                    {sessionStatus?.enabled ? "ON" : "OFF"}
                  </span>
                </div>
                <div className="left-subbody">
                  <div className="left-kpi-row"><span>Prossima</span><b className="sev-meta" style={{fontSize:"0.6rem"}}>
                    {sessionStatus?.next_morning ? sessionStatus.next_morning.slice(0,16).replace("T"," ") : "—"}
                  </b></div>
                  <div className="left-kpi-row"><span>Ultima morning</span><b className="sev-meta" style={{fontSize:"0.6rem"}}>
                    {sessionStatus?.last_morning ? sessionStatus.last_morning.slice(0,16).replace("T"," ") : "mai"}
                  </b></div>
                </div>
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
            <button className={`tab ${centerPhase === "old" ? "active" : ""}`} onClick={() => setCenterPhase("old")}>OLD</button>
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
          {centerPhase === "old" && (
            <div className="tabs subtabs old-tabs">
              {oldNavItems.map((tab) => (
                <button key={tab.id} className={`tab ${activeTab === tab.id ? "active" : ""}`} onClick={() => setActiveTab(tab.id)}>
                  {tab.label}
                </button>
              ))}
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
                    <div className="lc-action-bar">
                      <button className="btn btn-primary" onClick={() => void doScanFull()} disabled={busy || !apiOnline}>
                        {busy ? "..." : "▶ Scan completo"}
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
                <span className="lc-step-title">Execution e Monitoraggio</span>
                <span className={`lc-step-sub ${goGate?.pass ? "sev-ok" : "sev-warn"}`}>
                  Go/No-Go: {goGate?.pass ? "✓ GO" : "✗ NO-GO"} · Kill switch: {sysStatus?.kill_switch_active ? "🛑 ON" : "off"}
                </span>
              </div>
              <div className="lc-body">
                <div className="lc-panel">
                  <div className="lc-panel-title">Candidati — filtri duri + score</div>
                  {scanCandidates.length === 0 && universeItems.length === 0 && (
                    <div style={{color:"var(--dim)", fontSize:"0.7rem", padding:"8px 0"}}>
                      Nessun candidato. Esegui scan dalla tab ANALISI.
                    </div>
                  )}
                  {premarketRows.slice(0, 8).map((c, i) => (
                    <div key={i} className="lc-candidate-row">
                      <span className="lc-candidate-rank">#{i + 1}</span>
                      <span className="lc-candidate-sym">
                        <span style={{color:"var(--text)", fontWeight:600}}>{c.symbol}</span>
                        <span style={{color:"var(--dim)", fontSize:"0.6rem"}}> {c.strategy}</span>
                      </span>
                      {c.scorePct !== undefined && (
                        <span className={`lc-badge ${c.scorePct >= 65 ? "ok" : c.scorePct >= 50 ? "warn" : "bad"}`}>{c.scorePct.toFixed(0)}</span>
                      )}
                    </div>
                  ))}
                  {urgentExits.length > 0 && (
                    <div style={{marginTop:14}}>
                      <div className="lc-panel-title" style={{color:"var(--amber)"}}>Exit urgenti 🚨 ({urgentExits.length})</div>
                      {urgentExits.map((c, i) => (
                        <div key={i} className="lc-candidate-row">
                          <span className="lc-candidate-rank" style={{color:"var(--red)"}}>!</span>
                          <span className="lc-candidate-sym">{c.symbol} <span style={{color:"var(--dim)", fontSize:"0.6rem"}}>{c.right ?? ""} {c.strike ?? ""}</span></span>
                          <span className="lc-badge warn">exit {c.exit_score}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="lc-kpi-grid" style={{marginTop:14}}>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Gate Go/No-Go</div>
                      <div className={`lc-kpi-value ${goGate?.pass ? "sev-ok" : "sev-error"}`}>{goGate?.pass ? "GO ✓" : "NO-GO"}</div>
                      <div className="lc-kpi-sub">accesso mercato</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Trades chiusi</div>
                      <div className="lc-kpi-value sev-data">{sysStatus?.n_closed_trades ?? 0}</div>
                      <div className="lc-kpi-sub">paper journal</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Exit urgenti</div>
                      <div className={`lc-kpi-value ${urgentExits.length > 0 ? "sev-warn" : "sev-ok"}`}>{urgentExits.length}</div>
                      <div className="lc-kpi-sub">score ≥ 5</div>
                    </div>
                    <div className="lc-kpi-item">
                      <div className="lc-kpi-label">Finestra</div>
                      <div className="lc-kpi-value sev-meta" style={{fontSize:"0.68rem"}}>10:00–11:30</div>
                      <div className="lc-kpi-sub">evita 09:30–45</div>
                    </div>
                  </div>
                </div>
                <div className="lc-screen">
                  <div className="lc-screen-bar">
                    <span className="lc-dot r"/><span className="lc-dot y"/><span className="lc-dot g"/>
                    <span className="lc-screen-title">execution_window.log</span>
                  </div>
                  <div className="lc-screen-body">
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
                    <div className="lc-action-bar">
                      <button className="btn btn-primary" onClick={() => void doPreview()} disabled={busy || !goGate?.pass || !apiOnline}>
                        {busy ? "..." : "▶ Preview ordine"}
                      </button>
                      <button className="btn btn-ghost" onClick={refreshAll} disabled={busy}>⟳</button>
                    </div>
                  </div>
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
                      <button className="btn btn-ghost" onClick={() => void doAddSnapshot()} disabled={busy || !apiOnline}>
                        + Snapshot
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

                    {centerPhase === "old" && resolvedTab === "warroom" && (
            <>
            {/* ── BANNER SESSIONI ──────────────────────────────────────────────── */}
            {sessionStatus && (
              <div style={{
                display: "flex", alignItems: "center", gap: "1.5rem",
                padding: "6px 14px", background: "var(--card2)",
                borderBottom: "1px solid var(--border)",
                fontSize: "0.7rem", color: "var(--muted)", flexWrap: "wrap",
              }}>
                <span style={{ color: sessionStatus.enabled ? "var(--p1)" : "var(--muted)", fontWeight: 600 }}>
                  {sessionStatus.enabled ? "● SCHEDULER ON" : "○ SCHEDULER OFF"}
                </span>
                {sessionStatus.running && (
                  <span style={{ color: "var(--warn)", fontWeight: 600 }}>⟳ SESSIONE IN CORSO</span>
                )}
                {sessionStatus.last_morning && (
                  <span>Ultima morning: <strong style={{ color: "var(--text)" }}>{sessionStatus.last_morning.replace("T", " ").slice(0, 16)} UTC</strong></span>
                )}
                {sessionStatus.last_eod && (
                  <span>Ultima EOD: <strong style={{ color: "var(--text)" }}>{sessionStatus.last_eod.replace("T", " ").slice(0, 16)} UTC</strong></span>
                )}
                {sessionStatus.next_morning && !sessionStatus.running && (
                  <span>Prossima morning: <strong style={{ color: "var(--p1)" }}>{sessionStatus.next_morning.replace("T", " ").slice(0, 16)}</strong></span>
                )}
                {sessionStatus.next_eod && !sessionStatus.running && (
                  <span>Prossima EOD: <strong style={{ color: "var(--p1)" }}>{sessionStatus.next_eod.replace("T", " ").slice(0, 16)}</strong></span>
                )}
                <span style={{ marginLeft: "auto", display: "flex", gap: "6px", alignItems: "center" }}>
                  <button className="btn btn-ghost" style={{ fontSize: "0.65rem", padding: "2px 8px" }}
                    disabled={sessionStatus.running}
                    onClick={() => void doRunSession("morning")}
                    title="Avvia sessione morning manualmente">▶ Morning</button>
                  <button className="btn btn-ghost" style={{ fontSize: "0.65rem", padding: "2px 8px" }}
                    disabled={sessionStatus.running}
                    onClick={() => void doRunSession("eod")}
                    title="Avvia sessione EOD manualmente">▶ EOD</button>
                  <button className="btn btn-ghost" style={{ fontSize: "0.65rem", padding: "2px 8px" }}
                    onClick={() => void doFetchSessionStatus()} title="Aggiorna stato sessioni">⟳</button>
                </span>
              </div>
            )}
            {/* ── NARRATORE — player inline ───────────────────────────────────── */}
            <div className="narrator-player-bar">
              {/* label + track */}
              <div className="narrator-player-track">
                <span className="narrator-player-icon">📻</span>
                <span className="narrator-player-label">{briefingLabel}</span>
              </div>
              {/* transport controls */}
              <div className="narrator-player-transport">
                <button className="btn btn-ghost narrator-btn"
                  onClick={doBriefingPrev}
                  disabled={briefingListIdx >= briefingList.length - 1 || briefingList.length === 0}
                  title="Briefing precedente">◀ PREV</button>
                <button
                  className={`btn narrator-btn-main ${briefingPlaying ? "btn-warning" : "btn-primary"}`}
                  onClick={briefingPlaying ? doBriefingStop : doBriefingPlay}
                  disabled={!apiOnline || (!briefingPlaying && briefingList.length === 0)}
                >{briefingPlaying ? "■ STOP" : "▶ PLAY"}</button>
                <button className="btn btn-ghost narrator-btn"
                  onClick={doBriefingNext}
                  disabled={briefingListIdx <= 0}
                  title="Briefing successivo">NEXT ▶</button>
                <button className="btn btn-ghost narrator-btn"
                  onClick={() => void doBriefingGenerate()}
                  disabled={briefingBusy || !apiOnline}
                  title="Genera nuovo briefing e invia su Telegram"
                >{briefingBusy ? "..." : "⊕ GENERA"}</button>
              </div>
              {/* automation switches */}
              <div className="narrator-player-switches">
                <label className="narrator-switch-row">
                  <span>Auto-apri</span>
                  <span className={`toggle-pill ${briefingAutoOpen ? "on" : ""}`}
                    onClick={() => setBriefingAutoOpen(v => !v)} role="switch"
                    aria-checked={briefingAutoOpen} tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && setBriefingAutoOpen(v => !v)}>
                    <span className="toggle-knob" />
                  </span>
                </label>
                <label className="narrator-switch-row">
                  <span>AutoPlay</span>
                  <span className={`toggle-pill ${briefingAutoPlay ? "on" : ""}`}
                    onClick={() => setBriefingAutoPlay(v => !v)} role="switch"
                    aria-checked={briefingAutoPlay} tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && setBriefingAutoPlay(v => !v)}>
                    <span className="toggle-knob" />
                  </span>
                </label>
              </div>
            </div>

            <div className="panel-grid three">
              <article className="panel">
                {/* ── ROC10: equity sparkline header ── */}
                <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarEquityOpen((v) => !v)}>
                      {warEquityOpen ? "▾" : "▸"}
                    </button>
                    <Tooltip text={TOOLTIPS.equity_curve}><span>EQUITY CURVE</span></Tooltip>
                  </span>
                  {equityHistory && equityHistory.n_points > 0 && (() => {
                    const init = equityHistory.initial_equity!;
                    const last = equityHistory.latest_equity!;
                    const pnl = last - init;
                    const pct = (pnl / init) * 100;
                    return (
                      <span style={{ color: pnl >= 0 ? "#4ade80" : "#f87171", fontWeight: 700, fontSize: "0.75rem" }}>
                        €{last.toLocaleString("it-IT", { minimumFractionDigits: 0 })}
                        {" "}{pnl >= 0 ? "+" : ""}{pct.toFixed(1)}%
                      </span>
                    );
                  })()}
                </div>
                {warEquityOpen && (
                <>
                {/* ── Navigazione temporale equity ── */}
                <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 4, flexWrap: "nowrap", overflowX: "auto" }}>
                  <button className="btn btn-secondary" style={{ fontSize: "0.62rem", padding: "2px 5px" }}
                    onClick={() => shiftDate(-1)} title="Giorno precedente">◀ -1g</button>
                  <input
                    type="date"
                    value={navDate}
                    min={equityHistory?.min_date ?? undefined}
                    max={equityHistory?.max_date ?? new Date().toISOString().slice(0, 10)}
                    onChange={e => { setNavDate(e.target.value); void doFetchEquityHistory(e.target.value); }}
                    style={{ fontSize: "0.65rem", width: 118, minWidth: 118, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }}
                  />
                  <button className="btn btn-secondary" style={{ fontSize: "0.62rem", padding: "2px 5px" }}
                    onClick={() => shiftDate(+1)} title="Giorno successivo">+1g ▶</button>
                  {navDate && (
                    <button className="btn btn-secondary" style={{ fontSize: "0.62rem", padding: "2px 5px", color: "var(--p1)" }}
                      onClick={() => { setNavDate(""); void doFetchEquityHistory(""); }}>OGGI</button>
                  )}
                  {navDate && <span style={{ fontSize: "0.62rem", color: "var(--muted)", whiteSpace: "nowrap" }}>— vista al {navDate}</span>}
                </div>

                <EqSparkline points={equityHistory?.points ?? []} w={240} h={56} />

                <div className="panel-title mt10 subgroup-title" style={{ display: "flex", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarDrawdownOpen((v) => !v)}>
                      {warDrawdownOpen ? "▾" : "▸"}
                    </button>
                    <Tooltip text={TOOLTIPS.drawdown_gauge}>DRAWDOWN - 3 LAYER</Tooltip>
                    <span className="sev-data">{fmtPct(paperSummary?.max_drawdown ?? null)}</span>
                  </span>
                </div>
                {warDrawdownOpen ? (
                  <>
                    <div className="dd-gauge">
                      <div className="dd-track">
                        <div className="dd-fill" style={{ width: `${ddFill}%` }} />
                        <div className="dd-mark dd-mark10" />
                        <div className="dd-mark dd-mark15" />
                      </div>
                      <div className="dd-labels">
                        <span>0%</span><span>10%</span><span>15%</span><span>20%</span>
                      </div>
                    </div>
                    <div className="sev-meta">DD attuale: {fmtPct(paperSummary?.max_drawdown ?? null)} / limite 20%</div>
                  </>
                ) : (
                  <div className="subgroup-summary sev-meta">DD attuale {fmtPct(paperSummary?.max_drawdown ?? null)} · limite 20%</div>
                )}

                <div className="panel-title mt10 subgroup-title" style={{ display: "flex", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarGateOpen((v) => !v)}>
                      {warGateOpen ? "▾" : "▸"}
                    </button>
                    GATE STATUS
                    <span className={goGate?.pass ? "sev-ok" : "sev-error"}>{goGate?.pass ? "GO" : "NO-GO"}</span>
                  </span>
                </div>
                {warGateOpen ? (
                  <>
                    <div className="gate-line"><span><Tooltip text={TOOLTIPS.go_nogo}>GO/NO-GO</Tooltip></span>{goGate ? <GateBadge pass={goGate.pass} /> : <span className="sev-neutral">-</span>}</div>
                    {goGate?.reasons.map((r) => <div key={`go-${r}`} className="reason">- {r}</div>)}
                    <div className="gate-line"><span><Tooltip text={TOOLTIPS.f6_t1}>F6-T1 acceptance</Tooltip></span>{f6Gate ? <GateBadge pass={f6Gate.pass} /> : <span className="sev-neutral">-</span>}</div>
                    {f6Gate?.reasons.map((r) => <div key={`f6-${r}`} className="reason">- {r}</div>)}
                    <div className="gate-line"><span><Tooltip text={TOOLTIPS.f6_t2}>F6-T2 completeness</Tooltip></span>{f6t2Gate ? <GateBadge pass={f6t2Gate.pass} /> : <span className="sev-neutral">-</span>}</div>
                    {f6t2Gate && <div className="sev-meta">completeness: <Tooltip text={TOOLTIPS.f6_t2_ratio}>{(f6t2Gate.completeness_ratio * 100).toFixed(0)}%</Tooltip></div>}
                  </>
                ) : (
                  <div className="subgroup-summary sev-meta">
                    {goGate ? `GO/NO-GO ${goGate.pass ? "PASS" : "FAIL"}` : "GO/NO-GO —"} ·
                    {f6Gate ? ` F6-T1 ${f6Gate.pass ? "PASS" : "FAIL"}` : " F6-T1 —"} ·
                    {f6t2Gate ? ` F6-T2 ${(f6t2Gate.completeness_ratio * 100).toFixed(0)}%` : " F6-T2 —"}
                  </div>
                )}
                </>
                )}
              </article>

              <article className="panel">
                <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarSystemOpen((v) => !v)}>
                      {warSystemOpen ? "▾" : "▸"}
                    </button>
                    <span>SYSTEM STATUS</span>
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: "0.62rem", color: "#555" }}>agg: {_agoLabel(sysStatusFetchedAt)}</span>
                    <button className="btn btn-secondary" style={{ fontSize: "0.65rem", padding: "2px 6px" }}
                      onClick={() => void doFetchSysStatus()}>⟳</button>
                  </span>
                </div>
                {warSystemOpen && (
                <>
                {/* Signal grid */}
                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: "3px 8px", alignItems: "center", fontSize: "0.72rem", marginTop: 4 }}>
                  {(sysStatus?.signals ?? []).map((sig) => {
                    const detail = sanitizeSignalDetail(sig.detail, sig.status);
                    return [
                      <span key={`sn-${sig.name}`} className="dim" style={{ whiteSpace: "nowrap" }}>{sig.name}</span>,
                      <span key={`sd-${sig.name}`} className="sev-neutral" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{detail}</span>,
                      <span key={`ss-${sig.name}`} className={sevClassForSignalStatus(sig.status)} style={{ fontWeight: 700, textAlign: "right" }}>{sig.status}</span>,
                    ];
                  })}

                  {/* Campi aggiuntivi */}
                  <span className="dim">regime</span>
                  <span className={sevClassForRegime(sysStatus?.regime)}>
                    {sysStatus?.regime ?? "—"}
                  </span>
                  <span />

                  <span className="dim">trades completati</span>
                  <span className="sev-data">{sysStatus?.n_closed_trades ?? "—"}</span>
                  <span />

                  <span className="dim">api</span>
                  <span className="sev-neutral">{apiOnline ? "ONLINE" : "OFFLINE"}</span>
                  <span className={apiOnline ? "sev-ok" : "sev-error"} style={{ fontWeight: 700 }}>{apiOnline ? "OK" : "ALERT"}</span>
                </div>

                <div className="panel-title mt10 subgroup-title" style={{ display: "flex", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarHistoryOpen((v) => !v)}>
                      {warHistoryOpen ? "▾" : "▸"}
                    </button>
                    <Tooltip text={TOOLTIPS.history_readiness}>HISTORY READINESS</Tooltip>
                    <span className={historyReadiness?.ready ? "sev-ok" : "sev-warn"}>
                      {historyReadiness ? `${historyReadiness.score_pct.toFixed(1)}%` : "…"}
                    </span>
                  </span>
                </div>
                {warHistoryOpen ? (
                  historyReadiness ? (
                    <div className={`history-readiness-box ${historyStatusClass}`}>
                      <div className="history-readiness-head">
                        <span>{historyReadiness.ready ? "READY" : "BUILDING"}</span>
                        <span>{historyReadiness.score_pct.toFixed(1)}%</span>
                      </div>
                      <div className="checklist-item"><span className="ci-label"><Tooltip text={TOOLTIPS.history_window}>Finestra</Tooltip></span><span>{historyReadiness.window_days}g</span></div>
                      <div className="checklist-item"><span className="ci-label"><Tooltip text={TOOLTIPS.history_days}>Giorni coperti</Tooltip></span><span>{historyReadiness.days_observed}/{historyReadiness.target_days}</span></div>
                      <div className="checklist-item"><span className="ci-label"><Tooltip text={TOOLTIPS.history_events}>Eventi</Tooltip></span><span>{historyReadiness.events_observed}/{historyReadiness.target_events}</span></div>
                      <div className="checklist-item"><span className="ci-label"><Tooltip text={TOOLTIPS.history_quality}>Qualita journal</Tooltip></span><span>{(historyReadiness.quality_completeness * 100).toFixed(1)}%</span></div>
                      <div className="checklist-item"><span className="ci-label"><Tooltip text={TOOLTIPS.history_violations}>Violazioni window</Tooltip></span><span>{historyReadiness.compliance_violations_window}</span></div>
                      <div className="checklist-item"><span className="ci-label"><Tooltip text={TOOLTIPS.history_eta}>ETA</Tooltip></span><span>{historyEtaLabel}</span></div>
                      {!historyReadiness.ready && historyReadiness.blockers.length > 0 && (
                        <div className="history-blockers">
                          {historyReadiness.blockers.join(" | ")}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="sev-meta" style={{ fontSize: "0.7rem" }}>Caricamento readiness...</div>
                  )
                ) : (
                  <div className="subgroup-summary sev-meta">
                    {historyReadiness
                      ? `${historyReadiness.ready ? "READY" : "BUILDING"} · giorni ${historyReadiness.days_observed}/${historyReadiness.target_days} · eventi ${historyReadiness.events_observed}/${historyReadiness.target_events}`
                      : "Readiness in caricamento..."}
                  </div>
                )}

                {sysStatus?.kill_switch_active && (
                  <div style={{ marginTop: 8, padding: "6px 10px", background: "#3a1010", border: "1px solid #f87171", borderRadius: 4, color: "#f87171", fontWeight: 700, fontSize: "0.75rem" }}>
                    ⚠ KILL SWITCH ATTIVO — Esecuzione bloccata
                  </div>
                )}

                {sysStatus?.timestamp_utc && (
                  <div className="dim" style={{ marginTop: 4, fontSize: "0.65rem" }}>
                    Agg: {fmtTs(sysStatus.timestamp_utc)}
                  </div>
                )}

                {/* ── ROC9: Regime distribution bar ──────────────────────── */}
                <div className="panel-title mt10 subgroup-title" style={{ display: "flex", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarRegimeOpen((v) => !v)}>
                      {warRegimeOpen ? "▾" : "▸"}
                    </button>
                    REGIME
                    <span className="sev-data">({regimeCurrent?.n_recent ?? 0} sample)</span>
                    <span
                      className={
                        regimeCurrent?.regime === "SHOCK"
                          ? "sev-error"
                          : regimeCurrent?.regime === "CAUTION"
                            ? "sev-warn"
                            : regimeCurrent?.regime === "NORMAL"
                              ? "sev-ok"
                              : "sev-neutral"
                      }
                      style={{ fontWeight: 700, fontSize: "0.72rem" }}
                    >
                      {regimeCurrent?.regime ?? "—"}
                    </span>
                  </span>
                </div>

                {warRegimeOpen ? (
                  regimeCurrent && regimeCurrent.n_recent > 0 ? (
                    <>
                      {/* Stacked bar */}
                      <div style={{ display: "flex", height: 10, borderRadius: 4, overflow: "hidden", gap: 1, marginTop: 2 }}>
                        {(["NORMAL", "CAUTION", "SHOCK"] as const).map((lbl) => {
                          const pct = regimeCurrent.regime_pct[lbl] ?? 0;
                          const color = lbl === "NORMAL" ? "#4ade80" : lbl === "CAUTION" ? "#fbbf24" : "#f87171";
                          return pct > 0 ? (
                            <div key={lbl} style={{ width: `${pct}%`, background: color, transition: "width 0.4s" }} title={`${lbl}: ${pct}%`} />
                          ) : null;
                        })}
                      </div>
                      {/* Legend */}
                      <div style={{ display: "flex", gap: 10, fontSize: "0.65rem", marginTop: 3 }}>
                        {(["NORMAL", "CAUTION", "SHOCK"] as const).map((lbl) => {
                          const color = lbl === "NORMAL" ? "#4ade80" : lbl === "CAUTION" ? "#fbbf24" : "#f87171";
                          const pct = regimeCurrent.regime_pct[lbl] ?? 0;
                          const cnt = regimeCurrent.regime_counts[lbl] ?? 0;
                          return (
                            <span key={lbl} style={{ color }}>
                              {lbl[0]}{lbl.slice(1).toLowerCase()} {pct}% ({cnt})
                            </span>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <div className="sev-meta" style={{ fontSize: "0.7rem" }}>
                      {regimeCurrent ? "Nessun dato campione" : "Caricamento…"}
                    </div>
                  )
                ) : (
                  <div className="subgroup-summary sev-meta">
                    {regimeCurrent
                      ? `${regimeCurrent.regime} · sample ${regimeCurrent.n_recent}`
                      : "Regime in caricamento..."}
                  </div>
                )}

                <div className="panel-title mt10 subgroup-title" style={{ display: "flex", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarPipelineOpen((v) => !v)}>
                      {warPipelineOpen ? "▾" : "▸"}
                    </button>
                    AUTOMATION PIPELINE
                    <span className={pipeHasRegime ? "sev-ok" : "sev-warn"}>{pipeHasRegime ? "READY" : "WAIT"}</span>
                  </span>
                </div>
                {warPipelineOpen ? (
                  <>
                    <div className="pipeline-row">
                      <Tooltip text={TOOLTIPS.pipe_data}><span className="pipe-step done">DATA</span></Tooltip>
                      <span className="pipe-arrow">→</span>
                      <Tooltip text={TOOLTIPS.pipe_ivr}><span className="pipe-step done">IVR</span></Tooltip>
                      <span className="pipe-arrow">→</span>
                      <Tooltip text={TOOLTIPS.pipe_regime}><span className={`pipe-step ${pipeRegimeStep}`}>REGIME</span></Tooltip>
                      <span className="pipe-arrow">→</span>
                      <Tooltip text={TOOLTIPS.pipe_score}><span className={`pipe-step ${pipeScoreStep}`}>SCORE</span></Tooltip>
                      <span className="pipe-arrow">→</span>
                      <Tooltip text={TOOLTIPS.pipe_kelly}><span className={`pipe-step ${pipeKellyStep}`}>KELLY</span></Tooltip>
                    </div>
                    <div className="sev-meta" style={{ fontSize: "0.65rem", marginTop: 3 }}>
                      {pipeHasRegime
                        ? `${regimeCurrent?.n_recent ?? 0} sample · ultimo scan ${regimeCurrent?.last_scan_ts ? new Date(regimeCurrent.last_scan_ts).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) : "—"}`
                        : "In attesa dati regime…"}
                    </div>
                  </>
                ) : (
                  <div className="subgroup-summary sev-meta">
                    {`DATA→IVR→${pipeRegimeStep.toUpperCase()}→${pipeScoreStep.toUpperCase()}→${pipeKellyStep.toUpperCase()}`}
                  </div>
                )}

                {/* ── ROC16: Quick-nav action strip ───────────────────── */}
                <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                  <button className="btn btn-secondary" style={{ fontSize: "0.65rem", padding: "3px 8px", flex: 1 }}
                    onClick={() => openOldTab("universe")}>
                    → SCAN
                  </button>
                  <button className="btn btn-secondary" style={{ fontSize: "0.65rem", padding: "3px 8px", flex: 1 }}
                    onClick={() => openOldTab("pipeline")}>
                    → PIPELINE
                  </button>
                </div>
                </>
                )}
              </article>

              {/* ── ROC7: IBKR ACCOUNT panel ──────────────────────────────── */}
              <article className="panel">
                <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarIbkrOpen((v) => !v)}>
                      {warIbkrOpen ? "▾" : "▸"}
                    </button>
                    IBKR ACCOUNT
                    {hasUrgentExit && (
                      <span style={{
                        fontSize: "0.65rem", padding: "1px 6px", borderRadius: 3,
                        background: "#3a0808", border: "1px solid #f87171",
                        color: "#f87171", fontWeight: 700,
                        animation: "pulse-run 0.8s infinite",
                      }} title={`${urgentExits.length} posizione/i con urgenza alta`}>
                        🚨 EXIT {urgentExits.length}
                      </span>
                    )}
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: "0.62rem", color: "#555" }}>agg: {_agoLabel(ibkrAccountFetchedAt)}</span>
                    <span style={{
                      fontSize: "0.7rem", padding: "2px 8px", borderRadius: 4,
                      background: ibkrAccount?.connected ? "#1a4a1a" : "#2a2a2a",
                      color: ibkrAccount?.connected ? "#4ade80" : "#666",
                      border: `1px solid ${ibkrAccount?.connected ? "#4ade80" : "#444"}`,
                    }}>
                      {ibkrAccount?.connected ? `LIVE · ${ibkrAccount.account_id ?? "—"}` : "NOT CONNECTED"}
                    </span>
                  </span>
                </div>
                {warIbkrOpen && (
                <>
                {ibkrAccountLoading && <div className="dim">Caricamento account…</div>}

                {!ibkrAccount && !ibkrAccountLoading && (
                  <div className="dim">Nessun dato — clicca ⟳ per aggiornare.</div>
                )}

                {ibkrAccount && (
                  <>
                    <div className="form-grid" style={{ marginTop: 8 }}>
                      <span className="dim">Net Liq</span>
                      <span style={{ color: "#4ade80", fontWeight: 600 }}>
                        {ibkrAccount.net_liquidation != null
                          ? `€${ibkrAccount.net_liquidation.toLocaleString("it-IT", { minimumFractionDigits: 2 })}`
                          : "—"}
                      </span>
                      <span className="dim">Buying Power</span>
                      <span>
                        {ibkrAccount.buying_power != null
                          ? `€${ibkrAccount.buying_power.toLocaleString("it-IT", { minimumFractionDigits: 2 })}`
                          : "—"}
                      </span>
                      <span className="dim">P&amp;L realizzato</span>
                      <span style={{ color: (ibkrAccount.realized_pnl ?? 0) >= 0 ? "#4ade80" : "#f87171" }}>
                        {ibkrAccount.realized_pnl != null
                          ? `${ibkrAccount.realized_pnl >= 0 ? "+" : ""}${ibkrAccount.realized_pnl.toFixed(2)}`
                          : "—"}
                      </span>
                      <span className="dim">P&amp;L non realizzato</span>
                      <span style={{ color: (ibkrAccount.unrealized_pnl ?? 0) >= 0 ? "#4ade80" : "#f87171" }}>
                        {ibkrAccount.unrealized_pnl != null
                          ? `${ibkrAccount.unrealized_pnl >= 0 ? "+" : ""}${ibkrAccount.unrealized_pnl.toFixed(2)}`
                          : "—"}
                      </span>
                      {ibkrAccount.net_liquidation != null && ibkrAccount.net_liquidation > 0 && (() => {
                        const totalPnl = (ibkrAccount.realized_pnl ?? 0) + (ibkrAccount.unrealized_pnl ?? 0);
                        const pct = (totalPnl / ibkrAccount.net_liquidation) * 100;
                        return (
                          <>
                            <span className="dim">P&amp;L portafoglio %</span>
                            <span style={{ color: pct >= 0 ? "#4ade80" : "#f87171", fontWeight: 600 }}>
                              {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                            </span>
                          </>
                        );
                      })()}
                    </div>

                    <div className="panel-title mt10 subgroup-title" style={{ display: "flex", alignItems: "center" }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <button type="button" className="panel-fold-btn" onClick={() => setWarIbkrPositionsOpen((v) => !v)}>
                          {warIbkrPositionsOpen ? "▾" : "▸"}
                        </button>
                        POSIZIONI APERTE <span className="sev-data">({ibkrAccount.positions.length})</span>
                      </span>
                    </div>
                    {warIbkrPositionsOpen && (
                      ibkrAccount.positions.length === 0 ? (
                        <div className="dim">Nessuna posizione aperta.</div>
                      ) : (
                        <div style={{ overflowX: "auto", maxHeight: 150, overflowY: "auto" }}>
                          <table style={{ width: "100%", fontSize: "0.7rem", borderCollapse: "collapse" }}>
                            <thead>
                              <tr style={{ color: "#666", borderBottom: "1px solid #333" }}>
                                <th style={{ textAlign: "left", padding: "2px 4px" }}>Sym</th>
                                <th style={{ textAlign: "left", padding: "2px 4px" }}>Exp</th>
                                <th style={{ textAlign: "right", padding: "2px 4px" }}>Strike</th>
                                <th style={{ textAlign: "center", padding: "2px 4px" }}>P/C</th>
                                <th style={{ textAlign: "right", padding: "2px 4px" }}>Qty</th>
                                <th style={{ textAlign: "right", padding: "2px 4px" }}>MktVal</th>
                                <th style={{ textAlign: "right", padding: "2px 4px" }}>uPnL</th>
                              </tr>
                            </thead>
                            <tbody>
                              {ibkrAccount.positions.map((pos, i) => (
                                <tr key={i} style={{ borderBottom: "1px solid #222" }}>
                                  <td style={{ padding: "2px 4px" }}>{pos.symbol}</td>
                                  <td style={{ padding: "2px 4px", color: "#888" }}>{pos.expiry ?? "—"}</td>
                                  <td style={{ padding: "2px 4px", textAlign: "right" }}>{pos.strike ?? "—"}</td>
                                  <td style={{ padding: "2px 4px", textAlign: "center", color: pos.right === "C" ? "#60a5fa" : "#fb923c" }}>{pos.right ?? "—"}</td>
                                  <td style={{ padding: "2px 4px", textAlign: "right", color: (pos.quantity ?? 0) < 0 ? "#f87171" : "#4ade80" }}>{pos.quantity}</td>
                                  <td style={{ padding: "2px 4px", textAlign: "right" }}>{pos.market_value?.toFixed(0) ?? "—"}</td>
                                  <td style={{ padding: "2px 4px", textAlign: "right", color: (pos.unrealized_pnl ?? 0) >= 0 ? "#4ade80" : "#f87171" }}>
                                    {pos.unrealized_pnl != null ? `${pos.unrealized_pnl >= 0 ? "+" : ""}${pos.unrealized_pnl.toFixed(0)}` : "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )
                    )}
                  </>
                )}

                <button
                  className="btn btn-secondary mt10"
                  style={{ fontSize: "0.7rem", padding: "3px 8px" }}
                  disabled={ibkrAccountLoading}
                  onClick={() => void doFetchIbkrAccount()}
                >
                  {ibkrAccountLoading ? "…" : "⟳ ACCOUNT"}
                </button>

                {/* ── ROC14: Exit Candidates ──────────────────────────── */}
                <div className="panel-title mt10 subgroup-title" style={{ display: "flex", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarIbkrExitOpen((v) => !v)}>
                      {warIbkrExitOpen ? "▾" : "▸"}
                    </button>
                    EXIT CANDIDATES
                    <span
                      className={!exitCandidates ? "sev-neutral" : exitCandidates.n_flagged > 0 ? "sev-warn" : "sev-data"}
                      style={{ fontSize: "0.62rem", marginLeft: 8 }}
                    >
                      {exitCandidates ? `${exitCandidates.n_flagged}/${exitCandidates.n_total} flagged` : "—"}
                    </span>
                    <span className="sev-meta" style={{ fontSize: "0.62rem", marginLeft: 8 }}>
                      agg: {_agoLabel(exitCandidatesFetchedAt)}
                    </span>
                  </span>
                </div>

                {warIbkrExitOpen && (
                  <>
                    {!exitCandidates && (
                      <div className="dim" style={{ fontSize: "0.7rem" }}>Caricamento…</div>
                    )}

                    {exitCandidates && exitCandidates.candidates.length === 0 && (
                      <div className="dim" style={{ fontSize: "0.7rem" }}>
                        Nessuna posizione con segnale di uscita.
                      </div>
                    )}

                    {exitCandidates && exitCandidates.candidates.map((c, i) => {
                      const score = c.exit_score;
                      const color = score >= 5 ? "#f87171" : score >= 3 ? "#fbbf24" : "#60a5fa";
                      const dot   = score >= 5 ? "🔴" : score >= 3 ? "🟡" : "🔵";
                      const pnlColor = (c.unrealized_pnl ?? 0) >= 0 ? "#4ade80" : "#f87171";
                      return (
                        <div key={i} style={{
                          marginTop: 6, padding: "6px 8px",
                          background: "#1a1a1a", borderRadius: 4,
                          borderLeft: `3px solid ${color}`,
                          fontSize: "0.72rem",
                        }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontWeight: 700 }}>
                              {dot} {c.symbol} {c.strike ?? "—"}{c.right ?? ""}
                            </span>
                            <span style={{ color, fontWeight: 700 }}>score {score}</span>
                          </div>
                          <div style={{ color: "#888", marginTop: 2 }}>
                            exp {c.expiry ?? "—"}
                            {c.unrealized_pnl != null && (
                              <span style={{ color: pnlColor, marginLeft: 8 }}>
                                uPnL {c.unrealized_pnl >= 0 ? "+" : ""}{c.unrealized_pnl.toFixed(0)}
                              </span>
                            )}
                          </div>
                          <div style={{ color: "#666", marginTop: 2, fontStyle: "italic" }}>
                            {c.exit_reasons.join(" · ")}
                          </div>
                        </div>
                      );
                    })}

                    {exitCandidates && (
                      <button
                        className="btn btn-secondary mt10"
                        style={{ fontSize: "0.7rem", padding: "3px 8px" }}
                        onClick={() => void doFetchExitCandidates()}
                      >
                        ⟳ EXIT SCAN
                      </button>
                    )}
                  </>
                )}
                </>
                )}
              </article>

              {/* ── WHEEL POSITIONS ── */}
              {(() => {
                // Copilot model: due livelli separati
                // wheelAvailable: capitale sufficiente (capital_tier ≥ SMALL) — pannello visibile
                // wheelValidated: gate superato (active_mode ≥ SMALL) — operazione certificata
                const wheelAvailable  = tierInfo?.features_available?.wheel  ?? false;
                const wheelValidated  = tierInfo?.features_validated?.wheel  ?? false;
                const wheelWarning    = wheelAvailable && !wheelValidated;
                const capitalTierName = tierInfo?.capital_tier ?? "MICRO";
                return (
              <article className="panel" style={{ gridColumn: "1 / -1", position: "relative" }}>
                <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <button type="button" className="panel-fold-btn" onClick={() => setWarWheelOpen((v) => !v)}>
                      {warWheelOpen ? "▾" : "▸"}
                    </button>
                    🔄 WHEEL POSITIONS
                  </span>
                  <span style={{ fontSize: "0.65rem", color: "#555", fontWeight: 400 }}>
                    {!wheelAvailable
                      ? <span style={{ color: "#a78bfa" }}>🔒 Capitale insufficiente</span>
                      : wheelWarning
                        ? <span style={{ color: "#f97316" }}>⚠ Non ancora validato</span>
                        : (wheelFetchedAt ? new Date(wheelFetchedAt).toLocaleTimeString("it-IT") : "—")
                    }
                  </span>
                </div>
                {warWheelOpen && (
                  <>

                {/* BLOCCO REALE: capitale insufficiente */}
                {!wheelAvailable && (
                  <div style={{
                    padding: "16px 12px",
                    background: "rgba(167,139,250,0.06)",
                    border: "1px dashed #a78bfa44",
                    borderRadius: 6,
                    fontSize: "0.72rem", color: "#888",
                    display: "flex", alignItems: "center", gap: 10,
                  }}>
                    <span style={{ fontSize: "1.2rem" }}>🔒</span>
                    <div>
                      <div style={{ color: "#a78bfa", fontWeight: 700, marginBottom: 2 }}>Wheel richiede capitale SMALL (€2k–5k)</div>
                      <div>Capitale attuale: <strong style={{ color: "#60a5fa" }}>{capitalTierName}</strong> — aumenta il capitale per accedere a questa strategia.</div>
                      {tierInfo?.next_capital_tier && (
                        <div style={{ marginTop: 4, color: "#555" }}>
                          Prossimo tier capitale → {tierInfo.next_capital_tier}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* WARNING COPILOTA: capitale ok, gate non ancora superato */}
                {wheelWarning && (
                  <div style={{
                    padding: "10px 12px",
                    background: "rgba(249,115,22,0.08)",
                    border: "1px solid #f9731644",
                    borderRadius: 6,
                    fontSize: "0.72rem", color: "#f97316",
                    display: "flex", alignItems: "center", gap: 10,
                    marginBottom: 10,
                  }}>
                    <span style={{ fontSize: "1.1rem" }}>⚠</span>
                    <div>
                      <strong>Strategia non ancora validata sul tuo track record.</strong>
                      {" "}Procedi con consapevolezza.
                      {tierInfo?.next_operational_tier && (
                        <span style={{ color: "#888", marginLeft: 6 }}>
                          Gate operativo: 50 trade chiusi · Sharpe OOS ≥ 0.6 · 0 violazioni
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {wheelAvailable && !wheelPositions && (
                  <div className="dim" style={{ fontSize: "0.7rem" }}>Nessun dato — clicca ⟳ per aggiornare.</div>
                )}

                {wheelAvailable && wheelPositions && wheelPositions.positions.length === 0 && (
                  <div className="dim" style={{ fontSize: "0.7rem" }}>Nessuna posizione Wheel attiva.</div>
                )}

                {wheelAvailable && wheelPositions && wheelPositions.positions.length > 0 && (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.7rem" }}>
                      <thead>
                        <tr style={{ color: "#555", borderBottom: "1px solid #2a2a2a" }}>
                          <th style={{ textAlign: "left", padding: "3px 6px" }}>SYMBOL</th>
                          <th style={{ textAlign: "left", padding: "3px 6px" }}>STATE</th>
                          <th style={{ textAlign: "right", padding: "3px 6px" }}>CSP K</th>
                          <th style={{ textAlign: "left", padding: "3px 6px" }}>CSP EXP</th>
                          <th style={{ textAlign: "right", padding: "3px 6px" }}>CC K</th>
                          <th style={{ textAlign: "left", padding: "3px 6px" }}>CC EXP</th>
                          <th style={{ textAlign: "right", padding: "3px 6px" }}>PREMIUM</th>
                          <th style={{ textAlign: "right", padding: "3px 6px" }}>CYCLES</th>
                        </tr>
                      </thead>
                      <tbody>
                        {wheelPositions.positions.map((p) => {
                          const stateColor: Record<string, string> = {
                            IDLE: "#555",
                            OPEN_CSP: "#60a5fa",
                            ASSIGNED: "#fbbf24",
                            OPEN_CC: "#a78bfa",
                            CLOSED: "#4ade80",
                          };
                          const col = stateColor[p.state] ?? "#888";
                          return (
                            <tr key={p.position_id} style={{ borderBottom: "1px solid #1a1a1a" }}>
                              <td style={{ padding: "4px 6px", fontWeight: 700 }}>{p.symbol}</td>
                              <td style={{ padding: "4px 6px" }}>
                                <span style={{
                                  color: col, fontWeight: 700,
                                  background: col + "22", borderRadius: 3,
                                  padding: "1px 5px", fontSize: "0.65rem",
                                }}>{p.state}</span>
                              </td>
                              <td style={{ padding: "4px 6px", textAlign: "right", color: "#ccc" }}>
                                {p.csp_strike ?? "—"}
                              </td>
                              <td style={{ padding: "4px 6px", color: "#777" }}>
                                {p.csp_expiry ?? "—"}
                              </td>
                              <td style={{ padding: "4px 6px", textAlign: "right", color: "#ccc" }}>
                                {p.cc_strike ?? "—"}
                              </td>
                              <td style={{ padding: "4px 6px", color: "#777" }}>
                                {p.cc_expiry ?? "—"}
                              </td>
                              <td style={{ padding: "4px 6px", textAlign: "right", color: "#4ade80" }}>
                                +{p.total_premium_collected.toFixed(0)}
                              </td>
                              <td style={{ padding: "4px 6px", textAlign: "right", color: "#888" }}>
                                {p.cycle_count}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                {wheelAvailable && (
                  <button
                    className="btn btn-secondary mt10"
                    style={{ fontSize: "0.7rem", padding: "3px 8px" }}
                    onClick={() => void doFetchWheelPositions()}
                  >
                    ⟳ WHEEL REFRESH
                  </button>
                )}
                  </>
                )}
                {!warWheelOpen && (
                  <div className="dim" style={{ fontSize: "0.7rem", marginTop: 6 }}>
                    {!wheelAvailable
                      ? "Wheel bloccata: capitale insufficiente (richiede SMALL)."
                      : wheelWarning
                        ? "Strategia non ancora validata sul track record (gate operativo richiesto)."
                        : wheelPositions?.positions?.length
                          ? `${wheelPositions.positions.length} posizione/i Wheel attive.`
                          : "Nessuna posizione Wheel attiva."}
                  </div>
                )}
              </article>
                );
              })()}
            </div>
            </>
          )}

          {centerPhase === "old" && resolvedTab === "premarket" && (
            <div className="panel-grid two premarket-step-grid">
              <article className="panel">
                <div className="panel-title">STEP 1 — DATI</div>
                <div className="slide-step-card">
                  <button className="slide-step-head" onClick={() => setSlideStepDataOpen((v) => !v)}>
                    <span className="slide-step-title">
                      <span className="group-arrow">{slideStepDataOpen ? "▾" : "▸"}</span>
                      La pipeline si avvia
                    </span>
                    <span className={healthToSevClass(stepDataHealth)}>{stepDataStatusLabel}</span>
                  </button>
                  {!slideStepDataOpen ? (
                    <div className="subgroup-summary sev-meta">{stepDataSummary}</div>
                  ) : (
                    <>
                      <div className="sev-meta" style={{ marginBottom: 4 }}>
                        {premarketScanAt ? `${fmtTs(premarketScanAt)} — ingest feed` : "Nessun timestamp pipeline disponibile"}
                      </div>
                      <div className="sev-meta" style={{ marginBottom: 8 }}>{stepDataHint}</div>
                      <div className="adaptive-grid">
                        <div className="slide-mini-card">
                          <div className="slide-mini-headline">
                            <span>PIPELINE</span>
                            <span className="slide-mini-chevron">{slideDataPipelineOpen ? "▾" : "▸"}</span>
                          </div>
                          <button
                            className={`slide-mini-value-btn ${healthToSevClass(pipelineStateHealth)}`}
                            onClick={() => setSlideDataPipelineOpen((v) => !v)}
                          >
                            {pipelineStateLabel}
                          </button>
                          <div className="slide-mini-brief">
                            <Tooltip text="Stato complessivo del flusso ingest: combina esito feed, criticita aperte e disponibilita della sorgente.">
                              ingest + criticita + source
                            </Tooltip>
                          </div>
                          {slideDataPipelineOpen && (
                            <div className="slide-mini-detail">
                              ingest: <b className={healthToSevClass(ingestHealth)}>{ingestLabel}</b><br />
                              criticita: {pipelineCriticality ?? 0}<br />
                              source: {premarketSource}
                            </div>
                          )}
                        </div>
                        <div className="slide-mini-card">
                          <div className="slide-mini-headline">
                            <span>RECORD RICEVUTI</span>
                            <span className="slide-mini-chevron">{slideDataRecordsOpen ? "▾" : "▸"}</span>
                          </div>
                          <button
                            className="slide-mini-value-btn sev-data"
                            onClick={() => setSlideDataRecordsOpen((v) => !v)}
                          >
                            {pipelineRecords.toLocaleString("it-IT")}
                          </button>
                          <div className="slide-mini-brief">
                            <Tooltip text="Volume record utili caricati nel batch pre-market: indica dimensione e significativita del dataset per le fasi successive.">
                              volume batch + shortlist
                            </Tooltip>
                          </div>
                          {slideDataRecordsOpen && (
                            <div className="slide-mini-detail">
                              batch: <code>{pipelineBatch}</code><br />
                              shortlist: {premarketShortlistCount}<br />
                              pronti: {premarketReadyCount}
                            </div>
                          )}
                        </div>
                        <div className="slide-mini-card">
                          <div className="slide-mini-headline">
                            <span>DATA_MODE</span>
                            <span className="slide-mini-chevron">{slideDataModeOpen ? "▾" : "▸"}</span>
                          </div>
                          <button
                            className={`slide-mini-value-btn ${apiOnline ? (hasRealData ? "sev-ok" : "sev-warn") : "sev-neutral"}`}
                            onClick={() => setSlideDataModeOpen((v) => !v)}
                          >
                            {dataModeUpper || "N/D"}
                          </button>
                          <div className="slide-mini-brief">
                            <Tooltip text="Origine dei dati usati dal sistema. VENDOR_REAL indica feed reale; modalita sintetica segnala fallback di sicurezza.">
                              origine feed attivo
                            </Tooltip>
                          </div>
                          {slideDataModeOpen && (
                            <div className="slide-mini-detail">
                              yfinance/cboe: {yfinanceLabel}<br />
                              fred: {fredLabel}<br />
                              orats: {oratsLabel}
                            </div>
                          )}
                        </div>
                        <div className="slide-mini-card">
                          <div className="slide-mini-headline">
                            <span>LATENZA FEED</span>
                            <span className="slide-mini-chevron">{slideDataLatencyOpen ? "▾" : "▸"}</span>
                          </div>
                          <button
                            className={`slide-mini-value-btn ${!apiOnline ? "sev-neutral" : pipelineLatencyState === "FRESH" ? "sev-ok" : "sev-warn"}`}
                            onClick={() => setSlideDataLatencyOpen((v) => !v)}
                          >
                            {pipelineLatencyState}
                          </button>
                          <div className="slide-mini-brief">
                            <Tooltip text="Freschezza dell'ultimo ciclo ingest, errori fetch e stato readiness storico. Misura il ritardo operativo del feed.">
                              freshness + errors + readiness
                            </Tooltip>
                          </div>
                          {slideDataLatencyOpen && (
                            <div className="slide-mini-detail">
                              fetch errors: {fetchErrors.size}<br />
                              readiness: {pipelineReadinessLine}<br />
                              data health: {dataHealthLabel}
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </article>
              <article className="panel">
                <div className="adaptive-grid">
                  <div className="slide-mini-card span-full">
                    <div className="slide-mini-headline">
                      <span>INGEST PIPELINE LOG — PRE-MARKET</span>
                    </div>
                    <pre className="console premarket-console">{[
                      `[${premarketScanAt ? fmtTs(premarketScanAt) : "--"}] ${apiOnline ? "INFO" : "WARN"}  feed connected — source: ${premarketSource}`,
                      `[${premarketScanAt ? fmtTs(premarketScanAt) : "--"}] RECV  chain records — ${pipelineRecords}`,
                      `[${premarketScanAt ? fmtTs(premarketScanAt) : "--"}] META  DATA_MODE = ${dataModeUpper || "N/D"}`,
                      `[${premarketScanAt ? fmtTs(premarketScanAt) : "--"}] META  batch_id = ${pipelineBatch}`,
                      `[${premarketScanAt ? fmtTs(premarketScanAt) : "--"}] ${hasRealData ? "INFO" : "WARN"}  validation ${pipelineStateLabel}`,
                    ].join("\n")}</pre>
                  </div>

                  <div className="slide-mini-card">
                    <div className="slide-mini-headline">
                      <span>SOURCE QUALITY</span>
                    </div>
                    <div className={`slide-mini-value ${healthToSevClass(dataHealthOverall)}`}>{dataHealthLabel}</div>
                    <div className="slide-mini-brief">qualita dataset ingest</div>
                  </div>
                  <div className="slide-mini-card">
                    <div className="slide-mini-headline">
                      <span>HISTORY READINESS</span>
                    </div>
                    <div className={`slide-mini-value ${historyReadiness?.ready ? "sev-ok" : "sev-warn"}`}>
                      {historyReadiness ? `${historyReadiness.score_pct.toFixed(1)}%` : "N/D"}
                    </div>
                    <div className="slide-mini-brief">copertura e qualita storica</div>
                  </div>
                  <div className="slide-mini-card">
                    <div className="slide-mini-headline">
                      <span>PROSSIMA FASE</span>
                    </div>
                    <div className="slide-mini-value sev-data">ANALISI</div>
                    <div className="slide-mini-brief">step successivo della pipeline</div>
                  </div>
                  <div className="slide-mini-card">
                    <div className="slide-mini-headline">
                      <span>RECORD SCRITTI</span>
                    </div>
                    <div className="slide-mini-value sev-data">{pipelineRecords.toLocaleString("it-IT")}</div>
                    <div className="slide-mini-brief">record validati su batch corrente</div>
                  </div>
                  <div className="slide-mini-card">
                    <div className="slide-mini-headline">
                      <span>BATCH</span>
                    </div>
                    <div className="slide-mini-value sev-meta">{pipelineBatch}</div>
                    <div className="slide-mini-brief">identificativo ingest corrente</div>
                  </div>
                </div>
              </article>
            </div>
          )}

          {centerPhase === "old" && resolvedTab === "pipeline" && (
            <div className="panel-grid three">
              <article className="panel">
                <div className="panel-title">EQUITY SNAPSHOT</div>
                <div className="form-grid">
                  <label>Date UTC</label><input value={snapDate} onChange={(e) => setSnapDate(e.target.value)} />
                  <label>Equity</label><input value={snapEquity} onChange={(e) => setSnapEquity(e.target.value)} />
                  <label>Note</label><input value={snapNote} onChange={(e) => setSnapNote(e.target.value)} />
                </div>
                <button className="btn btn-primary" onClick={doAddSnapshot} disabled={busy}>ADD SNAPSHOT</button>
              </article>

              <article className="panel">
                <div className="panel-title">TRADE JOURNAL</div>
                <div className="form-grid">
                  <label>Entry TS UTC</label><input value={tradeEntryTs} onChange={(e) => setTradeEntryTs(e.target.value)} placeholder="2026-03-05T15:30:00Z" />
                  <label>Exit TS UTC</label><input value={tradeExitTs} onChange={(e) => setTradeExitTs(e.target.value)} placeholder="2026-03-05T17:30:00Z" />
                  <label>Strikes JSON</label><input value={tradeStrikes} onChange={(e) => setTradeStrikes(e.target.value)} placeholder="[185,180]" />
                  <label>Regime</label><input value={tradeRegime} onChange={(e) => setTradeRegime(e.target.value)} />
                  <label>Score</label><input value={tradeScore} onChange={(e) => setTradeScore(e.target.value)} />
                  <label>Kelly</label><input value={tradeKelly} onChange={(e) => setTradeKelly(e.target.value)} />
                  <label>Exit reason</label><input value={tradeExitReason} onChange={(e) => setTradeExitReason(e.target.value)} />
                  <label>PnL</label><input value={tradePnl} onChange={(e) => setTradePnl(e.target.value)} />
                  <label>PnL %</label><input value={tradePnlPct} onChange={(e) => setTradePnlPct(e.target.value)} />
                  <label>Slippage</label><input value={tradeSlip} onChange={(e) => setTradeSlip(e.target.value)} />
                  <label>Violations</label><input value={tradeViol} onChange={(e) => setTradeViol(e.target.value)} />
                  <label>Note</label><input value={tradeNote} onChange={(e) => setTradeNote(e.target.value)} />
                </div>
                <button className="btn btn-primary" onClick={doAddTrade} disabled={busy}>ADD TRADE</button>
              </article>

              <article className="panel">
                <div className="panel-title">EXEC PREVIEW/CONFIRM</div>
                {!blk("order_preview").interactive && blk("order_preview").reason && (
                  <div className="notice error" style={{ marginBottom: 6 }}>
                    🛑 {blk("order_preview").reason}
                  </div>
                )}
                <div className="form-grid">
                  <label>Symbol</label><input value={symbol} onChange={(e) => setSymbol(e.target.value)} disabled={!blk("order_preview").interactive} />
                  <label>Strategy</label>
                  <select value={strategy} onChange={(e) => setStrategy(e.target.value)} disabled={!blk("order_preview").interactive} style={{ background: "#111", color: "#ccc", border: "1px solid #333", padding: "2px 4px", fontSize: "0.75rem" }}>
                    {/* Tier-aware strategy list — shows only strategies available for current capital_tier */}
                    <option value="BULL_PUT">BULL_PUT</option>
                    {(tierInfo?.features_available?.iron_condor ?? true) && <option value="IRON_CONDOR">IRON_CONDOR</option>}
                    {(tierInfo?.features_available?.wheel ?? true) && <option value="WHEEL">WHEEL</option>}
                    {(tierInfo?.features_available?.pmcc_calendar ?? false) && <option value="PMCC_CALENDAR">PMCC_CALENDAR</option>}
                    {(tierInfo?.features_available?.hedge_active ?? false) && <option value="HEDGE_ACTIVE">HEDGE_ACTIVE</option>}
                    {(tierInfo?.features_available?.ratio_spread ?? false) && <option value="RATIO_SPREAD">RATIO_SPREAD</option>}
                    {(tierInfo?.features_available?.delta_overlay ?? false) && <option value="DELTA_OVERLAY">DELTA_OVERLAY</option>}
                    {/* Allow custom value if already set (e.g. loaded from scan) */}
                    {!["BULL_PUT","IRON_CONDOR","WHEEL","PMCC_CALENDAR","HEDGE_ACTIVE","RATIO_SPREAD","DELTA_OVERLAY"].includes(strategy) && (
                      <option value={strategy}>{strategy}</option>
                    )}
                  </select>
                  <label>Payload JSON</label><textarea rows={6} value={payload} onChange={(e) => setPayload(e.target.value)} disabled={!blk("order_preview").interactive} />
                </div>
                {payloadJsonError && <div className="notice error">Payload JSON non valido.</div>}
                {previewDirty && <div className="notice error">Preview non allineata al payload corrente.</div>}
                <div className="actions">
                  <button className="btn btn-primary" onClick={doPreview} disabled={busy || payloadJsonError || !blk("order_preview").interactive}>PREVIEW</button>
                  <select value={confirmDecision} onChange={(e) => setConfirmDecision(e.target.value as "APPROVE" | "REJECT")} disabled={!blk("order_confirm").interactive}>
                    <option value="APPROVE">APPROVE</option><option value="REJECT">REJECT</option>
                  </select>
                  <button
                    className={`btn ${confirmArmed ? "btn-warning" : "btn-danger"}`}
                    onClick={doConfirm}
                    disabled={busy || !preview || payloadJsonError || previewDirty || !blk("order_confirm").interactive}
                    title={!blk("order_confirm").interactive ? (blk("order_confirm").reason ?? "Non disponibile") : confirmArmed ? "Clicca ancora per inviare l'ordine" : "Prima conferma — secondo click invia"}
                  >{confirmArmed ? "⚠ CONFERMA ORDINE?" : "CONFIRM"}</button>
                </div>
                <pre className="console">{preview ? JSON.stringify(preview, null, 2) : "Nessuna anteprima."}</pre>
              </article>
            </div>
          )}

          {centerPhase === "old" && resolvedTab === "universe" && (
            <div className="panel-grid two">
                            <article className="panel">
                <div className="panel-title">UNIVERSE CONFIG</div>
                <div className="form-grid">
                  <label>Source</label>
                  <select value={universeSource} onChange={(e) => setUniverseSource(e.target.value as "auto" | "manual" | "ibkr_settings") }>
                    <option value="ibkr_settings">ibkr_settings</option>
                    <option value="manual">manual</option>
                    <option value="auto">auto</option>
                  </select>

                  {universeSource === "manual" && (
                    <>
                      <label>Symbols</label>
                      <input
                        value={universeSymbols}
                        onChange={(e) => setUniverseSymbols(e.target.value)}
                        placeholder="SPY,QQQ,IWM,..."
                      />
                    </>
                  )}

                  <label>Regime</label>
                  <select
                    value={universeRegime}
                    onChange={(e) => setUniverseRegime(e.target.value as "NORMAL" | "CAUTION" | "SHOCK")}
                  >
                    <option value="NORMAL">NORMAL</option>
                    <option value="CAUTION">CAUTION</option>
                    <option value="SHOCK">SHOCK</option>
                  </select>

                  <label>Top N</label>
                  <input value={universeTopN} onChange={(e) => setUniverseTopN(e.target.value)} />

                  <label>Settings path</label>
                  <input
                    value={universeSettingsPath}
                    onChange={(e) => setUniverseSettingsPath(e.target.value)}
                    placeholder="default: docs/IBKE setting decriptato.sanitized.xml"
                  />

                  <label>Scanner</label>
                  <select value={universeScannerName} onChange={(e) => setUniverseScannerName(e.target.value)}>
                    {ibkrScanners.map((s) => (
                      <option key={s.scanner_name} value={s.scanner_name}>
                        {s.scanner_name} ({s.scan_code || "n/a"})
                      </option>
                    ))}
                    {ibkrScanners.length === 0 && <option value="">No scanner</option>}
                  </select>
                </div>

                <div className="actions">
                  <button className="btn btn-primary" onClick={() => void doAutoDemoPipeline()} disabled={busy}>
                    AUTO PIPELINE
                  </button>
                  <button className="btn btn-primary" onClick={doUniverseScan} disabled={busy}>
                    RUN SCAN
                  </button>
                  <button className="btn" onClick={refreshAll} disabled={busy}>
                    REFRESH
                  </button>
                </div>

                <ul className="activity-list">
                  <li>Batch: <code>{universeLatest?.batch_id ?? "-"}</code></li>
                  <li>Created UTC: {universeLatest?.created_at_utc ? fmtTs(universeLatest.created_at_utc) : "-"}</li>
                  <li>Regime: {universeLatest?.regime ?? "-"}</li>
                  <li>Source: {universeLatest?.source ?? "-"}</li>
                  <li>Market rows: {universeLatest?.market_rows_available ?? 0}</li>
                  <li>Universe size: {universeLatest?.universe_size ?? 0}</li>
                  <li>Settings file: {ibkrContext?.settings_exists ? "FOUND" : "MISSING"}</li>
                  <li>Quote symbols in settings: {ibkrContext?.quote_symbol_count ?? 0}</li>
                  <li>Scanner code: {selectedScanner?.scan_code || "-"}</li>
                  <li>Filter fallback: {universeLatest?.filter_fallback ? "YES" : "NO"}</li>
                  <li>Provenance rows API/OCR: {(universeProvenance?.api_rows ?? 0)} / {(universeProvenance?.ocr_rows ?? 0)}</li>
                  <li>Provenance ts: {universeProvenance?.generated_at_utc ? fmtTs(universeProvenance.generated_at_utc) : "-"}</li>
                </ul>

                {selectedScannerFilters.length > 0 && (
                  <pre className="console">{JSON.stringify(Object.fromEntries(selectedScannerFilters), null, 2)}</pre>
                )}
              </article>

              <article className="panel">
                <div className="panel-title">UNIVERSE PANELS (IBKR)</div>
                <div className="universe-subtabs">
                  <button className={`btn ${universeSubTab === "titoli" ? "btn-primary" : ""}`} onClick={() => setUniverseSubTab("titoli")}>Titoli</button>
                  <button className={`btn ${universeSubTab === "indici" ? "btn-primary" : ""}`} onClick={() => setUniverseSubTab("indici")}>Indici</button>
                  <button className={`btn ${universeSubTab === "opzioni" ? "btn-primary" : ""}`} onClick={() => setUniverseSubTab("opzioni")}>Opzioni</button>
                  <button className={`btn ${universeSubTab === "ciclo" ? "btn-primary" : ""}`} onClick={() => setUniverseSubTab("ciclo")}>Ciclo</button>
                  <button className={`btn ${universeSubTab === "palinsesto" ? "btn-primary" : ""}`} onClick={() => setUniverseSubTab("palinsesto")}>Palinsesto</button>
                </div>

                {universeSubTab === "opzioni" && (
                  <table className="data-table shortlist-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Symbol</th>
                        <th>Strategy</th>
                        <th><Tooltip text={TOOLTIPS.score_composito}>Score</Tooltip></th>
                        <th><Tooltip text={TOOLTIPS.ivr}>IVR</Tooltip></th>
                        <th><Tooltip text={TOOLTIPS.spread_pct}>Spread</Tooltip></th>
                        <th>Source</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {opzioniRows.map((it) => (
                        <tr key={`u-${it.rank}-${it.symbol}`}>
                          <td>{it.rank}</td>
                          <td>{it.symbol}</td>
                          <td>{it.strategy}</td>
                          <td>{it.score.toFixed(3)}</td>
                          <td>{(it.iv_rank * 100).toFixed(1)}%</td>
                          <td>{(it.spread_pct * 100).toFixed(2)}%</td>
                          <td><span className={`source-badge ${sourceBadgeClass(rowSourceBySymbol.get(it.symbol.toUpperCase()) ?? "none")}`}>{(rowSourceBySymbol.get(it.symbol.toUpperCase()) ?? "none").toUpperCase()}</span></td>
                          <td>
                            <button
                              className="btn btn-ghost"
                              onClick={() => {
                                setSymbol(it.symbol);
                                setStrategy(it.strategy);
                                setPayload(
                                  JSON.stringify(
                                    {
                                      source: "universe_shortlist",
                                      symbol: it.symbol,
                                      strategy: it.strategy,
                                      rank: it.rank,
                                      score: it.score,
                                      regime: universeLatest?.regime ?? universeRegime,
                                    },
                                    null,
                                    2
                                  )
                                );
                                openOldTab("pipeline");
                                setError("");
                                setMessage(`Candidate loaded: ${it.symbol}/${it.strategy}`);
                              }}
                            >
                              LOAD
                            </button>
                          </td>
                        </tr>
                      ))}
                      {opzioniRows.length === 0 && (
                        <tr>
                          <td colSpan={8} className="dim">Nessuna shortlist disponibile. Esegui RUN SCAN.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}

                {universeSubTab !== "opzioni" && (
                  <table className="data-table shortlist-table">
                    <thead>
                      <tr><th>#</th><th>Symbol</th><th>Last</th><th>VS%</th><th>VI%</th><th>Source</th></tr>
                    </thead>
                    <tbody>
                      {nonOptionsRows.map((row, idx) => (
                        <tr key={`sym-${universeSubTab}-${row.symbol}`}>
                          <td>{idx + 1}</td>
                          <td>{row.symbol}</td>
                          <td className={fieldClass(row.field_sources?.last)}>{row.last === null ? "-" : row.last.toFixed(3)}</td>
                          <td className={fieldClass(row.field_sources?.vs_pct)}>{row.vs_pct === null ? "-" : `${(row.vs_pct * 100).toFixed(2)}%`}</td>
                          <td className={fieldClass(row.field_sources?.vi_pct)}>{row.vi_pct === null ? "-" : `${(row.vi_pct * 100).toFixed(2)}%`}</td>
                          <td><span className={`source-badge ${sourceBadgeClass(row.source)}`}>{row.source.toUpperCase()}</span></td>
                        </tr>
                      ))}
                      {nonOptionsRows.length === 0 && (
                        <tr><td colSpan={6} className="dim">Nessun simbolo disponibile in questo pannello.</td></tr>
                      )}
                    </tbody>
                  </table>
                )}
              </article>
            </div>
          )}
          {centerPhase === "old" && resolvedTab === "opportunity" && (
            <div className="panel-grid two">

              {/* ── LEFT: SCAN OPZ ───────────────────────────────────────── */}
              <article className="panel">
                <div className="panel-title">SCAN OPZ</div>
                <div className="form-grid">
                  <label>Simboli</label>
                  <input value={oppScanSymbols} onChange={(e) => setOppScanSymbols(e.target.value)} placeholder="SPY,QQQ,AAPL" />
                  <label>Regime</label>
                  <select value={oppScanRegime} onChange={(e) => setOppScanRegime(e.target.value as typeof oppScanRegime)}>
                    <option value="NORMAL">NORMAL</option>
                    <option value="CAUTION">CAUTION</option>
                    <option value="SHOCK">SHOCK</option>
                  </select>
                  <label>Top N</label>
                  <input value={oppScanTopN} onChange={(e) => setOppScanTopN(e.target.value)} style={{ width: "60px" }} />
                  <label>Account €</label>
                  <input value={oppScanAccountSize} onChange={(e) => setOppScanAccountSize(e.target.value)} />
                </div>
                <div className="actions">
                  <button className="btn btn-primary" onClick={doScanFull} disabled={oppScanBusy || busy}>
                    {oppScanBusy ? "SCANNING..." : "RUN SCAN"}
                  </button>
                  <button className="btn btn-ghost" onClick={doLoadEvReport} disabled={busy}>EV REPORT</button>
                </div>

                {/* ── IBKR connection badge ──────────────────────────────── */}
                <div style={{ display: "flex", gap: "6px", alignItems: "center", marginTop: "6px" }}>
                  <Tooltip text={ibkrStatus?.connected ? TOOLTIPS.ibkr_connected : TOOLTIPS.ibkr_disconnected}>
                    <span
                      style={{
                        padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontWeight: 600,
                        background: ibkrStatus?.connected ? "#1a4a1a" : "#3a2a10",
                        color: ibkrStatus?.connected ? "#4ade80" : "#fbbf24",
                        border: `1px solid ${ibkrStatus?.connected ? "#4ade80" : "#fbbf24"}`,
                      }}
                    >
                      {ibkrStatus?.connected
                        ? `IBKR ● :${ibkrStatus.port}`
                        : ibkrStatus ? "IBKR ○ yfinance" : "IBKR ?"}
                    </span>
                  </Tooltip>
                  <button
                    className="btn-small"
                    disabled={ibkrChecking}
                    onClick={() => doCheckIbkr(true)}
                    title="Tenta connessione a TWS/Gateway"
                  >
                    {ibkrChecking ? "…" : "⟳ IBKR"}
                  </button>
                </div>

                {oppScanResult && (
                  <ul className="activity-list" style={{ marginTop: "8px" }}>
                    <li>Batch: <code>{oppScanResult.batch_id}</code> &nbsp;|&nbsp; {fmtTs(oppScanResult.scan_ts)}</li>
                    <li>
                      Data: <code>{oppScanResult.data_mode}</code>
                      &nbsp;|&nbsp;
                      Fonte eventi:&nbsp;
                      <span style={{
                        color: oppScanResult.events_source === "ibkr_live" ? "#4ade80"
                          : oppScanResult.events_source === "yfinance" ? "#fbbf24" : "#94a3b8"
                      }}>
                        {oppScanResult.events_source}
                      </span>
                    </li>
                    <li>Chain: {oppScanResult.symbols_with_chain}/{oppScanResult.symbols_scanned} &nbsp;|&nbsp; Filtrati: {oppScanResult.filtered_count}</li>
                    {oppScanResult.ranking_suspended && (
                      <li className="val-bad">SOSPESO: {oppScanResult.suspension_reason}</li>
                    )}
                  </ul>
                )}

                <table className="data-table shortlist-table" style={{ marginTop: "8px" }}>
                  <thead>
                    <tr>
                      <th>#</th><th>Symbol</th><th>Strat</th>
                      <th><Tooltip text={TOOLTIPS.score_opp}>Score</Tooltip></th>
                      <th><Tooltip text={TOOLTIPS.ivz_30}>IVZ-30</Tooltip></th>
                      <th><Tooltip text={TOOLTIPS.em_pct}>EM%</Tooltip></th>
                      <th><Tooltip text={TOOLTIPS.dte}>DTE</Tooltip></th>
                      <th><Tooltip text={TOOLTIPS.events_flag}>Flag</Tooltip></th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {scanCandidates.map((c, i) => {
                      const key = `${c.symbol}::${c.strategy}::${c.expiry}`;
                      const sel = key === selectedScanKey;
                      return (
                        <tr key={key} className={sel ? "row-selected" : ""}>
                          <td>{i + 1}</td>
                          <td>{c.symbol}</td>
                          <td>{c.strategy.replace("_", " ")}</td>
                          <td className={c.score >= 75 ? "val-good" : "val-warn"}>{c.score.toFixed(1)}/100</td>
                          <td>{c.iv_zscore_30 !== null ? c.iv_zscore_30.toFixed(2) : "-"}</td>
                          <td>{c.expected_move !== null ? `${(c.expected_move * 100).toFixed(1)}%` : "-"}</td>
                          <td>{c.dte}</td>
                          <td>
                            {c.events_flag ? <span className="val-bad">{c.events_flag.split("_")[0]}</span>
                              : c.human_review_required ? <span className="val-warn">REV</span> : "-"}
                          </td>
                          <td>
                            <button className={`btn ${sel ? "btn-primary" : "btn-ghost"}`}
                              onClick={() => setSelectedScanKey(key)}>
                              {sel ? "SEL" : "→"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                    {scanCandidates.length === 0 && (
                      <tr><td colSpan={9} className="dim">Nessun candidato. Esegui RUN SCAN.</td></tr>
                    )}
                  </tbody>
                </table>

                {evReport && (
                  <>
                    <div className="panel-title mt10">EV REPORT (30gg)</div>
                    <ul className="activity-list">
                      <li>Candidati: {evReport.total_candidates} &nbsp;|&nbsp; Tracked: {evReport.total_tracked}</li>
                      <li>Score &lt;70: {evReport.score_distribution.below_70} &nbsp;|&nbsp; 70-80: {evReport.score_distribution.score_70_80} &nbsp;|&nbsp; 80+: {evReport.score_distribution.score_80_plus}</li>
                      <li>Human review: {evReport.human_review_required} &nbsp;|&nbsp; Events flag: {evReport.events_flagged}</li>
                      {Object.entries(evReport.strategies).map(([k, v]) => <li key={k}>{k}: {v}</li>)}
                      <li className="dim">Mode: {evReport.data_mode}</li>
                    </ul>
                  </>
                )}

                <div className="panel-title mt10">UNIVERSE QUEUE (legacy)</div>
                <ul className="activity-list">
                  <li>Batch: <code>{universeLatest?.batch_id ?? "-"}</code></li>
                  <li>Candidati: {universeItems.length} &nbsp;|&nbsp; Pronti ≥0.55: {opportunityReady}</li>
                </ul>
              </article>

              {/* ── RIGHT: DETAIL + VALIDAZIONE ──────────────────────────── */}
              <article className="panel">
                {selectedScanCandidate ? (
                  <>
                    <div className="panel-title">
                      {selectedScanCandidate.symbol} / {selectedScanCandidate.strategy}
                      {selectedScanCandidate.human_review_required && <span className="val-warn" style={{ marginLeft: "8px" }}>⚠ REVIEW</span>}
                    </div>
                    <ul className="activity-list">
                      <li>Score: <span className={selectedScanCandidate.score >= 75 ? "val-good" : "val-warn"}>{selectedScanCandidate.score.toFixed(2)}/100</span> &nbsp;|&nbsp; Expiry: {selectedScanCandidate.expiry} &nbsp;|&nbsp; DTE: {selectedScanCandidate.dte}</li>
                      <li>IV: {(selectedScanCandidate.iv * 100).toFixed(1)}% &nbsp;|&nbsp; Z-30: {selectedScanCandidate.iv_zscore_30?.toFixed(2) ?? "-"} &nbsp;|&nbsp; Z-60: {selectedScanCandidate.iv_zscore_60?.toFixed(2) ?? "-"} &nbsp;|&nbsp; <em>{selectedScanCandidate.iv_interp ?? "-"}</em></li>
                      <li>EM: {selectedScanCandidate.expected_move !== null ? `${(selectedScanCandidate.expected_move * 100).toFixed(2)}%` : "-"} &nbsp;|&nbsp; δ: {selectedScanCandidate.delta.toFixed(2)} &nbsp;|&nbsp; Spread: {selectedScanCandidate.spread_pct.toFixed(2)}%</li>
                      <li>Strikes: [{selectedScanCandidate.strikes.join(", ")}] &nbsp;|&nbsp; Spot: {selectedScanCandidate.underlying_price.toFixed(2)}</li>
                      <li>
                        Credit/Debit: <span className={selectedScanCandidate.credit_or_debit >= 0 ? "val-good" : "val-bad"}>
                          {selectedScanCandidate.credit_or_debit >= 0 ? "+" : ""}{selectedScanCandidate.credit_or_debit.toFixed(2)}
                        </span> &nbsp;|&nbsp; Max Loss: {selectedScanCandidate.max_loss.toFixed(2)} ({selectedScanCandidate.max_loss_pct.toFixed(2)}%)
                      </li>
                      <li>Breakeven: {selectedScanCandidate.breakeven.toFixed(2)} ({selectedScanCandidate.breakeven_pct > 0 ? "+" : ""}{selectedScanCandidate.breakeven_pct.toFixed(2)}%)</li>
                      <li>Sizing: {selectedScanCandidate.sizing_suggested.toFixed(1)}% &nbsp;|&nbsp; <Tooltip text={TOOLTIPS.oi}>OI</Tooltip>: {selectedScanCandidate.open_interest} &nbsp;|&nbsp; Vol: {selectedScanCandidate.volume}</li>
                      <li>Stress base: {selectedScanCandidate.stress_base.toFixed(2)} &nbsp;|&nbsp; Stress shock: {selectedScanCandidate.stress_shock.toFixed(2)}</li>
                    </ul>
                    <div className="panel-title mt10">SCORE BREAKDOWN</div>
                    <ul className="activity-list">
                      <li><Tooltip text={TOOLTIPS.vol_edge}>Vol Edge</Tooltip>: {selectedScanCandidate.score_breakdown.vol_edge.toFixed(1)} &nbsp;|&nbsp; <Tooltip text={TOOLTIPS.liquidity_score}>Liquidità</Tooltip>: {selectedScanCandidate.score_breakdown.liquidity.toFixed(1)}</li>
                      <li><Tooltip text={TOOLTIPS.risk_reward}>Risk/Reward</Tooltip>: {selectedScanCandidate.score_breakdown.risk_reward.toFixed(1)} &nbsp;|&nbsp; <Tooltip text={TOOLTIPS.regime_align}>Regime Align</Tooltip>: {selectedScanCandidate.score_breakdown.regime_align.toFixed(1)}</li>
                    </ul>
                    {(selectedScanCandidate.events_flag || selectedScanCandidate.human_review_required) && (
                      <>
                        <div className="panel-title mt10">FLAGS</div>
                        <ul className="activity-list">
                          {selectedScanCandidate.events_flag && <li className="val-bad">⚑ {selectedScanCandidate.events_flag}</li>}
                          {selectedScanCandidate.human_review_required && <li className="val-warn">⚠ HUMAN REVIEW REQUIRED</li>}
                        </ul>
                      </>
                    )}
                    <ul className="activity-list">
                      <li className="dim">Quality: {selectedScanCandidate.data_quality} &nbsp;|&nbsp; Source: {selectedScanCandidate.source}</li>
                    </ul>
                  </>
                ) : (
                  <div className="dim" style={{ padding: "12px 0" }}>Esegui RUN SCAN e seleziona un candidato per vedere i dettagli.</div>
                )}

                <div className="panel-title mt10">VALIDAZIONE OPERATORE</div>
                <div className="form-grid">
                  <label>Candidato</label>
                  <input
                    value={selectedScanCandidate
                      ? `${selectedScanCandidate.symbol} / ${selectedScanCandidate.strategy}`
                      : selectedOpportunity ? `${selectedOpportunity.symbol} / ${selectedOpportunity.strategy}` : "-"}
                    readOnly
                  />
                  <label>Score</label>
                  <input
                    value={selectedScanCandidate
                      ? selectedScanCandidate.score.toFixed(2)
                      : selectedOpportunity ? selectedOpportunity.score.toFixed(3) : "-"}
                    readOnly
                  />
                  <label>Decision</label>
                  <select value={oppDecision} onChange={(e) => setOppDecision(e.target.value as "APPROVE" | "REJECT" | "MODIFY")}>
                    <option value="APPROVE">APPROVE</option>
                    <option value="REJECT">REJECT</option>
                    <option value="MODIFY">MODIFY</option>
                  </select>
                  <label>Confidence (1-5)</label>
                  <input value={oppConfidence} onChange={(e) => setOppConfidence(e.target.value)} />
                  <label>Note</label>
                  <input value={oppNote} onChange={(e) => setOppNote(e.target.value)} placeholder="motivo decisione / override" />
                </div>
                <div className="actions">
                  <button className="btn btn-primary" onClick={doOpportunityDecision}
                    disabled={busy || (!selectedScanCandidate && !selectedOpportunity)}>
                    LOG DECISION
                  </button>
                  <button
                    className="btn btn-ghost"
                    disabled={!selectedScanCandidate && !selectedOpportunity}
                    onClick={() => {
                      const c = selectedScanCandidate ?? selectedOpportunity;
                      if (!c) return;
                      const isFullC = "strikes" in c;
                      setSymbol(c.symbol);
                      setStrategy(c.strategy);
                      setPayload(JSON.stringify({
                        source: isFullC ? "opportunity_scanner" : "opportunity_queue",
                        batch_id: oppScanResult?.batch_id ?? universeLatest?.batch_id ?? null,
                        symbol: c.symbol, strategy: c.strategy,
                        score: Number(c.score.toFixed(2)),
                        regime: oppScanResult?.regime ?? universeLatest?.regime ?? oppScanRegime,
                        metrics: isFullC ? {
                          iv_zscore_30: (c as ScanFullCandidate).iv_zscore_30,
                          expected_move: (c as ScanFullCandidate).expected_move,
                          max_loss: (c as ScanFullCandidate).max_loss,
                          max_loss_pct: (c as ScanFullCandidate).max_loss_pct,
                          breakeven: (c as ScanFullCandidate).breakeven,
                          strikes: (c as ScanFullCandidate).strikes,
                          events_flag: (c as ScanFullCandidate).events_flag,
                        } : {
                          iv_rank: (c as UniverseScanItem).iv_rank,
                          spread_pct: (c as UniverseScanItem).spread_pct,
                        },
                      }, null, 2));
                      setPreview(null); setPreviewSignature(null);
                      openOldTab("pipeline");
                      setMessage(`Candidato caricato in pipeline: ${c.symbol}/${c.strategy}`);
                      setError("");
                    }}
                  >
                    LOAD TO PIPELINE
                  </button>
                </div>

                <div className="panel-title mt10">LOG (PERSISTENTE)</div>
                <ul className="activity-list">
                  {(lastActions?.opportunity_decisions ?? []).map((x, i) => (
                    <li key={`opplog-${i}`}>
                      <code>{fmtTs(x.ts_utc)}</code> {x.symbol} {x.decision} conf={x.confidence}/5 score={x.score === null ? "-" : x.score.toFixed(2)}
                    </li>
                  ))}
                  {((lastActions?.opportunity_decisions?.length ?? 0) === 0) && <li className="dim">Nessuna decisione opportunity.</li>}
                </ul>
              </article>

            </div>
          )}

          {centerPhase === "old" && resolvedTab === "trades" && (
            <div className="panel-grid two">
              <article className="panel">
                <div className="panel-title">LAST PAPER TRADES</div>
                <table className="data-table">
                  <thead><tr><th>TS</th><th>Symbol</th><th>Strategy</th><th>PnL</th><th>Viol</th><th>Src</th></tr></thead>
                  <tbody>
                    {(lastActions?.paper_trades ?? []).map((x, i) => {
                      const isAuto = x.trigger === "auto";
                      return (
                        <tr key={`t-${i}`} style={{ background: isAuto ? "rgba(74,222,128,0.06)" : "transparent" }}>
                          <td>{fmtTs(x.ts_utc)}</td>
                          <td>{x.symbol}</td>
                          <td>{x.strategy}</td>
                          <td>{x.pnl ?? "-"}</td>
                          <td>{x.violations}</td>
                          <td>
                            {isAuto
                              ? <span style={{ color: "#4ade80", fontSize: "0.6rem", fontWeight: 700 }}>AUTO</span>
                              : <span style={{ color: "var(--muted)", fontSize: "0.6rem" }}>MAN</span>}
                          </td>
                        </tr>
                      );
                    })}
                    {(lastActions?.paper_trades.length ?? 0) === 0 && <tr><td colSpan={6} className="dim">Nessun trade registrato.</td></tr>}
                  </tbody>
                </table>
              </article>
              <article className="panel">
                <div className="panel-title">PREVIEWS / CONFIRMS</div>
                <h4>Previews</h4>
                <ul className="activity-list">
                  {(lastActions?.execution_previews ?? []).map((x, i) => <li key={`p-${i}`}><code>{fmtUnix(x.ts_unix)}</code> {x.symbol ?? "-"}/{x.strategy ?? "-"} tk={shortToken(x.confirm_token)}</li>)}
                </ul>
                <h4>Confirms</h4>
                <ul className="activity-list">
                  {(lastActions?.execution_confirms ?? []).map((x, i) => <li key={`c-${i}`}><code>{fmtUnix(x.ts_unix)}</code> {x.decision ?? "-"} by {x.operator ?? "-"} tk={shortToken(x.confirm_token)}</li>)}
                </ul>
              </article>
            </div>
          )}

          {centerPhase === "old" && resolvedTab === "regime" && (
            <div className="panel-grid two">
              <article className="panel">
                <div className="panel-title">REGIME MATRIX</div>
                <div className="matrix-grid">
                  <div className="matrix-head">Regime</div><div className="matrix-head">Iron Condor</div><div className="matrix-head">Bull Put</div><div className="matrix-head"><Tooltip text={TOOLTIPS.regime_matrix_sizing}>Sizing</Tooltip></div><div className="matrix-head"><Tooltip text={TOOLTIPS.regime_matrix_hedge}>Hedge</Tooltip></div>
                  <div className="matrix-cell cell-act">NORMAL</div><div className="matrix-cell cell-yes">YES</div><div className="matrix-cell cell-yes">YES</div><div className="matrix-cell cell-yes">1.0x</div><div className="matrix-cell">OFF</div>
                  <div className="matrix-cell cell-warn">CAUTION</div><div className="matrix-cell cell-warn">LIMIT</div><div className="matrix-cell cell-yes">YES</div><div className="matrix-cell cell-warn">0.5x</div><div className="matrix-cell cell-warn">MONITOR</div>
                  <div className="matrix-cell cell-no">SHOCK</div><div className="matrix-cell cell-no">STOP</div><div className="matrix-cell cell-no">STOP</div><div className="matrix-cell cell-no">0x</div><div className="matrix-cell cell-no">ON</div>
                </div>
              </article>
              <article className="panel">
                <div className="panel-title">REGIME INPUTS</div>
                <ul className="activity-list">
                  <li>GO/NO-GO: {goGate === undefined ? <span className="dim">–</span> : <GateBadge pass={goGate.pass} />}</li>
                  <li>F6-T1: {f6Gate === undefined ? <span className="dim">–</span> : <GateBadge pass={f6Gate.pass} />}</li>
                  <li>F6-T2 ratio: {f6t2Gate ? `${(f6t2Gate.completeness_ratio * 100).toFixed(2)}%` : "-"}</li>
                  <li><Tooltip text={TOOLTIPS.max_dd}>MaxDD</Tooltip>: {fmtPct(paperSummary?.max_drawdown ?? null)}</li>
                  <li><Tooltip text={TOOLTIPS.win_rate}>Win rate</Tooltip>: {fmtPct(paperSummary?.win_rate ?? null)}</li>
                </ul>
              </article>
            </div>
          )}

          {centerPhase === "old" && resolvedTab === "tests" && (
            <div className="panel-grid two">
              <article className="panel">
                <div className="panel-title">STATE SNAPSHOT</div>
                <pre className="console">{stateJson ? JSON.stringify(stateJson, null, 2) : "Premi REFRESH per aggiornare."}</pre>
              </article>
              <article className="panel">
                <div className="panel-title">RELEASE STATUS</div>
                {!releaseMd && <pre className="console">Premi REFRESH per aggiornare.</pre>}
                {releaseMd && (
                  <div className="release-md">
                    {releaseView.before && <pre className="console">{releaseView.before}</pre>}
                    {releaseView.table && (
                      <div className="md-table-wrap">
                        <table className="data-table md-table">
                          <thead>
                            <tr>
                              {releaseView.table.headers.map((h, idx) => (
                                <th key={`mh-${idx}-${h}`}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {releaseView.table.rows.map((row, ridx) => (
                              <tr key={`mr-${ridx}`}>
                                {row.map((cell, cidx) => (
                                  <td key={`mc-${ridx}-${cidx}`}>{cell || "-"}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {!releaseView.table && <pre className="console">{releaseMd}</pre>}
                    {releaseView.after && <pre className="console">{releaseView.after}</pre>}
                  </div>
                )}
              </article>
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
