# PubQuizStats

PubQuizStats is a desktop application and reporting toolkit for PubQuiz results. It can import quiz spreadsheets into a SQLite database, manage event themes, and generate a range of team and championship reports from the imported data.

## Features

- GUI for importing quiz result files and event themes
- SQLite-based storage for quiz events, teams, and report data
- Report generation for standings, team summaries, averages, consistency, round strength, event difficulty, and more
- Team event/category detail report export as text or PDF
- Helper scripts for launching the app and re-importing all quiz files

## Requirements

- Python 3.11 or newer
- A virtual environment is recommended
- Dependencies from `requirements.txt`
- Optional: LibreOffice or `soffice` for document conversion features used by the GUI

## Setup

Install dependencies into your virtual environment:

```bash
pip install -r requirements.txt
```

The project uses a local SQLite database stored at `data/quiz_results.db` by default.

## Activate the virtual environment

Activate the virtual environment:

```bash
source .venv/bin/activate
```

## Run the web GUI

Start the web application with:

```bash
./start_gui.sh
```

You can also launch it directly from Python:

```bash
python main.py            # opens http://localhost:8765 in your browser
python main.py --port 9000 --no-browser
```

The web GUI (modern, light/dark design) covers all former desktop features: importing quiz files and event themes (drag & drop), every report with interactive charts plus the original text output, PDF exports (team report, team category detail, theme difficulties, standing progress, text report), batch generation of all team reports (with ZIP download) and settings. By default it only listens on `127.0.0.1`; use `--host` to change that.

## Import data

Import one quiz file:

```bash
python src/import_quiz_results.py path/to/result.xlsx --db data/quiz_results.db
```

Import all quiz files from a folder:

```bash
python src/import_quiz_results.py --folder data/quizzes --db data/quiz_results.db
```

Import event themes:

```bash
python src/import_quiz_results.py --themes data/themes/PQ_Themen.xlsx --db data/quiz_results.db
```

To re-import all quiz files from the default folder, use:

```bash
./reimport_all.sh
```

## Reports

The report module can be run from the command line:

```bash
python src/db_report.py --db data/quiz_results.db list
python src/db_report.py --db data/quiz_results.db standings --year 2026
python src/db_report.py --db data/quiz_results.db team --team "Team Name" --year 2026
python src/db_report.py --db data/quiz_results.db team-category-detail --team "Team Name" --year 2026
```

Other useful commands include `result`, `averages`, `radar`, `consistency`, `difficulty`, `event-difficulty`, `round-strength`, `leaders`, and `standing-progress`.

## Project Layout

- `main.py` - application entry point
- `src/web_app.py` - web server and JSON API
- `src/report_export.py` - PDF/DOCX export helpers (PySide6 is only used for rendering)
- `web/` - web frontend (HTML/CSS/JS, bundled Chart.js in `web/vendor/`)
- `src/import_quiz_results.py` - import logic and CLI
- `src/db_report.py` - report generation and CLI
- `data/` - database, themes, and imported files

## Notes

- Generated outputs, PDFs, charts, and database files are kept in the `data/` folder unless you choose a different path.
- Batch team reports are written to `data/exports/`.
- The GUI and CLI share the same underlying import and reporting code, so changes to the database are immediately reflected in reports.
