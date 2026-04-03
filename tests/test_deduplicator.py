"""Test for deduplicator."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pubquizstats.models.database import Base, Team, TeamGroup
from pubquizstats.processing.deduplicator import TeamDeduplicator


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_find_similar_teams(db_session):
    """Test finding similar team names."""
    # Add test teams
    team1 = Team(name="Team A")
    team2 = Team(name="Team A ")
    team3 = Team(name="Team B")
    db_session.add_all([team1, team2, team3])
    db_session.commit()

    deduplicator = TeamDeduplicator(db_session)
    matches = deduplicator.find_similar_teams("Team A")

    assert len(matches) >= 1
    # Should find exact or very similar matches
    assert any(name in ["Team A", "Team A "] for name, _ in matches)


def test_suggest_merges(db_session):
    """Test merge suggestions."""
    # Add similar teams
    team1 = Team(name="London Eagles")
    team2 = Team(name="London Eagles ")
    team3 = Team(name="New York Hawks")
    db_session.add_all([team1, team2, team3])
    db_session.commit()

    deduplicator = TeamDeduplicator(db_session, threshold=0.8)
    suggestions = deduplicator.suggest_merges()

    # Should suggest merging similar teams
    assert any(
        (t1.id, t2.id) == (team1.id, team2.id) or (t1.id, t2.id) == (team2.id, team1.id)
        for t1, t2, _ in suggestions
    )


def test_merge_teams(db_session):
    """Test merging teams."""
    # Add teams
    team1 = Team(name="Primary Team")
    team2 = Team(name="Secondary Team")
    db_session.add_all([team1, team2])
    db_session.commit()

    deduplicator = TeamDeduplicator(db_session)
    result = deduplicator.merge_teams(team1.id, team2.id)

    assert result is True
    # Check that both teams have same group
    db_session.refresh(team1)
    db_session.refresh(team2)
    assert team1.group is not None
    assert team1.group_id == team2.group_id
