import colorsys
import os
import sys
import numpy as np
from PIL import Image
import easyocr

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(['en'], gpu=False)
    return _reader


SCREEN_W, SCREEN_H = 720, 1520

COL_CENTERS = [127, 275, 423, 573]
ROW_CENTERS = [415, 540, 665, 785, 910, 1035]
NUM_COLS = 4
MAX_ROWS = 6

TILE_HALF_W = 74
TILE_HALF_H = 44
TILE_INSET = 8

GRID_LEFT = 60
GRID_RIGHT = 660


def _strip_avg(image, row_y):
    strip = image.crop((GRID_LEFT, row_y - 5, GRID_RIGHT, row_y + 5))
    pixels = list(strip.getdata())
    n = len(pixels)
    r = sum(p[0] for p in pixels) / n
    g = sum(p[1] for p in pixels) / n
    b = sum(p[2] for p in pixels) / n
    return r, g, b


def _row_avg_hue(image, row_y):
    r, g, b = _strip_avg(image, row_y)
    h, _, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return h * 360


def _is_header_row(image, row_y):
    hue = _row_avg_hue(image, row_y)
    return not (10 <= hue <= 45)


def validate_grid(image):
    if image.size != (SCREEN_W, SCREEN_H):
        return False
    game_rows = 0
    for cy in ROW_CENTERS:
        r, g, b = _strip_avg(image, cy)
        if (r + g + b) / 3 < 30:
            continue
        hue = _row_avg_hue(image, cy)
        if 5 <= hue <= 50 or not (10 <= hue <= 45):
            game_rows += 1
    return game_rows >= 3


def crop_tiles(image):
    tiles = []
    for row_idx, cy in enumerate(ROW_CENTERS):
        if _is_header_row(image, cy):
            continue
        for col_idx, cx in enumerate(COL_CENTERS):
            box = (cx - TILE_HALF_W, cy - TILE_HALF_H,
                   cx + TILE_HALF_W, cy + TILE_HALF_H)
            tile = image.crop(box)
            tiles.append((tile, row_idx, col_idx))
    return tiles




def _find_text_band(image, cx, cy, half_w=50):
    gray = image.convert('L')
    text_top = None
    text_bottom = None
    gap = 0
    for dy in range(20, 80):
        y = cy + dy
        if y >= gray.height:
            break
        strip = gray.crop((cx - half_w, y, cx + half_w, y + 1))
        pixels = list(strip.getdata())
        dark_count = sum(1 for p in pixels if p < 80)
        if dark_count > 8:
            if text_top is None:
                text_top = y
            text_bottom = y
            gap = 0
        elif text_top is not None:
            gap += 1
            if gap > 15:
                break
    if text_top is None:
        return None
    return text_top - 2, text_bottom + 3


def _clean_ocr(text):
    import re
    text = text.upper()
    text = ' '.join(text.split())
    text = re.sub(r'[^A-Z ]+', '', text)
    text = ' '.join(text.split())
    text = re.sub(r'^[A-Z] ', '', text)
    text = re.sub(r' [A-Z]$', '', text)
    return text.strip()


def ocr_tile_at(image, cx, cy):
    band = _find_text_band(image, cx, cy)
    if band is None:
        return None
    text_top, text_bottom = band
    h_inset = 15
    text_region = image.crop((cx - TILE_HALF_W + h_inset, text_top,
                              cx + TILE_HALF_W - h_inset, text_bottom))
    gray = text_region.convert('L')
    scale = 4
    big = gray.resize((gray.width * scale, gray.height * scale), Image.LANCZOS)

    arr = np.array(big)
    results = _get_reader().readtext(arr, detail=0, paragraph=True)
    text = ' '.join(results)
    text = _clean_ocr(text)
    if len(text) < 2:
        return None
    return text


def ocr_tile(tile):
    gray = tile.convert('L')
    scale = 4
    big = gray.resize((gray.width * scale, gray.height * scale), Image.LANCZOS)

    arr = np.array(big)
    results = _get_reader().readtext(arr, detail=0, paragraph=True)
    text = ' '.join(results)
    text = ' '.join(text.split())
    if len(text) < 2 or not any(c.isalpha() for c in text):
        return None
    return text


def read_board_positioned(image):
    if not validate_grid(image):
        return []
    results = []
    for row_idx, cy in enumerate(ROW_CENTERS):
        if _is_header_row(image, cy):
            continue
        for col_idx, cx in enumerate(COL_CENTERS):
            word = ocr_tile_at(image, cx, cy)
            results.append((word, row_idx, col_idx))
    return results


def read_board(image_path):
    image = Image.open(image_path).convert('RGB')
    tiles = read_board_positioned(image)
    return [word for word, row, col in tiles if word]


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'captures/w01_195033.png'
    words = read_board(path)
    print(f'{len(words)} words: {words}')
