<!-- /markbook/README.md -->
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
python main.py                     # the schema is created or migrated automatically on start
```

### First steps in the app

1. **Students → Add class** (or Settings → Classes & grading → Add class): name it and choose A-Level, O-Level or a custom scale.
2. **Students → Add student** or **Add many** to fill the class list. You can also type a new class name straight into the student dialog, or let a class be created by an import.
3. **Subjects → Add subject**, marking General Studies and similar as subsidiary.
4. **Tests & exams → New assessment**, then enter marks.

Remove the sample data at any time with `python -m backend.seed --remove` or from **Settings → Remove sample data**.

## 4. Keeping your marks safe

**Backups.** Settings → Backups: back up now, choose the folder, or restore an earlier backup.
Markbook also backs up once a day when you close it (switchable). Each backup is one compressed
`.dump` file holding everything; the newest 20 are kept. Restoring first takes a `before-restore`
backup of the current data, so even a mistaken restore is recoverable. This needs `pg_dump` and `pg_restore`, which come with PostgreSQL. Markbook looks on PATH and in
the usual install folders (including the Windows registry and every drive). If they still aren't
found — common on Windows — press **Locate PostgreSQL tools…** in Settings → Backups and choose
the `bin` folder of your PostgreSQL installation, e.g. `C:\Program Files\PostgreSQL\16\bin`.
`MARKBOOK_PG_BIN` overrides both.

**Autosave.** Marks typed into the grid are autosaved to a draft file a moment after you stop
typing. If the app closes, the laptop dies or the power goes out, the next time you open that
assessment the marks are back in the grid with a notice; press Save marks to keep them, or
discard them. The draft is deleted once the marks reach the database.

**Archive instead of delete.** Removing a student or subject archives it: it leaves class lists,
results, report cards and exports, but every mark and attendance record is kept. Tick **Show
archived** on the Students or Subjects page to see what is archived, restore it, or delete it for
good. Archiving a subject hides its assessments too. Deleting for good is the only irreversible
action in the app.

**Logs.** Problems are written to a rotating log (`logs/markbook.log` in the app folder, path
shown in Settings). Send that file along when reporting a bug.

**Schema migrations.** The database schema is versioned with Alembic. `python main.py` runs any
pending migration on start, so upgrading Markbook never means rebuilding your data by hand. A
database created before migrations existed is stamped at the baseline and then upgraded, keeping
its data.

```bash
alembic upgrade head                        # apply migrations manually
alembic revision --autogenerate -m "note"   # after changing backend/models.py
alembic current                             # which revision this database is at
```

Files outside the database (logs, drafts, backups) live in `~/.markbook` (`%LOCALAPPDATA%\Markbook`
on Windows). Set `MARKBOOK_HOME` to put them elsewhere.

## 5. Tests

```bash
pytest -q                          # uses markbook_test (override with TEST_DATABASE_URL)
```

The tests cover grading, divisions, choice-section totals, phone normalisation, the full flow (sample data → analytics → Excel export → import round trip → comments → three PDFs), paper editing, moving a student between classes, attendance, and an offscreen run through every screen.

## Project structure

```
markbook_desktop/
├── main.py                    Entry point
├── alembic.ini, migrations/   Schema versions (Alembic)
├── backend/                   No Qt imports: can sit behind a REST API later
│   ├── config.py              .env settings (DATABASE_URL, DEFAULT_COUNTRY_CODE)
│   ├── db.py                  Engine, session_scope(), create_schema()
│   ├── migrate.py             Runs pending migrations at startup
│   ├── log.py                 Rotating log file
│   ├── paths.py               Where logs, drafts and backups are kept
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
│       ├── backup.py          pg_dump / pg_restore backups
│       ├── drafts.py          Autosaved mark entry
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