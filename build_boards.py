import os
import sys
import csv
import json
import hashlib
import datetime
from collections import OrderedDict, Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "answers.csv")
OUT_PATH = os.path.join(SCRIPT_DIR, "boards.json")
SOURCE = "gameanswer.net"


def load_csv():
    rows = []
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                {
                    "source": r["source"],
                    "level": int(r["level"]),
                    "variant": r["variant"],
                    "category": r["category"],
                    "word": r["word"],
                }
            )
    return rows


def repair_washington_dc(rows):
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["level"], r["variant"], r["category"])].append(i)

    repaired = 0
    indices_to_remove = []

    for key, idxs in groups.items():
        _, _, category = key
        if category != "East Coast Cities":
            continue
        words = {rows[i]["word"] for i in idxs}
        if "Washington" in words and "D.C." in words:
            for i in idxs:
                if rows[i]["word"] == "Washington":
                    rows[i]["word"] = "Washington, D.C."
                elif rows[i]["word"] == "D.C.":
                    indices_to_remove.append(i)
            repaired += 1

    if repaired != 5:
        fail(f"Expected 5 East Coast Cities repairs, got {repaired}")

    for i in sorted(indices_to_remove, reverse=True):
        rows.pop(i)

    return rows


def build_board_instances(rows):
    boards = OrderedDict()
    for r in rows:
        key = (r["level"], r["variant"])
        if key not in boards:
            boards[key] = OrderedDict()
        cat = r["category"]
        if cat not in boards[key]:
            boards[key][cat] = []
        boards[key][cat].append(r["word"])

    instances = {}
    for (level, variant), group_dict in boards.items():
        groups = []
        for label, words in group_dict.items():
            groups.append({"label": label, "words": list(words)})
        instances[(level, variant)] = groups

    return instances


def compute_signature(groups):
    pairs = []
    for g in groups:
        for w in g["words"]:
            pairs.append((g["label"], w))
    pairs.sort()
    raw = repr(pairs).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def deduplicate(instances):
    sig_map = {}
    for (level, variant), groups in instances.items():
        sig = compute_signature(groups)
        if sig not in sig_map:
            sig_map[sig] = {"groups": groups, "occurrences": []}
        sig_map[sig]["occurrences"].append((level, variant))

    for entry in sig_map.values():
        entry["occurrences"].sort()

    return sig_map


def classify_groups(board_groups):
    all_words = set()
    for g in board_groups:
        for w in g["words"]:
            all_words.add(w)

    for g in board_groups:
        g["type"] = "picture" if g["label"] in all_words else "theme"

    return board_groups


def resolve_consumed_by(board_groups):
    for i, g in enumerate(board_groups):
        if g["type"] == "theme":
            g["consumed_by"] = None
            continue

        found = None
        for j, other in enumerate(board_groups):
            if i == j:
                continue
            if g["label"] in other["words"]:
                found = j
                break

        if found is None and g["label"] in g["words"]:
            found = i

        if found is None:
            raise ValueError(f"Picture group '{g['label']}' has no consumed_by target")

        g["consumed_by"] = found

    return board_groups


def detect_cycles(board_groups):
    cyclic = set()
    for i, g in enumerate(board_groups):
        if g["type"] != "picture":
            continue
        visited = []
        visited_set = set()
        cur = i
        while board_groups[cur]["consumed_by"] is not None and cur not in visited_set:
            visited.append(cur)
            visited_set.add(cur)
            cur = board_groups[cur]["consumed_by"]
        if cur in visited_set:
            idx = visited.index(cur)
            for c in visited[idx:]:
                cyclic.add(c)
    return cyclic


def compute_depths(board_groups, cyclic):
    depths = {}

    def get_depth(idx):
        if idx in depths:
            return depths[idx]
        g = board_groups[idx]
        if g["type"] == "theme":
            depths[idx] = 0
            return 0
        if idx in cyclic:
            depths[idx] = None
            return None
        target = g["consumed_by"]
        td = get_depth(target)
        if td is None:
            depths[idx] = None
            return None
        depths[idx] = td + 1
        return depths[idx]

    for i in range(len(board_groups)):
        get_depth(i)

    return depths


def reorder_groups(board_groups):
    for i, g in enumerate(board_groups):
        g["_orig_idx"] = i

    def sort_key(g):
        d = g["depth"]
        if d is None:
            return (1, 999, g["_orig_idx"])
        return (0, d, g["_orig_idx"])

    reordered = sorted(board_groups, key=sort_key)

    old_to_new = {}
    for new_idx, g in enumerate(reordered):
        old_to_new[g["_orig_idx"]] = new_idx

    for g in reordered:
        if g["consumed_by"] is not None:
            g["consumed_by"] = old_to_new[g["consumed_by"]]

    for g in reordered:
        del g["_orig_idx"]

    return reordered


def print_report(boards, stats):
    print("\n" + "=" * 60)
    print("BUILD REPORT")
    print("=" * 60)
    print(f"  Distinct boards:              {len(boards)}")
    print(f"  Picture groups (pre-dedup):    {stats['picture']}")
    print(f"  Depth-2 groups (pre-dedup):    {stats['depth2']}")
    print(f"  Null-depth groups (pre-dedup): {stats['null_depth']}")
    print(f"  Cycle instances (pre-dedup):   {stats['cycle_instances']}")
    print(f"  No-picture instances:          {stats['no_pic_instances']}")

    occ_counts = Counter(len(b["occurrences"]) for b in boards)
    print(f"\n  Occurrences distribution:")
    for n, cnt in sorted(occ_counts.items()):
        print(f"    {n} occurrence(s): {cnt} boards")

    gc_counts = Counter(len(b["groups"]) for b in boards)
    print(f"\n  Groups-per-board distribution:")
    for n, cnt in sorted(gc_counts.items()):
        print(f"    {n} groups: {cnt} boards")
    print("=" * 60)


def fail(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    print("Loading CSV...")
    rows = load_csv()
    print(f"  {len(rows)} rows loaded")

    print("Repairing Washington D.C. split...")
    rows = repair_washington_dc(rows)

    print("Building board instances...")
    instances = build_board_instances(rows)

    if len(instances) != 7353:
        fail(f"Expected 7353 board instances, got {len(instances)}")

    levels = set(k[0] for k in instances)
    if levels != set(range(1, 3001)):
        fail("Levels not contiguous 1-3000")

    total_groups = sum(len(gs) for gs in instances.values())
    if total_groups != 77336:
        fail(f"Expected 77336 total groups, got {total_groups}")

    bad_groups = sum(1 for gs in instances.values() for g in gs if len(g["words"]) != 4)
    if bad_groups != 0:
        fail(f"{bad_groups} groups with != 4 words after repair")

    print("Deduplicating...")
    sig_map = deduplicate(instances)
    if len(sig_map) != 1952:
        fail(f"Expected 1952 distinct boards, got {len(sig_map)}")

    print("Classifying groups and resolving consumed_by...")
    total_picture = 0
    total_depth2 = 0
    total_null_depth = 0
    cycle_instances = 0
    no_pic_instances = 0
    boards_list = []

    for sig, entry in sig_map.items():
        groups = entry["groups"]
        n_occ = len(entry["occurrences"])

        classify_groups(groups)
        resolve_consumed_by(groups)

        cyclic = detect_cycles(groups)
        depths = compute_depths(groups, cyclic)

        for i, g in enumerate(groups):
            g["depth"] = depths[i]

        pic_count = sum(1 for g in groups if g["type"] == "picture")
        d2_count = sum(1 for d in depths.values() if d is not None and d >= 2)
        null_count = sum(1 for d in depths.values() if d is None)
        has_cycle = len(cyclic) > 0

        total_picture += pic_count * n_occ
        total_depth2 += d2_count * n_occ
        total_null_depth += null_count * n_occ
        if has_cycle:
            cycle_instances += n_occ
        if pic_count == 0:
            no_pic_instances += n_occ

        groups = reorder_groups(groups)

        boards_list.append(
            {
                "id": sig,
                "occurrences": [list(occ) for occ in entry["occurrences"]],
                "cyclic": has_cycle,
                "groups": [
                    {
                        "label": g["label"],
                        "type": g["type"],
                        "depth": g["depth"],
                        "consumed_by": g["consumed_by"],
                        "words": g["words"],
                    }
                    for g in groups
                ],
            }
        )

    if total_picture != 33277:
        fail(f"Expected 33277 picture groups, got {total_picture}")
    if total_depth2 != 4:
        fail(f"Expected 4 depth-2 groups, got {total_depth2}")
    if total_null_depth != 133:
        fail(f"Expected 133 null-depth groups, got {total_null_depth}")
    if cycle_instances != 51:
        fail(f"Expected 51 cycle instances, got {cycle_instances}")
    if no_pic_instances != 909:
        fail(f"Expected 909 no-picture instances, got {no_pic_instances}")

    boards_list.sort(key=lambda b: min(occ[0] for occ in b["occurrences"]))

    output = {
        "meta": {
            "source": SOURCE,
            "board_count": len(boards_list),
            "built_at": datetime.datetime.now(datetime.timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        },
        "boards": boards_list,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    stats = {
        "picture": total_picture,
        "depth2": total_depth2,
        "null_depth": total_null_depth,
        "cycle_instances": cycle_instances,
        "no_pic_instances": no_pic_instances,
    }

    print(f"\nWrote {len(boards_list)} boards to {OUT_PATH}")
    print_report(boards_list, stats)


if __name__ == "__main__":
    main()
