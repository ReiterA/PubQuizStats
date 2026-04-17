import argparse
import os
import re
import sqlite3
from datetime import datetime, timezone

from openpyxl import load_workbook

DB_PATH_DEFAULT = os.path.join("data", "quiz_results.db")

EVENT_FILE_PATTERN = re.compile(r"(?P<date>\d{8})_(?P<location>.+)\.(xlsx|xlsm|xltx|xltm)$")


def parse_event_from_filename(filename):
    basename = os.path.basename(filename)
    match = EVENT_FILE_PATTERN.match(basename)
    if not match:
        raise ValueError(
            f"Unable to parse date and location from filename '{basename}'. "
            "Expected format: YYYYMMDD_Location.xlsx"
        )

    event_date = datetime.strptime(match.group("date"), "%Y%m%d").date().isoformat()
    location = match.group("location").replace("_", " ")
    return event_date, location


def normalize_int(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def create_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_events (
            id INTEGER PRIMARY KEY,
            event_date TEXT NOT NULL,
            location TEXT NOT NULL,
            source_file TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_teams (
            id INTEGER PRIMARY KEY,
            event_id INTEGER NOT NULL REFERENCES quiz_events(id),
            team_rank INTEGER,
            team_name TEXT NOT NULL,
            penalty_points INTEGER,
            total INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_scores (
            id INTEGER PRIMARY KEY,
            team_id INTEGER NOT NULL REFERENCES quiz_teams(id),
            question_index INTEGER NOT NULL,
            points INTEGER
        )
        """
    )
    conn.commit()


def read_quiz_sheet(excel_path):
    workbook = load_workbook(filename=excel_path, data_only=True)
    worksheet = workbook.active

    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError(f"Excel workbook '{excel_path}' is empty.")

    header = [str(cell).strip() if cell is not None else None for cell in rows[0]]
    if "Teamname" not in header:
        raise ValueError(
            "Expected a header row containing 'Teamname'. "
            "The template in data/quizzes should include that column."
        )

    teamname_idx = header.index("Teamname")
    rank_idx = header.index("#") if "#" in header else None
    pp_idx = header.index("PP") if "PP" in header else None
    total_idx = header.index("Gesamt") if "Gesamt" in header else None

    question_indices = []
    for idx, title in enumerate(header):
        if title is None:
            continue
        if title.isdigit():
            question_indices.append((idx, int(title)))

    teams = []
    for row in rows[1:]:
        if row is None or len(row) <= teamname_idx:
            continue
        team_name = row[teamname_idx]
        if team_name is None or str(team_name).strip() == "":
            continue

        team = {
            "team_rank": normalize_int(row[rank_idx]) if rank_idx is not None else None,
            "team_name": str(team_name).strip(),
            "penalty_points": normalize_int(row[pp_idx]) if pp_idx is not None else None,
            "total": normalize_int(row[total_idx]) if total_idx is not None else None,
            "scores": [],
        }

        for idx, question_number in question_indices:
            if idx >= len(row):
                value = None
            else:
                value = normalize_int(row[idx])
            team["scores"].append((question_number, value))

        teams.append(team)

    return teams


def import_quiz_file(excel_path, db_path=DB_PATH_DEFAULT):
    event_date, location = parse_event_from_filename(excel_path)
    teams = read_quiz_sheet(excel_path)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    imported_at = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quiz_events (event_date, location, source_file, imported_at) VALUES (?, ?, ?, ?)",
        (event_date, location, os.path.basename(excel_path), imported_at),
    )
    event_id = cur.lastrowid

    for team in teams:
        cur.execute(
            "INSERT INTO quiz_teams (event_id, team_rank, team_name, penalty_points, total) VALUES (?, ?, ?, ?, ?)",
            (
                event_id,
                team["team_rank"],
                team["team_name"],
                team["penalty_points"],
                team["total"],
            ),
        )
        team_id = cur.lastrowid

        for question_index, points in team["scores"]:
            cur.execute(
                "INSERT INTO team_scores (team_id, question_index, points) VALUES (?, ?, ?)",
                (team_id, question_index, points),
            )

    conn.commit()
    conn.close()

    return {
        "event_date": event_date,
        "location": location,
        "teams_imported": len(teams),
        "database": db_path,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Import PubQuiz results from an Excel file into a SQLite database."
    )
    parser.add_argument("excel_file", help="Path to the quiz result Excel file.")
    parser.add_argument(
        "--db",
        default=DB_PATH_DEFAULT,
        help="Path to SQLite database file. Defaults to data/quiz_results.db.",
    )
    args = parser.parse_args()

    result = import_quiz_file(args.excel_file, args.db)
    print(f"Imported {result['teams_imported']} teams from {result['event_date']} @ {result['location']}")
    print(f"Saved into {result['database']}")


if __name__ == "__main__":
    main()
