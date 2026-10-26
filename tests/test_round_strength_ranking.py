import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import db_report
from import_quiz_results import create_schema


class RoundStrengthRankingTests(unittest.TestCase):
    def test_puzzle_category_report_uses_individual_scores_for_min_and_max(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "puzzle_category.db"
            conn = sqlite3.connect(db_path)
            create_schema(conn)
            conn.executemany(
                "INSERT INTO quiz_events (id, event_date, location, source_file, imported_at) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, "2026-03-12", "Vienna", "event1.xlsx", "2026-03-12T10:00:00Z"),
                    (2, "2026-03-19", "Vienna", "event2.xlsx", "2026-03-19T10:00:00Z"),
                ],
            )
            conn.executemany(
                "INSERT INTO quiz_teams (id, event_id, team_rank, team_name, puzzle_points, total, bonus_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (1, 1, 1, "Alpha", 9, 50, None),
                    (2, 1, 2, "Beta", 8, 45, None),
                    (3, 2, 1, "Alpha", 4, 40, None),
                    (4, 2, 2, "Beta", 2, 35, None),
                ],
            )
            conn.executemany(
                "INSERT INTO event_themes (event_id, puzzle_category, puzzle_solution, image_round_topic, surprise_round_topic, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (1, "Land", "Austria", None, None, "2026-03-12T10:00:00Z"),
                    (2, "Land", "Germany", None, None, "2026-03-19T10:00:00Z"),
                ],
            )
            conn.commit()
            conn.close()

            result = db_report.get_puzzle_category_report(year=2026, db_path=str(db_path))

        category = result["categories"][0]
        self.assertEqual(category["events"], 2)
        self.assertEqual(category["avg_points"], 5.75)
        self.assertEqual(category["min_points"], 2)
        self.assertEqual(category["max_points"], 9)

    def test_puzzle_ranking_reports_maximum_and_minimum_points(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "round_strength.db"
            conn = sqlite3.connect(db_path)
            create_schema(conn)
            conn.executemany(
                "INSERT INTO quiz_events (id, event_date, location, source_file, imported_at) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, "2026-03-12", "Vienna", "event1.xlsx", "2026-03-12T10:00:00Z"),
                    (2, "2026-03-19", "Vienna", "event2.xlsx", "2026-03-19T10:00:00Z"),
                ],
            )
            conn.executemany(
                "INSERT INTO quiz_teams (id, event_id, team_rank, team_name, puzzle_points, total, bonus_round) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (1, 1, 1, "Alpha", 9, 50, None),
                    (2, 2, 1, "Alpha", 3, 45, None),
                ],
            )
            conn.commit()
            conn.close()

            result = db_report.get_round_strength_ranking(
                year=2026,
                round_name="Puzzle",
                min_events=2,
                db_path=str(db_path),
            )

        team = result["rankings"][0]["teams"][0]
        self.assertEqual(team["events"], 2)
        self.assertEqual(team["avg_points"], 6)
        self.assertEqual(team["best"], 9)
        self.assertEqual(team["worst"], 3)


if __name__ == "__main__":
    unittest.main()
