import argparse
import os
import sqlite3
from typing import Dict, List, Optional

DB_PATH_DEFAULT = os.path.join("data", "quiz_results.db")


def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_event_list(db_path: str = DB_PATH_DEFAULT) -> List[Dict]:
    """Return a list of imported events with winner and team count."""
    with _connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                e.id,
                e.event_date,
                e.location,
                COUNT(t.id) AS team_count,
                (
                    SELECT team_name
                    FROM quiz_teams
                    WHERE event_id = e.id
                    ORDER BY COALESCE(team_rank, 9999), total DESC, puzzle_points DESC, team_name ASC
                    LIMIT 1
                ) AS winner
            FROM quiz_events e
            LEFT JOIN quiz_teams t ON t.event_id = e.id
            GROUP BY e.id
            ORDER BY e.event_date, e.location
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _resolve_event_id(
    db_path: str,
    event_id: Optional[int] = None,
    source_file: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
) -> int:
    if event_id is not None:
        return event_id

    if source_file is not None:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT id FROM quiz_events WHERE source_file = ?",
                (source_file,),
            ).fetchone()
            if row is None:
                raise ValueError(f"No event found for source_file='{source_file}'")
            return row["id"]

    if event_date is not None and location is not None:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT id FROM quiz_events WHERE event_date = ? AND location = ?",
                (event_date, location),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"No event found for date='{event_date}' and location='{location}'"
                )
            return row["id"]

    raise ValueError(
        "A single event must be identified by event_id, source_file, or event_date and location."
    )


def get_event_result(
    db_path: str = DB_PATH_DEFAULT,
    event_id: Optional[int] = None,
    source_file: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict:
    """Return the event summary and team results for a single event."""
    resolved_event_id = _resolve_event_id(
        db_path, event_id=event_id, source_file=source_file, event_date=event_date, location=location
    )
    with _connect(db_path) as conn:
        event = conn.execute(
            "SELECT id, event_date, location, source_file, imported_at FROM quiz_events WHERE id = ?",
            (resolved_event_id,),
        ).fetchone()
        if event is None:
            raise ValueError(f"No event found with id={resolved_event_id}")

        teams = conn.execute(
            """
            SELECT team_rank, team_name, total, puzzle_points
            FROM quiz_teams
            WHERE event_id = ?
            ORDER BY COALESCE(team_rank, 9999), total DESC, puzzle_points DESC, team_name ASC
            """,
            (resolved_event_id,),
        ).fetchall()

        return {
            "event": dict(event),
            "teams": [dict(row) for row in teams],
        }


def print_event_list(db_path: str = DB_PATH_DEFAULT) -> None:
    events = get_event_list(db_path)
    if not events:
        print("No imported quiz events found.")
        return

    print(f"{'ID':>3}  {'Date':10}  {'Location':20}  {'Teams':>5}  {'Winner'}")
    print("""----  ----------  --------------------  -----  ------------------------------""")
    for event in events:
        print(
            f"{event['id']:>3}  {event['event_date']:10}  {event['location'][:20]:20}  {event['team_count']:>5}  {event['winner'] or 'N/A'}"
        )


def print_event_results(
    db_path: str = DB_PATH_DEFAULT,
    event_id: Optional[int] = None,
    source_file: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
) -> None:
    result = get_event_result(
        db_path=db_path,
        event_id=event_id,
        source_file=source_file,
        event_date=event_date,
        location=location,
    )
    event = result["event"]
    teams = result["teams"]

    print(f"Event: {event['event_date']} @ {event['location']} ({event['source_file']})")
    print(f"Imported at: {event['imported_at']}")
    print(f"Teams: {len(teams)}")
    print()

    if not teams:
        print("No teams recorded for this event.")
        return

    print(f"{'Pos':>3}  {'Team':30}  {'Total':>5}  {'PP':>4}")
    print("""----  ------------------------------  -----  ----""")
    for position, team in enumerate(teams, start=1):
        print(
            f"{position:>3}  {team['team_name'][:30]:30}  {team['total'] or 0:>5}  {team['puzzle_points'] if team['puzzle_points'] is not None else '':>4}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print quiz event summaries and results from the SQLite database.")
    parser.add_argument("--db", default=DB_PATH_DEFAULT, help="Path to the SQLite database file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="Print a list of imported quiz events.")

    result_parser = subparsers.add_parser("result", help="Print results for a single imported event.")
    result_parser.add_argument("--event-id", type=int, help="Event id to show.")
    result_parser.add_argument("--source-file", help="Source Excel filename of the event.")
    result_parser.add_argument("--date", dest="event_date", help="Event date in YYYY-MM-DD format.")
    result_parser.add_argument("--location", help="Event location string.")

    args = parser.parse_args()
    if args.command == "list":
        print_event_list(args.db)
    elif args.command == "result":
        print_event_results(
            db_path=args.db,
            event_id=args.event_id,
            source_file=args.source_file,
            event_date=args.event_date,
            location=args.location,
        )
