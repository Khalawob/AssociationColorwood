import argparse
import json
import os
import time

from difflib import SequenceMatcher

from matcher import Matcher, _normalise_squash


def load_boards(boards_path):
    with open(boards_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    lookup = {b['id']: b for b in data['boards']}
    return data['boards'], lookup


def compute_solve_order(board):
    groups = board['groups']
    by_depth = []
    cyclic = []
    for i, g in enumerate(groups):
        if g['depth'] is None:
            cyclic.append((i, g))
        else:
            by_depth.append((i, g))
    by_depth.sort(key=lambda x: x[1]['depth'])
    return by_depth + cyclic


def _norm(word):
    return _normalise_squash(word)


def _fuzzy_match(word: str, candidates: set[str],
                  threshold: float = 0.8) -> str | None:
    best_ratio = 0.0
    best_match = None
    for candidate in candidates:
        ratio = SequenceMatcher(None, word, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = candidate
    if best_match and best_ratio >= threshold:
        return best_match
    return None


def match_words_to_group(tiles, group):
    needed = {_norm(w) for w in group['words']}
    positions = []
    matched = set()
    for word, row, col in tiles:
        if word is None:
            continue
        n = _norm(word)
        if n in needed and n not in matched:
            positions.append((row, col))
            matched.add(n)
    if matched == needed:
        return positions
    remaining = needed - matched
    for word, row, col in tiles:
        if word is None:
            continue
        n = _norm(word)
        if n in matched:
            continue
        fuzzy = _fuzzy_match(n, remaining)
        if fuzzy:
            positions.append((row, col))
            matched.add(fuzzy)
            remaining.discard(fuzzy)
    if matched == needed:
        return positions
    return None


def solve_board(boards_path=None, variant_hint=None, dry_run=False):
    from capture import screencap, tap
    from ocr import read_board_positioned, COL_CENTERS, ROW_CENTERS

    if boards_path is None:
        boards_path = os.path.join(os.path.dirname(__file__), 'boards.json')

    _, lookup = load_boards(boards_path)
    matcher = Matcher(boards_path)

    board = None
    solve_order = None
    solved = set()
    retries = 0
    max_retries = 3

    while True:
        print('Capturing screenshot...')
        image = screencap()
        tiles = read_board_positioned(image)
        visible_words = [w for w, _, _ in tiles if w]
        print(f'  {len(visible_words)} words visible: {visible_words[:8]}...')

        if board is None:
            result = matcher.identify(visible_words, variant_hint)
            if result.status == 'none':
                print(f'Cannot identify board. Visible words: {visible_words}')
                return False
            board = lookup[result.board_id]
            solve_order = compute_solve_order(board)
            print(f'Board identified: {result.board_id} ({result.status}, '
                  f'confidence={result.confidence:.2f})')
            print(f'  {len(solve_order)} groups to solve:')
            for i, g in solve_order:
                print(f'    [{i}] depth={g["depth"]} {g["label"]}: {g["words"]}')
            if result.corrections:
                print('  OCR corrections:')
                for original, corrected, ratio in result.corrections:
                    print(f'    "{original}" -> "{corrected}" ({ratio:.0%} match)')
            if result.unmatched:
                print('  OCR unmatched:')
                for word in result.unmatched:
                    print(f'    "{word}" (no match above 80%)')

        solved_one = False
        for idx, group in solve_order:
            if idx in solved:
                continue
            positions = match_words_to_group(tiles, group)
            if positions is None:
                continue

            print(f'\nSolving: {group["label"]} ({group["words"]})')
            print(f'  Tapping at: {positions}')

            if dry_run:
                solved.add(idx)
                solved_one = True
                continue

            for row, col in positions:
                tap_x = COL_CENTERS[col]
                tap_y = ROW_CENTERS[row] + 30
                print(f'  tap({tap_x}, {tap_y})')
                tap(tap_x, tap_y)
                time.sleep(0.3)

            solved.add(idx)
            solved_one = True
            retries = 0
            time.sleep(2.0)
            break

        if len(solved) == len(solve_order):
            print(f'\nBoard complete! Solved {len(solved)} groups.')
            return True

        if not solved_one:
            retries += 1
            if retries > max_retries:
                print(f'\nStuck after {max_retries} retries. '
                      f'Solved {len(solved)}/{len(solve_order)} groups.')
                unsolved = [g['label'] for i, g in solve_order if i not in solved]
                print(f'  Remaining: {unsolved}')
                return False
            print(f'No group matched, retrying ({retries}/{max_retries})...')
            time.sleep(1.0)

        if dry_run and not solved_one:
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Solve a Colorwood Associations board')
    parser.add_argument('--variant', type=str, default=None,
                        help='Variant hint (e.g. "US Version")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show solve plan without tapping')
    parser.add_argument('--boards', type=str, default=None,
                        help='Path to boards.json')
    args = parser.parse_args()
    solve_board(boards_path=args.boards, variant_hint=args.variant,
                dry_run=args.dry_run)
