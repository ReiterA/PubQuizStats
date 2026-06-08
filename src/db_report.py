import argparse
import math
import os
import sqlite3
from pathlib import Path
from xml.sax.saxutils import escape
from typing import Dict, List, Optional

from championship_config import CHAMPIONSHIP_POINTS_BY_POSITION
from round_config import ROUND_NAMES
from team_aliases import TEAM_NAME_ALIASES

DB_PATH_DEFAULT = os.path.join("data", "quiz_results.db")

TEAM_REPORT_ROUND_MAX_POINTS = {
    "Allgemeinwissen": 5,
    "Geographie": 5,
    "Entertainment": 5,
    "Sport": 5,
    "Linz/OÖ": 5,
    "Geschichte": 5,
    "Bilderrunde": 10,
    "Interessantes": 6,
    "Überraschung": 5,
    "Musik": 5,
}
TEAM_REPORT_PUZZLE_MAX_POINTS = 10


def _bonus_points_from_normal_points(round_name: str, normal_points: float) -> float:
    """Return potential bonus points for one round from its normal points."""
    points = max(0.0, float(normal_points))
    if round_name in {"Bilderrunde", "Puzzle"}:
        return 0.0

    if round_name == "Überraschung":
        # Rule requested by user:
        # 6->5, 5->4, 4->3, 3->2, 2->1, 1->1, 0->0
        rounded = int(points)
        if rounded <= 0:
            return 0.0
        if rounded <= 2:
            return 1.0
        return float(min(5, rounded - 1))

    return points


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
                        "wins": 0,
                    }
                standings[team_name]["points"] += points
                standings[team_name]["events_count"] += 1
                if rank == 1:
                    standings[team_name]["wins"] += 1

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

    print(f"{'Pos':>4}  {'Team':30}  {'Points':>6}  {'Events':>6}  {'Wins':>5}")
    print("""----  ------------------------------  ------  ------  -----""")
    
    pos = 1
    for idx, team in enumerate(standings):
        # Check if this team is tied with the previous one
        if idx > 0:
            prev_team = standings[idx - 1]
            if team['points'] == prev_team['points']:
                # Same points: use same position
                display_pos = pos
            else:
                # Different points: advance position to next available
                pos = idx + 1
                display_pos = pos
        else:
            display_pos = pos
        
        print(
            f"{display_pos:>4}  {team['team_name'][:30]:30}  {team['points']:>6}  {team['events_count']:>6}  {team['wins']:>5}"
        )


def print_event_list(db_path: str = DB_PATH_DEFAULT) -> None:
    events = get_event_list(db_path)
    if not events:
        print("No imported quiz events found.")
        return

    print(f"{'ID':>4}  {'Date':10}  {'Location':20}  {'Teams':>5}  {'Winner':25}  {'Bonus'}")
    print("""----  ----------  --------------------  -----  -------------------------  -----""")
    for event in events:
        bonus = event.get('winner_bonus')
        print(
            f"{event['id']:>4}  {event['event_date']:10}  {event['location'][:20]:20}  {event['team_count']:>5}  {event['winner'][:25] if event['winner'] else 'N/A':25}  {str(bonus) if bonus is not None else '':>5}"
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

    print(f"{'Pos':>4}  {'Team':30}  {'Total':>5}  {'PP':>4}  {'Bonus'}")
    print("""----  ------------------------------  -----  ----  -----""")
    for position, team in enumerate(teams, start=1):
        bonus_round = team.get('bonus_round')
        bonus_text = str(bonus_round) if bonus_round is not None else ''
        print(
            f"{position:>4}  {team['team_name'][:30]:30}  {team['total'] or 0:>5}  {team['puzzle_points'] if team['puzzle_points'] is not None else '':>4}  {bonus_text:>5}"
        )


def get_event_team_result(
    team_name: str,
    db_path: str = DB_PATH_DEFAULT,
    event_id: Optional[int] = None,
    source_file: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict:
    """Return a detailed result report for one team in one selected event."""
    if not team_name or not team_name.strip():
        raise ValueError("Team name is required.")

    canonical_team = _canonical_team_name(team_name)
    resolved_event_id = _resolve_event_id(
        db_path, event_id=event_id, source_file=source_file, event_date=event_date, location=location
    )

    with _connect(db_path) as conn:
        event_row = conn.execute(
            """
            SELECT id, event_date, location, source_file, imported_at
            FROM quiz_events
            WHERE id = ?
            """,
            (resolved_event_id,),
        ).fetchone()
        if event_row is None:
            raise ValueError(f"No event found with id={resolved_event_id}")

        teams = conn.execute(
            """
            SELECT id, team_name, team_rank, total, puzzle_points, bonus_round
            FROM quiz_teams
            WHERE event_id = ?
            ORDER BY COALESCE(team_rank, 9999), total DESC, puzzle_points DESC, team_name ASC
            """,
            (resolved_event_id,),
        ).fetchall()

        selected_team_row = None
        selected_position = None
        for fallback_pos, row in enumerate(teams, start=1):
            if _canonical_team_name(row["team_name"]) != canonical_team:
                continue

            rank = row["team_rank"] if row["team_rank"] is not None else fallback_pos
            candidate = {
                "id": row["id"],
                "team_name": row["team_name"],
                "canonical_team_name": canonical_team,
                "rank": rank,
                "total": row["total"] if row["total"] is not None else 0,
                "puzzle_points": row["puzzle_points"],
                "bonus_round": row["bonus_round"],
            }

            if selected_team_row is None:
                selected_team_row = candidate
                selected_position = rank
                continue

            # If aliases appear twice in one event, keep the better rank/score row.
            prev_rank = selected_team_row["rank"]
            prev_total = selected_team_row["total"] if selected_team_row["total"] is not None else 0
            if rank < prev_rank or (rank == prev_rank and candidate["total"] > prev_total):
                selected_team_row = candidate
                selected_position = rank

        if selected_team_row is None:
            raise ValueError(
                f"Team '{canonical_team}' has no result in event #{resolved_event_id} ({event_row['event_date']} @ {event_row['location']})."
            )

        round_rows = conn.execute(
            """
            SELECT round_name, points
            FROM team_scores
            WHERE team_id = ?
            """,
            (selected_team_row["id"],),
        ).fetchall()

    round_order = {name: idx for idx, name in ROUND_NAMES.items()}
    selected_bonus_round = (selected_team_row.get("bonus_round") or "").strip()

    rounds = []
    possible_candidates = []
    achieved_bonus_points = 0.0
    adjusted_round_points_sum = 0.0

    for row in sorted(round_rows, key=lambda r: (round_order.get(r["round_name"], 999), r["round_name"])):
        round_name = str(row["round_name"])
        raw_points = row["points"]
        if raw_points is None:
            continue

        observed_points = max(0.0, float(raw_points))
        adjusted_points = observed_points
        is_bonus_round = (
            bool(selected_bonus_round)
            and round_name.casefold() == selected_bonus_round.casefold()
        )

        if is_bonus_round:
            adjusted_points = float(math.floor(observed_points / 2.0))
            achieved_bonus_points = adjusted_points

        possible_candidates.append(_bonus_points_from_normal_points(round_name, adjusted_points))
        adjusted_round_points_sum += adjusted_points

        rounds.append(
            {
                "round_name": round_name,
                "raw_points": observed_points,
                "points": adjusted_points,
                "is_bonus_round": is_bonus_round,
            }
        )

    possible_bonus_points = max(possible_candidates) if possible_candidates else 0.0
    bonus_efficiency = None
    if possible_bonus_points > 0.0:
        bonus_efficiency = achieved_bonus_points / possible_bonus_points

    total_teams = len(teams)
    championship_points = CHAMPIONSHIP_POINTS_BY_POSITION.get(selected_position or 0, 0)

    return {
        "event": dict(event_row),
        "team": {
            **selected_team_row,
            "position": selected_position,
            "total_teams": total_teams,
            "championship_points": championship_points,
            "round_points_sum": adjusted_round_points_sum,
            "bonus_efficiency": bonus_efficiency,
            "achieved_bonus_points": achieved_bonus_points,
            "possible_bonus_points": possible_bonus_points,
        },
        "rounds": rounds,
    }


def print_event_team_result(
    team_name: str,
    db_path: str = DB_PATH_DEFAULT,
    event_id: Optional[int] = None,
    source_file: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
) -> None:
    """Print a detailed one-event result report for one team."""
    result = get_event_team_result(
        team_name=team_name,
        db_path=db_path,
        event_id=event_id,
        source_file=source_file,
        event_date=event_date,
        location=location,
    )

    event = result["event"]
    team = result["team"]
    rounds = result["rounds"]

    print(f"Event result team: {team['canonical_team_name']}")
    print(f"Event: {event['event_date']} @ {event['location']} ({event['source_file']})")
    print(f"Imported at: {event['imported_at']}")
    print()

    print(f"Team in event: {team['team_name']}")
    print(f"Position: {team['position']} / {team['total_teams']}")
    print(f"Total points: {team['total']}")
    puzzle_text = "-" if team["puzzle_points"] is None else f"{team['puzzle_points']}"
    print(f"Puzzle points: {puzzle_text}")
    print(f"Championship points (event): {team['championship_points']}")
    print(f"Selected bonus round: {team.get('bonus_round') or '-'}")

    if team["bonus_efficiency"] is None:
        print("Bonus efficiency: -")
    else:
        print(
            "Bonus efficiency: "
            f"{team['bonus_efficiency'] * 100:.1f}% "
            f"({team['achieved_bonus_points']:.1f}/{team['possible_bonus_points']:.1f})"
        )

    print()
    if not rounds:
        print("No round scores found for this team/event.")
        return

    print(f"{'Round':20}  {'Points':>7}  {'Raw':>7}  {'Bonus'}")
    print("""--------------------  -------  -------  -----""")
    for row in rounds:
        bonus_tag = "yes" if row["is_bonus_round"] else ""
        print(
            f"{row['round_name'][:20]:20}  {row['points']:>7.1f}  {row['raw_points']:>7.1f}  {bonus_tag:>5}"
        )

    print("""--------------------  -------  -------  -----""")
    print(f"{'Round points sum':20}  {team['round_points_sum']:>7.1f}")


def get_team_season_results(team_name: str, year: int, db_path: str = DB_PATH_DEFAULT) -> Dict:
    """Return all events and results for a team in a given year."""
    canonical_team = _canonical_team_name(team_name)
    year_prefix = f"{year:04d}-%"
    
    with _connect(db_path) as conn:
        all_rows = conn.execute(
            """
            SELECT
                e.id AS event_id,
                e.event_date,
                e.location,
                t.id AS team_id,
                t.team_name,
                t.team_rank,
                t.total,
                t.bonus_round
            FROM quiz_events e
            JOIN quiz_teams t ON e.id = t.event_id
            WHERE e.event_date LIKE ?
            ORDER BY e.event_date ASC, e.location ASC
            """,
            (year_prefix,),
        ).fetchall()

        # Collect all rows that canonicalize to the requested team.
        # If aliases appear twice in one event, keep the better rank/score row.
        results_by_event: Dict[int, Dict] = {}
        for row in all_rows:
            if _canonical_team_name(row["team_name"]) != canonical_team:
                continue

            event_id = row["event_id"]
            candidate = dict(row)
            existing = results_by_event.get(event_id)
            if existing is None:
                results_by_event[event_id] = candidate
                continue

            candidate_rank = candidate["team_rank"] if candidate["team_rank"] is not None else 9999
            existing_rank = existing["team_rank"] if existing["team_rank"] is not None else 9999
            candidate_total = candidate["total"] if candidate["total"] is not None else 0
            existing_total = existing["total"] if existing["total"] is not None else 0

            if candidate_rank < existing_rank or (candidate_rank == existing_rank and candidate_total > existing_total):
                results_by_event[event_id] = candidate

        results = sorted(results_by_event.values(), key=lambda row: (row["event_date"], row["location"]))
        
        events_data = []
        for row in results:
            rank = row["team_rank"] if row["team_rank"] is not None else None
            # Get the winning team's total for this event
            winner_total = conn.execute(
                """
                SELECT MAX(total) as max_total
                FROM quiz_teams
                WHERE event_id = ?
                """,
                (row["event_id"],),
            ).fetchone()["max_total"]
            
            percentage = (row["total"] / winner_total * 100) if winner_total else 0
            
            events_data.append({
                "event_id": row["event_id"],
                "team_id": row["team_id"],
                "event_date": row["event_date"],
                "location": row["location"],
                "position": rank,
                "total_points": row["total"],
                "percentage": percentage,
                "bonus_round": row["bonus_round"],
            })
        
        return {
            "team_name": canonical_team,
            "year": year,
            "events": events_data,
        }


def print_team_season_results(team_name: str, year: int, db_path: str = DB_PATH_DEFAULT) -> None:
    """Print season results for a team in a given year."""
    result = get_team_season_results(team_name, year, db_path)
    
    print(f"Season results for {result['team_name']} ({result['year']})")
    print()
    
    if not result["events"]:
        print("No events found for this team in this year.")
        return
    
    print(f"{'Date':10}  {'Location':20}  {'Pos':>3}  {'Points':>6}  {'%':>5}  {'Bonus'}")
    print("""----------  --------------------  ---  ------  -----  -----""")
    
    total_points = 0
    for event in result["events"]:
        bonus_text = str(event['bonus_round']) if event['bonus_round'] is not None else ''
        pos_text = str(event['position']) if event['position'] is not None else '-'
        print(
            f"{event['event_date']:10}  {event['location'][:20]:20}  {pos_text:>3}  {event['total_points']:>6}  {event['percentage']:>5.1f}  {bonus_text:>5}"
        )
        total_points += event['total_points']
    
    print("""----------  --------------------  ---  ------  -----  -----""")
    print(f"{'Total':>34}  {total_points:>6}")


def get_team_round_averages(team_name: str, year: int, db_path: str = DB_PATH_DEFAULT) -> Dict:
    """Return average points per round/question for a team in a given year."""
    canonical_team = _canonical_team_name(team_name)
    year_prefix = f"{year:04d}-%"
    
    with _connect(db_path) as conn:
        # Resolve all team IDs in the year that canonicalize to the requested team.
        all_team_ids = conn.execute(
            """
            SELECT DISTINCT t.id, t.team_name
            FROM quiz_teams t
            JOIN quiz_events e ON t.event_id = e.id
            WHERE e.event_date LIKE ?
            """,
            (year_prefix,),
        ).fetchall()

        team_id_list = [row["id"] for row in all_team_ids if _canonical_team_name(row["team_name"]) == canonical_team]
        if not team_id_list:
            return {
                "team_name": canonical_team,
                "year": year,
                "round_averages": [],
                "puzzle_average": None,
            }
        
        # Get average points per question, adjusting for bonus rounds
        placeholders = ",".join("?" * len(team_id_list))
        round_data = conn.execute(
            f"""
            SELECT
                ts.round_name,
                AVG(
                    CASE 
                        WHEN ts.round_name = qt.bonus_round THEN
                            CASE 
                                WHEN ts.points % 2 = 0 THEN ts.points / 2
                                ELSE (ts.points - 1) / 2
                            END
                        ELSE ts.points
                    END
                ) as avg_points,
                COUNT(*) as appearances
            FROM team_scores ts
            JOIN quiz_teams qt ON ts.team_id = qt.id
            WHERE ts.team_id IN ({placeholders})
            GROUP BY ts.round_name
            ORDER BY 
                CASE ts.round_name
                    WHEN 'Allgemeinwissen' THEN 1
                    WHEN 'Geographie' THEN 2
                    WHEN 'Entertainment' THEN 3
                    WHEN 'Sport' THEN 4
                    WHEN 'Linz/OÖ' THEN 5
                    WHEN 'Geschichte' THEN 6
                    WHEN 'Bilderrunde' THEN 7
                    WHEN 'Interessantes' THEN 8
                    WHEN 'Überraschung' THEN 9
                    WHEN 'Musik' THEN 10
                    ELSE 999
                END
            """,
            team_id_list,
        ).fetchall()
        
        # Get puzzle points average
        puzzle_avg = conn.execute(
            f"""
            SELECT AVG(puzzle_points) as avg_puzzle
            FROM quiz_teams
            WHERE id IN ({placeholders})
            """,
            team_id_list,
        ).fetchone()
        
        round_averages = [
            {
                "round_name": row["round_name"],
                "avg_points": row["avg_points"],
                "appearances": row["appearances"],
            }
            for row in round_data
        ]
        
        return {
            "team_name": canonical_team,
            "year": year,
            "round_averages": round_averages,
            "puzzle_average": puzzle_avg["avg_puzzle"],
        }


def get_overall_round_averages(year: int, db_path: str = DB_PATH_DEFAULT) -> Dict:
    """Return average round points across all teams in the given year."""
    year_prefix = f"{year:04d}-%"

    with _connect(db_path) as conn:
        round_rows = conn.execute(
            """
            SELECT
                ts.round_name,
                AVG(
                    CASE
                        WHEN ts.round_name = qt.bonus_round THEN
                            CASE
                                WHEN ts.points % 2 = 0 THEN ts.points / 2
                                ELSE (ts.points - 1) / 2
                            END
                        ELSE ts.points
                    END
                ) AS avg_points
            FROM team_scores ts
            JOIN quiz_teams qt ON ts.team_id = qt.id
            JOIN quiz_events e ON qt.event_id = e.id
            WHERE e.event_date LIKE ?
            GROUP BY ts.round_name
            """,
            (year_prefix,),
        ).fetchall()

        puzzle_row = conn.execute(
            """
            SELECT AVG(qt.puzzle_points) AS avg_puzzle
            FROM quiz_teams qt
            JOIN quiz_events e ON qt.event_id = e.id
            WHERE e.event_date LIKE ?
              AND qt.puzzle_points IS NOT NULL
            """,
            (year_prefix,),
        ).fetchone()

    return {
        "year": year,
        "round_averages": {
            row["round_name"]: float(row["avg_points"])
            for row in round_rows
            if row["avg_points"] is not None
        },
        "puzzle_average": None if puzzle_row is None else puzzle_row["avg_puzzle"],
    }


def get_team_radar_report(
    team_name: str,
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> Dict:
    """Return radar-chart data for a team in a given year."""
    canonical_team = _canonical_team_name(team_name)
    ranking_report = get_round_strength_ranking(year=year, min_events=min_events, db_path=db_path)
    ranking_map = {block["round_name"]: block["teams"] for block in ranking_report["rankings"]}

    rounds = []
    for round_name in ROUND_NAMES.values():
        teams = ranking_map.get(round_name, [])
        selected_position = None
        selected_team = None
        for position, team in enumerate(teams, start=1):
            if team["team_name"].casefold() == canonical_team.casefold():
                selected_position = position
                selected_team = team
                break

        if selected_team is not None:
            total_teams = len(teams)
            max_avg_points = teams[0]["avg_points"] if teams else 0
            avg_points = float(selected_team["avg_points"])
            avg_score = (avg_points / max_avg_points) if max_avg_points else 0.0
            placement_score = 1.0 if total_teams == 1 else (total_teams - selected_position) / (total_teams - 1)
            rounds.append(
                {
                    "round_name": round_name,
                    "avg_points": avg_points,
                    "position": selected_position,
                    "total_teams": total_teams,
                    "avg_score": avg_score,
                    "placement_score": placement_score,
                    "events": selected_team["events"],
                }
            )
            continue

        rounds.append(
            {
                "round_name": round_name,
                "avg_points": None,
                "position": None,
                "total_teams": len(teams),
                "avg_score": 0.0,
                "placement_score": 0.0,
                "events": 0,
            }
        )

    return {
        "team_name": canonical_team,
        "year": year,
        "min_events": min_events,
        "rounds": rounds,
    }


def get_team_puzzle_ranking(
    team_name: str,
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> Dict:
    """Return puzzle ranking info for one team in a given year."""
    canonical_team = _canonical_team_name(team_name)
    year_prefix = f"{year:04d}-%"

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                qt.team_name,
                qt.event_id,
                qt.puzzle_points
            FROM quiz_teams qt
            JOIN quiz_events e ON e.id = qt.event_id
            WHERE e.event_date LIKE ?
              AND qt.puzzle_points IS NOT NULL
            """,
            (year_prefix,),
        ).fetchall()

    by_team: Dict[str, Dict[int, float]] = {}
    for row in rows:
        normalized_team = _canonical_team_name(row["team_name"])
        event_id = row["event_id"]
        puzzle_points = float(row["puzzle_points"])
        by_team.setdefault(normalized_team, {})

        # If aliases appear twice in one event, keep the higher puzzle score.
        previous = by_team[normalized_team].get(event_id)
        if previous is None or puzzle_points > previous:
            by_team[normalized_team][event_id] = puzzle_points

    rankings = []
    for normalized_team, per_event in by_team.items():
        values = list(per_event.values())
        events_count = len(values)
        if events_count < min_events:
            continue
        avg_points = sum(values) / events_count
        rankings.append(
            {
                "team_name": normalized_team,
                "avg_points": avg_points,
                "events": events_count,
            }
        )

    rankings.sort(key=lambda row: (-row["avg_points"], -row["events"], row["team_name"].lower()))

    selected = None
    for idx, row in enumerate(rankings, start=1):
        if row["team_name"].casefold() == canonical_team.casefold():
            selected = {
                "team_name": canonical_team,
                "position": idx,
                "total_teams": len(rankings),
                "avg_points": row["avg_points"],
                "events": row["events"],
            }
            break

    if selected is not None:
        return selected

    return {
        "team_name": canonical_team,
        "position": None,
        "total_teams": len(rankings),
        "avg_points": None,
        "events": 0,
    }


def _radar_output_path(team_name: str, year: int, output_path: Optional[str] = None) -> Path:
    if output_path is not None and output_path.strip():
        return Path(output_path.strip())

    safe_team = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in team_name.strip()).strip("_")
    if not safe_team:
        safe_team = "team"
    return Path("data") / "tmp" / f"team_radar_{safe_team}_{year}.svg"


def render_team_radar_svg(result: Dict, output_path: Optional[str] = None) -> str:
    """Render a team radar report to SVG and return the written file path."""
    rounds = result["rounds"]
    if not rounds:
        raise ValueError("No round data available for radar rendering.")

    target_path = _radar_output_path(result["team_name"], result["year"], output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    width = 1100
    height = 940
    center_x = width / 2
    center_y = 470
    radius = 300
    ring_count = 5

    def polar_point(value: float, angle: float):
        distance = radius * max(0.0, min(1.0, value))
        return center_x + math.cos(angle) * distance, center_y + math.sin(angle) * distance

    def format_point(x: float, y: float) -> str:
        return f"{x:.1f},{y:.1f}"

    def series_points(key: str):
        points = []
        count = len(rounds)
        for index, row in enumerate(rounds):
            angle = -math.pi / 2 + (2 * math.pi * index / count)
            points.append(polar_point(float(row[key]), angle))
        return points

    avg_points = series_points("avg_score")
    placement_points = series_points("placement_score")

    labels = []
    count = len(rounds)
    for index, row in enumerate(rounds):
        angle = -math.pi / 2 + (2 * math.pi * index / count)
        label_x, label_y = polar_point(1.18, angle)
        position = row["position"]
        total_teams = row["total_teams"]
        if row["avg_points"] is None:
            subtitle = "keine Daten"
        else:
            subtitle = f"Ø {row['avg_points']:.2f} | Platz {position}/{total_teams}"
        labels.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="18" font-weight="600" fill="#1f2937">{escape(row["round_name"])}</text>'
            f'<text x="{label_x:.1f}" y="{label_y + 22:.1f}" text-anchor="middle" font-size="13" fill="#4b5563">{escape(subtitle)}</text>'
        )

    grid_rings = []
    for step in range(1, ring_count + 1):
        ring_radius = radius * step / ring_count
        grid_rings.append(
            f'<circle cx="{center_x:.1f}" cy="{center_y:.1f}" r="{ring_radius:.1f}" fill="none" stroke="#d6dbe6" stroke-width="1" />'
        )

    spokes = []
    for index, _row in enumerate(rounds):
        angle = -math.pi / 2 + (2 * math.pi * index / count)
        end_x, end_y = polar_point(1.0, angle)
        spokes.append(
            f'<line x1="{center_x:.1f}" y1="{center_y:.1f}" x2="{end_x:.1f}" y2="{end_y:.1f}" stroke="#d6dbe6" stroke-width="1" />'
        )

    def polygon_points(points):
        return " ".join(format_point(x, y) for x, y in points)

    avg_polygon = polygon_points(avg_points)
    placement_polygon = polygon_points(placement_points)

    avg_markers = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#2563eb" stroke="#ffffff" stroke-width="2" />'
        for x, y in avg_points
    )
    placement_markers = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#f97316" stroke="#ffffff" stroke-width="2" />'
        for x, y in placement_points
    )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f8fafc" />
  <rect x="26" y="26" width="{width - 52}" height="{height - 52}" rx="28" fill="#ffffff" stroke="#e5e7eb" />
  <text x="{center_x:.1f}" y="78" text-anchor="middle" font-size="30" font-weight="700" fill="#111827">Radar-Report für {escape(result["team_name"])} ({result["year"]})</text>
  <text x="{center_x:.1f}" y="112" text-anchor="middle" font-size="15" fill="#4b5563">Durchschnittspunkte und Platzierung pro Runde sind auf 0..1 normalisiert.</text>

  <g opacity="0.95">
    {''.join(grid_rings)}
    {''.join(spokes)}
  </g>

  <polygon points="{avg_polygon}" fill="#2563eb" fill-opacity="0.16" stroke="#2563eb" stroke-width="3" />
  <polygon points="{placement_polygon}" fill="#f97316" fill-opacity="0.14" stroke="#f97316" stroke-width="3" />
  {avg_markers}
  {placement_markers}

  <g>
    {''.join(labels)}
  </g>

  <g transform="translate(72, 834)">
    <rect x="0" y="0" width="228" height="58" rx="16" fill="#eff6ff" stroke="#bfdbfe" />
    <circle cx="24" cy="20" r="7" fill="#2563eb" />
    <text x="42" y="25" font-size="15" fill="#1f2937">Ø Punkte</text>
    <circle cx="24" cy="42" r="7" fill="#f97316" />
    <text x="42" y="47" font-size="15" fill="#1f2937">Platzierung</text>
  </g>
</svg>
'''

    target_path.write_text(svg, encoding="utf-8")
    return str(target_path)


def render_team_report_radar_svg(result: Dict, output_path: Optional[str] = None) -> str:
    """Render a minimalist radar plot for team reports (avg points only)."""
    rounds = result["rounds"]
    if not rounds:
        raise ValueError("No round data available for radar rendering.")

    axes = []
    for row in rounds:
        axis_max = TEAM_REPORT_ROUND_MAX_POINTS.get(row["round_name"], 5)
        axes.append(
            {
                "name": row["round_name"],
                "avg_points": row["avg_points"],
                "axis_max": axis_max,
            }
        )

    axes.append(
        {
            "name": "Puzzle",
            "avg_points": result.get("puzzle_average"),
            "axis_max": result.get("puzzle_max_points", TEAM_REPORT_PUZZLE_MAX_POINTS),
        }
    )

    overall_round_averages = result.get("overall_round_averages", {}) or {}
    overall_puzzle_average = result.get("overall_puzzle_average")

    avg_values = [float(axis["avg_points"]) for axis in axes if axis["avg_points"] is not None]
    if not avg_values:
        raise ValueError("No average round points available for radar rendering.")

    target_path = _radar_output_path(result["team_name"], result["year"], output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    width = 980
    height = 980
    center_x = width / 2
    center_y = height / 2
    radius = 360
    ring_count = 5

    def polar_point(normalized_value: float, angle: float):
        normalized = max(0.0, min(1.0, normalized_value))
        distance = radius * normalized
        return center_x + math.cos(angle) * distance, center_y + math.sin(angle) * distance

    def full_radius_point(angle: float):
        return center_x + math.cos(angle) * radius, center_y + math.sin(angle) * radius

    count = len(axes)
    polygon_points = []
    overall_polygon_points = []
    labels = []
    spokes = []

    for index, axis in enumerate(axes):
        angle = -math.pi / 2 + (2 * math.pi * index / count)
        avg_points = float(axis["avg_points"] or 0.0)
        axis_max = float(axis["axis_max"]) if axis["axis_max"] else 1.0
        normalized_points = avg_points / axis_max if axis_max else 0.0
        px, py = polar_point(normalized_points, angle)
        polygon_points.append((px, py))

        if axis["name"] == "Puzzle":
            overall_value = overall_puzzle_average
        else:
            overall_value = overall_round_averages.get(axis["name"])
        overall_normalized = (float(overall_value) / axis_max) if (overall_value is not None and axis_max) else 0.0
        ox, oy = polar_point(overall_normalized, angle)
        overall_polygon_points.append((ox, oy))

        sx, sy = full_radius_point(angle)
        spokes.append(
            f'<line x1="{center_x:.1f}" y1="{center_y:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="#d6dbe6" stroke-width="1" />'
        )

        lx, ly = center_x + math.cos(angle) * (radius + 38), center_y + math.sin(angle) * (radius + 38)
        value_text = "-" if axis["avg_points"] is None else f"{avg_points:.2f} Pts"
        labels.append(
            f'<text x="{lx:.1f}" y="{ly - 8:.1f}" text-anchor="middle" font-size="21" font-weight="600" fill="#1f2937">{escape(axis["name"])}</text>'
            f'<text x="{lx:.1f}" y="{ly + 13:.1f}" text-anchor="middle" font-size="17" fill="#4b5563">{escape(value_text)}</text>'
        )

    rings = []
    for step in range(1, ring_count + 1):
        ring_radius = radius * step / ring_count
        rings.append(
            f'<circle cx="{center_x:.1f}" cy="{center_y:.1f}" r="{ring_radius:.1f}" fill="none" stroke="#d6dbe6" stroke-width="1" />'
        )

    points_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in polygon_points)
    overall_points_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in overall_polygon_points)
    markers = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#2563eb" stroke="#ffffff" stroke-width="2" />'
        for x, y in polygon_points
    )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <g opacity="0.95">
    {''.join(rings)}
    {''.join(spokes)}
  </g>
    <polygon points="{overall_points_text}" fill="none" stroke="#7dd3fc" stroke-width="2.5" stroke-dasharray="10 8" />
  <polygon points="{points_text}" fill="#2563eb" fill-opacity="0.18" stroke="#2563eb" stroke-width="3" />
  {markers}
  <g>
    {''.join(labels)}
  </g>
</svg>
'''

    target_path.write_text(svg, encoding="utf-8")
    return str(target_path)


def render_team_report_position_radar_svg(result: Dict, output_path: Optional[str] = None) -> str:
    """Render a minimalist radar plot for team reports (placement only)."""
    rounds = result["rounds"]
    if not rounds:
        raise ValueError("No round data available for placement radar rendering.")

    axes = list(rounds)
    axes.append(
        {
            "round_name": "Puzzle",
            "position": result.get("puzzle_position"),
            "total_teams": result.get("puzzle_total_teams", 0),
        }
    )

    if output_path is not None and output_path.strip():
        target_path = Path(output_path.strip())
    else:
        safe_team = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in result["team_name"].strip()).strip("_")
        if not safe_team:
            safe_team = "team"
        target_path = Path("data") / "tmp" / f"team_radar_pos_{safe_team}_{result['year']}.svg"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    width = 980
    height = 980
    center_x = width / 2
    center_y = height / 2
    radius = 360
    ring_count = 5

    def polar_point(normalized_value: float, angle: float):
        normalized = max(0.0, min(1.0, normalized_value))
        distance = radius * normalized
        return center_x + math.cos(angle) * distance, center_y + math.sin(angle) * distance

    def full_radius_point(angle: float):
        return center_x + math.cos(angle) * radius, center_y + math.sin(angle) * radius

    count = len(axes)
    polygon_points = []
    labels = []
    spokes = []

    for index, row in enumerate(axes):
        angle = -math.pi / 2 + (2 * math.pi * index / count)
        position = row.get("position")
        total_teams = row.get("total_teams") or 0

        if position is None or total_teams <= 0:
            normalized_pos = 0.0
            pos_text = "Pos. -"
        elif total_teams == 1:
            normalized_pos = 1.0
            pos_text = "Pos. 1"
        else:
            normalized_pos = max(0.0, min(1.0, (total_teams - float(position)) / (total_teams - 1)))
            pos_text = f"Pos. {int(position)}"

        px, py = polar_point(normalized_pos, angle)
        polygon_points.append((px, py))

        sx, sy = full_radius_point(angle)
        spokes.append(
            f'<line x1="{center_x:.1f}" y1="{center_y:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="#d6dbe6" stroke-width="1" />'
        )

        lx, ly = center_x + math.cos(angle) * (radius + 38), center_y + math.sin(angle) * (radius + 38)
        labels.append(
            f'<text x="{lx:.1f}" y="{ly - 8:.1f}" text-anchor="middle" font-size="21" font-weight="600" fill="#1f2937">{escape(row["round_name"])}</text>'
            f'<text x="{lx:.1f}" y="{ly + 13:.1f}" text-anchor="middle" font-size="17" fill="#4b5563">{escape(pos_text)}</text>'
        )

    rings = []
    for step in range(1, ring_count + 1):
        ring_radius = radius * step / ring_count
        rings.append(
            f'<circle cx="{center_x:.1f}" cy="{center_y:.1f}" r="{ring_radius:.1f}" fill="none" stroke="#d6dbe6" stroke-width="1" />'
        )

    points_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in polygon_points)
    markers = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#f97316" stroke="#ffffff" stroke-width="2" />'
        for x, y in polygon_points
    )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <g opacity="0.95">
    {''.join(rings)}
    {''.join(spokes)}
  </g>
  <polygon points="{points_text}" fill="#f97316" fill-opacity="0.18" stroke="#f97316" stroke-width="3" />
  {markers}
  <g>
    {''.join(labels)}
  </g>
</svg>
'''

    target_path.write_text(svg, encoding="utf-8")
    return str(target_path)


def render_team_report_event_bars_svg(result: Dict, output_path: Optional[str] = None) -> str:
    """Render a wide season event bar chart for points and placement."""
    events = result.get("season_events", [])
    if not events:
        raise ValueError("No event data available for season chart rendering.")

    if output_path is not None and output_path.strip():
        target_path = Path(output_path.strip())
    else:
        safe_team = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in result["team_name"].strip()).strip("_")
        if not safe_team:
            safe_team = "team"
        target_path = Path("data") / "tmp" / f"team_events_{safe_team}_{result['year']}.svg"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    width = 1600
    height = 760
    margin_left = 95
    margin_right = 45
    margin_top = 48
    margin_bottom = 155
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    baseline_y = margin_top + plot_height

    points_axis_min = float(result.get("points_axis_min", 30.0))
    points_axis_max = float(result.get("points_axis_max", points_axis_min))
    position_axis_min = 1.0
    position_axis_max = float(result.get("position_axis_max", 1.0))

    event_slot_width = plot_width / max(1, len(events))
    group_width = min(110.0, event_slot_width * 0.72)
    bar_width = min(40.0, group_width * 0.36)
    bar_gap = min(14.0, group_width * 0.12)

    def points_height(points_value: float) -> float:
        if points_axis_max <= points_axis_min:
            normalized = 1.0 if points_value >= points_axis_max else 0.0
        else:
            normalized = (points_value - points_axis_min) / (points_axis_max - points_axis_min)
        return plot_height * max(0.0, min(1.0, normalized))

    def position_height(position_value: Optional[int]) -> float:
        if position_value is None:
            return 0.0
        if position_axis_max <= position_axis_min:
            return plot_height
        normalized = (position_axis_max - float(position_value)) / (position_axis_max - position_axis_min)
        return plot_height * max(0.0, min(1.0, normalized))

    grid_lines = []
    for step in range(6):
        y = margin_top + plot_height * step / 5
        grid_lines.append(
            f'<line x1="{margin_left:.1f}" y1="{y:.1f}" x2="{width - margin_right:.1f}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1" />'
        )

    bars = []
    labels = []
    value_labels = []
    x_axis = [
        f'<line x1="{margin_left:.1f}" y1="{baseline_y:.1f}" x2="{width - margin_right:.1f}" y2="{baseline_y:.1f}" stroke="#cbd5e1" stroke-width="1.5" />'
    ]

    for idx, event in enumerate(events):
        group_center = margin_left + event_slot_width * idx + event_slot_width / 2
        points_value = float(event.get("total_points") or 0)
        position_value = event.get("position")

        points_bar_height = points_height(points_value)
        position_bar_height = position_height(position_value)

        points_x = group_center - bar_gap / 2 - bar_width
        position_x = group_center + bar_gap / 2
        points_y = baseline_y - points_bar_height
        position_y = baseline_y - position_bar_height

        bars.append(
            f'<rect x="{points_x:.1f}" y="{points_y:.1f}" width="{bar_width:.1f}" height="{points_bar_height:.1f}" rx="7" fill="#2563eb" />'
        )
        bars.append(
            f'<rect x="{position_x:.1f}" y="{position_y:.1f}" width="{bar_width:.1f}" height="{position_bar_height:.1f}" rx="7" fill="#f97316" />'
        )

        value_labels.append(
            f'<text x="{(points_x + bar_width / 2):.1f}" y="{max(20.0, points_y - 10):.1f}" text-anchor="middle" font-size="18" font-weight="600" fill="#1e3a8a">{points_value:.0f} Pts</text>'
        )
        pos_label = f"Pos. {int(position_value)}" if position_value is not None else "Pos. -"
        value_labels.append(
            f'<text x="{(position_x + bar_width / 2):.1f}" y="{max(20.0, position_y - 10):.1f}" text-anchor="middle" font-size="18" font-weight="600" fill="#c2410c">{pos_label}</text>'
        )

        date_text = escape(str(event.get("event_date", "")))
        location_raw = str(event.get("location", "")).strip()
        if location_raw.casefold() == "gloriousbastards":
            location_raw = "Bastards"
        location_text = escape(location_raw[:18])
        labels.append(
            f'<text x="{group_center:.1f}" y="{baseline_y + 40:.1f}" text-anchor="end" font-size="18" font-weight="600" fill="#111827" transform="rotate(-90 {group_center:.1f} {baseline_y + 40:.1f})">{date_text}</text>'
            f'<text x="{group_center + 22:.1f}" y="{baseline_y + 40:.1f}" text-anchor="end" font-size="16" fill="#6b7280" transform="rotate(-90 {group_center + 22:.1f} {baseline_y + 40:.1f})">{location_text}</text>'
        )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <g opacity="0.95">{''.join(grid_lines)}</g>
  <g>{''.join(x_axis)}</g>
  <g>{''.join(bars)}</g>
  <g>{''.join(value_labels)}</g>
  <g>{''.join(labels)}</g>
</svg>
'''

    target_path.write_text(svg, encoding="utf-8")
    return str(target_path)


def print_team_radar_report(
    team_name: str,
    year: int,
    min_events: int = 2,
    output_path: Optional[str] = None,
    db_path: str = DB_PATH_DEFAULT,
) -> None:
    """Print a team radar report and export an SVG radar plot."""
    result = get_team_radar_report(team_name=team_name, year=year, min_events=min_events, db_path=db_path)

    print(f"Radar report for {result['team_name']} ({result['year']})")
    print(f"Minimum events per round: {result['min_events']}")
    print()

    if not result["rounds"]:
        print("No round data found for this team in this year.")
        return

    print(f"{'Round':20}  {'Avg':>6}  {'Pos':>5}  {'Of':>4}  {'Norm Avg':>8}  {'Norm Pos':>8}")
    print("""--------------------  ------  -----  ----  --------  --------""")

    if not any(row["avg_points"] is not None for row in result["rounds"]):
        print("No round data found for this team in this year.")
        return

    for row in result["rounds"]:
        avg_text = f"{row['avg_points']:.2f}" if row["avg_points"] is not None else "-"
        pos_text = f"{row['position']}" if row["position"] is not None else "-"
        of_text = f"{row['total_teams']}" if row["total_teams"] else "-"
        print(
            f"{row['round_name'][:20]:20}  {avg_text:>6}  {pos_text:>5}  {of_text:>4}  {row['avg_score']:>8.2f}  {row['placement_score']:>8.2f}"
        )

    svg_path = render_team_radar_svg(result, output_path=output_path)
    print()
    print(f"Radar plot saved to: {svg_path}")


def get_team_bonus_efficiency_report(
    team_name: str,
    year: int,
    db_path: str = DB_PATH_DEFAULT,
) -> Dict:
    """Return per-event bonus efficiency and average for one team."""
    season_result = get_team_season_results(team_name, year, db_path)
    events = season_result["events"]

    team_ids = [event["team_id"] for event in events if event.get("team_id") is not None]
    score_rows: Dict[int, List[sqlite3.Row]] = {}
    if team_ids:
        placeholders = ",".join("?" * len(team_ids))
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT team_id, round_name, points
                FROM team_scores
                WHERE team_id IN ({placeholders})
                """,
                team_ids,
            ).fetchall()
        for row in rows:
            score_rows.setdefault(row["team_id"], []).append(row)

    result_events = []
    efficiency_values = []

    for event in events:
        selected_bonus_round = (event.get("bonus_round") or "").strip()
        rows_for_team = score_rows.get(event.get("team_id"), [])

        possible_candidates = []
        achieved_bonus_points = 0.0

        for row in rows_for_team:
            round_name = str(row["round_name"])
            raw_points = row["points"]
            if raw_points is None:
                continue

            observed_points = max(0.0, float(raw_points))
            if selected_bonus_round and round_name.casefold() == selected_bonus_round.casefold():
                observed_points = float(math.floor(observed_points / 2.0))
                achieved_bonus_points = observed_points

            possible_candidates.append(_bonus_points_from_normal_points(round_name, observed_points))

        possible_bonus_points = max(possible_candidates) if possible_candidates else 0.0
        bonus_efficiency = None
        if possible_bonus_points > 0.0:
            bonus_efficiency = achieved_bonus_points / possible_bonus_points
            efficiency_values.append(bonus_efficiency)

        result_events.append(
            {
                **event,
                "achieved_bonus_points": achieved_bonus_points,
                "possible_bonus_points": possible_bonus_points,
                "bonus_efficiency": bonus_efficiency,
            }
        )

    average_bonus_efficiency = (
        sum(efficiency_values) / len(efficiency_values) if efficiency_values else None
    )

    return {
        "team_name": season_result["team_name"],
        "year": year,
        "events": result_events,
        "average_bonus_efficiency": average_bonus_efficiency,
    }


def print_team_bonus_efficiency_report(
    team_name: str,
    year: int,
    db_path: str = DB_PATH_DEFAULT,
) -> None:
    """Print per-event bonus efficiency and its average for one team."""
    result = get_team_bonus_efficiency_report(team_name, year, db_path)
    events = result["events"]

    print(f"Bonus efficiency report for {result['team_name']} ({result['year']})")
    print()

    if not events:
        print("No events found for this team in this year.")
        return

    print(f"{'Date':10}  {'Location':20}  {'Bonus Round':14}  {'Achieved':>8}  {'Possible':>8}  {'Eff':>7}")
    print("""----------  --------------------  --------------  --------  --------  -------""")

    for event in events:
        efficiency = event["bonus_efficiency"]
        efficiency_text = "-" if efficiency is None else f"{efficiency * 100:6.1f}%"
        print(
            f"{event['event_date']:10}  {event['location'][:20]:20}  {(event.get('bonus_round') or '-')[:14]:14}  {event['achieved_bonus_points']:>8.1f}  {event['possible_bonus_points']:>8.1f}  {efficiency_text:>7}"
        )

    print("""----------  --------------------  --------------  --------  --------  -------""")
    average = result["average_bonus_efficiency"]
    if average is None:
        print("Average bonus efficiency: -")
    else:
        print(f"Average bonus efficiency: {average * 100:.1f}%")


def get_team_profile_report(
    team_name: str,
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> Dict:
    """Return a consolidated team profile summary with radar chart output."""
    season_result = get_team_season_results(team_name, year, db_path)
    averages_result = get_team_round_averages(team_name, year, db_path)
    overall_averages_result = get_overall_round_averages(year, db_path)
    championship = get_championship_standings(year, db_path)
    radar_result = get_team_radar_report(team_name, year, min_events=min_events, db_path=db_path)
    radar_render_input = {
        **radar_result,
        "puzzle_average": averages_result["puzzle_average"],
        "puzzle_max_points": TEAM_REPORT_PUZZLE_MAX_POINTS,
        "overall_round_averages": overall_averages_result["round_averages"],
        "overall_puzzle_average": overall_averages_result["puzzle_average"],
    }
    puzzle_ranking = get_team_puzzle_ranking(team_name, year, min_events=min_events, db_path=db_path)
    radar_position_render_input = {
        **radar_result,
        "puzzle_position": puzzle_ranking["position"],
        "puzzle_total_teams": puzzle_ranking["total_teams"],
    }
    event_chart_render_input = {
        "team_name": season_result["team_name"],
        "year": year,
        "season_events": season_result["events"],
        "position_axis_max": float(championship["teams_count"] or 1),
        "points_axis_min": 30.0,
    }

    with _connect(db_path) as conn:
        best_total_row = conn.execute(
            """
            SELECT MAX(total) AS max_total
            FROM quiz_teams
            WHERE total IS NOT NULL
            """
        ).fetchone()
    event_chart_render_input["points_axis_max"] = float(best_total_row["max_total"]) if best_total_row and best_total_row["max_total"] is not None else 30.0
    radar_svg_path = render_team_report_radar_svg(radar_render_input)
    radar_position_svg_path = render_team_report_position_radar_svg(radar_position_render_input)

    bonus_efficiency_result = get_team_bonus_efficiency_report(team_name, year, db_path)
    events = bonus_efficiency_result["events"]

    total_points = sum(event["total_points"] or 0 for event in events)
    participation_count = len(events)
    average_points = (total_points / participation_count) if participation_count else None
    average_bonus_efficiency = bonus_efficiency_result["average_bonus_efficiency"]

    best_result = None
    if events:
        best_result = max(events, key=lambda event: event["total_points"] or 0)

    best_bonus_category = None
    if averages_result["round_averages"]:
        best_bonus_category = max(
            averages_result["round_averages"],
            key=lambda row: row["avg_points"] if row["avg_points"] is not None else float("-inf"),
        )

    championship_place = None
    championship_points = None
    for position, row in enumerate(championship["standings"], start=1):
        if row["team_name"].casefold() == season_result["team_name"].casefold():
            championship_place = position
            championship_points = row["points"]
            break

    return {
        "team_name": season_result["team_name"],
        "year": year,
        "participation_count": participation_count,
        "year_events_count": championship["events_count"],
        "teams_total": championship["teams_count"],
        "championship_points": championship_points,
        "championship_place": championship_place,
        "average_points": average_points,
        "bonus_efficiency_avg": average_bonus_efficiency,
        "best_bonus_category": best_bonus_category,
        "best_result": best_result,
        "radar_svg_path": radar_svg_path,
        "radar_position_svg_path": radar_position_svg_path,
        "event_chart_svg_path": render_team_report_event_bars_svg(event_chart_render_input),
        "season_events": events,
        "radar_rounds": radar_result["rounds"],
        "puzzle_average": averages_result["puzzle_average"],
        "puzzle_max_points": TEAM_REPORT_PUZZLE_MAX_POINTS,
        "round_averages": averages_result["round_averages"],
    }


def print_team_round_averages(team_name: str, year: int, db_path: str = DB_PATH_DEFAULT) -> None:
    """Print average points per round for a team in a given year."""
    result = get_team_round_averages(team_name, year, db_path)
    
    print(f"Round averages for {result['team_name']} ({result['year']})")
    print()
    
    if not result["round_averages"]:
        print("No data found for this team in this year.")
        return
    
    print(f"{'Round':>20}  {'Avg Points':>11}  {'Events'}")
    print("""--------------------  -----------  ------""")
    
    for round_info in result["round_averages"]:
        print(
            f"{round_info['round_name']:>20}  {round_info['avg_points']:>11.2f}  {round_info['appearances']:>6}"
        )
    
    print("""--------------------  -----------  ------""")
    if result["puzzle_average"] is not None:
        print(f"Puzzle average: {result['puzzle_average']:.2f}")


def get_consistency_report(year: int, min_events: int = 2, db_path: str = DB_PATH_DEFAULT) -> Dict:
    """Return team consistency metrics for a given year.

    Consistency is measured via standard deviation of event totals.
    Lower stddev means more consistent performance.
    """
    year_prefix = f"{year:04d}-%"

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                e.id AS event_id,
                t.team_name,
                t.total
            FROM quiz_events e
            JOIN quiz_teams t ON t.event_id = e.id
            WHERE e.event_date LIKE ?
            ORDER BY e.event_date ASC, e.location ASC
            """,
            (year_prefix,),
        ).fetchall()

    by_team: Dict[str, Dict[int, int]] = {}
    for row in rows:
        canonical = _canonical_team_name(row["team_name"])
        event_id = row["event_id"]
        total = row["total"] if row["total"] is not None else 0
        if canonical not in by_team:
            by_team[canonical] = {}

        # If aliases accidentally appear twice in one event, keep the higher total.
        previous = by_team[canonical].get(event_id)
        if previous is None or total > previous:
            by_team[canonical][event_id] = total

    standings = []
    for team_name, event_totals_map in by_team.items():
        totals = list(event_totals_map.values())
        events_count = len(totals)
        if events_count < min_events:
            continue

        avg_points = sum(totals) / events_count
        variance = sum((x - avg_points) ** 2 for x in totals) / events_count
        stddev = variance ** 0.5
        cv = (stddev / avg_points * 100) if avg_points > 0 else 0.0

        standings.append(
            {
                "team_name": team_name,
                "events": events_count,
                "avg_points": avg_points,
                "stddev": stddev,
                "cv_percent": cv,
                "min_points": min(totals),
                "max_points": max(totals),
            }
        )

    standings.sort(key=lambda s: (-s["avg_points"], s["stddev"], s["team_name"].lower()))

    return {
        "year": year,
        "min_events": min_events,
        "teams_count": len(standings),
        "standings": standings,
    }


def print_consistency_report(year: int, min_events: int = 2, db_path: str = DB_PATH_DEFAULT) -> None:
    """Print team consistency report for a given year."""
    result = get_consistency_report(year=year, min_events=min_events, db_path=db_path)
    standings = result["standings"]

    print(f"Consistency report {result['year']}")
    print(f"Minimum events: {result['min_events']}")
    print(f"Teams: {result['teams_count']}")
    print()

    if not standings:
        print("No teams found for this year and filter.")
        return

    print(
        f"{'Pos':>4}  {'Team':30}  {'Events':>6}  {'Avg':>6}  {'StdDev':>7}  {'CV%':>6}  {'Min':>4}  {'Max':>4}"
    )
    print("""----  ------------------------------  ------  ------  -------  ------  ----  ----""")

    for pos, team in enumerate(standings, start=1):
        print(
            f"{pos:>4}  {team['team_name'][:30]:30}  {team['events']:>6}  {team['avg_points']:>6.2f}  {team['stddev']:>7.2f}  {team['cv_percent']:>6.2f}  {team['min_points']:>4}  {team['max_points']:>4}"
        )


def get_round_difficulty_report(year: int, db_path: str = DB_PATH_DEFAULT) -> Dict:
    """Return round difficulty metrics for a given year.

    Difficulty is measured by lower average points (harder rounds first).
    Bonus-round points are normalized back to normal scoring before aggregation.
    """
    year_prefix = f"{year:04d}-%"
    round_order = {name: idx for idx, name in ROUND_NAMES.items()}

    with _connect(db_path) as conn:
        events_count_row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM quiz_events
            WHERE event_date LIKE ?
            """,
            (year_prefix,),
        ).fetchone()

        rows = conn.execute(
            """
            WITH ranked_teams AS (
                SELECT
                    t.id,
                    t.event_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.event_id
                        ORDER BY COALESCE(t.team_rank, 9999), t.total DESC, t.puzzle_points DESC, t.team_name ASC
                    ) AS rn
                FROM quiz_teams t
                JOIN quiz_events e ON e.id = t.event_id
                WHERE e.event_date LIKE ?
            )
            SELECT
                ts.round_name,
                CASE
                    WHEN ts.round_name = qt.bonus_round THEN
                        CASE
                            WHEN ts.points % 2 = 0 THEN ts.points / 2
                            ELSE (ts.points - 1) / 2
                        END
                    ELSE ts.points
                END AS adjusted_points
            FROM team_scores ts
            JOIN quiz_teams qt ON qt.id = ts.team_id
                        JOIN ranked_teams rt ON rt.id = qt.id
                        WHERE rt.rn <= 30
              AND ts.points IS NOT NULL
            """,
            (year_prefix,),
        ).fetchall()

    grouped: Dict[str, List[float]] = {}
    for row in rows:
        round_name = row["round_name"]
        adjusted_points = float(row["adjusted_points"])
        grouped.setdefault(round_name, []).append(adjusted_points)

    rounds = []
    for round_name, values in grouped.items():
        count = len(values)
        if count == 0:
            continue

        avg_points = sum(values) / count
        variance = sum((x - avg_points) ** 2 for x in values) / count
        stddev = variance ** 0.5

        rounds.append(
            {
                "round_name": round_name,
                "samples": count,
                "avg_points": avg_points,
                "stddev": stddev,
                "min_points": min(values),
                "max_points": max(values),
            }
        )

    rounds.sort(key=lambda r: (r["avg_points"], round_order.get(r["round_name"], 999)))

    return {
        "year": year,
        "events_count": events_count_row["c"] if events_count_row else 0,
        "rounds_count": len(rounds),
        "rounds": rounds,
    }


def print_round_difficulty_report(year: int, db_path: str = DB_PATH_DEFAULT) -> None:
    """Print round difficulty report for a given year."""
    result = get_round_difficulty_report(year=year, db_path=db_path)
    rounds = result["rounds"]

    print(f"Round difficulty report {result['year']}")
    print(f"Events: {result['events_count']}")
    print(f"Rounds: {result['rounds_count']}")
    print()

    if not rounds:
        print("No round data found for this year.")
        return

    print(f"{'Pos':>4}  {'Round':20}  {'Avg':>6}  {'StdDev':>7}  {'Min':>4}  {'Max':>4}  {'Samples':>7}")
    print("""----  --------------------  ------  -------  ----  ----  -------""")
    for pos, row in enumerate(rounds, start=1):
        print(
            f"{pos:>4}  {row['round_name'][:20]:20}  {row['avg_points']:>6.2f}  {row['stddev']:>7.2f}  {row['min_points']:>4.1f}  {row['max_points']:>4.1f}  {row['samples']:>7}"
        )


def get_event_difficulty_report(
    db_path: str = DB_PATH_DEFAULT,
    event_id: Optional[int] = None,
    source_file: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict:
    """Compare round averages in one event with all other events of the same year."""
    resolved_event_id = _resolve_event_id(
        db_path, event_id=event_id, source_file=source_file, event_date=event_date, location=location
    )

    with _connect(db_path) as conn:
        event = conn.execute(
            """
            SELECT id, event_date, location, source_file
            FROM quiz_events
            WHERE id = ?
            """,
            (resolved_event_id,),
        ).fetchone()
        if event is None:
            raise ValueError(f"No event found with id={resolved_event_id}")

        year_prefix = f"{int(event['event_date'][:4]):04d}-%"

        event_rows = conn.execute(
            """
            WITH ranked_teams AS (
                SELECT
                    t.id,
                    t.event_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.event_id
                        ORDER BY COALESCE(t.team_rank, 9999), t.total DESC, t.puzzle_points DESC, t.team_name ASC
                    ) AS rn
                FROM quiz_teams t
                WHERE t.event_id = ?
            )
            SELECT
                ts.round_name,
                AVG(
                    CASE
                        WHEN ts.round_name = qt.bonus_round THEN
                            CASE
                                WHEN ts.points % 2 = 0 THEN ts.points / 2
                                ELSE (ts.points - 1) / 2
                            END
                        ELSE ts.points
                    END
                ) AS avg_points,
                COUNT(*) AS samples
            FROM team_scores ts
            JOIN quiz_teams qt ON qt.id = ts.team_id
            JOIN ranked_teams rt ON rt.id = qt.id
            WHERE qt.event_id = ?
              AND rt.rn <= 30
              AND ts.points IS NOT NULL
            GROUP BY ts.round_name
            """,
            (resolved_event_id, resolved_event_id),
        ).fetchall()

        other_rows = conn.execute(
            """
            WITH ranked_teams AS (
                SELECT
                    t.id,
                    t.event_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.event_id
                        ORDER BY COALESCE(t.team_rank, 9999), t.total DESC, t.puzzle_points DESC, t.team_name ASC
                    ) AS rn
                FROM quiz_teams t
                JOIN quiz_events e ON e.id = t.event_id
                WHERE e.event_date LIKE ?
            )
            SELECT
                ts.round_name,
                AVG(
                    CASE
                        WHEN ts.round_name = qt.bonus_round THEN
                            CASE
                                WHEN ts.points % 2 = 0 THEN ts.points / 2
                                ELSE (ts.points - 1) / 2
                            END
                        ELSE ts.points
                    END
                ) AS avg_points,
                COUNT(*) AS samples
            FROM team_scores ts
            JOIN quiz_teams qt ON qt.id = ts.team_id
                        JOIN ranked_teams rt ON rt.id = qt.id
                        WHERE rt.rn <= 30
                            AND qt.event_id != ?
              AND ts.points IS NOT NULL
            GROUP BY ts.round_name
            """,
                        (year_prefix, resolved_event_id),
        ).fetchall()

    event_map = {row["round_name"]: {"avg_points": row["avg_points"], "samples": row["samples"]} for row in event_rows}
    other_map = {row["round_name"]: {"avg_points": row["avg_points"], "samples": row["samples"]} for row in other_rows}

    round_order = {name: idx for idx, name in ROUND_NAMES.items()}
    round_names = sorted(
        set(event_map.keys()) | set(other_map.keys()),
        key=lambda name: round_order.get(name, 999),
    )

    rounds = []
    for round_name in round_names:
        event_avg = event_map.get(round_name, {}).get("avg_points")
        other_avg = other_map.get(round_name, {}).get("avg_points")
        diff = (event_avg - other_avg) if event_avg is not None and other_avg is not None else None

        rounds.append(
            {
                "round_name": round_name,
                "event_avg": event_avg,
                "other_avg": other_avg,
                "diff": diff,
                "event_samples": event_map.get(round_name, {}).get("samples", 0),
                "other_samples": other_map.get(round_name, {}).get("samples", 0),
            }
        )

    return {
        "event": dict(event),
        "year": int(event["event_date"][:4]),
        "rounds": rounds,
    }


def print_event_difficulty_report(
    db_path: str = DB_PATH_DEFAULT,
    event_id: Optional[int] = None,
    source_file: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
) -> None:
    """Print event round-average comparison against other events in same year."""
    result = get_event_difficulty_report(
        db_path=db_path,
        event_id=event_id,
        source_file=source_file,
        event_date=event_date,
        location=location,
    )
    event = result["event"]

    print(f"Event difficulty report: {event['event_date']} @ {event['location']} ({event['source_file']})")
    print(f"Comparison baseline: all other events in {result['year']}")
    print()

    if not result["rounds"]:
        print("No round data found for this event.")
        return

    print(f"{'Round':20}  {'Event Avg':>9}  {'Other Avg':>9}  {'Diff':>8}  {'N_evt':>5}  {'N_oth':>5}")
    print("""--------------------  ---------  ---------  --------  -----  -----""")
    for row in result["rounds"]:
        event_avg_text = f"{row['event_avg']:.2f}" if row["event_avg"] is not None else "-"
        other_avg_text = f"{row['other_avg']:.2f}" if row["other_avg"] is not None else "-"
        diff_text = f"{row['diff']:+.2f}" if row["diff"] is not None else "-"
        print(
            f"{row['round_name'][:20]:20}  {event_avg_text:>9}  {other_avg_text:>9}  {diff_text:>8}  {row['event_samples']:>5}  {row['other_samples']:>5}"
        )


def get_round_strength_ranking(
    year: int,
    round_name: Optional[str] = None,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> Dict:
    """Return league-wide team strength ranking per round for a given year."""
    year_prefix = f"{year:04d}-%"
    allowed_rounds = set(ROUND_NAMES.values())
    if round_name is not None and round_name not in allowed_rounds:
        raise ValueError(
            f"Unknown round '{round_name}'. Allowed values: {', '.join(ROUND_NAMES.values())}"
        )

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                qt.team_name,
                ts.round_name,
                CASE
                    WHEN ts.round_name = qt.bonus_round THEN
                        CASE
                            WHEN ts.points % 2 = 0 THEN ts.points / 2
                            ELSE (ts.points - 1) / 2
                        END
                    ELSE ts.points
                END AS adjusted_points
            FROM team_scores ts
            JOIN quiz_teams qt ON qt.id = ts.team_id
            JOIN quiz_events e ON e.id = qt.event_id
            WHERE e.event_date LIKE ?
              AND ts.points IS NOT NULL
            """,
            (year_prefix,),
        ).fetchall()

    round_team_scores: Dict[str, Dict[str, List[float]]] = {}
    for row in rows:
        row_round = row["round_name"]
        if row_round not in allowed_rounds:
            continue
        if round_name is not None and row_round != round_name:
            continue

        team = _canonical_team_name(row["team_name"])
        round_team_scores.setdefault(row_round, {}).setdefault(team, []).append(float(row["adjusted_points"]))

    round_order = {name: idx for idx, name in ROUND_NAMES.items()}
    rankings = []
    for row_round in sorted(round_team_scores.keys(), key=lambda r: round_order.get(r, 999)):
        team_rows = []
        for team_name, values in round_team_scores[row_round].items():
            events = len(values)
            if events < min_events:
                continue
            avg_points = sum(values) / events
            team_rows.append(
                {
                    "team_name": team_name,
                    "avg_points": avg_points,
                    "events": events,
                    "best": max(values),
                    "worst": min(values),
                }
            )

        team_rows.sort(key=lambda t: (-t["avg_points"], -t["events"], t["team_name"].lower()))
        rankings.append({"round_name": row_round, "teams": team_rows})

    return {
        "year": year,
        "min_events": min_events,
        "rankings": rankings,
    }


def print_round_strength_ranking(
    year: int,
    round_name: Optional[str] = None,
    min_events: int = 2,
    top: int = 10,
    team_name: Optional[str] = None,
    db_path: str = DB_PATH_DEFAULT,
) -> None:
    """Print league-wide team strength ranking per round."""
    result = get_round_strength_ranking(
        year=year,
        round_name=round_name,
        min_events=min_events,
        db_path=db_path,
    )

    print(f"Round strength ranking {result['year']}")
    print(f"Minimum events per team/round: {result['min_events']}")
    selected_team = _canonical_team_name(team_name) if team_name else None
    if selected_team is not None:
        print(f"Team filter: {selected_team}")
    print()

    if not result["rankings"]:
        print("No round data found for this year and filter.")
        return

    for block in result["rankings"]:
        print(f"{block['round_name']}")
        if not block["teams"]:
            print("  No teams match the filter.")
            print()
            continue

        if selected_team is not None:
            selected_row = None
            for pos, team in enumerate(block["teams"], start=1):
                if team["team_name"].casefold() == selected_team.casefold():
                    selected_row = (pos, team)
                    break

            if selected_row is None:
                print("  Team not ranked in this round (filter/min-events).")
                print()
                continue

            pos, team = selected_row
            total_ranked = len(block["teams"])
            print(f"{'Pos':>4}  {'Team':30}  {'Avg':>6}  {'Events':>6}  {'Best':>5}  {'Worst':>5}  {'Of':>4}")
            print("""----  ------------------------------  ------  ------  -----  -----  ----""")
            print(
                f"{pos:>4}  {team['team_name'][:30]:30}  {team['avg_points']:>6.2f}  {team['events']:>6}  {team['best']:>5.1f}  {team['worst']:>5.1f}  {total_ranked:>4}"
            )
            print()
            continue

        print(f"{'Pos':>4}  {'Team':30}  {'Avg':>6}  {'Events':>6}  {'Best':>5}  {'Worst':>5}")
        print("""----  ------------------------------  ------  ------  -----  -----""")
        for pos, team in enumerate(block["teams"][:top], start=1):
            print(
                f"{pos:>4}  {team['team_name'][:30]:30}  {team['avg_points']:>6.2f}  {team['events']:>6}  {team['best']:>5.1f}  {team['worst']:>5.1f}"
            )
        print()


def _get_puzzle_leaderboard(
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> List[Dict]:
    """Return puzzle average ranking across teams for one year."""
    year_prefix = f"{year:04d}-%"

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                qt.team_name,
                qt.event_id,
                qt.puzzle_points
            FROM quiz_teams qt
            JOIN quiz_events e ON e.id = qt.event_id
            WHERE e.event_date LIKE ?
              AND qt.puzzle_points IS NOT NULL
            """,
            (year_prefix,),
        ).fetchall()

    by_team: Dict[str, Dict[int, float]] = {}
    for row in rows:
        team = _canonical_team_name(row["team_name"])
        event_id = row["event_id"]
        value = float(row["puzzle_points"])
        by_team.setdefault(team, {})

        # If aliases appear multiple times in one event, keep the better puzzle score.
        previous = by_team[team].get(event_id)
        if previous is None or value > previous:
            by_team[team][event_id] = value

    ranking = []
    for team_name, per_event in by_team.items():
        values = list(per_event.values())
        events = len(values)
        if events < min_events:
            continue
        avg_points = sum(values) / events
        ranking.append(
            {
                "team_name": team_name,
                "avg_points": avg_points,
                "events": events,
            }
        )

    ranking.sort(key=lambda row: (-row["avg_points"], -row["events"], row["team_name"].lower()))
    return ranking


def _get_points_average_leaderboard(
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> List[Dict]:
    """Return average total-points leaderboard across teams for one year."""
    year_prefix = f"{year:04d}-%"

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                qt.team_name,
                qt.event_id,
                qt.total,
                qt.team_rank
            FROM quiz_teams qt
            JOIN quiz_events e ON e.id = qt.event_id
            WHERE e.event_date LIKE ?
            """,
            (year_prefix,),
        ).fetchall()

    # Keep one canonical row per team/event, preferring better rank then higher score.
    by_team_event: Dict[str, Dict[int, Dict]] = {}
    for row in rows:
        team_name = _canonical_team_name(row["team_name"])
        event_id = row["event_id"]
        candidate = {
            "rank": row["team_rank"] if row["team_rank"] is not None else 9999,
            "total": float(row["total"] if row["total"] is not None else 0),
        }

        by_team_event.setdefault(team_name, {})
        existing = by_team_event[team_name].get(event_id)
        if existing is None:
            by_team_event[team_name][event_id] = candidate
            continue

        if candidate["rank"] < existing["rank"] or (
            candidate["rank"] == existing["rank"] and candidate["total"] > existing["total"]
        ):
            by_team_event[team_name][event_id] = candidate

    ranking = []
    for team_name, per_event in by_team_event.items():
        totals = [row["total"] for row in per_event.values()]
        events = len(totals)
        if events < min_events:
            continue

        avg_points = sum(totals) / events
        ranking.append(
            {
                "team_name": team_name,
                "avg_points": avg_points,
                "events": events,
            }
        )

    ranking.sort(key=lambda row: (-row["avg_points"], -row["events"], row["team_name"].lower()))
    return ranking


def _get_bonus_efficiency_leaderboard(
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> List[Dict]:
    """Return bonus-efficiency leaderboard across teams for one year."""
    year_prefix = f"{year:04d}-%"

    with _connect(db_path) as conn:
        team_rows = conn.execute(
            """
            SELECT
                qt.id AS team_id,
                qt.team_name,
                qt.event_id,
                qt.team_rank,
                qt.total,
                qt.bonus_round
            FROM quiz_teams qt
            JOIN quiz_events e ON e.id = qt.event_id
            WHERE e.event_date LIKE ?
            """,
            (year_prefix,),
        ).fetchall()

    # Keep one row per canonical team/event for consistent alias handling.
    selected_by_team_event: Dict[str, Dict[int, Dict]] = {}
    selected_team_ids = []
    for row in team_rows:
        team_name = _canonical_team_name(row["team_name"])
        event_id = row["event_id"]
        candidate = {
            "team_id": row["team_id"],
            "bonus_round": row["bonus_round"],
            "rank": row["team_rank"] if row["team_rank"] is not None else 9999,
            "total": float(row["total"] if row["total"] is not None else 0),
        }

        selected_by_team_event.setdefault(team_name, {})
        existing = selected_by_team_event[team_name].get(event_id)
        if existing is None:
            selected_by_team_event[team_name][event_id] = candidate
            selected_team_ids.append(candidate["team_id"])
            continue

        if candidate["rank"] < existing["rank"] or (
            candidate["rank"] == existing["rank"] and candidate["total"] > existing["total"]
        ):
            selected_team_ids.append(candidate["team_id"])
            selected_by_team_event[team_name][event_id] = candidate

    score_rows: Dict[int, List[sqlite3.Row]] = {}
    unique_team_ids = sorted(set(selected_team_ids))
    if unique_team_ids:
        placeholders = ",".join("?" * len(unique_team_ids))
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT team_id, round_name, points
                FROM team_scores
                WHERE team_id IN ({placeholders})
                """,
                unique_team_ids,
            ).fetchall()
        for row in rows:
            score_rows.setdefault(row["team_id"], []).append(row)

    leaderboard = []
    for team_name, per_event in selected_by_team_event.items():
        efficiencies = []

        for event_row in per_event.values():
            selected_bonus_round = (event_row.get("bonus_round") or "").strip()
            rows_for_team = score_rows.get(event_row["team_id"], [])

            possible_candidates = []
            achieved_bonus_points = 0.0

            for score_row in rows_for_team:
                round_name = str(score_row["round_name"])
                raw_points = score_row["points"]
                if raw_points is None:
                    continue

                observed_points = max(0.0, float(raw_points))
                if selected_bonus_round and round_name.casefold() == selected_bonus_round.casefold():
                    observed_points = float(math.floor(observed_points / 2.0))
                    achieved_bonus_points = observed_points

                possible_candidates.append(_bonus_points_from_normal_points(round_name, observed_points))

            possible_bonus_points = max(possible_candidates) if possible_candidates else 0.0
            if possible_bonus_points > 0.0:
                efficiencies.append(achieved_bonus_points / possible_bonus_points)

        events = len(efficiencies)
        if events < min_events:
            continue

        leaderboard.append(
            {
                "team_name": team_name,
                "avg_efficiency": sum(efficiencies) / events,
                "events": events,
            }
        )

    leaderboard.sort(
        key=lambda row: (-row["avg_efficiency"], -row["events"], row["team_name"].lower())
    )
    return leaderboard


def get_leaders_report(
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> Dict:
    """Return a leaders summary for championship, averages, bonus efficiency and round categories."""
    standings = get_championship_standings(year=year, db_path=db_path)
    championship_leader = standings["standings"][0] if standings["standings"] else None

    points_avg_leaderboard = _get_points_average_leaderboard(
        year=year,
        min_events=min_events,
        db_path=db_path,
    )
    points_avg_leader = points_avg_leaderboard[0] if points_avg_leaderboard else None

    bonus_eff_leaderboard = _get_bonus_efficiency_leaderboard(
        year=year,
        min_events=min_events,
        db_path=db_path,
    )
    bonus_efficiency_leader = bonus_eff_leaderboard[0] if bonus_eff_leaderboard else None

    round_strength = get_round_strength_ranking(
        year=year,
        round_name=None,
        min_events=min_events,
        db_path=db_path,
    )
    category_leaders = []
    for block in round_strength["rankings"]:
        if not block["teams"]:
            continue
        best = block["teams"][0]
        category_leaders.append(
            {
                "category_name": block["round_name"],
                "team_name": best["team_name"],
                "avg_points": best["avg_points"],
                "events": best["events"],
            }
        )

    puzzle_leaderboard = _get_puzzle_leaderboard(year=year, min_events=min_events, db_path=db_path)
    puzzle_leader = puzzle_leaderboard[0] if puzzle_leaderboard else None
    if puzzle_leader is not None:
        category_leaders.append(
            {
                "category_name": "Puzzle",
                "team_name": puzzle_leader["team_name"],
                "avg_points": puzzle_leader["avg_points"],
                "events": puzzle_leader["events"],
            }
        )

    return {
        "year": year,
        "min_events": min_events,
        "events_count": standings["events_count"],
        "teams_count": standings["teams_count"],
        "championship_leader": championship_leader,
        "points_average_leader": points_avg_leader,
        "bonus_efficiency_leader": bonus_efficiency_leader,
        "category_leaders": category_leaders,
    }


def print_leaders_report(
    year: int,
    min_events: int = 2,
    db_path: str = DB_PATH_DEFAULT,
) -> None:
    """Print leaders summary for one year."""
    result = get_leaders_report(year=year, min_events=min_events, db_path=db_path)

    print(f"Leaders report {result['year']}")
    print(f"Events: {result['events_count']}")
    print(f"Teams: {result['teams_count']}")
    print(f"Minimum events for averages/efficiency/categories: {result['min_events']}")
    print()

    championship_leader = result["championship_leader"]
    if championship_leader is None:
        print("No championship data found for this year.")
    else:
        print(
            "Championship leader: "
            f"{championship_leader['team_name']} "
            f"({championship_leader['points']} pts, "
            f"{championship_leader['events_count']} events, "
            f"{championship_leader['wins']} wins)"
        )

    points_leader = result["points_average_leader"]
    if points_leader is None:
        print("Best point average: -")
    else:
        print(
            "Best point average: "
            f"{points_leader['team_name']} "
            f"({points_leader['avg_points']:.2f} pts/event, {points_leader['events']} events)"
        )

    bonus_leader = result["bonus_efficiency_leader"]
    if bonus_leader is None:
        print("Best bonus efficiency: -")
    else:
        print(
            "Best bonus efficiency: "
            f"{bonus_leader['team_name']} "
            f"({bonus_leader['avg_efficiency'] * 100:.1f}%, {bonus_leader['events']} events)"
        )

    print()
    print(f"{'Category':20}  {'Leader Team':30}  {'Avg':>6}  {'Events':>6}")
    print("""--------------------  ------------------------------  ------  ------""")

    if not result["category_leaders"]:
        print("No category data found for this year and filter.")
        return

    for row in result["category_leaders"]:
        print(
            f"{row['category_name'][:20]:20}  {row['team_name'][:30]:30}  {row['avg_points']:>6.2f}  {row['events']:>6}"
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

    team_parser = subparsers.add_parser(
        "team", help="Print season results for a team in a given year."
    )
    team_parser.add_argument("--team", type=str, required=True, help="Team name to show.")
    team_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")

    averages_parser = subparsers.add_parser(
        "averages", help="Print round and puzzle point averages for a team in a given year."
    )
    averages_parser.add_argument("--team", type=str, required=True, help="Team name to show.")
    averages_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")

    radar_parser = subparsers.add_parser(
        "radar", help="Print and export a radar plot for a team in a given year."
    )
    radar_parser.add_argument("--team", type=str, required=True, help="Team name to show.")
    radar_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")
    radar_parser.add_argument(
        "--min-events",
        type=int,
        default=2,
        help="Minimum events per team in a round (default: 2).",
    )
    radar_parser.add_argument(
        "--output",
        type=str,
        help="Optional SVG path for the generated radar plot.",
    )

    consistency_parser = subparsers.add_parser(
        "consistency", help="Print team consistency report for a given year."
    )
    consistency_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")
    consistency_parser.add_argument(
        "--min-events",
        type=int,
        default=2,
        help="Minimum events per team to include in consistency ranking (default: 2).",
    )

    difficulty_parser = subparsers.add_parser(
        "difficulty", help="Print round difficulty report for a given year."
    )
    difficulty_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")

    event_difficulty_parser = subparsers.add_parser(
        "event-difficulty",
        help="Compare round averages in one event against all other events in the same year.",
    )
    event_difficulty_parser.add_argument("--event-id", type=int, help="Event id to show.")
    event_difficulty_parser.add_argument("--source-file", help="Source Excel filename of the event.")
    event_difficulty_parser.add_argument("--date", dest="event_date", help="Event date in YYYY-MM-DD format.")
    event_difficulty_parser.add_argument("--location", help="Event location string.")

    round_strength_parser = subparsers.add_parser(
        "round-strength",
        help="League-wide ranking per round: best teams in Allgemeinwissen, Musik, etc.",
    )
    round_strength_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")
    round_strength_parser.add_argument("--round", dest="round_name", help="Optional single round name filter.")
    round_strength_parser.add_argument(
        "--min-events",
        type=int,
        default=2,
        help="Minimum events per team in that round (default: 2).",
    )
    round_strength_parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="How many teams to print per round (default: 10).",
    )
    round_strength_parser.add_argument(
        "--team",
        type=str,
        help="Optional team name. If set, prints this team's rank in each round.",
    )

    leaders_parser = subparsers.add_parser(
        "leaders",
        help="Print championship/average/bonus/category leaders for a year.",
    )
    leaders_parser.add_argument("--year", type=int, required=True, help="Year, e.g. 2026")
    leaders_parser.add_argument(
        "--min-events",
        type=int,
        default=2,
        help="Minimum events for average-based leader metrics (default: 2).",
    )

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
    elif args.command == "team":
        print_team_season_results(args.team, args.year, args.db)
    elif args.command == "averages":
        print_team_round_averages(args.team, args.year, args.db)
    elif args.command == "radar":
        print_team_radar_report(args.team, args.year, args.min_events, args.output, args.db)
    elif args.command == "consistency":
        print_consistency_report(args.year, args.min_events, args.db)
    elif args.command == "difficulty":
        print_round_difficulty_report(args.year, args.db)
    elif args.command == "event-difficulty":
        print_event_difficulty_report(
            db_path=args.db,
            event_id=args.event_id,
            source_file=args.source_file,
            event_date=args.event_date,
            location=args.location,
        )
    elif args.command == "round-strength":
        print_round_strength_ranking(
            year=args.year,
            round_name=args.round_name,
            min_events=args.min_events,
            top=args.top,
            team_name=args.team,
            db_path=args.db,
        )
    elif args.command == "leaders":
        print_leaders_report(
            year=args.year,
            min_events=args.min_events,
            db_path=args.db,
        )
