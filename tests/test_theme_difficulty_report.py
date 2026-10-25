import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import db_report
from report_export import build_theme_difficulty_html
from import_quiz_results import create_schema


class ThemeDifficultyReportTests(unittest.TestCase):
    def test_round_difficulty_report_includes_all_teams(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "round_difficulty.db"
            conn = sqlite3.connect(db_path)
            create_schema(conn)

            conn.execute(
                "INSERT INTO quiz_events (id, event_date, location, source_file, imported_at) VALUES (?, ?, ?, ?, ?)",
                (1, "2026-03-12", "Vienna", "20260312_Vienna.xlsx", "2026-03-12T10:00:00Z"),
            )
            conn.executemany(
                "INSERT INTO quiz_teams (id, event_id, team_rank, team_name, puzzle_points, total, bonus_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (team_id, 1, team_id, f"Team {team_id}", team_id % 11, 50 - team_id, None)
                    for team_id in range(1, 32)
                ],
            )
            conn.executemany(
                "INSERT INTO team_scores (team_id, round_name, points) VALUES (?, ?, ?)",
                [(team_id, "Geographie", team_id % 6) for team_id in range(1, 32)],
            )
            conn.commit()
            conn.close()

            result = db_report.get_round_difficulty_report(year=2026, db_path=str(db_path))

        rounds = {row["round_name"]: row for row in result["rounds"]}
        self.assertEqual(rounds["Geographie"]["samples"], 31)
        self.assertAlmostEqual(rounds["Geographie"]["avg_points"], 76 / 31)
        self.assertAlmostEqual(rounds["Geographie"]["reachable_percent"], 76 / 31 / 5 * 100)
        self.assertEqual(rounds["Puzzle"]["samples"], 31)
        self.assertAlmostEqual(rounds["Puzzle"]["avg_points"], 5.0)
        self.assertAlmostEqual(rounds["Puzzle"]["reachable_percent"], 50.0)

    def test_event_difficulty_report_includes_all_teams(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "event_difficulty.db"
            conn = sqlite3.connect(db_path)
            create_schema(conn)
            conn.executemany(
                "INSERT INTO quiz_events (id, event_date, location, source_file, imported_at) VALUES (?, ?, ?, ?, ?)",
                [
                    (event_id, f"2026-03-{12 + (event_id - 1) * 7:02d}", f"Location {event_id}", f"event{event_id}.xlsx", "2026-03-12T10:00:00Z")
                    for event_id in (1, 2)
                ],
            )

            teams = [
                (event_id * 100 + team_id, event_id, team_id, f"Team {event_id}-{team_id}", team_id + (event_id - 1) * 10, 100 - team_id, None)
                for event_id in (1, 2)
                for team_id in range(1, 32)
            ]
            conn.executemany(
                "INSERT INTO quiz_teams (id, event_id, team_rank, team_name, puzzle_points, total, bonus_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
                teams,
            )
            conn.executemany(
                "INSERT INTO team_scores (team_id, round_name, points) VALUES (?, ?, ?)",
                [(team[0], "Geographie", team[4]) for team in teams],
            )
            conn.commit()
            conn.close()

            result = db_report.get_event_difficulty_report(event_id=1, db_path=str(db_path))

        rounds = {row["round_name"]: row for row in result["rounds"]}
        self.assertEqual(rounds["Geographie"]["event_samples"], 31)
        self.assertEqual(rounds["Geographie"]["event_avg"], 16.0)
        self.assertEqual(rounds["Geographie"]["other_samples"], 31)
        self.assertEqual(rounds["Geographie"]["other_avg"], 26.0)
        self.assertEqual(rounds["Puzzle"]["event_samples"], 31)
        self.assertEqual(rounds["Puzzle"]["other_samples"], 31)

    def test_theme_difficulty_html_uses_five_events_per_page(self):
        report = {
            "events": [
                {
                    "event_date": "2026-03-12",
                    "location": "Vienna",
                    "puzzle_category": "Land",
                    "puzzle_solution": "Aland",
                    "puzzle_average_points": 5.0,
                    "image_round_topic": "Filmwelt",
                    "image_average_points": 7.0,
                    "surprise_round_topic": "Länder",
                    "surprise_average_points": 3.5,
                },
                {
                    "event_date": "2026-03-19",
                    "location": "Berlin",
                    "puzzle_category": "Städte",
                    "puzzle_solution": "Hamburg",
                    "puzzle_average_points": 4.5,
                    "image_round_topic": "Musik",
                    "image_average_points": 6.5,
                    "surprise_round_topic": "Sprachen",
                    "surprise_average_points": 2.5,
                },
                {
                    "event_date": "2026-03-26",
                    "location": "Prag",
                    "puzzle_category": "Flüsse",
                    "puzzle_solution": "Elbe",
                    "puzzle_average_points": 6.0,
                    "image_round_topic": "Tiere",
                    "image_average_points": 5.5,
                    "surprise_round_topic": "Küche",
                    "surprise_average_points": 4.0,
                },
                {
                    "event_date": "2026-04-02",
                    "location": "Budapest",
                    "puzzle_category": "Berge",
                    "puzzle_solution": "Alpen",
                    "puzzle_average_points": 5.5,
                    "image_round_topic": "Autos",
                    "image_average_points": 4.5,
                    "surprise_round_topic": "Wetter",
                    "surprise_average_points": 3.0,
                },
                {
                    "event_date": "2026-04-09",
                    "location": "Paris",
                    "puzzle_category": "Länder",
                    "puzzle_solution": "Frankreich",
                    "puzzle_average_points": 7.0,
                    "image_round_topic": "Städte",
                    "image_average_points": 8.0,
                    "surprise_round_topic": "Sport",
                    "surprise_average_points": 2.0,
                },
                {
                    "event_date": "2026-04-16",
                    "location": "Rome",
                    "puzzle_category": "Münzen",
                    "puzzle_solution": "Euro",
                    "puzzle_average_points": 5.0,
                    "image_round_topic": "Architektur",
                    "image_average_points": 7.5,
                    "surprise_round_topic": "Film",
                    "surprise_average_points": 6.0,
                },
            ]
        }

        html = build_theme_difficulty_html(report, 2026)

        self.assertNotIn("page-break-before: always;", html)
        self.assertIn("page-break-inside: avoid;", html)
        self.assertIn("break-inside: avoid;", html)
        self.assertEqual(html.count("page-break-after: always; break-after: page;"), 1)

    def test_theme_difficulty_report_averages_event_round_themes(self):
        db_path = Path(__file__).resolve().parent / "test_theme_difficulty_report.db"
        if db_path.exists():
            db_path.unlink()

        conn = sqlite3.connect(db_path)
        create_schema(conn)

        conn.execute(
            "INSERT INTO quiz_events (id, event_date, location, source_file, imported_at) VALUES (?, ?, ?, ?, ?)",
            (1, "2026-03-12", "Vienna", "20260312_Vienna.xlsx", "2026-03-12T10:00:00Z"),
        )

        conn.execute(
            "INSERT INTO quiz_teams (id, event_id, team_rank, team_name, puzzle_points, total, bonus_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (10, 1, 1, "Alpha", 7, 42, "Überraschung"),
        )
        conn.execute(
            "INSERT INTO quiz_teams (id, event_id, team_rank, team_name, puzzle_points, total, bonus_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (11, 1, 2, "Beta", 3, 35, "Überraschung"),
        )

        conn.execute(
            "INSERT INTO event_themes (event_id, puzzle_category, puzzle_solution, image_round_topic, surprise_round_topic, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "Land", "Aland", "Filmwelt", "Länder", "2026-03-12T10:00:00Z"),
        )

        conn.execute(
            "INSERT INTO team_scores (team_id, round_name, points) VALUES (?, ?, ?)",
            (10, "Bilderrunde", 8),
        )
        conn.execute(
            "INSERT INTO team_scores (team_id, round_name, points) VALUES (?, ?, ?)",
            (10, "Überraschung", 8),
        )
        conn.execute(
            "INSERT INTO team_scores (team_id, round_name, points) VALUES (?, ?, ?)",
            (11, "Bilderrunde", 6),
        )
        conn.execute(
            "INSERT INTO team_scores (team_id, round_name, points) VALUES (?, ?, ?)",
            (11, "Überraschung", 6),
        )
        conn.commit()
        conn.close()

        result = db_report.get_theme_difficulty_report(db_path=str(db_path))

        self.assertEqual(result["events_count"], 1)
        event = result["events"][0]
        self.assertEqual(event["event_date"], "2026-03-12")
        self.assertEqual(event["puzzle_category"], "Land")
        self.assertEqual(event["puzzle_average_points"], 5.0)
        self.assertEqual(event["image_round_topic"], "Filmwelt")
        self.assertEqual(event["image_average_points"], 7.0)
        self.assertEqual(event["surprise_round_topic"], "Länder")
        self.assertEqual(event["surprise_average_points"], 3.5)


if __name__ == "__main__":
    unittest.main()
