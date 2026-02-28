"""
Udemy full-catalog scraper using keyword sweep strategy.

The search API returns up to 10,000 courses per query (416 pages × 24).
We sweep across ~120 topic keywords covering all Udemy categories,
deduplicate by course ID, and stream to data/udemy.csv.

Expected yield: 50,000–150,000 unique courses.
Runtime: 20–60 minutes depending on network.

Usage:
    python scripts/udemy.py [--resume]

    --resume   Skip keywords already completed in the last run (reads progress.json)

Cookies:
    Place cookies.json in the project root (see format below), OR set UDEMY_COOKIES
    env var to the raw Cookie header string from Chrome DevTools.

cookies.json (project root):
    Paste the parsed output of your browser's cookie header as a JSON dict.
    Key cookies needed: cf_clearance, __cf_bm, csrftoken, __udmy_2_v57r
"""

import asyncio
import csv
import json
import logging
import os
import sys
from pathlib import Path

from curl_cffi.requests import AsyncSession

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL       = "https://www.udemy.com/api/2024-01/graphql/"
PAGE_SIZE     = 24
CONCURRENCY   = 5         # simultaneous pages in-flight
RETRY_ATTEMPTS = 3
BATCH_PAUSE   = 0.3       # seconds between page-batches (polite rate limiting)
OUTPUT_PATH   = Path("data/udemy.csv")
PROGRESS_PATH = Path("data/progress.json")

# Topic keywords spanning all Udemy categories.
# Each keyword yields up to 10,000 unique courses from the search API.
KEYWORDS = [
    # ── Programming languages ─────────────────────────────────────────────
    "python", "javascript", "java", "c++", "c#", "golang", "ruby", "php",
    "swift", "kotlin", "rust", "typescript", "scala", "r programming",
    "perl", "bash scripting", "powershell", "assembly language", "lua",
    # ── Web development ───────────────────────────────────────────────────
    "react", "angular", "vue", "nodejs", "html css", "wordpress",
    "django", "flask", "laravel", "spring boot", "nextjs", "nuxtjs",
    "graphql", "rest api", "microservices", "web scraping",
    # ── Data & AI ─────────────────────────────────────────────────────────
    "machine learning", "deep learning", "data science", "tensorflow",
    "pytorch", "natural language processing", "computer vision",
    "data analysis", "tableau", "power bi", "data engineering",
    "apache spark", "hadoop", "airflow", "mlops",
    # ── Cloud & DevOps ────────────────────────────────────────────────────
    "aws", "azure", "google cloud", "docker", "kubernetes", "devops",
    "terraform", "ansible", "jenkins", "linux administration",
    "networking", "cloud computing",
    # ── Database ──────────────────────────────────────────────────────────
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "oracle database", "sqlite", "cassandra",
    # ── Mobile ────────────────────────────────────────────────────────────
    "android development", "ios development", "flutter", "react native",
    "xamarin", "ionic",
    # ── Game development ──────────────────────────────────────────────────
    "unity", "unreal engine", "game development", "godot", "blender",
    # ── Cybersecurity ─────────────────────────────────────────────────────
    "ethical hacking", "cybersecurity", "penetration testing",
    "network security", "cryptography", "soc analyst",
    # ── Business & Management ─────────────────────────────────────────────
    "project management", "agile", "scrum", "pmp certification",
    "leadership", "business analysis", "six sigma", "lean management",
    "supply chain", "operations management",
    # ── Marketing ─────────────────────────────────────────────────────────
    "digital marketing", "seo", "social media marketing", "google ads",
    "facebook ads", "email marketing", "content marketing",
    "affiliate marketing", "copywriting",
    # ── Finance & Accounting ──────────────────────────────────────────────
    "accounting", "excel", "financial modeling", "investing",
    "cryptocurrency", "stock trading", "forex trading", "bookkeeping",
    "quickbooks", "cfa exam",
    # ── Office Productivity ───────────────────────────────────────────────
    "microsoft office", "powerpoint", "word", "google workspace",
    "notion", "monday", "jira",
    # ── Design ────────────────────────────────────────────────────────────
    "photoshop", "illustrator", "figma", "graphic design", "ui ux design",
    "motion graphics", "after effects", "canva", "indesign", "3d modeling",
    # ── Photography & Video ───────────────────────────────────────────────
    "photography", "lightroom", "video editing", "premiere pro",
    "final cut pro", "youtube", "filmmaking", "color grading",
    # ── Music ─────────────────────────────────────────────────────────────
    "guitar", "piano", "music production", "music theory",
    "mixing mastering", "ableton", "fl studio", "singing",
    # ── Personal Development ──────────────────────────────────────────────
    "public speaking", "time management", "productivity",
    "critical thinking", "mindfulness", "nlp coaching",
    # ── Health & Fitness ──────────────────────────────────────────────────
    "yoga", "meditation", "fitness training", "nutrition",
    "weight loss", "mental health",
    # ── Lifestyle ─────────────────────────────────────────────────────────
    "cooking", "drawing", "watercolor painting", "calligraphy",
    "knitting", "interior design", "astrology",
    # ── Language Learning ─────────────────────────────────────────────────
    "english grammar", "spanish", "french", "german", "japanese",
    "chinese mandarin", "arabic language", "ielts",
    # ── Teaching & Academics ──────────────────────────────────────────────
    "online teaching", "curriculum design", "mathematics",
    "statistics", "physics", "chemistry",
]

GRAPHQL_QUERY = """
query SrpMxCourseSearch(
  $query: String!
  $page: NonNegativeInt!
  $pageSize: MaxResultsPerPage!
  $sortOrder: CourseSearchSortType
  $context: CourseSearchContext!
) {
  courseSearch(
    query: $query
    page: $page
    pageSize: $pageSize
    sortOrder: $sortOrder
    context: $context
  ) {
    count
    pageCount
    results {
      course {
        badges { __typename name }
        curriculum {
          contentCounts { lecturesCount practiceTestQuestionsCount }
        }
        durationInSeconds
        headline
        id
        images { px240x135 }
        instructors { id name }
        isFree
        isPracticeTestCourse
        level
        updatedOn
        locale
        rating { average count }
        title
        urlCourseLanding
        urlCourseTaking
      }
      trackingId
      handsOnRibbons
    }
    page
  }
}
"""

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "content-type": "application/json",
    "dnt": "1",
    "origin": "https://www.udemy.com",
    "referer": "https://www.udemy.com/courses/search/?q=*&src=ukw",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
}

CSV_FIELDS = [
    "id", "title", "headline", "level", "locale",
    "rating_average", "rating_count", "duration_seconds",
    "is_free", "is_practice_test_course",
    "instructors", "lectures_count", "practice_test_questions_count",
    "badges", "updated_on", "url_course_landing", "url_course_taking",
    "image_240x135", "tracking_id", "hands_on_ribbons",
]

COOKIES_FILE = Path("cookies.json")


# ---------------------------------------------------------------------------
# Cookie loading
# ---------------------------------------------------------------------------
def parse_cookie_string(raw: str) -> dict:
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def load_cookies() -> dict:
    if COOKIES_FILE.exists():
        try:
            data = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                logger.info(f"Loaded {len(data)} cookies from {COOKIES_FILE}")
                return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not read {COOKIES_FILE}: {exc}")

    raw = os.environ.get("UDEMY_COOKIES", "").strip()
    if raw:
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                logger.info(f"Loaded {len(data)} cookies from UDEMY_COOKIES (JSON)")
                return data
            except json.JSONDecodeError:
                pass
        data = parse_cookie_string(raw)
        if data:
            logger.info(f"Loaded {len(data)} cookies from UDEMY_COOKIES (raw string)")
            return data

    logger.warning("No cookies found — requests may be blocked by Cloudflare.")
    return {}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def build_payload(keyword: str, page: int) -> dict:
    return {
        "query": GRAPHQL_QUERY,
        "variables": {
            "page": page,
            "query": keyword,
            "sortOrder": "RELEVANCE",
            "pageSize": PAGE_SIZE,
            "context": {"triggerType": "USER_QUERY"},
        },
    }


def flatten_result(result: dict) -> dict:
    course    = result.get("course") or {}
    rating    = course.get("rating") or {}
    curriculum = course.get("curriculum") or {}
    counts    = curriculum.get("contentCounts") or {}
    images    = course.get("images") or {}
    instructors = course.get("instructors") or []
    badges    = course.get("badges") or []
    hands_on  = result.get("handsOnRibbons") or []
    return {
        "id":                           course.get("id"),
        "title":                        course.get("title"),
        "headline":                     course.get("headline"),
        "level":                        course.get("level"),
        "locale":                       course.get("locale"),
        "rating_average":               rating.get("average"),
        "rating_count":                 rating.get("count"),
        "duration_seconds":             course.get("durationInSeconds"),
        "is_free":                      course.get("isFree"),
        "is_practice_test_course":      course.get("isPracticeTestCourse"),
        "instructors":                  "|".join(i.get("name", "") for i in instructors),
        "lectures_count":               counts.get("lecturesCount"),
        "practice_test_questions_count": counts.get("practiceTestQuestionsCount"),
        "badges":                       "|".join(b.get("name", "") for b in badges),
        "updated_on":                   course.get("updatedOn"),
        "url_course_landing":           course.get("urlCourseLanding"),
        "url_course_taking":            course.get("urlCourseTaking"),
        "image_240x135":                images.get("px240x135"),
        "tracking_id":                  result.get("trackingId"),
        "hands_on_ribbons":             "|".join(hands_on),
    }


# ---------------------------------------------------------------------------
# Async fetch
# ---------------------------------------------------------------------------
async def fetch_page(
    session: AsyncSession,
    sem: asyncio.Semaphore,
    keyword: str,
    page: int,
    request_headers: dict,
) -> dict | None:
    async with sem:
        payload = build_payload(keyword, page)
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                resp = await session.post(API_URL, json=payload, headers=request_headers, timeout=30)
                if resp.status_code == 429:
                    wait = 2 ** attempt * 5
                    logger.warning(f"[{keyword}] p{page}: rate-limited, waiting {wait}s…")
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (403, 503):
                    logger.error(f"[{keyword}] p{page}: HTTP {resp.status_code} — refresh cookies.json")
                    return None
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                logger.warning(f"[{keyword}] p{page}: {exc} (attempt {attempt}/{RETRY_ATTEMPTS})")
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(2 ** attempt)
        return None


def extract_cs(response: dict) -> dict:
    return (response.get("data") or {}).get("courseSearch") or {}


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------
def load_progress() -> set:
    """Return set of keyword strings already fully processed."""
    if PROGRESS_PATH.exists():
        try:
            return set(json.loads(PROGRESS_PATH.read_text(encoding="utf-8")).get("done", []))
        except Exception:
            pass
    return set()


def save_progress(done: set) -> None:
    PROGRESS_PATH.write_text(json.dumps({"done": sorted(done)}, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(resume: bool = False) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cookies = load_cookies()

    request_headers = dict(HEADERS)
    if "csrftoken" in cookies:
        request_headers["x-csrftoken"] = cookies["csrftoken"]

    done_keywords = load_progress() if resume else set()
    if resume and done_keywords:
        logger.info(f"Resuming — {len(done_keywords)} keywords already done, skipping them.")

    pending_keywords = [kw for kw in KEYWORDS if kw not in done_keywords]
    logger.info(f"Keywords to process: {len(pending_keywords)}/{len(KEYWORDS)}")

    seen_ids: set[int] = set()
    saved = 0

    # If resuming, we can't know which IDs are already in the CSV without reading it.
    # Open in append mode when resuming, write mode otherwise.
    file_mode = "a" if resume and OUTPUT_PATH.exists() else "w"
    write_header = file_mode == "w"

    sem = asyncio.Semaphore(CONCURRENCY)

    async with AsyncSession(impersonate="chrome142", cookies=cookies) as session:
        with open(OUTPUT_PATH, file_mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if write_header:
                writer.writeheader()

            for kw_idx, keyword in enumerate(pending_keywords, 1):
                # ── Step 1: probe page 1 to get pageCount ──────────────────
                first = await fetch_page(session, sem, keyword, 1, request_headers)
                if first is None:
                    logger.error(f"[{keyword}] skipping — failed to fetch page 1")
                    continue

                cs = extract_cs(first)
                total  = cs.get("count", 0)
                pages  = cs.get("pageCount", 1)
                results_p1 = cs.get("results") or []

                kw_new = 0
                for result in results_p1:
                    cid = result.get("course", {}).get("id")
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        writer.writerow(flatten_result(result))
                        kw_new += 1

                logger.info(
                    f"[{kw_idx}/{len(pending_keywords)}] '{keyword}': "
                    f"{total:,} total, {pages} pages — +{kw_new} new (running total: {saved + kw_new:,})"
                )
                saved += kw_new

                if pages <= 1:
                    done_keywords.add(keyword)
                    save_progress(done_keywords)
                    continue

                # ── Step 2: fetch remaining pages in batches ───────────────
                remaining = list(range(2, pages + 1))
                batch_size = CONCURRENCY * 4

                for batch_start in range(0, len(remaining), batch_size):
                    batch = remaining[batch_start : batch_start + batch_size]
                    tasks = [fetch_page(session, sem, keyword, p, request_headers) for p in batch]
                    responses = await asyncio.gather(*tasks)

                    batch_new = 0
                    for resp_data in responses:
                        if resp_data is None:
                            continue
                        for result in (extract_cs(resp_data).get("results") or []):
                            cid = result.get("course", {}).get("id")
                            if cid and cid not in seen_ids:
                                seen_ids.add(cid)
                                writer.writerow(flatten_result(result))
                                batch_new += 1

                    saved += batch_new
                    f.flush()
                    await asyncio.sleep(BATCH_PAUSE)

                done_keywords.add(keyword)
                save_progress(done_keywords)
                logger.info(f"  └─ '{keyword}' done — unique so far: {saved:,}  (seen pool: {len(seen_ids):,})")

    logger.info(f"\nFinished — {saved:,} unique courses → {OUTPUT_PATH}")
    logger.info(f"Total ID pool seen: {len(seen_ids):,}")


if __name__ == "__main__":
    resume = "--resume" in sys.argv
    asyncio.run(main(resume=resume))
