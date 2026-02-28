# Architecture

## Overview

The scraper queries Udemy's internal GraphQL API (`/api/2024-01/graphql/`) using the same requests the browser makes on the search results page. It bypasses Cloudflare by replaying Chrome's exact TLS and HTTP/2 fingerprint via `curl_cffi`.

---

## Why the API is hard to use directly

### Cloudflare bot protection

Udemy sits behind Cloudflare. Every request is evaluated against:

| Signal | What Cloudflare checks |
|---|---|
| **TLS fingerprint** (JA3/JA4) | Does the TLS handshake look like Chrome's? |
| **HTTP/2 fingerprint** | Do the SETTINGS/HEADERS frames match Chrome's? |
| **`cf_clearance` cookie** | Was a JS challenge solved from this IP? |
| **`__cf_bm` cookie** | Bot Management token (refreshed every ~30 min) |

Standard Python HTTP libraries (`requests`, `aiohttp`, `httpx`) all fail the TLS fingerprint check and receive HTTP 403 regardless of cookies. `curl_cffi` solves this by wrapping `curl-impersonate`, which replays Chrome 142's exact handshake.

### Search result cap

The GraphQL `courseSearch` query uses Elasticsearch under the hood. Elasticsearch's default `max_result_window` is 10,000. Udemy exposes this as `pageCount` × `pageSize` max = 417 pages × 24 = 10,008.

A wildcard `query: "*"` is interpreted by Elasticsearch's search-as-you-type field and returns only ~750 documents (an index-level cap on wildcard results). Real keyword queries return the full 10,000.

---

## Keyword sweep strategy

Since no single query covers all courses, the scraper iterates 183 curated topic keywords:

```
python scripts/udemy.py
  └─ for each keyword in KEYWORDS (183 total):
       1. POST /api/2024-01/graphql/  page=1  →  get count + pageCount
       2. POST /api/2024-01/graphql/  pages 2..pageCount  (batched, 5 concurrent)
       3. Deduplicate by course.id against in-memory set
       4. Write new rows to data/udemy.csv
       5. Mark keyword done in data/progress.json
```

**Deduplication:** A `set[int]` of seen course IDs is maintained in memory for the entire run. A course is written to CSV exactly once, even if it appears in 10 different keyword searches.

**Coverage:** The 183 keywords span every major Udemy category. For the largest topics (python, javascript, java) the API cap of 10,000 is reached, meaning some courses in those topics are not captured. For medium and small topics, all courses are collected.

---

## Async execution model

```
asyncio event loop
  │
  ├─ AsyncSession (curl_cffi)   ← one HTTP/2 connection, Chrome fingerprint
  │
  ├─ Semaphore(5)               ← max 5 concurrent in-flight requests
  │
  └─ for each keyword:
       gather(batch of 20 pages)   → 5 fly simultaneously
       write new rows
       asyncio.sleep(0.3)          → polite pause between batches
```

`asyncio.gather` is used per batch (not per keyword) so that pages for a single keyword are fetched concurrently but progress is saved and rows are flushed after each batch.

---

## GraphQL query

The scraper uses Udemy's `SrpMxCourseSearch` query — the same one the search results page (`/courses/search/`) sends:

```graphql
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
        curriculum { contentCounts { lecturesCount practiceTestQuestionsCount } }
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
```

Variables sent per request:

```json
{
  "page": 1,
  "query": "python",
  "sortOrder": "RELEVANCE",
  "pageSize": 24,
  "context": { "triggerType": "USER_QUERY" }
}
```

---

## Request headers

The following headers are sent with every request to match what Chrome sends:

```
accept: */*
accept-language: en-GB,en-US;q=0.9,en;q=0.8
content-type: application/json
dnt: 1
origin: https://www.udemy.com
referer: https://www.udemy.com/courses/search/?q=*&src=ukw
sec-ch-ua: "Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: same-origin
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...Chrome/145.0.0.0...
x-csrftoken: <value of csrftoken cookie>
```

---

## Error handling

| HTTP status | Action |
|---|---|
| `200` | Parse JSON, extract results |
| `429` | Exponential backoff: `2^attempt × 5` seconds, then retry |
| `403` | Log error "refresh cookies", return `None` (skip page) |
| `503` | Same as 403 |
| Network timeout | Retry up to `RETRY_ATTEMPTS` times with exponential backoff |
| All retries failed | Log error, skip page, continue with next |

---

## Progress and resume

After each keyword completes, its name is appended to `data/progress.json`:

```json
{
  "done": ["c#", "c++", "golang", "java", "javascript", "python"]
}
```

Running with `--resume` loads this file and skips completed keywords. The CSV is opened in append mode so existing rows are preserved.

**Note:** Resume does not reload already-seen IDs from the CSV, so if a keyword was partially completed before a crash, its pages are re-fetched and duplicates are handled by Elasticsearch returning the same courses — they will simply be skipped by the in-memory deduplication set (which starts empty on resume). The only side effect is some wasted API calls for the in-progress keyword at time of crash.

---

## Data flow

```
Udemy GraphQL API
      │
      │  JSON (gzip/br compressed)
      ▼
curl_cffi AsyncSession
      │
      │  resp.json()  →  dict
      ▼
extract_cs()          →  courseSearch node
      │
      │  for each result
      ▼
flatten_result()      →  20-column dict
      │
      │  if course.id not in seen_ids
      ▼
csv.DictWriter        →  data/udemy.csv  (UTF-8, streamed)
```
