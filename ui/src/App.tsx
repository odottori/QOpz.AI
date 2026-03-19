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
type SystemStatusResponse = {
  ok: boolean; timestamp_utc: string; api_online: boolean;
  kill_switch_active: boolean; data_mode: string; kelly_enabled: boolean;
  ibkr_connected: boolean; ibkr_port: number | null; ibkr_source_system: string;
  ibkr_connected_at: string | null; execution_config_ready: boolean;
  n_closed_trades: number; regime: string; signals: SystemSignal[];
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

type TabKey = "warroom" | "pipeline" | "universe" | "opportunity" | "trades" | "regime" | "tests";
type UniverseSubTab = "titoli" | "indici" | "opzioni" | "ciclo" | "palinsesto";
type MarkdownTable = { headers: string[]; rows: string[][] };
type ReleaseMdView = { before: string; table: MarkdownTable | null; after: string };
// In production (Docker/nginx) usa URL relativo — nginx fa proxy.
// In dev locale: VITE_API_BASE=http://localhost:8765 in .env.local
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
/** Profilo attivo — unico punto di modifica per dev/paper/live */
const ACTIVE_PROFILE = (import.meta.env.VITE_PROFILE as string | undefined) ?? "paper";

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
  const [exitCandidates, setExitCandidates] = useState<ExitCandidatesResponse | null>(null);
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
      void doFetchWheelPositions();
      void doFetchTier();
      void doFetchBriefingList();
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

  async function doFetchEquityHistory() {
    try {
      const r = await apiJson<EquityHistoryResponse>(`${API_BASE}/opz/paper/equity_history?profile=${ACTIVE_PROFILE}&limit=60`);
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
  const canPlayBriefingAction = briefingPlaying || (apiOnline && briefingList.length > 0);

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

  // Auto-check IBKR status on mount + poll every 30s
  useEffect(() => {
    void doCheckIbkr(true);
    const id = window.setInterval(() => void doCheckIbkr(false), 30_000);
    return () => window.clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fetch IBKR account on mount + poll every 60s
  useEffect(() => {
    void doFetchIbkrAccount();
    const id = window.setInterval(() => void doFetchIbkrAccount(), 60_000);
    return () => window.clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fetch system status on mount + poll every 15s
  useEffect(() => {
    void doFetchSysStatus();
    const id = window.setInterval(() => void doFetchSysStatus(), 15_000);
    return () => window.clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fetch regime current on mount + poll every 30s
  useEffect(() => {
    void doFetchRegimeCurrent();
    const id = window.setInterval(() => void doFetchRegimeCurrent(), 30_000);
    return () => window.clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fetch equity history on mount + poll every 60s
  useEffect(() => {
    void doFetchEquityHistory();
    const id = window.setInterval(() => void doFetchEquityHistory(), 60_000);
    return () => window.clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fetch exit candidates on mount + poll every 60s
  useEffect(() => {
    void doFetchExitCandidates();
    const id = window.setInterval(() => void doFetchExitCandidates(), 30_000); // 30s — urgency-sensitive
    return () => window.clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch tier when regime changes — block_visibility depends on regime
  useEffect(() => {
    if (regimeCurrent?.regime) void doFetchTier(regimeCurrent.regime);
  }, [regimeCurrent?.regime]); // eslint-disable-line react-hooks/exhaustive-deps

  // Helper: read block visibility for a block key (safe default = fully visible/interactive)
  function blk(key: string): BlockVis {
    return tierInfo?.block_visibility?.[key]
      ?? { visible: true, interactive: true, gate: "unknown", reason: null };
  }

  const navItems: Array<{ id: TabKey; label: string }> = [
    { id: "warroom", label: "WAR ROOM" },
    { id: "universe", label: "UNIVERSE SCANNER" },
    { id: "opportunity", label: "OPPORTUNITY" },
    { id: "pipeline", label: "PIPELINE AUTO" },
    { id: "trades", label: "TRADE LOG" },
    { id: "regime", label: "REGIME MATRIX" },
    { id: "tests", label: "TEST SUITE" },
  ];
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

  // ── ROC16: High-urgency exit signal ───────────────────────────────────────
  const urgentExits = (exitCandidates?.candidates ?? []).filter(c => c.exit_score >= 5);
  const hasUrgentExit = urgentExits.length > 0;

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
          <span className={`regime-pill ${regimeView.cls}`}>REGIME: {regimeView.text}</span>
          {apiOnline && <span className="top-mini">XGBoost: {(stateObj as any)?.model_scores?.xgboost ?? "—"}</span>}
          {apiOnline && <span className="top-mini">HMM P(shock): {(stateObj as any)?.model_scores?.hmm_p_shock ?? "—"}</span>}
          <span className="top-mini">Sizing: {regimeView.text === "NORMAL" ? "100%" : regimeView.text === "CAUTION" ? "50%" : regimeView.text === "SHOCK" ? "0%" : "—"}</span>
        </div>
        <div className="topbar-right">
          {fetchErrors.size > 0 && (
            <span style={{ color: "#f97316", fontSize: "0.7rem" }} title={`Fetch falliti: ${Array.from(fetchErrors).join(", ")}`}>
              ⚠ {fetchErrors.size} stale
            </span>
          )}
          <span className="clock">{clockText}</span>
          <span className={`live-pill ${apiOnline ? "online" : "offline"}`}>{apiOnline ? "API LIVE" : "API DOWN"}</span>
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
          <div className="nav-section">
            <div className="nav-label">MODULI CORE</div>
            {navItems.map((tab) => (
              <button key={tab.id} className={`nav-item ${activeTab === tab.id ? "active" : ""}`} onClick={() => setActiveTab(tab.id)}>
                <span className={`nav-dot ${activeTab === tab.id ? "dot-green" : "dot-gray"}`} /> {tab.label}
              </button>
            ))}
          </div>

          <div className="nav-section">
            <div className="nav-label">PIPELINE DATI</div>
            <div className="nav-item static"><span className="nav-dot dot-green" /> yfinance / CBOE <span className="nav-badge ok">OK</span></div>
            <div className="nav-item static"><span className="nav-dot dot-green" /> FRED API <span className="nav-badge ok">OK</span></div>
            <div className="nav-item static"><span className="nav-dot dot-amber" /> ORATS (5 ticker) <span className="nav-badge warn">LAG</span></div>
          </div>

          <div className="nav-section">
            <div className="nav-label">RISK</div>
            <div className="nav-item static"><span className="nav-dot dot-green" /> VaR/CVaR <span className="nav-badge ok">OK</span></div>
            <div className="nav-item static"><span className="nav-dot dot-amber" /> DD Control <span className="nav-badge warn">{fmtPct(paperSummary?.max_drawdown ?? null)}</span></div>
            <div className="nav-item static"><span className="nav-dot dot-gray" /> Tail Hedge <span className="nav-badge">OFF</span></div>
          </div>

          <div className="phases-box">
            <div className="phases-title">PROGRESSIONE 90 GIORNI</div>
            <div className="phase-row"><span>F1 Pipeline</span><b className={phaseProgress.f1 === 100 ? "ok" : "warn"}>{phaseProgress.f1}%</b></div>
            <div className="phase-bar"><span style={{ width: `${phaseProgress.f1}%` }} /></div>
            <div className="phase-row"><span>F2 Regime</span><b className={phaseProgress.f2 === 100 ? "ok" : "warn"}>{phaseProgress.f2}%</b></div>
            <div className="phase-bar"><span style={{ width: `${phaseProgress.f2}%` }} /></div>
            <div className="phase-row"><span>F3 Paper</span><b className={phaseProgress.f3 === 100 ? "ok" : phaseProgress.f3 > 0 ? "warn" : "dim"}>{phaseProgress.f3}%</b></div>
            <div className="phase-bar"><span style={{ width: `${phaseProgress.f3}%` }} /></div>
            <div className="phase-row"><span>F4 Scoring</span><b className={phaseProgress.f4 === 100 ? "ok" : phaseProgress.f4 > 0 ? "warn" : "dim"}>{phaseProgress.f4}%</b></div>
            <div className="phase-bar"><span style={{ width: `${phaseProgress.f4}%` }} /></div>
          </div>
        </aside><section className="centerpane">
          <div className="metrics-row">
            <div className="metric-box"><div className="metric-label">TRADES</div><div className="metric-val">{paperSummary?.trades ?? "-"}</div></div>
            <div className="metric-box"><div className="metric-label">SHARPE</div><div className="metric-val">{fmtNum(paperSummary?.sharpe_annualized ?? null)}</div></div>
            <div className="metric-box"><div className="metric-label">MAX DD</div><div className="metric-val amber">{fmtPct(paperSummary?.max_drawdown ?? null)}</div></div>
            <div className="metric-box"><div className="metric-label">WIN RATE</div><div className="metric-val">{fmtPct(paperSummary?.win_rate ?? null)}</div></div>
            <div className="metric-box"><div className="metric-label">COMPLIANCE</div><div className="metric-val red">{paperSummary?.compliance_violations ?? "-"}</div></div>
            {tierInfo && (() => {
              const tierColor: Record<string, string> = {
                MICRO: "#60a5fa", SMALL: "#a78bfa", MEDIUM: "#4ade80", ADVANCED: "#f97316",
              };
              const col = tierColor[tierInfo.active_mode] ?? "#888";
              return (
                <div className="metric-box" style={{ borderLeft: `3px solid ${col}` }}>
                  <div className="metric-label" style={{ color: col }}>TIER</div>
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

          <div className="tabs">
            {navItems.map((tab) => (
              <button key={tab.id} className={`tab ${activeTab === tab.id ? "active" : ""}`} onClick={() => setActiveTab(tab.id)}>
                {tab.label}
              </button>
            ))}
          </div>

                    {activeTab === "warroom" && (
            <>
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
                  disabled={!canPlayBriefingAction}
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
                  <span>EQUITY CURVE</span>
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

                <EqSparkline points={equityHistory?.points ?? []} w={240} h={56} />

                <div className="panel-title mt10">DRAWDOWN - 3 LAYER</div>
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
                <div className="dim">DD attuale: {fmtPct(paperSummary?.max_drawdown ?? null)} / limite 20%</div>
                <div className="panel-title mt10">GATE STATUS</div>
                <div className="gate-line"><span>GO/NO-GO</span>{goGate ? <GateBadge pass={goGate.pass} /> : <span className="dim">-</span>}</div>
                {goGate?.reasons.map((r) => <div key={`go-${r}`} className="reason">- {r}</div>)}
                <div className="gate-line"><span>F6-T1 acceptance</span>{f6Gate ? <GateBadge pass={f6Gate.pass} /> : <span className="dim">-</span>}</div>
                {f6Gate?.reasons.map((r) => <div key={`f6-${r}`} className="reason">- {r}</div>)}
                <div className="gate-line"><span>F6-T2 completeness</span>{f6t2Gate ? <GateBadge pass={f6t2Gate.pass} /> : <span className="dim">-</span>}</div>
                {f6t2Gate && <div className="dim">completeness: {(f6t2Gate.completeness_ratio * 100).toFixed(0)}%</div>}
              </article>

              <article className="panel">
                <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>SYSTEM STATUS</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: "0.62rem", color: "#555" }}>agg: {_agoLabel(sysStatusFetchedAt)}</span>
                    <button className="btn btn-secondary" style={{ fontSize: "0.65rem", padding: "2px 6px" }}
                      onClick={() => void doFetchSysStatus()}>⟳</button>
                  </span>
                </div>

                {/* Signal grid */}
                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: "3px 8px", alignItems: "center", fontSize: "0.72rem", marginTop: 4 }}>
                  {(sysStatus?.signals ?? []).map((sig) => {
                    const color = sig.status === "OK" ? "#4ade80"
                      : sig.status === "ALERT" ? "#f87171"
                      : sig.status === "DISABLED" ? "#666"
                      : "#fbbf24"; // WARN
                    return [
                      <span key={`sn-${sig.name}`} className="dim" style={{ whiteSpace: "nowrap" }}>{sig.name}</span>,
                      <span key={`sd-${sig.name}`} style={{ color: "#aaa", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sig.detail}</span>,
                      <span key={`ss-${sig.name}`} style={{ color, fontWeight: 700, textAlign: "right" }}>{sig.status}</span>,
                    ];
                  })}

                  {/* Campi aggiuntivi */}
                  <span className="dim">regime</span>
                  <span style={{ color: sysStatus?.regime === "SHOCK" ? "#f87171" : sysStatus?.regime === "CAUTION" ? "#fbbf24" : "#4ade80" }}>
                    {sysStatus?.regime ?? "—"}
                  </span>
                  <span />

                  <span className="dim">trades completati</span>
                  <span>{sysStatus?.n_closed_trades ?? "—"}</span>
                  <span />

                  <span className="dim">api</span>
                  <span>{apiOnline ? "ONLINE" : "OFFLINE"}</span>
                  <span style={{ color: apiOnline ? "#4ade80" : "#f87171", fontWeight: 700 }}>{apiOnline ? "OK" : "ALERT"}</span>
                </div>

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
                <div className="panel-title mt10" style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>REGIME ({regimeCurrent?.n_recent ?? 0} sample)</span>
                  <span style={{
                    fontWeight: 700, fontSize: "0.72rem",
                    color: regimeCurrent?.regime === "SHOCK" ? "#f87171"
                      : regimeCurrent?.regime === "CAUTION" ? "#fbbf24"
                      : regimeCurrent?.regime === "NORMAL" ? "#4ade80"
                      : "#666",
                  }}>
                    {regimeCurrent?.regime ?? "—"}
                  </span>
                </div>

                {regimeCurrent && regimeCurrent.n_recent > 0 ? (
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
                  <div className="dim" style={{ fontSize: "0.7rem" }}>
                    {regimeCurrent ? "Nessun dato campione" : "Caricamento…"}
                  </div>
                )}

                <div className="panel-title mt10">AUTOMATION PIPELINE</div>
                <div className="pipeline-row">
                  <span className="pipe-step done">DATA</span>
                  <span className="pipe-arrow">→</span>
                  <span className="pipe-step done">IVR</span>
                  <span className="pipe-arrow">→</span>
                  <span className={`pipe-step ${pipeRegimeStep}`}>REGIME</span>
                  <span className="pipe-arrow">→</span>
                  <span className={`pipe-step ${pipeScoreStep}`}>SCORE</span>
                  <span className="pipe-arrow">→</span>
                  <span className={`pipe-step ${pipeKellyStep}`} title={pipeKellyReady ? "Kelly abilitato" : "Kelly disabilitato (VENDOR_REAL_CHAIN + N≥50 richiesti)"}>KELLY</span>
                </div>
                <div className="dim" style={{ fontSize: "0.65rem", marginTop: 3 }}>
                  {pipeHasRegime
                    ? `${regimeCurrent?.n_recent ?? 0} sample · ultimo scan ${regimeCurrent?.last_scan_ts ? new Date(regimeCurrent.last_scan_ts).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) : "—"}`
                    : "In attesa dati regime…"}
                </div>

                {/* ── ROC16: Quick-nav action strip ───────────────────── */}
                <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                  <button className="btn btn-secondary" style={{ fontSize: "0.65rem", padding: "3px 8px", flex: 1 }}
                    onClick={() => setActiveTab("universe" as TabKey)}>
                    → SCAN
                  </button>
                  <button className="btn btn-secondary" style={{ fontSize: "0.65rem", padding: "3px 8px", flex: 1 }}
                    onClick={() => setActiveTab("pipeline" as TabKey)}>
                    → PIPELINE
                  </button>
                </div>
              </article>

              {/* ── ROC7: IBKR ACCOUNT panel ──────────────────────────────── */}
              <article className="panel">
                <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
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

                    <div className="panel-title mt10">
                      POSIZIONI APERTE ({ibkrAccount.positions.length})
                    </div>
                    {ibkrAccount.positions.length === 0 ? (
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
                <div className="panel-title mt10" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>EXIT CANDIDATES</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.62rem", color: "#555" }}>
                    {exitCandidates ? `${exitCandidates.n_flagged}/${exitCandidates.n_total} flagged` : "—"}
                    <span>agg: {_agoLabel(exitCandidatesFetchedAt)}</span>
                  </span>
                </div>

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
                  <span>🔄 WHEEL POSITIONS</span>
                  <span style={{ fontSize: "0.65rem", color: "#555", fontWeight: 400 }}>
                    {!wheelAvailable
                      ? <span style={{ color: "#a78bfa" }}>🔒 Capitale insufficiente</span>
                      : wheelWarning
                        ? <span style={{ color: "#f97316" }}>⚠ Non ancora validato</span>
                        : (wheelFetchedAt ? new Date(wheelFetchedAt).toLocaleTimeString("it-IT") : "—")
                    }
                  </span>
                </div>

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
              </article>
                );
              })()}
            </div>
            </>
          )}

          {activeTab === "pipeline" && (
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

          {activeTab === "universe" && (
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
                        <th>Score</th>
                        <th>IVR</th>
                        <th>Spread</th>
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
                                setActiveTab("pipeline");
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
          {activeTab === "opportunity" && (
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
                      <th>#</th><th>Symbol</th><th>Strat</th><th>Score</th>
                      <th>IVZ-30</th><th>EM%</th><th>DTE</th><th>Flag</th><th></th>
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
                      <li>Sizing: {selectedScanCandidate.sizing_suggested.toFixed(1)}% &nbsp;|&nbsp; OI: {selectedScanCandidate.open_interest} &nbsp;|&nbsp; Vol: {selectedScanCandidate.volume}</li>
                      <li>Stress base: {selectedScanCandidate.stress_base.toFixed(2)} &nbsp;|&nbsp; Stress shock: {selectedScanCandidate.stress_shock.toFixed(2)}</li>
                    </ul>
                    <div className="panel-title mt10">SCORE BREAKDOWN</div>
                    <ul className="activity-list">
                      <li>Vol Edge: {selectedScanCandidate.score_breakdown.vol_edge.toFixed(1)} &nbsp;|&nbsp; Liquidità: {selectedScanCandidate.score_breakdown.liquidity.toFixed(1)}</li>
                      <li>Risk/Reward: {selectedScanCandidate.score_breakdown.risk_reward.toFixed(1)} &nbsp;|&nbsp; Regime Align: {selectedScanCandidate.score_breakdown.regime_align.toFixed(1)}</li>
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
                      setActiveTab("pipeline");
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

          {activeTab === "trades" && (
            <div className="panel-grid two">
              <article className="panel">
                <div className="panel-title">LAST PAPER TRADES</div>
                <table className="data-table">
                  <thead><tr><th>TS</th><th>Symbol</th><th>Strategy</th><th>PnL</th><th>Viol</th></tr></thead>
                  <tbody>
                    {(lastActions?.paper_trades ?? []).map((x, i) => (
                      <tr key={`t-${i}`}><td>{fmtTs(x.ts_utc)}</td><td>{x.symbol}</td><td>{x.strategy}</td><td>{x.pnl ?? "-"}</td><td>{x.violations}</td></tr>
                    ))}
                    {(lastActions?.paper_trades.length ?? 0) === 0 && <tr><td colSpan={5} className="dim">Nessun trade registrato.</td></tr>}
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

          {activeTab === "regime" && (
            <div className="panel-grid two">
              <article className="panel">
                <div className="panel-title">REGIME MATRIX</div>
                <div className="matrix-grid">
                  <div className="matrix-head">Regime</div><div className="matrix-head">Iron Condor</div><div className="matrix-head">Bull Put</div><div className="matrix-head">Sizing</div><div className="matrix-head">Hedge</div>
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
                  <li>MaxDD: {fmtPct(paperSummary?.max_drawdown ?? null)}</li>
                  <li>Win rate: {fmtPct(paperSummary?.win_rate ?? null)}</li>
                </ul>
              </article>
            </div>
          )}

          {activeTab === "tests" && (
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
          {blk("kelly_sizing").visible ? (
            <section className="rp-section">
              <div className="rp-title">KELLY SIZING LIVE</div>
              <div className="kelly-result">
                <div className="kelly-val">{kellyHalf === null ? "-" : `${(kellyHalf * 100).toFixed(2)}%`}</div>
                <div className="kelly-label">Half-Kelly target</div>
              </div>
              <div className="kelly-row"><span className="kelly-key">Win rate</span><span className="kelly-v">{fmtPct(paperSummary?.win_rate ?? null)}</span></div>
              <div className="kelly-row"><span className="kelly-key">Profit factor</span><span className="kelly-v">{fmtNum(paperSummary?.profit_factor ?? null)}</span></div>
              <div className="kelly-row"><span className="kelly-key">Avg slippage</span><span className="kelly-v">{fmtNum(paperSummary?.avg_slippage_ticks ?? null)}</span></div>
            </section>
          ) : (
            <section className="rp-section">
              <div className="rp-title">KELLY SIZING</div>
              <div style={{ color: "#555", fontSize: "0.7rem", padding: "4px 0" }}>
                🔒 {blk("kelly_sizing").reason ?? "Kelly disabilitato"}
              </div>
            </section>
          )}

          <section className="rp-section">
            <div className="rp-title">FASE CORRENTE</div>
            <div className="phase-d-name">{nextStep}</div>
            <div className="checklist-item"><span className="ci-label">Blocked steps</span><span>{blockedCount}</span></div>
            <div className="checklist-item"><span className="ci-label">equity points</span><span>{paperSummary?.equity_points ?? 0}</span></div>
            <div className="checklist-item"><span className="ci-label">trade journal</span><span>{paperSummary?.trades ?? 0}</span></div>
            <div className="checklist-item"><span className="ci-label">Data aggiorn.</span><span>{paperSummary?.as_of_date ?? "-"}</span></div>
          </section>

          <section className="rp-section">
            <div className="rp-title">EXECUTION WINDOW</div>
            <div style={{ color: "var(--g1)", marginBottom: 4 }}>10:00-11:30 EST</div>
            <div className="dim">13:30-15:00 EST</div>
            <div className="dim">Avoid: 09:30-09:45 | 15:30-16:00</div>
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

            {/* controlli player */}
            <div className="narrator-controls">
              <button className="btn" onClick={doBriefingPrev}
                disabled={briefingListIdx >= briefingList.length - 1 || briefingList.length === 0}
                title="Briefing precedente">◀ PREV</button>
              <button
                className={`btn ${briefingPlaying ? "btn-warning" : "btn-primary"}`}
                onClick={briefingPlaying ? doBriefingStop : doBriefingPlay}
                disabled={!canPlayBriefingAction}
              >{briefingPlaying ? "■ STOP" : "▶ PLAY"}</button>
              <button className="btn" onClick={doBriefingNext}
                disabled={briefingListIdx <= 0}
                title="Briefing successivo">NEXT ▶</button>
              <button className="btn btn-ghost" onClick={() => void doBriefingGenerate()}
                disabled={briefingBusy || !apiOnline}
                title="Genera nuovo briefing e invia su Telegram"
                style={{ gridColumn: "1 / -1" }}
              >{briefingBusy ? "generazione..." : "⊕ GENERA NUOVO"}</button>
            </div>

            {/* switch automazione */}
            <div className="narrator-switches">
              <label className="narrator-switch-row">
                <span>Auto-apri finestra</span>
                <span className={`toggle-pill ${briefingAutoOpen ? "on" : ""}`}
                  onClick={() => setBriefingAutoOpen(v => !v)} role="switch"
                  aria-checked={briefingAutoOpen} tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setBriefingAutoOpen(v => !v)}>
                  <span className="toggle-knob" />
                </span>
              </label>
              <label className="narrator-switch-row">
                <span>Play automatico</span>
                <span className={`toggle-pill ${briefingAutoPlay ? "on" : ""}`}
                  onClick={() => setBriefingAutoPlay(v => !v)} role="switch"
                  aria-checked={briefingAutoPlay} tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setBriefingAutoPlay(v => !v)}>
                  <span className="toggle-knob" />
                </span>
              </label>
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
