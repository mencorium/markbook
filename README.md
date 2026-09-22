<!-- /markbook_desktop/README.md -->
# Markbook Desktop

Student progress analysis for teachers and tutors: PyQt6 desktop app with a PostgreSQL database.

It covers subjects, students (with phone numbers), tests and exams, per-question marking with topics and choice sections, attendance, NECTA A-Level / O-Level grading and divisions, predictions and targets, topic and question analysis, class results, full report cards (PDF), Excel/CSV import and export.

## 1. Set up PostgreSQL

Install PostgreSQL 14+ and create a user and database:

```sql
CREATE USER markbook WITH PASSWORD 'markbook';
CREATE DATABASE markbook OWNER markbook;
-- only needed for running the tests:
CREATE DATABASE markbook_test OWNER markbook;
```

## 2. Install and configure

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then edit DATABASE_URL if your user/password differ
```

## 3. Run

```bash
python -m backend.seed             # optional: add the sample class
python main.py                     # tables are created automatically on first start
```

Remove the sample data at any time with `python -m backend.seed --remove` or from **Settings → Remove sample data**.

## 4. Tests

```bash
pytest -q                          # uses markbook_test (override with TEST_DATABASE_URL)
```

The tests cover grading, divisions, choice-section totals, phone normalisation, the full flow (sample data → analytics → Excel export → import round trip → comments → three PDFs), paper editing, moving a student between classes, attendance, and an offscreen run through every screen.

## Project structure

```
markbook_desktop/
├── main.py                    Entry point
├── backend/                   No Qt imports: can sit behind a REST API later
│   ├── config.py              .env settings (DATABASE_URL, DEFAULT_COUNTRY_CODE)
│   ├── db.py                  Engine, session_scope(), create_schema()
│   ├── models.py              SQLAlchemy tables
│   ├── schemas.py             Plain dataclasses handed to the UI
│   ├── grading.py             NECTA presets, custom scales, points, divisions, remarks
│   ├── paper.py               Paper total / maximum with "answer any N" sections
│   ├── phone.py               Phone normalisation to E.164 (+255…)
│   ├── seed.py                Sample class
│   └── services/
│       ├── records.py         Settings, classes, subjects, students (CRUD + validation)
│       ├── assessments.py     Assessments, question papers, marks
│       ├── attendance.py      Daily registers
│       ├── analytics.py       Gradebook: every calculation (results, ranking, predictions, topic/question analysis)
│       ├── comments.py        Suggested class-teacher comments from real results
│       ├── exports.py         Excel (styled) and CSV sheets
│       ├── imports.py         Read and match Excel/CSV class lists and mark sheets
│       ├── charts.py          Matplotlib charts shared by screens and PDFs
│       └── reports.py         ReportLab PDFs: report cards, result sheet, exam analysis
├── frontend/
│   ├── main_window.py         Sidebar, page stack, shared state
│   ├── theme.py               Colours and Qt stylesheet
│   ├── widgets.py             Page scaffold, tables, chart canvas, helpers
│   ├── dialogs.py             Student (with phone), subject, assessment, scale dialogs
│   └── pages/                 One module per screen
└── tests/
```

The frontend never opens a database session. It calls `backend.services` and reads a `Gradebook` snapshot, then reloads it after each save.

## Phone numbers (for message automation later)

- Entered on the student dialog, the "Add many" box (`Name, RegNo, Phone`), or a **Phone** column when importing.
- Stored normalised in E.164 form in `students.phone` (indexed), e.g. `0712 345 678` → `+255712345678`. Tanzanian numbers are checked as valid mobiles (06/07).
- `DEFAULT_COUNTRY_CODE` in `.env` controls how local numbers are expanded.
- **Import & export → Class list with phones** exports them.

A messaging module can read `Student.phone` directly. For example, it could send each parent a results summary built from `Gradebook.summary()` and `comments.auto_comment()` through an SMS gateway or the WhatsApp Business API.

## How results are calculated

- **Final mark per subject** = test average × CA weight + exam average × (1 − CA weight). The CA weight is set in Settings; the default is 40%. With no exam yet, the final mark is the test average (marked *provisional*).
- **A-Level division**: best 3 principal subjects; subsidiary subjects are excluded. **O-Level**: best 7 subjects.
- **Ranking**: students with a complete division come first, ordered by points and then average. The rest follow by average.
- **Per-question papers**: a blank compulsory question counts as 0. In "answer any N" sections only the best N answers count.