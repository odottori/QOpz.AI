# F1-T6 / F1-T7 Real Data Validation - 2026-03-12

## Objective

Validate the extraction and dataset-build stages using real repository artifacts rather than synthetic runtime inputs.

## Real source used

- `data/ibkr_screens/tesseract_extraction.json`

## Validation approach

- A small set of real OCR rows was seeded into the demo pipeline index under the ignored `data/demo_pipeline/` area.
- Extraction was executed with `scripts/extract_with_ollama.py` using `--backend json-pass`.
- Dataset build was then executed with `scripts/build_test_dataset.py` against the same indexed outputs.

## Observed outcome

- `NVDA` option row produced a valid quote cluster and was accepted.
- `MSFT` quote row with OCR-missing decimal (`41249`) is now normalized to `412.49` and validated.
- `AMZN` quote row with a real three-price cluster is now validated.
- A sequential dataset build produced a reproducible CSV plus provenance JSON from the accepted record set.

## Residual rejects audited

The remaining rejected OCR rows in the sampled batch are not silent failures. They are incomplete or non-quote-like rows and remain correctly classified as `NEEDS_REVIEW`:

- `MSFT augas 168 412.48) 10.37`
- `MSFT aug 168 412.48 + 029.35`
- `AMZN Augot 168 216.82 + c17.08`

These rows do not contain a credible bid/ask/last cluster and should not be force-promoted.

## Quality note

The extractor was tightened to reduce false negatives on real quote rows while still preferring honest `NEEDS_REVIEW` outcomes over permissive but unreliable numeric guesses. This matches the project rule of using real evidence and avoiding weak fallback behavior.

## Operational note

DuckDB access must be sequential for these local validation runs. Parallel extract/build execution can contend on the same database file and fail due to file locking even when the pipeline logic is correct.
