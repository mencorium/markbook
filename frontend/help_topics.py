# /markbook/frontend/help_topics.py
"""The help text.

Written as tasks a teacher actually has ("record a test", "print report cards"), not as a tour
of the menus. Each topic carries keywords so the search finds it by the words people would type,
and a page key so a screen can open help at the right place.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Topic:
    key: str
    title: str
    summary: str
    body: str                                   # simple HTML: <p>, <ul>, <b>, <i>
    page: str | None = None                     # the screen this topic explains
    keywords: list[str] = field(default_factory=list)

    def matches(self, query: str) -> bool:
        return self.rank(query) is not None

    def rank(self, query: str) -> int | None:
        """Lower is better, None means no match. A word in the title or keywords counts for
        much more than the same word buried in the text, so 'division' leads with divisions."""
        strong = f"{self.title} {self.summary} {' '.join(self.keywords)}".lower()
        body = self.body.lower()
        total = 0
        for word in query.lower().split():
            if word in strong:
                total += 0 if strong.startswith(word) else 1
            elif word in body:
                total += 10
            else:
                return None
        return total


def _p(*paragraphs: str) -> str:
    return "".join(f"<p>{text}</p>" for text in paragraphs)


def _steps(*items: str) -> str:
    return "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


def _bullets(*items: str) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


TOPICS: list[Topic] = [
    Topic(
        "start", "Setting up for the first time",
        "The order to do things in when the app is empty.",
        _p("Markbook needs four things before it can calculate anything: a term, a class, some "
           "students and some subjects. Set them up in this order and nothing will be missing later.")
        + _steps(
            "<b>Settings → Terms &amp; academic years → Add term.</b> Give it a name (Term 1), the "
            "academic year and its start and end dates. A term is whatever period you teach in — two "
            "six-month terms, three shorter ones, or a single short course.",
            "<b>Students → Add class.</b> Name the class, pick NECTA A-Level, O-Level or a custom "
            "scale, and say what happens to it at the end of the year.",
            "<b>Students → Add student</b> for one, or <b>Add many</b> to paste a list. You can also "
            "import a class list from Excel.",
            "<b>Subjects → Add subject.</b> Mark General Studies and similar as subsidiary so they "
            "are graded but left out of the A-Level division.",
            "<b>Tests &amp; exams → New assessment</b>, then enter the marks.")
        + _p("In a hurry? <b>Settings → Data &amp; logs → Add sample class</b> fills the app with a "
             "made-up Form Five so you can see every screen working. Remove it whenever you like; it "
             "never touches your own data."),
        page="dashboard",
        keywords=["begin", "first", "new", "empty", "setup", "install", "order", "sample"],
    ),
    Topic(
        "terms", "Terms and academic years",
        "Why each term has its own results, and how to start the next one.",
        _p("Every mark and every register belongs to the term its date falls in. That is what stops "
           "Term 1 dragging on Term 2: each term has its own averages, positions and divisions.")
        + _p("Switch term with the picker at the top left. <b>All terms</b> shows everything together.")
        + _p("<b>Starting the next term.</b> Settings → Terms → <b>Start the next term…</b> creates the "
             "term and moves every class on at the same time, according to the rule you set for each one:")
        + _bullets(
            "<b>Students move up</b> — they go to the next class (Form Five → Form Six). The marks they "
            "already have stay with the old class and term, so last year's results are untouched.",
            "<b>Same class carries on</b> — the class continues into the new term.",
            "<b>Short course finishes</b> — its students are archived, and can be restored at any time.")
        + _p("<b>Weight</b> decides how much a term counts towards the annual result. Two terms weighted "
             "1 and 2 means the second counts double."),
        page="settings",
        keywords=["term", "year", "semester", "promote", "rollover", "next", "academic", "weight"],
    ),
    Topic(
        "students", "Students and classes",
        "Adding, editing, moving and searching for students.",
        _p("<b>Add student</b> takes a name, reg. number and phone. The phone is stored in international "
           "form (+255…) ready for sending results to parents later; type it however you like.")
        + _p("<b>Add many</b> takes one student per line: <i>Name, RegNo, Phone</i> — the last two optional.")
        + _p("<b>Moving a student</b> to another class keeps every mark and register they already have. "
             "Edit them and change the class.")
        + _p("<b>Finding one student</b> in a long list: press <b>Ctrl+K</b> anywhere in the app, type a few "
             "letters and press Enter. Words can come in any order and be shortened, so “mwa nee” finds "
             "Neema Mwakalinga. You can also type a reg. number, or a phone the way you dial it (0793…).")
        + _p("<b>Removing a student</b> archives them: they leave class lists, results and exports, but every "
             "mark is kept. Tick <b>Show archived</b> to restore them, or to delete one for good."),
        page="students",
        keywords=["student", "class", "add", "phone", "reg", "search", "find", "ctrl+k", "move", "archive"],
    ),
    Topic(
        "marks", "Recording marks",
        "Entering, correcting and saving a test or exam.",
        _p("<b>Tests &amp; exams → New assessment</b>, choose the subject, type (Test, Quiz, Assignment or "
           "Exam), date and what it is out of. Then type the marks straight into the grid.")
        + _bullets(
            "An empty box means the student was absent; <b>0</b> means they sat it and scored nothing.",
            "A mark outside the range goes red as you type, so you cannot save a typo.",
            "The grade and percentage next to each row update while you type.")
        + _p("<b>Exams count differently from tests.</b> The final mark for a subject is the test average "
             "and the exam average combined, using the share set in Settings (40% tests by default). A "
             "student with no exam yet is marked from their tests alone, shown with an asterisk.")
        + _p("<b>Your typing is autosaved.</b> If the app closes, the battery dies or the power goes out, "
             "reopening the assessment puts the marks back in the grid with a note saying when you typed "
             "them. Press Save marks to keep them, or discard them.")
        + _p("<b>Changing a mark later</b> is recorded — who changed it, when, and from what — on the "
             "Activity page. If someone else changed the same marks while your page was open, saving is "
             "refused and the differences are listed rather than one of you overwriting the other."),
        page="assessments",
        keywords=["mark", "score", "enter", "test", "exam", "grade", "absent", "save", "autosave", "correct"],
    ),
    Topic(
        "papers", "Marking question by question",
        "Seeing which topics a paper exposed, not just who passed.",
        _p("Tick <b>Mark per question</b> when creating an assessment, or open an existing one and use the "
           "<b>Question paper</b> tab. List each question with the topic it tests and its marks.")
        + _p("<b>Choice questions.</b> Put them in their own section and set “answer any 2 of 3”. Only the "
             "best answers count towards the total, and a student who answers too many keeps their best "
             "ones — the row shows a warning triangle so you know why.")
        + _p("Once marks are in, the <b>Topic &amp; question analysis</b> tab shows:")
        + _bullets(
            "each topic ranked hardest first, with the students below the pass mark named;",
            "each question's average, how many attempted it, and how many scored full marks or zero;",
            "whether a question separated strong students from weak ones — a weak or negative figure "
            "usually means an unclear question or a marking slip, not a weak class;",
            "a table of every student against every topic, coloured red, amber and green.")
        + _p("<b>Analysis report (PDF)</b> puts all of that on paper for a department meeting."),
        page="assessments",
        keywords=["question", "paper", "topic", "analysis", "choice", "section", "difficulty", "discrimination"],
    ),
    Topic(
        "subject", "Looking at one subject",
        "Every test in a subject, and the running totals.",
        _p("Double-click a subject on the <b>Subjects</b> page — or select it and press <b>Open results</b>.")
        + _p("You get, for the chosen class and term: every test and exam with its mean, highest, lowest and "
             "pass rate; the class average across them; the spread of final grades; and a cumulative table "
             "with a column per assessment, then tests %, exam %, final %, grade, position and trend for "
             "every student.")
        + _p("Double-click an assessment there to enter its marks, or a student to open their profile. "
             "<b>Export (Excel)</b> saves the same table."),
        page="subjects",
        keywords=["subject", "cumulative", "per subject", "totals", "position", "trend", "open results"],
    ),
    Topic(
        "timetable", "Timetable and attendance",
        "Why a register belongs to a lesson, and how to take one.",
        _p("Set the weekly lessons for a class on the <b>Timetable</b> page: subject, day, start and end "
           "time, room. A timetable belongs to a term, and <b>Copy from another term…</b> saves typing it "
           "again next term.")
        + _p("Attendance is then taken against those lessons. Pick a date on the <b>Attendance</b> page and "
             "the day's sessions are listed, each showing whether its register has been taken. Choose one "
             "and mark it. That way every register says which lesson it belongs to, and a day with no "
             "lessons tells you so instead of letting you record a register that means nothing.")
        + _p("A <b>whole-day register</b> is still available for a day that is not a normal lesson, but it is "
             "a deliberate choice rather than the default.")
        + _p("Because registers carry their subject, attendance reads per subject as well as overall — the "
             "subject page shows both, next to how much time that subject gets each week."),
        page="timetable",
        keywords=["timetable", "attendance", "register", "lesson", "session", "absent", "present", "room"],
    ),
    Topic(
        "results", "Results, divisions and report cards",
        "Ranking a class and printing what parents see.",
        _p("<b>Results &amp; reports</b> ranks the class, counts the divisions and shows how each subject "
           "performed. Students with a complete division come first, ordered by points then average; the "
           "rest follow by average.")
        + _p("<b>Divisions</b> follow NECTA: A-Level from the best 3 principal subjects with subsidiaries "
             "excluded, O-Level from the best 7. A student with results in too few subjects has no division "
             "yet, and the page says how many are missing.")
        + _p("<b>Report cards</b> show every subject with tests, exam, total, grade and position; total marks "
             "and position in class; a progress chart; weakest topics; and boxes for the class teacher's and "
             "head teacher's comments. Print one student or the whole class in rank order.")
        + _p("<b>Comments write themselves</b> from the actual results — band, best and weakest subject, "
             "trend, attendance — and you edit them before printing. Use <b>Write suggested comments</b> to "
             "fill in everyone who has none.")
        + _p("Set the school name, head teacher and next term's date in Settings; they appear on every card."),
        page="results",
        keywords=["result", "report card", "division", "rank", "position", "print", "pdf", "comment", "parent"],
    ),
    Topic(
        "annual", "End-of-year results",
        "Combining every term into a year mark.",
        _p("On <b>Results &amp; reports</b>, switch <b>Show</b> to <b>Whole year</b>.")
        + _p("Each subject's year mark is the weighted average of the finals from each term — a term weighted "
             "2 counts double. Year average, division and position follow from those year marks. A student "
             "who sat only one term still gets a year mark, from that term alone, and the card says how many "
             "terms they sat.")
        + _p("From there you can print the <b>annual result sheet</b>, <b>annual report cards</b> (a column per "
             "term beside the year mark, and a “Promoted to” line), or export the same to Excel.")
        + _p("Individual term marks are never rewritten; this view only combines them."),
        page="results",
        keywords=["annual", "year", "end of year", "combine", "weight", "promotion", "final"],
    ),
    Topic(
        "io", "Excel and CSV",
        "Getting marks in and out.",
        _p("<b>Export</b> a single test, a subject's running totals, a whole class or a class list with phone "
           "numbers, as Excel or CSV. Columns show marks <i>or</i> grades, never both.")
        + _p("<b>Import</b> takes those same sheets straight back, per-question marks included, so another "
             "teacher can fill one in and you load it. Other sheets work too as long as there is a "
             "<b>Student Name</b> column; Reg. No., Phone and Marks columns are used when present.")
        + _p("Before anything is written you see a preview: who matched an existing student, who would be "
             "added, and which phone numbers are not valid. Students are matched on reg. number first, then "
             "on name within the class."),
        page="io",
        keywords=["import", "export", "excel", "csv", "sheet", "upload", "download", "xlsx"],
    ),
    Topic(
        "safety", "Backups, undo and history",
        "Getting your marks back when something goes wrong.",
        _p("<b>Backups.</b> Settings → Backups: back up now, choose the folder, or restore an earlier backup. "
           "Markbook also backs itself up once a day when you close it. Each backup is a single file holding "
           "everything, and the newest 20 are kept. Restoring takes a “before-restore” backup first, so even "
           "a mistaken restore can be undone.")
        + _p("This needs PostgreSQL's <i>pg_dump</i>. If it is not found, press <b>Locate PostgreSQL tools…</b> "
             "and choose the <b>bin</b> folder of your PostgreSQL installation.")
        + _p("<b>Nothing is deleted by accident.</b> Removing a student or subject archives it — hidden from "
             "results, every mark kept, restorable from <b>Show archived</b>. Deleting for good is the only "
             "irreversible action in the app, and it lives behind that view.")
        + _p("<b>Every change to a mark is recorded</b> on the <b>Activity</b> page: what it was, what it "
             "became, who did it and when. That history survives even a student being deleted, so an old "
             "mark can always be accounted for. Set the name changes are recorded under in Settings."),
        page="settings",
        keywords=["backup", "restore", "undo", "delete", "archive", "history", "activity", "audit", "lost"],
    ),
    Topic(
        "shortcuts", "Keyboard shortcuts",
        "The few worth learning.",
        _bullets(
            "<b>Ctrl+K</b> — find a student from anywhere and jump to them.",
            "<b>F1</b> — open this help at the page you are on.",
            "<b>Alt+Left</b> — go back to wherever you came from.",
            "<b>Ctrl+A</b> — select every row in a list.",
            "<b>Delete</b> — archive the selected students or subjects.",
            "<b>Tab</b> and <b>Enter</b> — move through the mark grid while typing.")
        + _p("In lists, hold <b>Ctrl</b> to pick several rows one by one, or <b>Shift</b> to pick a range."),
        keywords=["shortcut", "keyboard", "key", "f1", "ctrl", "alt", "quick"],
    ),
    Topic(
        "trouble", "When something goes wrong",
        "What to check first, and what to send.",
        _p("<b>Markbook will not start.</b> The message usually says why. If it mentions the database, check "
           "that PostgreSQL is running and that the connection in the <b>.env</b> file next to the program is "
           "right. If it mentions migrations, delete any <b>__pycache__</b> folder inside <b>migrations</b> "
           "and start again.")
        + _p("<b>The database is in use by another program.</b> Close any second copy of Markbook, pgAdmin or "
             "psql that is connected, then start again.")
        + _p("<b>Backups will not run.</b> PostgreSQL's tools are not on PATH — use <b>Locate PostgreSQL "
             "tools…</b> in Settings → Backups.")
        + _p("<b>A student's marks look wrong.</b> Check the term picker at the top left: you may be looking "
             "at a different term. The Activity page shows every change made to a mark.")
        + _p("<b>Reporting a problem.</b> Send the log file — its location is on the About page and in "
             "Settings → Data &amp; logs — together with the build details from About, which say which "
             "version, database and schema you are running."),
        keywords=["error", "problem", "crash", "fix", "broken", "log", "bug", "support", "help", "wrong"],
    ),
]

BY_KEY = {t.key: t for t in TOPICS}
BY_PAGE: dict[str, str] = {}
for _t in TOPICS:
    if _t.page and _t.page not in BY_PAGE:
        BY_PAGE[_t.page] = _t.key


def for_page(page: str | None) -> str:
    """The topic to open when help is asked for from a given screen."""
    return BY_PAGE.get(page or "", "start")


def search(query: str) -> list[Topic]:
    """Best matches first; with no query, the topics in their reading order."""
    query = query.strip()
    if not query:
        return list(TOPICS)
    scored = [(t.rank(query), i, t) for i, t in enumerate(TOPICS)]
    return [t for rank, _, t in sorted((s for s in scored if s[0] is not None), key=lambda s: (s[0], s[1]))]