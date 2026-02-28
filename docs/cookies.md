# Cookies Guide

Udemy's API is protected by Cloudflare. The scraper needs browser-issued cookies to pass the challenge. This document explains why, which cookies matter, and how to get and refresh them.

---

## Why cookies are required

Cloudflare issues a `cf_clearance` cookie after your browser completes a JavaScript challenge. This token is tied to your **IP address** and your browser's **TLS fingerprint**. The scraper uses `curl_cffi` to replicate Chrome's exact TLS/HTTP2 fingerprint, so as long as the cookies come from Chrome on the same machine, requests pass through.

Without valid cookies the API returns **HTTP 403**.

---

## Key cookies

| Cookie | Lifetime | Purpose |
|---|---|---|
| `cf_clearance` | ~1–24 hours | Cloudflare JS challenge clearance |
| `__cf_bm` | ~30 minutes | Cloudflare Bot Management token |
| `__cfruid` | session | Cloudflare routing |
| `csrftoken` | session/days | Django CSRF protection (sent as `x-csrftoken` header) |
| `__udmy_2_v57r` | 1 year | Udemy visitor ID |
| `dj_session_id` | session | Django session (only present when logged in) |

The scraper works both **logged-in and logged-out**. Logged-in sessions have richer cookies but are not required.

---

## How to get cookies

### Method 1 — Chrome DevTools (recommended)

1. Open **Google Chrome**
2. Go to `https://www.udemy.com/courses/search/?q=python`
3. Open DevTools: `F12` or `Ctrl+Shift+I`
4. Click the **Network** tab
5. In the filter box type `graphql` and press Enter
6. Click any POST request in the list
7. In the right panel click **Headers**
8. Scroll to **Request Headers** → find the `cookie:` row
9. Click the value field and select all (`Ctrl+A`) → copy

### Method 2 — Copy as cURL

1. Follow steps 1–6 above
2. Right-click the request → **Copy** → **Copy as cURL (bash)**
3. The cURL command contains `-H 'cookie: ...'` — extract that value

---

## Where to put cookies

### Option A — `cookies.json` (recommended)

The scraper auto-loads `cookies.json` from the project root. It accepts:

**Raw cookie string** (simplest — paste directly from DevTools):
```json
{
  "raw_cookie_string": "__udmy_2_v57r=fa4399...; csrftoken=jSWRep9...; cf_clearance=IVE..."
}
```

**Parsed JSON dict** (more explicit):
```json
{
  "cf_clearance": "IVEPYYFwT73EYcxCWAfyrg...",
  "__cf_bm": "5nnNyEDyVnbc...",
  "__cfruid": "b9008e70842554ce...",
  "csrftoken": "jSWRep9rTpNe7qvf...",
  "__udmy_2_v57r": "fa4399d1941d4c15..."
}
```

The load order is:
1. If `cookies.json` has a `"raw_cookie_string"` key → parsed as cookie string
2. If `cookies.json` is a dict without that key → used directly as cookie dict
3. Falls back to `UDEMY_COOKIES` environment variable

### Option B — environment variable

Set `UDEMY_COOKIES` to either format before running:

```bash
# Raw string
export UDEMY_COOKIES="__udmy_2_v57r=fa4399...; csrftoken=jSWRep9...; cf_clearance=..."
python scripts/udemy.py

# JSON dict
export UDEMY_COOKIES='{"cf_clearance":"IVE...","csrftoken":"jSWR..."}'
python scripts/udemy.py
```

---

## Refreshing cookies

The `__cf_bm` cookie expires after **~30 minutes**. When you see repeated HTTP 403 errors in the log:

```
ERROR    [python] p42: HTTP 403 — refresh cookies.json
```

Do the following:
1. Open Chrome → go to `udemy.com` (stay on the same network/IP)
2. Repeat the DevTools steps above to copy a fresh cookie string
3. Replace the contents of `cookies.json`
4. Re-run with `--resume` — completed keywords are skipped automatically

```bash
python scripts/udemy.py --resume
```

---

## Security notes

- `cookies.json` is listed in `.gitignore` — **never commit it to version control**
- The cookies represent your browser session. Anyone with them can impersonate you on Udemy for ~30 minutes
- The JWT token (`ud_user_jwt`) and `access_token` in the cookies are sensitive if you are logged in — treat the file like a password
- After a scraping run, the cookies will naturally expire

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 403 on every request | Expired `__cf_bm` or wrong IP | Refresh cookies from Chrome on same machine |
| HTTP 403 only on some pages | Intermittent Cloudflare challenge | Refresh cookies; lower `CONCURRENCY` |
| `cf_clearance` valid but still 403 | TLS fingerprint mismatch | Ensure `curl_cffi` is installed and `impersonate="chrome142"` is set |
| Script loads 0 cookies | `cookies.json` malformed | Validate JSON at jsonlint.com |
| `UDEMY_COOKIES` ignored | `cookies.json` exists and takes priority | Delete or update `cookies.json` |
