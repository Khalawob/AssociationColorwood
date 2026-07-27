import json
import os
import pytest
from matcher import Matcher, _normalise_squash

BOARDS_PATH = os.path.join(os.path.dirname(__file__), 'boards.json')

@pytest.fixture(scope='module')
def matcher():
    return Matcher(BOARDS_PATH)

@pytest.fixture(scope='module')
def boards_data():
    with open(BOARDS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)['boards']


LEVEL_11_US_WORDS = [
    "Speed", "Pawn", "Pit Stop", "Ball", "Leash", "Track",
    "Referee", "Stadium", "Goal", "Summer Dress", "Kimono", "Slacks",
    "Wetsuit", "Longboard", "Wave", "Striped", "Cocktail Dress", "Shorts",
    "Sweatpants", "Fuzzy", "Ball Gown", "Ankle", "Jeans", "Wool",
]

LEVEL_11_US_ID = "56f70eefcce8e8ef"
LEVEL_11_GB_ID = "2fd91b0168b66764"


def _opening_words(board):
    words = []
    for g in board['groups']:
        if g.get('depth') == 0:
            words.extend(g['words'])
    return words


def test_exact_opening(matcher, boards_data):
    sample_indices = [0, 10, 50, 100, 200, 500, 1000, 1500, 1900]
    for i in sample_indices:
        if i >= len(boards_data):
            continue
        board = boards_data[i]
        words = _opening_words(board)
        if not words:
            continue
        result = matcher.identify(words)
        candidate_ids = [cid for cid, _ in result.candidates]
        assert board['id'] in candidate_ids, (
            f"Board {board['id']} (index {i}) not in candidates"
        )


def test_level_11_us(matcher, boards_data):
    result = matcher.identify(LEVEL_11_US_WORDS)
    assert result.board_id == LEVEL_11_US_ID
    board = next(b for b in boards_data if b['id'] == LEVEL_11_US_ID)
    assert [11, "US Version"] in board['occurrences']


def test_variant_tiebreak(matcher, boards_data):
    us_board = next(b for b in boards_data if b['id'] == LEVEL_11_US_ID)
    gb_board = next(b for b in boards_data if b['id'] == LEVEL_11_GB_ID)

    us_words = {_normalise_squash(w) for g in us_board['groups'] for w in g['words']}
    gb_words = {_normalise_squash(w) for g in gb_board['groups'] for w in g['words']}
    shared_norm = us_words & gb_words

    all_words_us = [w for g in us_board['groups'] for w in g['words']]
    shared_original = [w for w in all_words_us if _normalise_squash(w) in shared_norm]

    result_us = matcher.identify(shared_original, variant_hint="US Version")
    assert result_us.board_id == LEVEL_11_US_ID

    result_gb = matcher.identify(shared_original, variant_hint="GB Version")
    assert result_gb.board_id == LEVEL_11_GB_ID


def test_ocr_robustness(matcher):
    words = list(LEVEL_11_US_WORDS)
    words[0] = "Spee"       # Speed → Spee
    words[1] = "Pwn"        # Pawn → Pwn
    result = matcher.identify(words)
    candidate_ids = [cid for cid, _ in result.candidates]
    assert LEVEL_11_US_ID in candidate_ids
    assert result.candidates[0][0] == LEVEL_11_US_ID


def test_missing_words(matcher):
    words = LEVEL_11_US_WORDS[:8]
    result = matcher.identify(words)
    candidate_ids = [cid for cid, _ in result.candidates]
    assert LEVEL_11_US_ID in candidate_ids


def test_known_ambiguous(matcher, boards_data):
    ambiguous_pair = None
    sig_groups: dict[frozenset, list] = {}
    for i, board in enumerate(boards_data):
        opening = frozenset(
            _normalise_squash(w)
            for g in board['groups'] if g.get('depth') == 0
            for w in g['words']
        )
        sig_groups.setdefault(opening, []).append(i)

    for sig, indices in sig_groups.items():
        if len(indices) >= 2 and len(sig) > 0:
            ambiguous_pair = indices[:2]
            break

    assert ambiguous_pair is not None, "No ambiguous boards found"
    board = boards_data[ambiguous_pair[0]]
    words = _opening_words(board)
    result = matcher.identify(words)
    assert result.status == 'ambiguous'
    ids_in_ambiguous = [result.board_id] + result.ambiguous_with
    for idx in ambiguous_pair:
        assert boards_data[idx]['id'] in ids_in_ambiguous


def test_garbage(matcher):
    words = ["Xylophone", "Quasar", "Zeppelin", "Platypus", "Fjord", "Synth"]
    result = matcher.identify(words)
    assert result.status == 'none'
    assert result.board_id is None


def test_fuzzy_ocr_correction(matcher):
    words = list(LEVEL_11_US_WORDS)
    words[0] = "Speeed"     # Speed → Speeed (OCR stutter)
    words[3] = "Bali"       # Ball → Bali (OCR misread)
    result = matcher.identify(words)
    assert result.board_id == LEVEL_11_US_ID
    assert result.status in ('confident', 'weak')
