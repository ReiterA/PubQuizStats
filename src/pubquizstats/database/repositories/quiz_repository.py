"""Repository for Quiz operations."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from pubquizstats.models.database import Quiz, QuizParticipation, Round, TeamRoundScore
from .base_repository import BaseRepository


class QuizRepository(BaseRepository[Quiz]):
    """Repository for quiz operations."""

    def __init__(self, session: Session):
        """Initialize quiz repository."""
        super().__init__(session, Quiz)

    def get_by_name(self, name: str) -> Optional[Quiz]:
        """Get quiz by name."""
        return self.session.query(Quiz).filter_by(name=name).first()

    def create_quiz(
        self, name: str, date: datetime, location: Optional[str] = None
    ) -> Quiz:
        """Create a new quiz."""
        quiz = Quiz(name=name, date=date, location=location)
        return self.create(quiz)

    def get_with_participations(self, quiz_id: int) -> Optional[Quiz]:
        """Get quiz with all participations and scores."""
        return (
            self.session.query(Quiz)
            .filter_by(id=quiz_id)
            .join(Quiz.participations)
            .outerjoin(QuizParticipation.round_scores)
            .first()
        )

    def get_quiz_rounds(self, quiz_id: int) -> List[Round]:
        """Get all rounds for a quiz."""
        return self.session.query(Round).filter_by(quiz_id=quiz_id).order_by(Round.round_number).all()

    def get_round_by_number(self, quiz_id: int, round_number: int) -> Optional[Round]:
        """Get a specific round."""
        return (
            self.session.query(Round)
            .filter_by(quiz_id=quiz_id, round_number=round_number)
            .first()
        )
