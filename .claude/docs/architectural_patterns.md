# Architectural Patterns

Cross-cutting patterns and conventions observed across the codebase.

## Linear Pipeline Architecture

The project is a two-phase pipeline with file-based inter-stage communication:

**Offline phase:** `fetch.py` → `raw/*.html` → `parse.py` → `answers.csv` → `build_boards.py` → `boards.json`

**Runtime phase:** `capture.py` (ADB screenshot) → `ocr.py` (word extraction) → `matcher.py` (board identification) → `solver.py` (tap actions)

Each offline stage reads a file and writes a file, making stages independently runnable and debuggable. Runtime stages pass Python objects directly (PIL Images, lists, dataclass instances).

## Functional Style, Minimal OOP

The codebase favors free functions over classes. `Matcher` (`matcher.py:7-13`) is the only class, justified by its expensive index-building initialization. Everything else — `compute_solve_order`, `match_words_to_group`, `read_board`, `screencap`, `tap` — is a stateless function.

## Configuration via Module-Level Constants

No config files, no environment variables. All configuration is hardcoded as `UPPER_SNAKE_CASE` constants at module level:
- `fetch.py` — `API_URL`, `PER_PAGE`, `SLEEP_SECONDS`
- `ocr.py:14-26` — `SCREEN_W`, `SCREEN_H`, `COL_CENTERS`, `ROW_CENTERS`, `TILE_HALF_W`, `TILE_HALF_H`
- `parse.py` — `RAW_DIR`, `CSV_PATH`, `SOURCE`
- `build_boards.py:9-12` — `SCRIPT_DIR`, `CSV_PATH`, `OUT_PATH`, `SOURCE`

## Script-Relative File Paths

All file paths are resolved relative to the script's own location using `os.path.join(os.path.dirname(os.path.abspath(__file__)), ...)`, not the working directory. See `build_boards.py:9-12`, `solver.py:54`.

## Lazy Imports for Hardware Decoupling

`solver.py:50-51` imports `capture` and `ocr` inside `solve_board()` rather than at module level. This allows `compute_solve_order` and `match_words_to_group` to be imported and tested without ADB or Tesseract installed.

## Error Handling Strategies

Three distinct approaches depending on module role:

1. **Fail-fast (`sys.exit`):** CLI tools where errors are unrecoverable — `capture.py` (multiple points), `build_boards.py` (`fail()` function)
2. **Collect-and-report:** `parse.py` catches exceptions per file, appends to an `errors` list, continues processing. `fetch.py` logs errors to `fetch_errors.log` and continues.
3. **Sentinel values:** `ocr.py` returns `None` for unrecognizable tiles. `matcher.py` returns `MatchResult` with `status='none'` and `board_id=None`. `solver.py` returns `False` on failure.

No custom exception classes are defined anywhere.

## Content-Addressed Deduplication

`build_boards.py` deduplicates boards using SHA-256 hashes of sorted `(label, word)` pairs. 7,353 board instances (3,000 levels × US/GB variants) collapse to 1,952 unique boards. Each board tracks its `occurrences` list.

## Dependency Graph with Topological Ordering

Picture groups form a directed graph via `consumed_by` pointers (index of the group whose label appears as a word). `build_boards.py` computes topological depth, detects cycles, and reorders groups by depth. `solver.py:16-26` (`compute_solve_order`) reproduces this ordering at solve time: depth-0 first, then ascending depth, cyclic groups last.

## Text Normalization

Normalization appears in two modules with distinct strategies:
- `matcher.py:16-17` — `_normalise_squash`: strips all non-alphanumeric, lowercases (for matching)
- `matcher.py:20` — `_normalise_spaced`: collapses whitespace, lowercases (for display)
- `ocr.py` — `_clean_ocr`: uppercases, strips non-alpha, removes leading/trailing single chars (for OCR cleanup)
- `solver.py:29-30` — `_norm` delegates to `_normalise_squash`, keeping normalization logic centralized

## Testing Conventions

- **Framework:** pytest with `@pytest.fixture(scope='module')` for expensive resources (Matcher init, boards data loading)
- **Conditional skipping:** `pytest.mark.skipif` for hardware/software deps — `test_ocr.py` defines `has_captures` and `needs_tesseract` decorators
- **Shared reference data:** Level 11 US Version board (`id="56f70eefcce8e8ef"`) is the canonical test fixture across all three test files
- **Naming:** `test_<feature>_<scenario>` (e.g., `test_variant_tiebreak`, `test_ocr_robustness`)
- **Property assertions:** Tests verify structural properties ("depth-0 groups before depth-1 in solve order") not just specific values
- **Integration tests:** `test_ocr.py::test_ocr_feeds_matcher` chains OCR output into the matcher

## Hardcoded Validation Invariants

`build_boards.py` contains assertion-based validation with hardcoded expected counts (exact numbers of boards, groups, picture groups, etc.). These act as regression tests for the data pipeline — any upstream data change triggers an immediate failure.
