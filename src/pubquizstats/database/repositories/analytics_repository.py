"""Repository for analytics queries."""

from typing import List, Dict, Optional, Tuple
from sqlalchemy import func, and_, desc
from sqlalchemy.orm import Session
from pubquizstats.models.database import (
    Team,
    TeamGroup,
    QuizParticipation,
    TeamRoundScore,
    Quiz,
    Round,
)


class AnalyticsRepository:
    """Repository for analytics queries."""

    def __init__(self, session: Session):
        """Initialize analytics repository."""
        self.session = session

    def get_team_stats(self, team_id: int) -> Dict:
        """Get statistics for a team."""
        team = self.session.query(Team).filter_by(id=team_id).first()
        if not team:
            return {}

        canonical_name = (
            team.group.canonical_name if team.group else team.name
        )

        # All participations for this team
        participations = (
            self.session.query(QuizParticipation)
            .filter_by(team_id=team_id)
            .all()
        )

        if not participations:
            return {
                "team_id": team_id,
                "team_name": team.name,
                "canonical_name": canonical_name,
                "quizzes_participated": 0,
            }

        total_points = sum(p.total_points for p in participations)
        average_points = total_points / len(participations)

        ranks = [p.rank_overall for p in participations if p.rank_overall is not None]
        average_rank = sum(ranks) / len(ranks) if ranks else None

        wins = sum(1 for p in participations if p.rank_overall == 1)
        podium_finishes = sum(1 for p in participations if p.rank_overall and p.rank_overall <= 3)

        # Points per round
        points_by_round = self._get_team_points_by_round(team_id)

        return {
            "team_id": team_id,
            "team_name": team.name,
            "canonical_name": canonical_name,
            "quizzes_participated": len(participations),
            "total_points": total_points,
            "average_points": round(average_points, 2),
            "average_rank": round(average_rank, 2) if average_rank else None,
            "wins": wins,
            "podium_finishes": podium_finishes,
            "points_by_round": points_by_round,
        }

    def get_all_team_stats(self) -> List[Dict]:
        """Get statistics for all teams."""
        teams = self.session.query(Team).all()
        return [self.get_team_stats(team.id) for team in teams]

    def _get_team_points_by_round(self, team_id: int) -> Dict[int, float]:
        """Get average points per round for a team."""
        results = (
            self.session.query(
                Round.round_number,
                func.avg(TeamRoundScore.points).label("avg_points"),
            )
            .join(TeamRoundScore.round)
            .join(TeamRoundScore.participation)
            .filter(QuizParticipation.team_id == team_id)
            .group_by(Round.round_number)
            .order_by(Round.round_number)
            .all()
        )

        return {round_num: round(float(avg), 2) for round_num, avg in results}

    def get_round_difficulty(self, round_id: int) -> Dict:
        """Get difficulty statistics for a round."""
        round_obj = self.session.query(Round).filter_by(id=round_id).first()
        if not round_obj:
            return {}

        scores = (
            self.session.query(TeamRoundScore)
            .filter_by(round_id=round_id)
            .all()
        )

        if not scores:
            return {"round_id": round_id, "avg_score": 0, "max_score": 0, "min_score": 0}

        points = [s.points for s in scores]
        return {
            "round_id": round_id,
            "round_number": round_obj.round_number,
            "round_name": round_obj.round_name,
            "team_count": len(scores),
            "avg_score": round(sum(points) / len(points), 2),
            "max_score": max(points),
            "min_score": min(points),
        }

    def get_team_vs_team(self, team_id_1: int, team_id_2: int) -> List[Dict]:
        """Get head-to-head comparison of two teams."""
        shared_quizzes = (
            self.session.query(
                Quiz.id,
                Quiz.name,
                Quiz.date,
                QuizParticipation.rank_overall,
                QuizParticipation.total_points,
            )
            .join(QuizParticipation)
            .filter(QuizParticipation.team_id.in_([team_id_1, team_id_2]))
            .group_by(Quiz.id)
            .having(func.count(func.distinct(QuizParticipation.team_id)) == 2)
            .all()
        )

        results = []
        for quiz_id, quiz_name, quiz_date, rank, total_points in shared_quizzes:
            results.append({
                "quiz_id": quiz_id,
                "quiz_name": quiz_name,
                "quiz_date": quiz_date,
            })

        return results

    def get_ranking_at_date(self, quiz_id: int) -> List[Tuple[str, int, int]]:
        """Get final ranking for a quiz as list of (team_name, rank, points)."""
        participations = (
            self.session.query(QuizParticipation)
            .filter_by(quiz_id=quiz_id)
            .order_by(QuizParticipation.rank_overall)
            .all()
        )

        return [
            (p.team.name, p.rank_overall, p.total_points)
            for p in participations
            if p.rank_overall is not None
        ]

    def get_team_ranking_history(self, team_id: int) -> List[Dict]:
        """Get team's ranking history across all quizzes."""
        participations = (
            self.session.query(QuizParticipation)
            .filter_by(team_id=team_id)
            .join(Quiz)
            .order_by(Quiz.date)
            .all()
        )

        return [
            {
                "quiz_id": p.quiz_id,
                "quiz_name": p.quiz.name,
                "quiz_date": p.quiz.date,
                "rank": p.rank_overall,
                "total_points": p.total_points,
            }
            for p in participations
        ]

    def get_performance_by_round_number(self, team_id: int) -> Dict[int, Dict]:
        """Get team's average performance in each round across all quizzes."""
        results = (
            self.session.query(
                Round.round_number,
                func.avg(TeamRoundScore.points).label("avg_points"),
                func.min(TeamRoundScore.points).label("min_points"),
                func.max(TeamRoundScore.points).label("max_points"),
                func.count().label("count"),
            )
            .join(TeamRoundScore.round)
            .join(TeamRoundScore.participation)
            .filter(QuizParticipation.team_id == team_id)
            .group_by(Round.round_number)
            .order_by(Round.round_number)
            .all()
        )

        return {
            round_num: {
                "avg_points": round(float(avg), 2),
                "min_points": min_pts,
                "max_points": max_pts,
                "attempts": count,
            }
            for round_num, avg, min_pts, max_pts, count in results
        }
