# Data Dictionary — `data/udemy.csv`

UTF-8 encoded CSV with a header row. One row per unique course, deduplicated by `id`.

---

## Columns

### `id`
- **Type:** integer
- **Source:** `courseSearch.results[].course.id`
- **Description:** Udemy's internal unique course identifier. Used as the deduplication key during scraping.
- **Example:** `5776686`

---

### `title`
- **Type:** string
- **Source:** `course.title`
- **Description:** Full display title of the course as shown on Udemy.
- **Example:** `"Learn Basics of Python Scripting for Server Side Automation"`

---

### `headline`
- **Type:** string
- **Source:** `course.headline`
- **Description:** Short marketing subtitle shown beneath the title in search results. Usually one sentence.
- **Example:** `"Learn How to Automate Repetitive Tasks with Python Scripting"`

---

### `level`
- **Type:** string enum
- **Source:** `course.level`
- **Values:**

  | Value | Meaning |
  |---|---|
  | `BEGINNER` | No prior knowledge assumed |
  | `INTERMEDIATE` | Some experience required |
  | `EXPERT` | Advanced audience |
  | `ALL_LEVELS` | Course is accessible regardless of experience |

---

### `locale`
- **Type:** string (IETF language tag)
- **Source:** `course.locale`
- **Description:** Language and optional region of the course content.
- **Examples:** `en-US`, `es-ES`, `pt-BR`, `tr-TR`, `ar-SA`, `zh-CN`

---

### `rating_average`
- **Type:** float (0.0 – 5.0)
- **Source:** `course.rating.average`
- **Description:** Weighted average star rating. Udemy uses a Bayesian-adjusted score that blends raw ratings with a prior, so new courses with few reviews appear closer to 3.5 than to their raw score.
- **Example:** `4.486754417419434`
- **Note:** May be `None` for courses with no reviews yet.

---

### `rating_count`
- **Type:** integer
- **Source:** `course.rating.count`
- **Description:** Total number of ratings submitted. Distinct from the number of reviews (text comments).
- **Example:** `64`

---

### `duration_seconds`
- **Type:** integer
- **Source:** `course.durationInSeconds`
- **Description:** Total video content duration in seconds. Does not include quizzes, assignments, or coding exercises.
- **Example:** `62338`  (≈ 17 hours 18 minutes)
- **Conversion:** `duration_seconds / 3600` → hours

---

### `is_free`
- **Type:** boolean (`True` / `False`)
- **Source:** `course.isFree`
- **Description:** Whether the course is permanently free (not a paid course that happens to be discounted to $0).

---

### `is_practice_test_course`
- **Type:** boolean (`True` / `False`)
- **Source:** `course.isPracticeTestCourse`
- **Description:** Whether the course is primarily a practice test (exam simulation) rather than a lecture-based course.

---

### `instructors`
- **Type:** string (pipe-separated list)
- **Source:** `course.instructors[].name`
- **Description:** Names of all instructors for the course. Multiple instructors are joined with `|`.
- **Examples:**
  - `"Jose Portilla"` — single instructor
  - `"Angela Yu|David Lowe"` — co-instructed course

---

### `lectures_count`
- **Type:** integer
- **Source:** `course.curriculum.contentCounts.lecturesCount`
- **Description:** Number of video lecture items in the curriculum. Does not count quizzes, articles, or coding exercises.
- **Example:** `142`

---

### `practice_test_questions_count`
- **Type:** integer
- **Source:** `course.curriculum.contentCounts.practiceTestQuestionsCount`
- **Description:** Total number of questions across all practice tests in the course. `0` or empty for courses without practice tests.
- **Example:** `300`

---

### `badges`
- **Type:** string (pipe-separated list)
- **Source:** `course.badges[].name`
- **Description:** Special labels Udemy assigns to notable courses. Multiple badges are joined with `|`.
- **Common values:**

  | Badge | Meaning |
  |---|---|
  | `Bestseller` | Top seller in its category |
  | `Hot & New` | Recently published with fast-growing enrollment |
  | `Highest Rated` | Top-rated in its category |
  | `Updated recently` | Major content update within the past few months |

- **Example:** `"Bestseller"` or `"Hot & New|Highest Rated"`

---

### `updated_on`
- **Type:** string (ISO 8601 date)
- **Source:** `course.updatedOn`
- **Description:** Date of the most recent content update published by the instructor. Format: `YYYY-MM-DD`.
- **Example:** `"2025-11-15"`

---

### `url_course_landing`
- **Type:** string (relative URL path)
- **Source:** `course.urlCourseLanding`
- **Description:** Path to the course landing/sales page. Prepend `https://www.udemy.com` to get the full URL.
- **Example:** `"/course/python-scripting-server-automation/"` → `https://www.udemy.com/course/python-scripting-server-automation/`

---

### `url_course_taking`
- **Type:** string (relative URL path)
- **Source:** `course.urlCourseTaking`
- **Description:** Path to the course player. Only accessible to enrolled users.
- **Example:** `"/course/5776686/learn/"`

---

### `image_240x135`
- **Type:** string (absolute HTTPS URL)
- **Source:** `course.images.px240x135`
- **Description:** Thumbnail image at 240×135 pixels (16:9). Hosted on Udemy's CDN.
- **Example:** `"https://img-c.udemycdn.com/course/240x135/5776686_abc1.jpg"`

---

### `tracking_id`
- **Type:** string (UUID)
- **Source:** `searchResult.trackingId`
- **Description:** Opaque identifier Udemy uses for click-tracking in search results. Not a stable course attribute — changes between requests.
- **Example:** `"3a7f9b2e-1c4d-4e8a-9f1b-0c2d3e4f5a6b"`

---

### `hands_on_ribbons`
- **Type:** string (pipe-separated list)
- **Source:** `searchResult.handsOnRibbons`
- **Description:** Labels indicating interactive content types within the course. Multiple values joined with `|`.
- **Common values:** `Coding Exercises`, `Practice Tests`, `Quizzes`, `Projects`
- **Example:** `"Coding Exercises|Quizzes"`

---

## Usage notes

### Derived columns you may want to add

```python
import pandas as pd

df = pd.read_csv("data/udemy.csv")

# Full landing page URL
df["url"] = "https://www.udemy.com" + df["url_course_landing"]

# Duration in hours
df["duration_hours"] = df["duration_seconds"] / 3600

# Instructor count
df["instructor_count"] = df["instructors"].str.count(r"\|") + 1

# Has a bestseller badge
df["is_bestseller"] = df["badges"].str.contains("Bestseller", na=False)

# Primary language
df["language"] = df["locale"].str.split("-").str[0]
```

### Pipe-separated fields

`instructors`, `badges`, and `hands_on_ribbons` use `|` as a delimiter because course titles and instructor names can contain commas. To explode into rows in pandas:

```python
df["instructor_list"] = df["instructors"].str.split("|")
df_exploded = df.explode("instructor_list")
```

### Missing values

| Column | When empty/None |
|---|---|
| `rating_average` | Course has no ratings yet |
| `rating_count` | Course has no ratings yet |
| `badges` | Course has no special badge |
| `hands_on_ribbons` | No interactive elements |
| `practice_test_questions_count` | Course has no practice tests |
| `headline` | Rare; some older courses lack a subtitle |
