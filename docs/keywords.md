# Keyword Strategy

## Why keywords instead of a wildcard

Udemy's search API (`courseSearch`) uses Elasticsearch. A `query: "*"` wildcard hits a different code path from a keyword search and Udemy caps it at **~750 results**. Named keyword queries return up to **10,000 results** (Elasticsearch's `max_result_window`).

The scraper sweeps 183 topic keywords, collecting up to 10,000 courses per keyword and deduplicating by course ID. This is the only reliable way to approach full-catalog coverage through the search API.

---

## Deduplication and overlap

Many courses appear in multiple keyword searches (a React course appears under "react", "javascript", and "web development"). The scraper maintains a `set[int]` of seen course IDs for the entire run. A course is written to CSV exactly once regardless of how many keywords surface it.

Expected deduplication rate increases over the run:
- First keyword (python): ~95% of results are new
- After 10 keywords: ~50–70% of results are new
- After 50 keywords: ~20–40% new
- After 183 keywords: ~5–15% new per keyword

---

## Coverage gaps

The 10,000 result cap means the scraper **does not** get every course in very large categories. For "python" (10,000+ courses), Udemy's relevance ranking determines which 10,000 are returned. Less popular or newer Python courses may not appear.

To capture more of a specific category, you can add more specific sub-keywords:

```python
# In scripts/udemy.py, add to KEYWORDS:
"pandas tutorial", "numpy", "scikit-learn", "matplotlib",
"python for beginners", "python automation", "python web development"
```

---

## Keyword list (183 total)

### Programming Languages (19)
```
python, javascript, java, c++, c#, golang, ruby, php, swift, kotlin, rust,
typescript, scala, r programming, perl, bash scripting, powershell,
assembly language, lua
```

### Web Development (16)
```
react, angular, vue, nodejs, html css, wordpress, django, flask, laravel,
spring boot, nextjs, nuxtjs, graphql, rest api, microservices, web scraping
```

### Data & AI (15)
```
machine learning, deep learning, data science, tensorflow, pytorch,
natural language processing, computer vision, data analysis, tableau,
power bi, data engineering, apache spark, hadoop, airflow, mlops
```

### Cloud & DevOps (12)
```
aws, azure, google cloud, docker, kubernetes, devops, terraform, ansible,
jenkins, linux administration, networking, cloud computing
```

### Database (9)
```
sql, mysql, postgresql, mongodb, redis, elasticsearch, oracle database,
sqlite, cassandra
```

### Mobile (6)
```
android development, ios development, flutter, react native, xamarin, ionic
```

### Game Development (5)
```
unity, unreal engine, game development, godot, blender
```

### Cybersecurity (6)
```
ethical hacking, cybersecurity, penetration testing, network security,
cryptography, soc analyst
```

### Business & Management (10)
```
project management, agile, scrum, pmp certification, leadership,
business analysis, six sigma, lean management, supply chain,
operations management
```

### Marketing (9)
```
digital marketing, seo, social media marketing, google ads, facebook ads,
email marketing, content marketing, affiliate marketing, copywriting
```

### Finance & Accounting (10)
```
accounting, excel, financial modeling, investing, cryptocurrency,
stock trading, forex trading, bookkeeping, quickbooks, cfa exam
```

### Office Productivity (7)
```
microsoft office, powerpoint, word, google workspace, notion, monday, jira
```

### Design (10)
```
photoshop, illustrator, figma, graphic design, ui ux design,
motion graphics, after effects, canva, indesign, 3d modeling
```

### Photography & Video (8)
```
photography, lightroom, video editing, premiere pro, final cut pro,
youtube, filmmaking, color grading
```

### Music (8)
```
guitar, piano, music production, music theory, mixing mastering,
ableton, fl studio, singing
```

### Personal Development (6)
```
public speaking, time management, productivity, critical thinking,
mindfulness, nlp coaching
```

### Health & Fitness (6)
```
yoga, meditation, fitness training, nutrition, weight loss, mental health
```

### Lifestyle (7)
```
cooking, drawing, watercolor painting, calligraphy, knitting,
interior design, astrology
```

### Language Learning (8)
```
english grammar, spanish, french, german, japanese, chinese mandarin,
arabic language, ielts
```

### Teaching & Academics (6)
```
online teaching, curriculum design, mathematics, statistics, physics,
chemistry
```

---

## Adding keywords

Edit `KEYWORDS` in `scripts/udemy.py`. Each keyword is an independent search — adding more keywords extends coverage but also extends runtime (~90 seconds per keyword).

Best practices for new keywords:
- **Be specific.** `"fastapi"` captures more relevant courses than `"api"`.
- **Avoid duplicates.** If "react" is already in the list, adding "reactjs" will capture mostly the same courses.
- **Check the count first.** Run a quick probe before committing to a full sweep:

```bash
python - << 'EOF'
import json, asyncio
from curl_cffi.requests import AsyncSession

cookies = json.loads(open("cookies.json").read())
HEADERS = {"accept": "*/*", "content-type": "application/json",
           "origin": "https://www.udemy.com",
           "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
           "x-csrftoken": cookies.get("csrftoken", "")}
Q = 'query S($q:String!,$p:NonNegativeInt!,$ps:MaxResultsPerPage!,$c:CourseSearchContext!){courseSearch(query:$q,page:$p,pageSize:$ps,context:$c){count pageCount}}'

async def main():
    async with AsyncSession(impersonate="chrome142", cookies=cookies) as s:
        for kw in ["fastapi", "streamlit", "langchain"]:
            r = await s.post("https://www.udemy.com/api/2024-01/graphql/",
                json={"query": Q, "variables": {"p": 1, "q": kw, "ps": 1,
                      "c": {"triggerType": "USER_QUERY"}}},
                headers=HEADERS, timeout=30)
            d = r.json()["data"]["courseSearch"]
            print(f"{kw:20s}: {d['count']:6,} courses ({d['pageCount']} pages)")

asyncio.run(main())
EOF
```

---

## Sorting and result diversity

The scraper uses `sortOrder: "RELEVANCE"` for all queries, which is Udemy's default. This means:
- Higher-rated, better-selling courses appear on earlier pages
- For capped topics (10,000 result limit), lower-quality or very new courses on later pages of a topic may be missed

To improve coverage of newer or niche courses, you could also sweep with `sortOrder: "NEWEST"` for the same keyword list. This would approximately double the runtime but significantly improve recency coverage.
