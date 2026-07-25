import json
import os
import pytest
from solver import compute_solve_order, match_words_to_group, load_boards

BOARDS_PATH = os.path.join(os.path.dirname(__file__), 'boards.json')


@pytest.fixture(scope='module')
def boards_data():
    with open(BOARDS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)['boards']


@pytest.fixture(scope='module')
def lookup():
    _, lk = load_boards(BOARDS_PATH)
    return lk


def test_compute_solve_order_simple(boards_data):
    simple = None
    for b in boards_data:
        if all(g['depth'] == 0 for g in b['groups']):
            simple = b
            break
    assert simple is not None
    order = compute_solve_order(simple)
    assert len(order) == len(simple['groups'])
    for idx, g in order:
        assert g['depth'] == 0


def test_compute_solve_order_with_depth1(boards_data):
    board = None
    for b in boards_data:
        depths = {g['depth'] for g in b['groups']}
        if 0 in depths and 1 in depths and not b['cyclic']:
            board = b
            break
    assert board is not None
    order = compute_solve_order(board)
    seen_depths = []
    for idx, g in order:
        seen_depths.append(g['depth'])
    first_d1 = seen_depths.index(1)
    assert all(d == 0 for d in seen_depths[:first_d1])


def test_compute_solve_order_cyclic(boards_data):
    board = next(b for b in boards_data if b['cyclic'])
    order = compute_solve_order(board)
    depths = [g['depth'] for _, g in order]
    first_none = None
    for i, d in enumerate(depths):
        if d is None:
            first_none = i
            break
    assert first_none is not None
    assert all(d is not None for d in depths[:first_none])


def test_match_words_to_group_exact():
    tiles = [
        ('SPEED', 0, 0), ('PAWN', 0, 1), ('PIT STOP', 0, 2), ('BALL', 0, 3),
        ('LEASH', 1, 0), ('TRACK', 1, 1), ('REFEREE', 1, 2), ('STADIUM', 1, 3),
    ]
    group = {'words': ['Speed', 'Pawn', 'Pit Stop', 'Ball']}
    result = match_words_to_group(tiles, group)
    assert result is not None
    assert set(result) == {(0, 0), (0, 1), (0, 2), (0, 3)}


def test_match_words_to_group_fuzzy():
    tiles = [
        ('STADIUN', 1, 3), ('REFEREE', 1, 2), ('GOAL', 2, 0), ('BALL', 0, 3),
    ]
    group = {'words': ['Referee', 'Stadium', 'Goal', 'Ball']}
    result = match_words_to_group(tiles, group)
    assert result is None


def test_match_words_to_group_missing():
    tiles = [
        ('SPEED', 0, 0), ('PAWN', 0, 1), ('PIT STOP', 0, 2),
    ]
    group = {'words': ['Speed', 'Pawn', 'Pit Stop', 'Ball']}
    result = match_words_to_group(tiles, group)
    assert result is None


def test_match_words_none_tiles():
    tiles = [
        ('SPEED', 0, 0), (None, 0, 1), ('PIT STOP', 0, 2), ('BALL', 0, 3),
        ('PAWN', 1, 0),
    ]
    group = {'words': ['Speed', 'Pawn', 'Pit Stop', 'Ball']}
    result = match_words_to_group(tiles, group)
    assert result is not None
    assert len(result) == 4


def test_solve_order_parent_before_child(lookup):
    board_id = '56f70eefcce8e8ef'
    board = lookup[board_id]
    order = compute_solve_order(board)
    solved_indices = set()
    for idx, g in order:
        if g['consumed_by'] is not None:
            assert g['consumed_by'] in solved_indices, (
                f'Group {idx} ({g["label"]}) needs parent {g["consumed_by"]} '
                f'solved first, but it has not been seen yet'
            )
        solved_indices.add(idx)
