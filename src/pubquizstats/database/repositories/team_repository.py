"""Repository for Team operations."""

from typing import Optional, List
from sqlalchemy.orm import Session
from pubquizstats.models.database import Team, TeamGroup, QuizParticipation
from .base_repository import BaseRepository


class TeamRepository(BaseRepository[Team]):
    """Repository for team operations."""

    def __init__(self, session: Session):
        """Initialize team repository."""
        super().__init__(session, Team)

    def get_by_name(self, name: str) -> Optional[Team]:
        """Get team by name."""
        return self.session.query(Team).filter_by(name=name).first()

    def get_or_create_team(self, name: str) -> Team:
        """Get team by name or create if not exists."""
        team = self.get_by_name(name)
        if not team:
            team = Team(name=name)
            self.create(team)
        return team

    def get_canonical_name(self, team_id: int) -> Optional[str]:
        """Get canonical name for a team (via group)."""
        team = self.get_by_id(team_id)
        if team and team.group:
            return team.group.canonical_name
        return team.name if team else None

    def merge_teams(self, primary_team_id: int, secondary_team_id: int) -> bool:
        """
        Merge secondary team into primary team.
        Transfers all participations and scores to primary team.
        """
        primary = self.get_by_id(primary_team_id)
        secondary = self.get_by_id(secondary_team_id)

        if not primary or not secondary:
            return False

        try:
            # Transfer all participations from secondary to primary
            secondary_participations = (
                self.session.query(QuizParticipation)
                .filter_by(team_id=secondary_team_id)
                .all()
            )

            for participation in secondary_participations:
                # Check if primary team already participated in this quiz
                existing = (
                    self.session.query(QuizParticipation)
                    .filter_by(quiz_id=participation.quiz_id, team_id=primary_team_id)
                    .first()
                )

                if not existing:
                    # Transfer participation
                    participation.team_id = primary_team_id
                else:
                    # Already participated, delete duplicate
                    self.session.delete(participation)

            # Update secondary team's group to point to primary
            if not primary.group:
                # Create group for primary team
                group = TeamGroup(canonical_name=primary.name)
                self.session.add(group)
                self.session.flush()
                primary.group_id = group.id

            secondary.group_id = primary.group_id

            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            raise e

    def get_teams_by_group(self) -> dict:
        """Get teams grouped by canonical name."""
        groups = self.session.query(TeamGroup).all()
        result = {}

        for group in groups:
            team_names = [t.name for t in group.teams]
            result[group.canonical_name] = team_names

        # Add ungrouped teams
        ungrouped = self.session.query(Team).filter_by(group_id=None).all()
        for team in ungrouped:
            result[team.name] = [team.name]

        return result

    def get_all_teams_with_participations(self) -> List[dict]:
        """Get all teams with participation counts."""
        teams = self.list_all()
        result = []

        for team in teams:
            canonical_name = self.get_canonical_name(team.id)
            participation_count = (
                self.session.query(QuizParticipation).filter_by(team_id=team.id).count()
            )
            result.append(
                {
                    "id": team.id,
                    "name": team.name,
                    "canonical_name": canonical_name,
                    "participations": participation_count,
                }
            )

        return result
