import os
import pytest
from PIL import Image
from ocr import validate_grid, crop_tiles, ocr_tile, ocr_tile_at, read_board, COL_CENTERS, ROW_CENTERS, TILE_HALF_W, TILE_HALF_H

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), 'captures')
FRESH_BOARD = os.path.join(CAPTURES_DIR, 'w01_195033.png')
MID_GAME = os.path.join(CAPTURES_DIR, 'w01_195150.png')
SOLVED_HEADER = os.path.join(CAPTURES_DIR, 'w03_195440.png')

has_captures = pytest.mark.skipif(
    not os.path.exists(FRESH_BOARD),
    reason='captures/ directory not available'
)

def _easyocr_available():
    try:
        import easyocr
        return True
    except ImportError:
        return False

needs_ocr = pytest.mark.skipif(
    not _easyocr_available(),
    reason='EasyOCR not installed'
)


@has_captures
def test_validate_grid_accepts_real():
    img = Image.open(FRESH_BOARD).convert('RGB')
    assert validate_grid(img)


def test_validate_grid_rejects_blank():
    img = Image.new('RGB', (720, 1520), (0, 0, 0))
    assert not validate_grid(img)


def test_validate_grid_rejects_wrong_size():
    img = Image.new('RGB', (800, 600), (230, 210, 170))
    assert not validate_grid(img)


@has_captures
def test_crop_tiles_full_board():
    img = Image.open(FRESH_BOARD).convert('RGB')
    tiles = crop_tiles(img)
    assert len(tiles) == 24


@has_captures
def test_crop_tiles_with_header():
    img = Image.open(SOLVED_HEADER).convert('RGB')
    tiles = crop_tiles(img)
    assert len(tiles) == 20


def _crop_single_tile(image_path, row, col):
    img = Image.open(image_path).convert('RGB')
    cx, cy = COL_CENTERS[col], ROW_CENTERS[row]
    return img.crop((cx - TILE_HALF_W, cy - TILE_HALF_H,
                     cx + TILE_HALF_W, cy + TILE_HALF_H))


@has_captures
@needs_ocr
def test_ocr_single_word():
    img = Image.open(FRESH_BOARD).convert('RGB')
    result = ocr_tile_at(img, COL_CENTERS[0], ROW_CENTERS[0])
    assert result == 'SPEED'


@has_captures
@needs_ocr
def test_ocr_multi_word():
    img = Image.open(FRESH_BOARD).convert('RGB')
    result = ocr_tile_at(img, COL_CENTERS[2], ROW_CENTERS[0])
    assert result == 'PIT STOP'


@has_captures
@needs_ocr
def test_ocr_two_line():
    img = Image.open(FRESH_BOARD).convert('RGB')
    result = ocr_tile_at(img, COL_CENTERS[1], ROW_CENTERS[2])
    assert result == 'SUMMER DRESS'


EXPECTED_FRESH_BOARD_WORDS = [
    'SPEED', 'PAWN', 'PIT STOP', 'BALL', 'LEASH', 'TRACK',
    'REFEREE', 'STADIUM', 'GOAL', 'SUMMER DRESS', 'KIMONO', 'SLACKS',
    'WETSUIT', 'LONGBOARD', 'WAVE', 'STRIPED', 'COCKTAIL DRESS', 'SHORTS',
    'SWEATPANTS', 'FUZZY', 'BALL GOWN', 'ANKLE', 'JEANS', 'WOOL',
]


@has_captures
@needs_ocr
def test_read_board_full():
    words = read_board(FRESH_BOARD)
    matched = sum(1 for w in EXPECTED_FRESH_BOARD_WORDS if w in words)
    assert matched >= 20, f'Only matched {matched}/24: got {words}'


@has_captures
@needs_ocr
def test_read_board_skips_solved_header():
    words = read_board(SOLVED_HEADER)
    for header_word in ['AFRICA', 'EUROPE', 'ASIA', 'SOUTH AMERICA', 'CONTINENTS']:
        assert header_word not in words, f'{header_word} should be filtered (solved header)'


@has_captures
@needs_ocr
def test_ocr_feeds_matcher():
    from matcher import Matcher
    boards_path = os.path.join(os.path.dirname(__file__), 'boards.json')
    if not os.path.exists(boards_path):
        pytest.skip('boards.json not available')
    matcher = Matcher(boards_path)
    words = read_board(FRESH_BOARD)
    result = matcher.identify(words)
    candidate_ids = [cid for cid, _ in result.candidates]
    assert '56f70eefcce8e8ef' in candidate_ids, (
        f'Level 11 US board not in candidates. Got: {result.candidates[:5]}'
    )
