"""SQLAlchemy database models."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Quiz(Base):
    """A pub quiz event."""

    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    date = Column(DateTime, nullable=False)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    rounds = relationship("Round", back_populates="quiz", cascade="all, delete-orphan")
    participations = relationship(
        "QuizParticipation", back_populates="quiz", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Quiz {self.name} ({self.date.date()})>"


class TeamGroup(Base):
    """Canonical grouping of teams (handles duplicates)."""

    __tablename__ = "team_groups"

    id = Column(Integer, primary_key=True)
    canonical_name = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    teams = relationship("Team", back_populates="group")

    def __repr__(self):
        return f"<TeamGroup {self.canonical_name}>"


class Team(Base):
    """A team that participated in quizzes."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    group_id = Column(Integer, ForeignKey("team_groups.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    group = relationship("TeamGroup", back_populates="teams")
    participations = relationship(
        "QuizParticipation", back_populates="team", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Team {self.name}>"


class Round(Base):
    """A round within a quiz."""

    __tablename__ = "rounds"

    id = Column(Integer, primary_key=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    round_name = Column(String(255), nullable=True)
    max_points = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    quiz = relationship("Quiz", back_populates="rounds")
    team_scores = relationship(
        "TeamRoundScore", back_populates="round", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("quiz_id", "round_number", name="uq_quiz_round"),)

    def __repr__(self):
        return f"<Round {self.round_number} (Quiz {self.quiz_id})>"


class QuizParticipation(Base):
    """A team's participation in a quiz."""

    __tablename__ = "quiz_participations"

    id = Column(Integer, primary_key=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    rank_overall = Column(Integer, nullable=True)
    total_points = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    quiz = relationship("Quiz", back_populates="participations")
    team = relationship("Team", back_populates="participations")
    round_scores = relationship(
        "TeamRoundScore", back_populates="participation", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("quiz_id", "team_id", name="uq_quiz_team"),)

    def __repr__(self):
        return f"<Participation {self.team.name} in {self.quiz.name} (Rank {self.rank_overall})>"


class TeamRoundScore(Base):
    """A team's score in a specific round."""

    __tablename__ = "team_round_scores"

    id = Column(Integer, primary_key=True)
    participation_id = Column(Integer, ForeignKey("quiz_participations.id"), nullable=False)
    round_id = Column(Integer, ForeignKey("rounds.id"), nullable=False)
    points = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    participation = relationship("QuizParticipation", back_populates="round_scores")
    round = relationship("Round", back_populates="team_scores")

    __table_args__ = (
        UniqueConstraint("participation_id", "round_id", name="uq_participation_round"),
    )

    def __repr__(self):
        return f"<TeamRoundScore {self.points} points>"
