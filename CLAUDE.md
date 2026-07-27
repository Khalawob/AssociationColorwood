# Colorwood Associations Solver

Automated solver for the mobile game "Colorwood Associations" (Burny Games). Scrapes answer data from gameanswer.net, builds a deduplicated board database, then uses ADB + OCR to capture screenshots from an Android phone, identify the current board, and tap the correct tile groups in dependency order.

## Tech Stack

- **Language:** Python 3.10+ (uses `str | None` union syntax)
- **Libraries:** `requirements.txt` — requests, beautifulsoup4, Pillow, easyocr (PyTorch-based OCR)
- **External tools:**
  - ADB (Android Debug Bridge) — all device communication goes through `capture.py:19-30`
- **Testing:** pytest (not in requirements.txt — install separately)

## Project Structure

### Data Pipeline (offline, run in order)

| File | Purpose |
|------|---------|
| `fetch.py` | Scrapes level pages from gameanswer.net WordPress API, saves to `raw/` |
| `parse.py` | Parses `raw/*.html` into `answers.csv` using BeautifulSoup |
| `build_boards.py` | Builds `boards.json` — deduplicates 7,353 instances into 1,952 unique boards via SHA-256, computes group dependencies and depth |

### Runtime Pipeline (solve loop)

| File | Purpose |
|------|---------|
| `capture.py` | ADB wrapper — screenshots (`screencap()`), tap input (`tap(x,y)`), CLI subcommands: `info`, `shot`, `burst`, `watch` |
| `ocr.py` | Extracts word tiles from screenshots using EasyOCR — hardcoded for 720x1520 resolution (`ocr.py:14-26`) |
| `matcher.py` | Identifies which board is being played using a voting algorithm. Only class in the project: `Matcher` (`matcher.py:7-13` for `MatchResult` dataclass) |
| `solver.py` | Main entry point — orchestrates capture → OCR → match → tap loop |

### Test Files

| File | Covers |
|------|--------|
| `test_matcher.py` | Board identification: exact match, variant tiebreaking, OCR robustness, ambiguous/garbage input |
| `test_ocr.py` | Grid detection, tile cropping, OCR accuracy. Skips if captures/ or EasyOCR unavailable |
| `test_solver.py` | Solve order computation, word-to-group matching (exact, fuzzy, missing), depth ordering |

### Data Files

| Path | Content |
|------|---------|
| `raw/` | 3,000 scraped HTML files (`1.html` – `3000.html`) |
| `answers.csv` | Parsed answers: `source, level, variant, category, word` |
| `boards.json` | Board database: 1,952 unique boards with group metadata |
| `captures/` | Screenshot PNGs for OCR testing |

## Essential Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Data pipeline (run in order)
python fetch.py          # Scrape levels (rate-limited, takes a while)
python parse.py          # Parse HTML → answers.csv
python build_boards.py   # Build boards.json from CSV

# Runtime
python solver.py                        # Solve the current board on connected phone
python solver.py --dry-run              # Identify board without tapping
python solver.py --preview              # Annotate screenshot with numbered tap markers
python solver.py --variant "US Version" # Hint for variant tiebreaking
python capture.py shot                  # Take a single screenshot

# Tests
pytest test_matcher.py test_ocr.py test_solver.py
```

## Key Concepts

### Board Model
Each board has 5-7 groups. Each group has a `label`, 4 `words`, and a `type`:
- **"theme"** — standard category (depth 0)
- **"picture"** — label appears as a word in another group, creating a dependency (depth 1+)

### Dependency & Solve Order
Picture groups depend on theme groups via `consumed_by` pointers. The solver must complete depth-0 groups first, then depth-1, etc. Cyclic groups (depth `null`) are solved last. See `solver.py:16-26` for `compute_solve_order`.

### OCR Calibration
All tile coordinates are hardcoded for 720x1520 screens — `COL_CENTERS`, `ROW_CENTERS`, tile dimensions at `ocr.py:14-26`. Changing phone resolution requires updating these constants. The EasyOCR Reader is initialized as a lazy singleton (`_get_reader()`) to avoid per-tile overhead.

### Text Normalization
Two normalization functions in `matcher.py:16-20`: `_normalise_squash` (strip non-alphanumeric) and `_normalise_spaced` (collapse whitespace). `solver.py` reuses `_normalise_squash` via `_norm()` at `solver.py:32-33`.

### Fuzzy OCR Correction
When OCR misreads a word, fuzzy matching corrects it against a scoped vocabulary using `difflib.SequenceMatcher`. The similarity threshold scales by word length to handle short words where a single character error causes a large ratio drop:
- **3 letters or fewer:** 60%
- **4 letters:** 70%
- **5+ letters:** 80%

This applies in two places:
- **Board identification** (`matcher.py`): After the first voting pass, unmatched OCR words are fuzzy-matched against the vocabulary of the top 5 candidate boards (`_fuzzy_correct`), then re-voted. Restricting candidates to top boards (rather than the full dictionary) minimizes false positives. Corrections and unmatched words are logged in the solver output.
- **Tile tapping** (`solver.py`): `match_words_to_group` does a second pass where unmatched tiles are fuzzy-matched against the group's remaining needed words (`_fuzzy_match`), so OCR errors don't block the solve loop.

### Board Matching
`Matcher` builds an inverted word→board index on init. Each visible word votes for boards containing it; highest-voted board wins. Confidence = top votes / total words. See `matcher.py` for statuses: `confident`, `weak`, `ambiguous`, `none`.

### Preview Mode
`--preview` runs the full solver pipeline (screenshot → OCR → board identification → solve order → word matching) but instead of tapping, draws numbered colored markers on the screenshot at each tap coordinate in solve order. Each group gets a distinct color and a label. Unmatched groups appear as red warning text at the bottom. The annotated image saves to `preview_<board_id>.png` and opens automatically. Requires a connected device via ADB but not the game itself. See `solver.py:115-208` for `_collect_tap_plan` and `_render_preview`.

## Additional Documentation

Check these files when working in the relevant areas:

- [Architectural Patterns](.claude/docs/architectural_patterns.md) — pipeline design, error handling strategies, deduplication, dependency ordering, testing conventions
