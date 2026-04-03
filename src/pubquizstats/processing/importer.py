"""Import pipeline for quiz data."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from pubquizstats.models.database import Quiz, Round, QuizParticipation, TeamRoundScore
from pubquizstats.models.schemas import ParsedQuizData
from pubquizstats.loaders.excel_loader import ExcelLoader
from pubquizstats.database.repositories import QuizRepository, TeamRepository
from pubquizstats.processing.deduplicator import TeamDeduplicator

logger = logging.getLogger(__name__)


class ImportResult:
    """Result of import operation."""

    def __init__(self):
        """Initialize result."""
        self.success = False
        self.quiz_id: Optional[int] = None
        self.new_teams = 0
        self.merged_teams = 0
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "quiz_id": self.quiz_id,
            "new_teams": self.new_teams,
            "merged_teams": self.merged_teams,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class ImportPipeline:
    """Pipeline for importing quiz data from files."""

    def __init__(self, session: Session):
        """Initialize import pipeline."""
        self.session = session
        self.excel_loader = ExcelLoader()
        self.quiz_repo = QuizRepository(session)
        self.team_repo = TeamRepository(session)
        self.deduplicator = TeamDeduplicator(session)

    def import_quiz(
        self, file_path: str, auto_merge: bool = True
    ) -> ImportResult:
        """
        Import quiz from Excel file.
        
        Args:
            file_path: Path to Excel file
            auto_merge: Whether to automatically merge similar team names
            
        Returns:
            ImportResult with details of import
        """
        result = ImportResult()

        try:
            # Step 1: Load and parse Excel
            logger.info(f"Loading Excel file: {file_path}")
            parsed_data = self.excel_loader.load_quiz(file_path)

            # Step 2: Validate parsed data
            logger.info("Validating parsed data")
            self._validate_quiz_data(parsed_data, result)
            if result.errors:
                return result

            # Step 3: Check if quiz already exists
            existing_quiz = self.quiz_repo.get_by_name(parsed_data.name)
            if existing_quiz:
                result.errors.append(
                    f"Quiz '{parsed_data.name}' already exists (ID: {existing_quiz.id})"
                )
                return result

            # Step 4: Create quiz
            logger.info(f"Creating quiz: {parsed_data.name}")
            quiz = self.quiz_repo.create_quiz(
                name=parsed_data.name,
                date=parsed_data.date,
                location=parsed_data.location,
            )
            result.quiz_id = quiz.id

            # Step 5: Create rounds
            logger.info("Creating rounds")
            rounds_map = {}  # Map round_number -> Round object
            for round_data in parsed_data.rounds:
                round_obj = Round(
                    quiz_id=quiz.id,
                    round_number=round_data.round_number,
                    round_name=round_data.round_name,
                    max_points=round_data.max_points,
                )
                self.session.add(round_obj)
            self.session.flush()

            # Reload to get IDs
            rounds = self.quiz_repo.get_quiz_rounds(quiz.id)
            for r in rounds:
                rounds_map[r.round_number] = r

            # Step 6: Process teams and scores
            logger.info(f"Processing {len(parsed_data.team_scores)} teams")
            for team_score_input in parsed_data.team_scores:
                # Get or create team
                team = self.team_repo.get_or_create_team(team_score_input.team_name)
                if team.id is None:
                    result.new_teams += 1

                # Check for similar teams
                if auto_merge:
                    similar = self.deduplicator.find_similar_teams(
                        team.name
                    )
                    for similar_name, score in similar:
                        if similar_name != team.name:
                            similar_team = self.team_repo.get_by_name(
                                similar_name
                            )
                            if similar_team:
                                logger.info(
                                    f"Auto-merging '{team.name}' into '{similar_name}' "
                                    f"(similarity: {score:.1%})"
                                )
                                if self.deduplicator.merge_teams(
                                    similar_team.id, team.id
                                ):
                                    result.merged_teams += 1
                                    team = similar_team
                                    break

                # Create participation
                participation = QuizParticipation(
                    quiz_id=quiz.id,
                    team_id=team.id,
                    rank_overall=team_score_input.rank_overall,
                    total_points=team_score_input.total_points,
                )
                self.session.add(participation)
                self.session.flush()

                # Create round scores
                for round_number, points in team_score_input.round_scores.items():
                    if round_number not in rounds_map:
                        result.warnings.append(
                            f"Round {round_number} not found for team {team.name}"
                        )
                        continue

                    score_obj = TeamRoundScore(
                        participation_id=participation.id,
                        round_id=rounds_map[round_number].id,
                        points=points,
                    )
                    self.session.add(score_obj)

            # Step 7: Commit all changes
            self.session.commit()
            result.success = True
            logger.info(
                f"Successfully imported quiz: {quiz.name} (ID: {quiz.id})"
            )

        except Exception as e:
            self.session.rollback()
            logger.error(f"Error importing quiz: {e}", exc_info=True)
            result.errors.append(f"Import failed: {str(e)}")

        return result

    def _validate_quiz_data(
        self, parsed_data: ParsedQuizData, result: ImportResult
    ) -> None:
        """Validate parsed quiz data."""
        if not parsed_data.name or not parsed_data.name.strip():
            result.errors.append("Quiz name is required")

        if not parsed_data.date:
            result.errors.append("Quiz date is required")

        if not parsed_data.team_scores:
            result.errors.append("No team scores found in file")

        if not parsed_data.rounds:
            result.warnings.append("No rounds found in file")

        # Check for duplicate team names in same quiz
        team_names = [ts.team_name for ts in parsed_data.team_scores]
        if len(team_names) != len(set(team_names)):
            result.errors.append("Duplicate team names in quiz")

        # Check rank and total points consistency
        ranked_teams = [ts for ts in parsed_data.team_scores if ts.rank_overall]
        if ranked_teams:
            max_rank = max(ts.rank_overall for ts in ranked_teams)
            if max_rank != len(ranked_teams):
                result.warnings.append(
                    f"Rank gaps detected: max rank {max_rank} but {len(ranked_teams)} ranked teams"
                )
