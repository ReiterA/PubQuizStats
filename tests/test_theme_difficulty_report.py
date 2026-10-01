import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import db_report
from gui_app import ReportsTab
from import_quiz_results import create_schema


class ThemeDifficultyReportTests(unittest.TestCase):
    def test_theme_difficulty_html_uses_five_events_per_page(self):
        tab = ReportsTab.__new__(ReportsTab)
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

        html = tab._build_theme_difficulty_html(report, 2026)

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
