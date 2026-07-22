import os
import re
import time
import datetime
import requests

LIMIT = None

API_URL = "https://www.gameanswer.net/wp-json/wp/v2/posts"
SEARCH_TERM = "colorwood associations level"
PER_PAGE = 100
FIELDS = "id,slug,content"
SLEEP_SECONDS = 1.5
RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
ERROR_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_errors.log")
USER_AGENT = (
    "ColorwoodScraper/1.0 "
    "(+https://github.com/placeholder; educational project) "
    "Python-requests"
)

SLUG_RE = re.compile(r"^colorwood-associations-level-(\d+)$")


def log_error(fh, msg):
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}\n"
    fh.write(line)
    fh.flush()
    print(f"  ERROR: {msg}")


def fetch_all():
    os.makedirs(RAW_DIR, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    saved = 0
    skipped = 0
    errors = 0
    all_levels_seen = set()

    with open(ERROR_LOG, "a", encoding="utf-8") as err_fh:
        page = 1
        total_pages = None

        while True:
            if total_pages is not None and page > total_pages:
                break

            params = {
                "search": SEARCH_TERM,
                "per_page": PER_PAGE,
                "page": page,
                "_fields": FIELDS,
            }

            try:
                resp = session.get(API_URL, params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                log_error(err_fh, f"page {page}: {e}")
                errors += 1
                page += 1
                time.sleep(SLEEP_SECONDS)
                continue

            if total_pages is None:
                total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
                total_posts = resp.headers.get("X-WP-Total", "?")
                print(f"API reports {total_posts} posts across {total_pages} pages")

            posts = resp.json()
            if not posts:
                break

            done = False
            for post in posts:
                slug = post.get("slug", "")
                m = SLUG_RE.match(slug)
                if not m:
                    continue

                level = int(m.group(1))
                all_levels_seen.add(level)
                path = os.path.join(RAW_DIR, f"{level}.html")

                if os.path.exists(path):
                    skipped += 1
                    continue

                content = post.get("content", {}).get("rendered", "")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                saved += 1

                if LIMIT is not None and saved >= LIMIT:
                    done = True
                    break

            if done:
                break

            page += 1
            if total_pages is not None and page <= total_pages:
                time.sleep(SLEEP_SECONDS)

        # Gap-fill: check for levels seen but not saved
        if LIMIT is None:
            missing = []
            for level in sorted(all_levels_seen):
                path = os.path.join(RAW_DIR, f"{level}.html")
                if not os.path.exists(path):
                    missing.append(level)

            if missing:
                print(f"\nGap-fill: {len(missing)} levels missing, fetching by slug...")
                for level in missing:
                    slug = f"colorwood-associations-level-{level}"
                    try:
                        resp = session.get(
                            API_URL,
                            params={"slug": slug, "_fields": FIELDS},
                            timeout=30,
                        )
                        resp.raise_for_status()
                        posts = resp.json()
                        if posts:
                            content = posts[0].get("content", {}).get("rendered", "")
                            path = os.path.join(RAW_DIR, f"{level}.html")
                            with open(path, "w", encoding="utf-8") as f:
                                f.write(content)
                            saved += 1
                            print(f"  Filled level {level}")
                        else:
                            log_error(err_fh, f"gap-fill level {level}: empty response")
                            errors += 1
                    except requests.RequestException as e:
                        log_error(err_fh, f"gap-fill level {level}: {e}")
                        errors += 1
                    time.sleep(SLEEP_SECONDS)

    print(f"\nDone. Saved: {saved}, Skipped (existing): {skipped}, Errors: {errors}")
    existing = len([f for f in os.listdir(RAW_DIR) if f.endswith(".html")])
    print(f"Total files in raw/: {existing}")


if __name__ == "__main__":
    fetch_all()
