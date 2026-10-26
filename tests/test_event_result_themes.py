import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import db_report


class EventResultThemesTests(unittest.TestCase):
    def test_both_event_result_reports_include_event_themes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "event_result_themes.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE quiz_events (
                    id INTEGER PRIMARY KEY,
                    event_date TEXT NOT NULL,
                    location TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );
                CREATE TABLE quiz_teams (
                    id INTEGER PRIMARY KEY,
                    event_id INTEGER NOT NULL,
                    team_rank INTEGER,
                    team_name TEXT NOT NULL,
                    puzzle_points REAL,
                    total REAL,
                    bonus_round TEXT
                );
                CREATE TABLE team_scores (
                    team_id INTEGER NOT NULL,
                    round_name TEXT NOT NULL,
                    points REAL
                );
                CREATE TABLE event_themes (
                    event_id INTEGER PRIMARY KEY,
                    puzzle_category TEXT,
                    puzzle_solution TEXT,
                    image_round_topic TEXT,
                    surprise_round_topic TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT INTO quiz_events (id, event_date, location, source_file, imported_at) VALUES (?, ?, ?, ?, ?)",
                (1, "2026-03-12", "Vienna", "event.xlsx", "2026-03-12T10:00:00Z"),
            )
            conn.execute(
                "INSERT INTO quiz_teams (id, event_id, team_rank, team_name, puzzle_points, total, bonus_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (10, 1, 1, "Alpha", 7, 42, None),
            )
            conn.execute(
                "INSERT INTO event_themes (event_id, puzzle_category, puzzle_solution, image_round_topic, surprise_round_topic, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (1, "Land", "Aland", "Filmwelt", "Länder", "2026-03-12T10:00:00Z"),
            )
            conn.commit()
            conn.close()

            event_result = db_report.get_event_result(event_id=1, db_path=str(db_path))
            team_result = db_report.get_event_team_result("Alpha", event_id=1, db_path=str(db_path))

        expected_themes = {
            "puzzle_category": "Land",
            "puzzle_solution": "Aland",
            "image_round_topic": "Filmwelt",
            "surprise_round_topic": "Länder",
        }
        for result in (event_result, team_result):
            with self.subTest(result=result):
                for key, value in expected_themes.items():
                    self.assertEqual(result["event"][key], value)


if __name__ == "__main__":
    unittest.main()
