import os
import re
import csv
import glob
from collections import Counter, defaultdict
from bs4 import BeautifulSoup

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "answers.csv")
SOURCE = "gameanswer.net"

FILENAME_RE = re.compile(r"^(\d+)\.html$")


def normalize_variant(text):
    text = text.strip()
    text = text.rstrip(":").strip()
    return text if text else "UNKNOWN"


def parse_level(filepath):
    level = int(FILENAME_RE.match(os.path.basename(filepath)).group(1))

    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")

    h2 = None
    for tag in soup.find_all("h2"):
        if "Answers" in tag.get_text():
            h2 = tag
            break

    if h2 is None:
        start = soup
        siblings = list(soup.children)
    else:
        siblings = list(h2.next_siblings)

    current_variant = "UNKNOWN"
    rows = []

    for el in siblings:
        if el.name == "p":
            b = el.find("b")
            if b:
                bold_text = b.get_text()
                if "Colorwood" in bold_text or len(bold_text) > 40:
                    continue
                current_variant = normalize_variant(bold_text)

        elif el.name == "ul":
            for li in el.find_all("li"):
                b = li.find("b")
                if not b:
                    continue
                category = b.get_text(strip=True)

                rest = ""
                for sibling in b.next_siblings:
                    rest += sibling.get_text() if hasattr(sibling, "get_text") else str(sibling)

                rest = re.sub(r"^\s*:\s*", "", rest)

                words = [w.strip() for w in rest.split(",") if w.strip()]

                for word in words:
                    rows.append((SOURCE, level, current_variant, category, word))

    return rows


def validate(all_rows, raw_files):
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    levels_parsed = set()
    for row in all_rows:
        levels_parsed.add(row[1])

    raw_levels = set()
    for f in raw_files:
        m = FILENAME_RE.match(os.path.basename(f))
        if m:
            raw_levels.add(int(m.group(1)))

    print(f"\nLevels parsed: {len(levels_parsed)} / {len(raw_levels)} raw files")

    missing_from_csv = raw_levels - levels_parsed
    if missing_from_csv:
        print(f"  Levels in raw/ but missing from CSV: {sorted(missing_from_csv)}")

    # Variant distribution
    variant_counts = Counter(row[2] for row in all_rows)
    print(f"\nVariant distribution (by word count):")
    for variant, count in variant_counts.most_common():
        print(f"  {variant}: {count}")

    # Words per group
    groups = defaultdict(list)
    for row in all_rows:
        key = (row[1], row[2], row[3])  # level, variant, category
        groups[key].append(row[4])

    group_sizes = Counter(len(words) for words in groups.values())
    print(f"\nWords-per-group distribution:")
    for size, count in sorted(group_sizes.items()):
        print(f"  {size} words: {count} groups")

    # Empty variants
    level_variant_groups = defaultdict(int)
    for key in groups:
        lv, var, _ = key
        level_variant_groups[(lv, var)] += 1

    # Duplicate words within (level, variant)
    dup_count = 0
    dup_examples = []
    by_level_variant = defaultdict(list)
    for row in all_rows:
        by_level_variant[(row[1], row[2])].append((row[3], row[4]))

    for (level, variant), entries in by_level_variant.items():
        words = [e[1] for e in entries]
        word_counts = Counter(words)
        for word, cnt in word_counts.items():
            if cnt > 1:
                dup_count += 1
                if len(dup_examples) < 10:
                    dup_examples.append(f"  Level {level} {variant}: '{word}' x{cnt}")

    print(f"\nDuplicate words within (level, variant): {dup_count}")
    for ex in dup_examples:
        print(ex)

    # Picture-group detection
    picture_count = 0
    picture_examples = []
    for (level, variant), entries in by_level_variant.items():
        categories = {e[0] for e in entries}
        words = {e[1] for e in entries}
        overlap = categories & words
        for name in overlap:
            picture_count += 1
            if len(picture_examples) < 10:
                picture_examples.append(f"  Level {level} {variant}: '{name}' is both a category and a word")

    print(f"\nPicture-group candidates: {picture_count}")
    for ex in picture_examples:
        print(ex)

    print(f"\nTotal rows: {len(all_rows)}")
    print(f"Total groups: {len(groups)}")
    print("=" * 60)


def main():
    raw_files = sorted(
        glob.glob(os.path.join(RAW_DIR, "*.html")),
        key=lambda f: int(FILENAME_RE.match(os.path.basename(f)).group(1)),
    )

    if not raw_files:
        print("No raw files found. Run fetch.py first.")
        return

    print(f"Found {len(raw_files)} raw files")

    all_rows = []
    errors = []

    for filepath in raw_files:
        try:
            rows = parse_level(filepath)
            all_rows.extend(rows)
        except Exception as e:
            level = os.path.basename(filepath)
            errors.append((level, str(e)))
            print(f"  Parse error in {level}: {e}")

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "level", "variant", "category", "word"])
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {CSV_PATH}")

    if errors:
        print(f"\n{len(errors)} parsing errors:")
        for filename, err in errors:
            print(f"  {filename}: {err}")

    validate(all_rows, raw_files)


if __name__ == "__main__":
    main()
