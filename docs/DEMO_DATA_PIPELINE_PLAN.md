# Demo Data Pipeline Plan (IBKR demo deferred + Ollama)

## Objective
Build a deterministic, low-footprint data pipeline for testing/tuning before realtime subscription.

## Scope
- Source: IBKR demo, delayed data, limited symbol set.
- Capture: selected pages/snapshots only.
- Extractor: Ollama `qwen2.5` with strict JSON output schema.
- Output: validated dataset (CSV/Parquet) for backtest.

## Steps
- `F1-T5` Capture pages with dedup and freshness skip.
- `F1-T6` Extract fields with Ollama and strict validator+retry.
- `F1-T7` Build clean test dataset and provenance index.
- `F1-T8` Enforce retention (TTL + disk cap) and produce audit report.
- `F2-T5` Run the classical dataset-driven backtest using the generated dataset.

## Boundary
This pipeline is for the classical offline backtest path.
It does not by itself implement the full operator-grade replay that simulates day-by-day decisions from a shifted historical "today".
That replay-oriented path lives mainly in the paper/operator execution area and should be treated as a distinct validation mode.

## Anti-bloat controls
- Content fingerprint (`sha256`) for every raw artifact.
- Unique key: `(source, symbol, page_type, fingerprint)`.
- `raw-on-change`: save only if payload changed.
- Freshness window: default 60 min per symbol/page.
- Retention: TTL + size cap with controlled pruning.

## Transparency
- Structured logs: `captured | skipped_fresh | duplicate | extracted | invalid_json | validated | pruned`.
- Per-record metadata: `raw_path`, `fingerprint`, `model`, `prompt_version`, `validator_version`.
- Daily report: ingested/skipped/duplicates/errors/bytes_on_disk.

## Acceptance criteria
- No duplicate raw persisted for same fingerprint.
- JSON extraction validity >= 99% after retry budget.
- Disk usage stays under configured cap.
- Dataset build is reproducible from indexed raw + prompt/model versions.
