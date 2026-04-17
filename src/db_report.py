import argparse
import os
import sqlite3
from typing import Dict, List, Optional

from championship_config import CHAMPIONSHIP_POINTS_BY_POSITION
from team_aliases import TEAM_NAME_ALIASES

DB_PATH_DEFAULT = os.path.join("data", "quiz_results.db")


def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _canonical_team_name(team_name: str) -> str:
    """Map team aliases to a canonical championship team name."""
    normalized = team_name.strip()
    alias_lookup = {alias.casefold(): canonical for alias, canonical in TEAM_NAME_ALIASES.items()}
    return alias_lookup.get(normalized.casefold(), normalized)


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
                ) AS winner,
                (
                    SELECT bonus_round
                    FROM quiz_teams
                    WHERE event_id = e.id
                    ORDER BY COALESCE(team_rank, 9999), total DESC, puzzle_points DESC, team_name ASC
                    LIMIT 1
                ) AS winner_bonus
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
            SELECT team_rank, team_name, total, puzzle_points, bonus_round
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


def get_championship_standings(year: int, db_path: str = DB_PATH_DEFAULT) -> Dict:
    """Return championship standings for the given year."""
    year_prefix = f"{year:04d}-%"
    with _connect(db_path) as conn:
        events = conn.execute(
            """
            SELECT id, event_date, location
            FROM quiz_events
            WHERE event_date LIKE ?
            ORDER BY event_date ASC, location ASC
            """,
            (year_prefix,),
        ).fetchall()

        standings: Dict[str, Dict] = {}
        for event in events:
            rows = conn.execute(
                """
                SELECT team_name, team_rank
                FROM quiz_teams
                WHERE event_id = ?
                ORDER BY COALESCE(team_rank, 9999), total DESC, puzzle_points DESC, team_name ASC
                """,
                (event["id"],),
            ).fetchall()

            for fallback_pos, row in enumerate(rows, start=1):
                rank = row["team_rank"] if row["team_rank"] is not None else fallback_pos
                points = CHAMPIONSHIP_POINTS_BY_POSITION.get(rank, 0)
                team_name = _canonical_team_name(row["team_name"])
                if team_name not in standings:
                    standings[team_name] = {
                        "team_name": team_name,
                        "points": 0,
                        "events_count": 0,
                    }
                standings[team_name]["points"] += points
                standings[team_name]["events_count"] += 1

        sorted_standings = sorted(
            standings.values(),
            key=lambda s: (-s["points"], -s["events_count"], s["team_name"].lower()),
        )

        return {
            "year": year,
            "events_count": len(events),
            "teams_count": len(sorted_standings),
            "standings": sorted_standings,
        }


def print_championship_standings(year: int, db_path: str = DB_PATH_DEFAULT) -> None:
    result = get_championship_standings(year, db_path)
    standings = result["standings"]

    print(f"Championship standings {result['year']}")
    print(f"Events: {result['events_count']}")
    print(f"Teams: {result['teams_count']}")
    print()

    if not standings:
        print("No events found for this year.")
        return

    print(f"{'Pos':>3}  {'Team':30}  {'Points':>6}  {'Events':>6}")
    print("""----  ------------------------------  ------  ------""")
    for pos, team in enumerate(standings, start=1):
        print(
            f"{pos:>3}  {team['team_name'][:30]:30}  {team['points']:>6}  {team['events_count']:>6}"
        )


def print_event_list(db_path: str = DB_PATH_DEFAULT) -> None:
    events = get_event_list(db_path)
    if not events:
        print("No imported quiz events found.")
        return

    print(f"{'ID':>3}  {'Date':10}  {'Location':20}  {'Teams':>5}  {'Winner':25}  {'Bonus'}")
    print("""----  ----------  --------------------  -----  -------------------------  -----""")
    for event in events:
        bonus = event.get('winner_bonus')
        print(
            f"{event['id']:>3}  {event['event_date']:10}  {event['location'][:20]:20}  {event['team_count']:>5}  {event['winner'][:25] if event['winner'] else 'N/A':25}  {str(bonus) if bonus is not None else '':>5}"
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

    print(f"{'Pos':>3}  {'Team':30}  {'Total':>5}  {'PP':>4}  {'Bonus'}")
    print("""----  ------------------------------  -----  ----  -----""")
    for position, team in enumerate(teams, start=1):
        bonus_round = team.get('bonus_round')
        bonus_text = str(bonus_round) if bonus_round is not None else ''
        print(
            f"{position:>3}  {team['team_name'][:30]:30}  {team['total'] or 0:>5}  {team['puzzle_points'] if team['puzzle_points'] is not None else '':>4}  {bonus_text:>5}"
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

    standings_parser = subparsers.add_parser(
        "standings", help="Print championship standings for a given year."
    )
    standings_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")

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
    elif args.command == "standings":
        print_championship_standings(args.year, args.db)
