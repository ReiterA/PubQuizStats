import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import db_report
from import_quiz_results import create_schema


class TeamPuzzleCategoryReportTests(unittest.TestCase):
    def test_reports_team_and_field_averages_per_category(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "team_puzzle_details.db"
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
                    (1, 1, 1, "Alpha", 10, 50, None),
                    (2, 1, 2, "Beta", 4, 40, None),
                    (3, 2, 1, "Alpha", 6, 45, None),
                    (4, 2, 2, "Beta", 8, 43, None),
                    (5, 2, 3, "Gamma", 2, 35, None),
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

            result = db_report.get_team_puzzle_category_report("Alpha", 2026, str(db_path))

        self.assertEqual(result["team_name"], "Alpha")
        self.assertEqual(len(result["categories"]), 1)
        category = result["categories"][0]
        self.assertEqual(category["category"], "Land")
        self.assertEqual(category["team_avg_points"], 8)
        self.assertEqual(category["field_avg_points"], 6)
        self.assertEqual(category["difference"], 2)
        self.assertEqual(category["team_events"], 2)
        self.assertEqual(category["field_samples"], 5)


if __name__ == "__main__":
    unittest.main()
