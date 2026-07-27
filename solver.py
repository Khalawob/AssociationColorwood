import argparse
import json
import os
import time
from dataclasses import dataclass

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


@dataclass
class PlannedTap:
    tap_number: int
    group_index: int
    group_label: str
    tap_x: int
    tap_y: int


@dataclass
class UnmatchedGroup:
    group_index: int
    group_label: str
    words: list


GROUP_COLORS = [
    (220, 50, 50),
    (50, 130, 220),
    (50, 180, 50),
    (200, 140, 30),
    (160, 50, 200),
    (30, 190, 190),
    (220, 100, 160),
]


def _threshold_for_length(length: int) -> float:
    if length <= 3:
        return 0.6
    if length <= 4:
        return 0.7
    return 0.8


def _fuzzy_match(word: str, candidates: set[str]) -> str | None:
    threshold = _threshold_for_length(len(word))
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


def _collect_tap_plan(boards_path, variant_hint):
    from capture import screencap
    from ocr import read_board_positioned, COL_CENTERS, ROW_CENTERS

    _, lookup = load_boards(boards_path)
    matcher = Matcher(boards_path)

    print('Capturing screenshot...')
    image = screencap()
    tiles = read_board_positioned(image)
    visible_words = [w for w, _, _ in tiles if w]
    print(f'  {len(visible_words)} words visible: {visible_words[:8]}...')

    result = matcher.identify(visible_words, variant_hint)
    if result.status == 'none':
        print(f'Cannot identify board. Visible words: {visible_words}')
        return None

    board = lookup[result.board_id]
    solve_order = compute_solve_order(board)
    print(f'Board identified: {result.board_id} ({result.status}, '
          f'confidence={result.confidence:.2f})')

    planned_taps = []
    unmatched_groups = []
    tap_number = 1

    for idx, group in solve_order:
        positions = match_words_to_group(tiles, group)
        if positions is None:
            unmatched_groups.append(UnmatchedGroup(idx, group['label'], group['words']))
            continue
        group_color_idx = len({t.group_index for t in planned_taps})
        for row, col in positions:
            planned_taps.append(PlannedTap(
                tap_number=tap_number,
                group_index=group_color_idx,
                group_label=group['label'],
                tap_x=COL_CENTERS[col],
                tap_y=ROW_CENTERS[row] + 30,
            ))
            tap_number += 1

    return image, planned_taps, unmatched_groups, result.board_id


def _render_preview(image, planned_taps, unmatched_groups, board_id):
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('arial.ttf', 14)
        small_font = ImageFont.truetype('arial.ttf', 11)
    except OSError:
        font = ImageFont.load_default()
        small_font = font

    label_drawn = set()

    for tap in planned_taps:
        color = GROUP_COLORS[tap.group_index % len(GROUP_COLORS)]
        cx, cy = tap.tap_x, tap.tap_y
        r = 16

        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=color, outline='white', width=2)

        text = str(tap.tap_number)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2), text, fill='white', font=font)

        if tap.group_index not in label_drawn:
            label_drawn.add(tap.group_index)
            label = tap.group_label
            lbbox = draw.textbbox((0, 0), label, font=small_font)
            lw = lbbox[2] - lbbox[0]
            lh = lbbox[3] - lbbox[1]
            lx = cx + r + 4
            ly = cy - lh // 2
            draw.rectangle([lx - 2, ly - 2, lx + lw + 2, ly + lh + 2],
                           fill=(0, 0, 0))
            draw.text((lx, ly), label, fill=color, font=small_font)

    if unmatched_groups:
        y_offset = image.height - 30 * len(unmatched_groups) - 10
        for ug in unmatched_groups:
            text = f"? {ug.group_label}: {', '.join(ug.words)}"
            draw.text((10, y_offset), text, fill=(255, 80, 80), font=small_font)
            y_offset += 30

    out_path = f'preview_{board_id}.png'
    image.save(out_path)
    return out_path


def solve_board(boards_path=None, variant_hint=None, dry_run=False, preview=False):
    from capture import screencap, tap
    from ocr import read_board_positioned, COL_CENTERS, ROW_CENTERS

    if boards_path is None:
        boards_path = os.path.join(os.path.dirname(__file__), 'boards.json')

    if preview:
        result = _collect_tap_plan(boards_path, variant_hint)
        if result is None:
            return False
        image, taps, unmatched, board_id = result
        out_path = _render_preview(image, taps, unmatched, board_id)
        print(f'Preview saved to {out_path}')
        os.startfile(out_path)
        return True

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
    parser.add_argument('--preview', action='store_true',
                        help='Annotate screenshot with tap markers; no tapping')
    args = parser.parse_args()
    solve_board(boards_path=args.boards, variant_hint=args.variant,
                dry_run=args.dry_run, preview=args.preview)
