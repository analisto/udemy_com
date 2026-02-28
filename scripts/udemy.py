"""
Udemy course scraper using the GraphQL API.
Saves all courses to data/udemy.csv for market research.

Usage:
    python scripts/udemy.py

Cookies (required — Cloudflare blocks cookie-less requests):
  Option 1: Place a cookies.json file in the project root with key/value pairs.
  Option 2: Set the UDEMY_COOKIES env var to a raw Cookie header string
            (copy the full "cookie" header value from Chrome DevTools → Network tab).

How to get cookies:
  1. Open udemy.com in Chrome and search for any courses.
  2. Open DevTools → Network → find the GraphQL request to /api/2024-01/graphql/
  3. Right-click → Copy → Copy as cURL
  4. Paste the cookie value from the cURL command into cookies.json or UDEMY_COOKIES.

cookies.json format (project root):
  {
    "cf_clearance": "...",
    "csrftoken": "...",
    "__udmy_2_v57r": "...",
    "__cf_bm": "..."
  }
"""

import asyncio
import csv
import json
import logging
import os
import sys
from pathlib import Path

from curl_cffi.requests import AsyncSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = "https://www.udemy.com/api/2024-01/graphql/"
PAGE_SIZE = 24          # max allowed per the API type MaxResultsPerPage
CONCURRENCY = 3         # simultaneous in-flight requests (be polite)
RETRY_ATTEMPTS = 4
OUTPUT_PATH = Path("data/udemy.csv")

GRAPHQL_QUERY = """
query SrpMxCourseSearch(
  $query: String!
  $page: NonNegativeInt!
  $pageSize: MaxResultsPerPage!
  $sortOrder: CourseSearchSortType
  $filters: CourseSearchFilters
  $context: CourseSearchContext!
) {
  courseSearch(
    query: $query
    page: $page
    pageSize: $pageSize
    sortOrder: $sortOrder
    filters: $filters
    context: $context
  ) {
    count
    results {
      course {
        badges { __typename name }
        curriculum {
          contentCounts {
            lecturesCount
            practiceTestQuestionsCount
          }
        }
        durationInSeconds
        headline
        id
        images { px240x135 }
        instructors { id name }
        isFree
        isPracticeTestCourse
        learningOutcomes
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
    pageCount
    count
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

COOKIES_FILE = Path("cookies.json")


def parse_cookie_string(raw: str) -> dict:
    """Parse a raw Cookie header string into a dict."""
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def load_cookies() -> dict:
    """Load cookies from cookies.json or UDEMY_COOKIES env var."""
    # 1. cookies.json takes priority
    if COOKIES_FILE.exists():
        try:
            data = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                logger.info(f"Loaded {len(data)} cookies from {COOKIES_FILE}")
                return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not read {COOKIES_FILE}: {exc}")

    # 2. Fall back to env var (accepts JSON dict or raw Cookie header string)
    raw = os.environ.get("UDEMY_COOKIES", "").strip()
    if raw:
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                logger.info(f"Loaded {len(data)} cookies from UDEMY_COOKIES (JSON)")
                return data
            except json.JSONDecodeError:
                logger.warning("UDEMY_COOKIES looks like JSON but failed to parse")
        # Try raw cookie string
        data = parse_cookie_string(raw)
        if data:
            logger.info(f"Loaded {len(data)} cookies from UDEMY_COOKIES (raw string)")
            return data

    logger.warning(
        "No cookies found. Requests will likely be blocked by Cloudflare.\n"
        f"  → Create {COOKIES_FILE} with your browser cookies (see script docstring)."
    )
    return {}

CSV_FIELDS = [
    "id",
    "title",
    "headline",
    "level",
    "locale",
    "rating_average",
    "rating_count",
    "duration_seconds",
    "is_free",
    "is_practice_test_course",
    "instructors",
    "lectures_count",
    "practice_test_questions_count",
    "badges",
    "updated_on",
    "url_course_landing",
    "url_course_taking",
    "image_240x135",
    "tracking_id",
    "hands_on_ribbons",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def build_payload(page: int) -> dict:
    return {
        "query": GRAPHQL_QUERY,
        "variables": {
            "page": page,
            "query": "*",
            "sortOrder": "RELEVANCE",
            "pageSize": PAGE_SIZE,
            "context": {"triggerType": "USER_QUERY"},
        },
    }


def flatten_result(result: dict) -> dict:
    """Flatten a single search result into a CSV-ready dict."""
    course = result.get("course") or {}
    rating = course.get("rating") or {}
    curriculum = course.get("curriculum") or {}
    counts = curriculum.get("contentCounts") or {}
    images = course.get("images") or {}
    instructors = course.get("instructors") or []
    badges = course.get("badges") or []
    hands_on = result.get("handsOnRibbons") or []

    return {
        "id": course.get("id"),
        "title": course.get("title"),
        "headline": course.get("headline"),
        "level": course.get("level"),
        "locale": course.get("locale"),
        "rating_average": rating.get("average"),
        "rating_count": rating.get("count"),
        "duration_seconds": course.get("durationInSeconds"),
        "is_free": course.get("isFree"),
        "is_practice_test_course": course.get("isPracticeTestCourse"),
        "instructors": "|".join(i.get("name", "") for i in instructors),
        "lectures_count": counts.get("lecturesCount"),
        "practice_test_questions_count": counts.get("practiceTestQuestionsCount"),
        "badges": "|".join(b.get("name", "") for b in badges),
        "updated_on": course.get("updatedOn"),
        "url_course_landing": course.get("urlCourseLanding"),
        "url_course_taking": course.get("urlCourseTaking"),
        "image_240x135": images.get("px240x135"),
        "tracking_id": result.get("trackingId"),
        "hands_on_ribbons": "|".join(hands_on),
    }


# ---------------------------------------------------------------------------
# Async fetching
# ---------------------------------------------------------------------------
async def fetch_page(
    session: AsyncSession,
    sem: asyncio.Semaphore,
    page: int,
    request_headers: dict,
) -> dict | None:
    """Fetch a single page with retries. Returns parsed JSON or None on failure."""
    async with sem:
        payload = build_payload(page)
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                resp = await session.post(
                    API_URL, json=payload, headers=request_headers, timeout=30
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt * 5
                    logger.warning(f"Page {page}: rate-limited, retrying in {wait}s…")
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (403, 503):
                    logger.error(
                        f"Page {page}: HTTP {resp.status_code} — Cloudflare blocking. "
                        "Update cookies.json with fresh browser cookies and retry."
                    )
                    return None
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                logger.warning(f"Page {page}: {exc} (attempt {attempt}/{RETRY_ATTEMPTS})")
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(2 ** attempt)
        logger.error(f"Page {page}: gave up after {RETRY_ATTEMPTS} attempts")
        return None


def extract_course_search(response: dict) -> dict:
    """Pull the courseSearch node from a GraphQL response."""
    return (response.get("data") or {}).get("courseSearch") or {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    cookies = load_cookies()

    sem = asyncio.Semaphore(CONCURRENCY)

    # Add CSRF token to headers when available
    request_headers = dict(HEADERS)
    if "csrftoken" in cookies:
        request_headers["x-csrftoken"] = cookies["csrftoken"]

    # chrome142 is the closest available fingerprint to Chrome 145
    async with AsyncSession(impersonate="chrome142", cookies=cookies) as session:

        # --- Page 1: discover total pages ---
        logger.info("Fetching page 1 to discover total page count…")
        first_resp = await fetch_page(session, sem, 1, request_headers)
        if first_resp is None:
            logger.error("Cannot continue without a valid first page.")
            sys.exit(1)

        cs = extract_course_search(first_resp)
        total_count = cs.get("count", 0)
        page_count = cs.get("pageCount", 1)
        first_results = cs.get("results") or []

        logger.info(f"Total courses: {total_count:,}  |  Pages: {page_count}")

        saved = 0
        failed_pages = []

        with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()

            # Write page 1
            for result in first_results:
                writer.writerow(flatten_result(result))
            saved += len(first_results)
            logger.info(f"Page  1/{page_count}: {len(first_results)} courses  (total saved: {saved:,})")

            if page_count <= 1:
                logger.info("Only one page — done.")
            else:
                # Schedule remaining pages; process in batches to keep memory low
                remaining = list(range(2, page_count + 1))
                batch_size = CONCURRENCY * 4  # fetch up to this many at once

                for batch_start in range(0, len(remaining), batch_size):
                    batch = remaining[batch_start : batch_start + batch_size]
                    tasks = [fetch_page(session, sem, p, request_headers) for p in batch]

                    responses = await asyncio.gather(*tasks)

                    for page_num, resp_data in zip(batch, responses):
                        if resp_data is None:
                            failed_pages.append(page_num)
                            continue
                        page_cs = extract_course_search(resp_data)
                        results = page_cs.get("results") or []
                        for result in results:
                            writer.writerow(flatten_result(result))
                        saved += len(results)
                        logger.info(
                            f"Page {page_num:>4}/{page_count}: {len(results):>2} courses"
                            f"  (total saved: {saved:,})"
                        )

                    # Polite pause between batches
                    await asyncio.sleep(0.5)

    logger.info(f"\nFinished — {saved:,} courses written to {OUTPUT_PATH}")
    if failed_pages:
        logger.warning(f"Failed pages (not saved): {failed_pages}")


if __name__ == "__main__":
    asyncio.run(main())
