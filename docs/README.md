# Udemy Course Catalog Scraper

Collects the full Udemy course catalog via the internal GraphQL API and saves it to a flat CSV file for market research and analysis.

**Expected output:** 100,000–200,000 unique courses across all categories.

---

## Quick Start

### 1. Install dependency

```bash
pip install curl_cffi
```

### 2. Get browser cookies

> The API requires Cloudflare-validated browser cookies. See [cookies.md](cookies.md) for the full guide.

**Short version:**
1. Open Chrome → go to `udemy.com/courses/search/?q=*`
2. DevTools → Network → click any `graphql` POST request → Headers
3. Copy the full value of the `cookie:` request header
4. Paste it into `cookies.json` at the project root (the raw string is accepted)

### 3. Run

```bash
python ../scripts/udemy.py
```

Output streams live to `../data/udemy.csv`. If interrupted, resume without losing progress:

```bash
python ../scripts/udemy.py --resume
```

### 4. Monitor

```bash
# Live log
tail -f ../data/scrape.log

# Row count
wc -l ../data/udemy.csv

# Keywords completed
cat ../data/progress.json
```

---

## How it works

Udemy's search API caps results at **10,000 per query** (416 pages × 24 courses). A single wildcard `*` query only returns ~750 results.

This scraper uses a **keyword sweep**: it queries 183 topic keywords spanning every Udemy category (Python, photography, guitar, yoga, …), collects up to 10,000 results per keyword, and deduplicates everything by course ID in memory. This covers the vast majority of the catalog.

See [architecture.md](architecture.md) for the full technical design.

---

## Output

| File | Description |
|---|---|
| `../data/udemy.csv` | Main output — one row per unique course |
| `../data/progress.json` | Completed keyword list (used by `--resume`) |
| `../data/scrape.log` | Timestamped log of the current/last run |

Column reference: [data_dictionary.md](data_dictionary.md)

---

## Project layout

```
udemy_com/
├── scripts/
│   └── udemy.py          # scraper
├── data/
│   ├── udemy.csv         # output dataset
│   ├── progress.json     # resume checkpoint
│   └── scrape.log        # run log
├── docs/
│   ├── README.md         # this file
│   ├── architecture.md   # technical design
│   ├── cookies.md        # cookie guide
│   ├── data_dictionary.md
│   └── keywords.md       # keyword list rationale
└── cookies.json          # browser cookies (gitignored)
```

---

## Runtime estimates

| Cookies | ~90 sec/keyword | 183 keywords | Total |
|---|---|---|---|
| Fresh (< 30 min old) | ~90 s | 183 | ~4–5 hours |

The bottleneck is polite rate limiting (`BATCH_PAUSE = 0.3 s`). Increasing `CONCURRENCY` from 5 to 10 cuts runtime roughly in half at the cost of higher ban risk.

---

## Configuration

All tuneable constants are at the top of `../scripts/udemy.py`:

| Constant | Default | Effect |
|---|---|---|
| `CONCURRENCY` | `5` | Simultaneous in-flight requests |
| `BATCH_PAUSE` | `0.3` | Seconds between page batches |
| `RETRY_ATTEMPTS` | `3` | Retries per page on network error |
| `PAGE_SIZE` | `24` | Results per API page (max allowed) |

---

## Limitations

- Cookies expire (~30 min for `__cf_bm`). Refresh if you see HTTP 403 errors.
- The API caps results at 10,000 per keyword query. Very large topics (python, javascript) hit this cap, so some courses in those topics may not appear.
- Coverage depends on the keyword list. Niche categories not in the keyword list will be missed. Add keywords to `KEYWORDS` in `../scripts/udemy.py` to extend coverage.
