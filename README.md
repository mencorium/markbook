<!-- /markbook/README.md -->
# Markbook

**Student progress analysis for teachers** — a PyQt6 desktop app with a PostgreSQL database.

Made by **Mencorium** · https://github.com/mencorium/markbook

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

### Terms and academic years

A term is whatever period you teach in — two six-month terms, three shorter ones, or a short
course. Set them up in **Settings → Terms & academic years**, then switch term with the picker at
the top left ("All terms" shows everything together). Marks and registers belong to the term their
date falls in, so each term has its own averages, positions and divisions and last term stops
dragging on this one.

Each class has a rule for the end of the year — students move up, the class carries on, or a short
course finishes. **Start the next term…** creates the term and applies those rules in one step:
promoted students move to the next class while the marks they already have stay with the old class
and term, and a finished course archives its students.

Upgrading an existing database puts everything already recorded into one term named after your old
Term setting, so nothing is lost.

**One subject at a time.** Double-click a subject (or select it and press Open results) to see, for
the chosen class and term: every test and exam in that subject with its mean, highest, lowest and
pass rate; the class average across them; the spread of final grades; and a cumulative table with a
column per assessment, then tests %, exams %, final %, grade, position and trend for each student.
Double-click an assessment to enter marks, or a student to open their profile. Export takes the
same table to Excel.

**Timetable and attendance.** Set each class's weekly lessons under **Timetable** — subject, day,
start and end time, room. A timetable belongs to a term and can be copied into the next one.
Attendance is then taken against those lessons: pick a date, the day's sessions are listed with
whether each register has been taken, and you mark one session at a time. A day with no lessons
says so rather than letting you record a register that belongs to nothing, and a whole-day register
is still available as a deliberate choice. Because registers carry their subject, attendance can be
read per subject as well as overall — the subject page shows both it and how much time that subject
gets each week. Registers taken before a lesson is removed, or before this feature existed, stay
valid.

**Help inside the app.** Press **F1** on any screen and help opens at the topic for that screen —
recording marks, question papers, timetable and attendance, divisions and report cards, backups
and so on. Every topic is searchable ("division", "backup", "absent"), and the same page carries
**About**: version, the team, the GitHub link, and the build details (Python, Qt, system, database,
schema revision, log file) with a **Copy build details** button for bug reports.

**Starting up.** Markbook shows a splash with the app icon, its name, what it is doing
("Opening the database…", "Reading this term's marks…") and a progress bar, plus a one-line tip
that changes every few seconds — the tips are in `frontend/splash.py` if you want to edit them.
It stays up for at least a moment even on a fast start, and steps aside if the database
connection dialog is needed.

**Moving around.** Detail pages have a back button naming where you came from ("← Computer
Science"), and **Alt+Left** does the same. Opening an exam from a subject returns to that subject;
opening the same exam from Tests & exams returns there. If the record you came from has since been
deleted, back skips past it.

**Finding a student.** Press **Ctrl+K** (or the Find a student button) from anywhere, type part of a
name, reg. number or phone, and press Enter. Words can come in any order and be shortened —
"mwa nee" finds Neema Mwakalinga — and a phone can be typed as dialled (0793…) even though it is
stored as +255793…. Archived students appear last, marked as archived.

**Annual results.** Results & reports → **Show: Whole year** combines every term of the academic
year into a year mark per subject, weighted by each term's weight, then the year average, division
and position. Terms a student did not sit are simply left out of their own average. From there:

- **Annual result sheet (PDF)** — the class for the year, with each term's average per subject.
- **Annual report cards (PDF)** — a column per term next to the year mark, grade, points and
  position, plus a progress chart across the whole year and a "Promoted to" line.
- **Export (Excel)** — one sheet for the class and one per subject, with a column per term.

Individual term marks are never rewritten; the year view only combines them.

### First steps in the app

1. **Settings → Terms & academic years → Add term**: name it, set the academic year and dates.
2. **Students → Add class** (or Settings → Classes & grading → Add class): name it and choose A-Level, O-Level or a custom scale.
3. **Students → Add student** or **Add many** to fill the class list. You can also type a new class name straight into the student dialog, or let a class be created by an import.
4. **Subjects → Add subject**, marking General Studies and similar as subsidiary.
5. **Tests & exams → New assessment**, then enter marks.

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

**Change history.** Every mark entered, changed or removed is recorded with the value before and
after, who made the change and when, as are archives, restores, deletions, imports and backup
restores. See it all on the **Activity** page, filtered by kind or searched by name. History has
no foreign keys, so it survives the student or assessment being deleted — an old mark can always
be accounted for. The name changes are recorded under is set in Settings ("Changes recorded as");
it defaults to the computer's user name.

**Two windows at once.** Marks are saved with a check against what they were when the page was
opened. If they changed in the meantime — another window, another teacher on a shared database —
the save is refused, the differences are listed, and nothing is overwritten. Reloading keeps what
you typed and puts it back in the grid against the current marks.

**Logs.** Problems are written to a rotating log (`logs/markbook.log` in the app folder, path
shown in Settings). Send that file along when reporting a bug.

**Schema migrations.** The database schema is versioned with Alembic. `python main.py` runs any
pending migration on start, so upgrading Markbook never means rebuilding your data by hand. A
database created before migrations existed is stamped at the baseline and then upgraded, keeping
its data.

If Markbook ever reports that it could not read its migrations, delete any `__pycache__` folder
inside `migrations/` and start again — a half-written `.pyc` (an interrupted run, or files copied
between machines) makes Alembic load an empty module. The app now clears that cache and retries by
itself, and says so in the log.

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

## Building a Windows program (.exe and installer)

Your own icon goes at `assets/markbook.ico` — replace the one there. It becomes the window,
taskbar and installer icon. (A `.png` of the same name also works for the window icon.)

On a Windows machine with Python installed:

```bat
build_windows.bat
```

That creates the virtual environment, installs everything, and produces:

- `dist\Markbook\markbook.exe` — the program folder, runnable as it is
- `dist\installer\MarkbookSetup-1.0.0.exe` — the installer, if
  [Inno Setup](https://jrsoftware.org/isdl.php) is installed

To run the steps by hand:

```bat
pip install -r requirements.txt pyinstaller
pyinstaller markbook.spec --noconfirm
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\markbook.iss
```

The build carries its own migrations and `alembic.ini`, so an installed copy creates and upgrades
its database on its own. Version and publisher are set at the top of `installer/markbook.iss`.

**PostgreSQL is still needed** on the machine that holds the data — it is not bundled. On first
start, if Markbook cannot reach a database it asks for the server, database, user and password,
tests the connection and writes `.env` next to `markbook.exe`. To point an installed copy somewhere
else later, edit that file.

Files a person creates (backups, logs, drafts in `~/.markbook`) are never touched by the uninstaller.

## Project structure

```
markbook_desktop/
├── main.py                    Entry point
├── markbook.spec              PyInstaller build
├── build_windows.bat          One-step Windows build
├── installer/markbook.iss     Inno Setup installer
├── assets/markbook.ico        Application icon
├── alembic.ini, migrations/   Schema versions (Alembic)
├── backend/                   No Qt imports: can sit behind a REST API later
│   ├── config.py              .env settings (DATABASE_URL, DEFAULT_COUNTRY_CODE)
│   ├── db.py                  Engine, session_scope(), create_schema()
│   ├── migrate.py             Runs pending migrations at startup
│   ├── log.py                 Rotating log file
│   ├── audit.py               Change history (who changed what, and when)
│   ├── about.py               App name, version, team and build details
│   ├── paths.py               Where logs, drafts, backups and bundled files live
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
│       ├── terms.py           Terms, academic years and class rollover
│       ├── timetable.py       Weekly lessons that attendance is taken against
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
│   ├── db_setup.py            First-run database connection dialog
│   ├── quick_find.py          Ctrl+K student search
│   ├── splash.py              Start-up window: progress and rotating tips
│   ├── help_topics.py         The help text, searchable by topic
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

## Credits

Markbook is built and maintained by **Mencorium**.

- Source, releases and issue tracker: https://github.com/mencorium/markbook
- Report a problem: https://github.com/mencorium/markbook/issues — include the build details from
  **Help & about → Copy build details** and the log file it names.

Version and team live in `backend/about.py`; the About screen, window title, splash and installer
all read from there, so bump the version in that one file.