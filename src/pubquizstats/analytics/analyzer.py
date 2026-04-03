"""Analytics engine for quiz data."""

import logging
from typing import List, Dict, Optional
import pandas as pd
from sqlalchemy.orm import Session
from pubquizstats.database.repositories import AnalyticsRepository, TeamRepository
from pubquizstats.models.schemas import TeamStatsOutput

logger = logging.getLogger(__name__)


class QuizAnalyzer:
    """Analytics engine for quiz data."""

    def __init__(self, session: Session):
        """Initialize analyzer."""
        self.session = session
        self.analytics_repo = AnalyticsRepository(session)
        self.team_repo = TeamRepository(session)

    def get_team_stats(self, team_id: int) -> Optional[TeamStatsOutput]:
        """Get comprehensive statistics for a team."""
        stats = self.analytics_repo.get_team_stats(team_id)
        if not stats:
            return None

        return TeamStatsOutput(**stats)

    def get_all_team_stats(self) -> List[TeamStatsOutput]:
        """Get statistics for all teams."""
        all_stats = self.analytics_repo.get_all_team_stats()
        return [TeamStatsOutput(**stats) for stats in all_stats]

    def get_team_ranking(self) -> pd.DataFrame:
        """Get overall team ranking based on average position."""
        all_stats = self.get_all_team_stats()

        data = []
        for stats in all_stats:
            data.append({
                "Team": stats.canonical_name or stats.team_name,
                "Quizzes": stats.quizzes_participated,
                "Total Points": stats.total_points,
                "Avg Points": stats.average_points,
                "Avg Rank": stats.average_rank,
                "Wins": stats.wins,
                "Podiums": stats.podium_finishes,
            })

        df = pd.DataFrame(data)
        if len(df) > 0:
            df = df.sort_values("Avg Rank", na_position="last")
        return df

    def get_team_comparison(self, team_ids: List[int]) -> Dict:
        """Compare statistics for multiple teams."""
        comparison = {}
        for team_id in team_ids:
            stats = self.get_team_stats(team_id)
            if stats:
                comparison[stats.canonical_name or stats.team_name] = {
                    "quizzes": stats.quizzes_participated,
                    "avg_points": stats.average_points,
                    "avg_rank": stats.average_rank,
                    "wins": stats.wins,
                    "podiums": stats.podium_finishes,
                }

        return comparison

    def get_team_performance_by_round(self, team_id: int) -> Dict[int, Dict]:
        """Get team's performance breakdown by round across all quizzes."""
        return self.analytics_repo.get_performance_by_round_number(team_id)

    def get_quiz_statistics(self, quiz_id: int) -> Dict:
        """Get statistics for a quiz."""
        ranking = self.analytics_repo.get_ranking_at_date(quiz_id)

        if not ranking:
            return {}

        return {
            "quiz_id": quiz_id,
            "total_teams": len(ranking),
            "ranking": [
                {
                    "rank": rank,
                    "team": team,
                    "points": points,
                }
                for team, rank, points in ranking
            ],
        }

    def get_round_statistics(self, round_id: int) -> Dict:
        """Get statistics for a specific round."""
        return self.analytics_repo.get_round_difficulty(round_id)

    def get_team_trend(self, team_id: int) -> pd.DataFrame:
        """Get team's performance trend across quizzes."""
        history = self.analytics_repo.get_team_ranking_history(team_id)

        if not history:
            return pd.DataFrame()

        data = []
        for entry in history:
            data.append({
                "Date": entry["quiz_date"],
                "Quiz": entry["quiz_name"],
                "Rank": entry["rank"],
                "Points": entry["total_points"],
            })

        df = pd.DataFrame(data)
        return df.sort_values("Date")

    def export_to_csv(self, df: pd.DataFrame, file_path: str) -> bool:
        """Export data to CSV."""
        try:
            df.to_csv(file_path, index=False)
            logger.info(f"Exported data to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False

    def export_to_json(self, data: Dict, file_path: str) -> bool:
        """Export data to JSON."""
        try:
            import json
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Exported data to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            return False
