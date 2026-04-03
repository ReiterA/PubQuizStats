"""Team deduplication using fuzzy matching."""

import logging
from typing import List, Tuple, Optional
from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from pubquizstats.models.database import Team, TeamGroup
from pubquizstats.config import FUZZY_MATCH_THRESHOLD

logger = logging.getLogger(__name__)


class TeamDeduplicator:
    """Handles team name deduplication and merging."""

    def __init__(self, session: Session, threshold: float = FUZZY_MATCH_THRESHOLD):
        """
        Initialize deduplicator.
        
        Args:
            session: SQLAlchemy session
            threshold: Similarity threshold (0-1) for fuzzy matching
        """
        self.session = session
        self.threshold = threshold

    def find_similar_teams(
        self, new_team_name: str, existing_team_names: Optional[List[str]] = None
    ) -> List[Tuple[str, float]]:
        """
        Find similar teams for a new team name.
        
        Args:
            new_team_name: Name of new team
            existing_team_names: List of existing team names to check. If None, uses DB.
            
        Returns:
            List of (team_name, similarity_score) tuples sorted by score descending
        """
        if existing_team_names is None:
            # Get all existing teams from DB
            teams = self.session.query(Team).all()
            existing_team_names = [t.name for t in teams]

        matches = []
        for existing_name in existing_team_names:
            if existing_name.lower() == new_team_name.lower():
                # Exact match (case-insensitive)
                matches.append((existing_name, 1.0))
            else:
                # Fuzzy match using token_set_ratio (handles typos and word order)
                score = fuzz.token_set_ratio(new_team_name, existing_name) / 100
                if score >= self.threshold:
                    matches.append((existing_name, score))

        # Sort by score descending
        return sorted(matches, key=lambda x: x[1], reverse=True)

    def suggest_merges(self) -> List[Tuple[Team, Team, float]]:
        """
        Suggest team merges based on fuzzy matching.
        
        Returns:
            List of (team1, team2, similarity_score) tuples
        """
        teams = self.session.query(Team).all()
        suggestions = []
        seen_pairs = set()

        for i, team1 in enumerate(teams):
            for team2 in teams[i + 1 :]:
                pair_key = tuple(sorted([team1.id, team2.id]))
                if pair_key in seen_pairs:
                    continue

                score = fuzz.token_set_ratio(team1.name, team2.name) / 100
                if score >= self.threshold and score < 1.0:  # Not exact match
                    suggestions.append((team1, team2, score))
                    seen_pairs.add(pair_key)

        # Sort by score descending
        return sorted(suggestions, key=lambda x: x[2], reverse=True)

    def merge_teams(
        self, primary_team_id: int, secondary_team_id: int
    ) -> bool:
        """
        Merge secondary team into primary team.
        
        All participations and scores from secondary team are transferred to primary.
        
        Args:
            primary_team_id: ID of team to keep
            secondary_team_id: ID of team to merge into primary
            
        Returns:
            True if merge successful, False otherwise
        """
        primary = self.session.query(Team).filter_by(id=primary_team_id).first()
        secondary = self.session.query(Team).filter_by(id=secondary_team_id).first()

        if not primary or not secondary:
            logger.error(
                f"Team not found: primary={primary}, secondary={secondary}"
            )
            return False

        try:
            # Get or create team group
            if not primary.group:
                group = TeamGroup(canonical_name=primary.name)
                self.session.add(group)
                self.session.flush()
                primary.group_id = group.id
                logger.info(f"Created new group for primary team: {primary.name}")

            # Update secondary team to point to same group
            secondary.group_id = primary.group_id

            # Transfer all participations (handled by DB foreign keys)
            from pubquizstats.models.database import QuizParticipation

            secondary_participations = (
                self.session.query(QuizParticipation)
                .filter_by(team_id=secondary_team_id)
                .all()
            )

            for participation in secondary_participations:
                # Check if primary already participated in this quiz
                existing = (
                    self.session.query(QuizParticipation)
                    .filter_by(quiz_id=participation.quiz_id, team_id=primary_team_id)
                    .first()
                )

                if existing:
                    # Conflict: both teams participated in same quiz
                    logger.warning(
                        f"Merge conflict: both {primary.name} and {secondary.name} "
                        f"participated in quiz {participation.quiz.name}. Keeping primary."
                    )
                    self.session.delete(participation)
                else:
                    # Transfer participation to primary team
                    participation.team_id = primary_team_id

            self.session.commit()
            logger.info(
                f"Successfully merged {secondary.name} (ID: {secondary_team_id}) "
                f"into {primary.name} (ID: {primary_team_id})"
            )
            return True

        except Exception as e:
            self.session.rollback()
            logger.error(f"Error merging teams: {e}")
            raise

    def auto_merge_similar_teams(self, dry_run: bool = False) -> List[Tuple]:
        """
        Automatically merge suggested similar teams.
        
        Args:
            dry_run: If True, only log suggestions without making changes
            
        Returns:
            List of (primary_team, secondary_team, score) tuples that were merged/suggested
        """
        suggestions = self.suggest_merges()

        if dry_run:
            logger.info(f"DRY RUN: Found {len(suggestions)} potential merges:")
            for team1, team2, score in suggestions:
                logger.info(
                    f"  {team1.name} <-> {team2.name}: {score:.2%} similar"
                )
            return suggestions

        # Actually perform merges
        merged = []
        for team1, team2, score in suggestions:
            # Merge smaller ID into larger (arbitrary choice)
            if team1.id < team2.id:
                primary, secondary = team1, team2
            else:
                primary, secondary = team2, team1

            if self.merge_teams(primary.id, secondary.id):
                merged.append((primary, secondary, score))

        logger.info(f"Merged {len(merged)} team pairs")
        return merged

    def get_team_canonical_name(self, team_id: int) -> Optional[str]:
        """Get canonical name for a team (via group)."""
        team = self.session.query(Team).filter_by(id=team_id).first()
        if not team:
            return None

        if team.group:
            return team.group.canonical_name

        return team.name
