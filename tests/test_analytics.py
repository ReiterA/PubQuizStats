"""Test for analytics engine."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pubquizstats.models.database import (
    Base,
    Quiz,
    Team,
    Round,
    QuizParticipation,
    TeamRoundScore,
)
from pubquizstats.analytics.analyzer import QuizAnalyzer


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_data(db_session):
    """Create sample quiz data."""
    # Create quiz
    quiz = Quiz(
        name="Test Quiz",
        date=datetime(2024, 3, 1),
        location="Test Location",
    )
    db_session.add(quiz)
    db_session.flush()

    # Create rounds
    round1 = Round(quiz_id=quiz.id, round_number=1, round_name="Round 1", max_points=20)
    round2 = Round(quiz_id=quiz.id, round_number=2, round_name="Round 2", max_points=20)
    db_session.add_all([round1, round2])
    db_session.flush()

    # Create teams
    team1 = Team(name="Team A")
    team2 = Team(name="Team B")
    db_session.add_all([team1, team2])
    db_session.flush()

    # Create participations
    part1 = QuizParticipation(
        quiz_id=quiz.id,
        team_id=team1.id,
        rank_overall=1,
        total_points=35,
    )
    part2 = QuizParticipation(
        quiz_id=quiz.id,
        team_id=team2.id,
        rank_overall=2,
        total_points=30,
    )
    db_session.add_all([part1, part2])
    db_session.flush()

    # Create round scores
    score1_r1 = TeamRoundScore(participation_id=part1.id, round_id=round1.id, points=18)
    score1_r2 = TeamRoundScore(participation_id=part1.id, round_id=round2.id, points=17)
    score2_r1 = TeamRoundScore(participation_id=part2.id, round_id=round1.id, points=15)
    score2_r2 = TeamRoundScore(participation_id=part2.id, round_id=round2.id, points=15)
    db_session.add_all([score1_r1, score1_r2, score2_r1, score2_r2])
    db_session.commit()

    return {
        "quiz": quiz,
        "teams": [team1, team2],
        "rounds": [round1, round2],
    }


def test_get_team_stats(db_session, sample_data):
    """Test getting team statistics."""
    analyzer = QuizAnalyzer(db_session)
    team = sample_data["teams"][0]

    stats = analyzer.get_team_stats(team.id)

    assert stats is not None
    assert stats.team_id == team.id
    assert stats.quizzes_participated == 1
    assert stats.total_points == 35
    assert stats.average_points == 35.0
    assert stats.wins == 1


def test_get_team_ranking(db_session, sample_data):
    """Test getting overall ranking."""
    analyzer = QuizAnalyzer(db_session)
    df = analyzer.get_team_ranking()

    assert len(df) == 2
    # Team A should be ranked higher (lower avg rank)
    assert df.iloc[0]["Team"] == "Team A"


def test_get_quiz_statistics(db_session, sample_data):
    """Test getting quiz statistics."""
    analyzer = QuizAnalyzer(db_session)
    quiz = sample_data["quiz"]

    stats = analyzer.get_quiz_statistics(quiz.id)

    assert stats["total_teams"] == 2
    assert len(stats["ranking"]) == 2
    assert stats["ranking"][0]["rank"] == 1
    assert stats["ranking"][0]["team"] == "Team A"


def test_get_team_performance_by_round(db_session, sample_data):
    """Test getting team performance by round."""
    analyzer = QuizAnalyzer(db_session)
    team = sample_data["teams"][0]

    perf = analyzer.get_team_performance_by_round(team.id)

    assert 1 in perf
    assert 2 in perf
    assert perf[1]["avg_points"] == 18.0
    assert perf[2]["avg_points"] == 17.0
