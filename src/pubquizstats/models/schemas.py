"""Pydantic schemas for data validation."""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class RoundData(BaseModel):
    """Data for a single round."""

    round_number: int = Field(..., ge=1, description="Round number")
    round_name: Optional[str] = Field(None, description="Name of the round")
    max_points: int = Field(0, ge=0, description="Maximum possible points")


class TeamScoreInput(BaseModel):
    """Team score for a single round."""

    team_name: str = Field(..., min_length=1, description="Name of the team")
    rank_overall: Optional[int] = Field(None, ge=1, description="Overall ranking")
    total_points: int = Field(..., ge=0, description="Total points in quiz")
    round_scores: Dict[int, int] = Field(
        default_factory=dict, description="Points per round {round_number: points}"
    )

    @field_validator("round_scores")
    @classmethod
    def validate_round_scores(cls, v: Dict[int, int]) -> Dict[int, int]:
        """Ensure all scores are non-negative."""
        for round_num, points in v.items():
            if points < 0:
                raise ValueError(f"Round {round_num}: points cannot be negative")
        return v


class ParsedQuizData(BaseModel):
    """Parsed quiz data from Excel file."""

    name: str = Field(..., min_length=1, description="Quiz name")
    date: datetime = Field(..., description="Quiz date")
    location: Optional[str] = Field(None, description="Quiz location")
    rounds: List[RoundData] = Field(default_factory=list, description="List of rounds")
    team_scores: List[TeamScoreInput] = Field(
        default_factory=list, description="Team scores"
    )

    @field_validator("team_scores")
    @classmethod
    def validate_team_scores(cls, v: List[TeamScoreInput]) -> List[TeamScoreInput]:
        """Ensure no duplicate team names."""
        team_names = [t.team_name for t in v]
        if len(team_names) != len(set(team_names)):
            raise ValueError("Duplicate team names in quiz")
        return v


class QuizSchema(BaseModel):
    """Schema for Quiz model."""

    id: int
    name: str
    date: datetime
    location: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TeamSchema(BaseModel):
    """Schema for Team model."""

    id: int
    name: str
    group_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class TeamStatsOutput(BaseModel):
    """Statistics for a team."""

    team_id: int
    team_name: str
    canonical_name: Optional[str]
    quizzes_participated: int
    total_points: int
    average_points: float
    average_rank: Optional[float]
    wins: int
    podium_finishes: int
    points_by_round: Dict[int, float] = Field(
        default_factory=dict, description="Average points per round"
    )


class QuizComparisonOutput(BaseModel):
    """Comparison of multiple teams."""

    quiz_id: int
    quiz_name: str
    teams_comparison: Dict[str, dict] = Field(
        default_factory=dict, description="Team stats keyed by team name"
    )
