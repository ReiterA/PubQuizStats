"""Configuration for PubQuizStats."""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_DIR = DATA_DIR
QUIZ_DIR = DATA_DIR / "quizzes"

# Database
DATABASE_URL = f"sqlite:///{DATABASE_DIR / 'pubquizstats.db'}"

# Fuzzy matching settings
FUZZY_MATCH_THRESHOLD = 0.85  # Similarity threshold for team name matching
FUZZY_MATCH_PROCESSOR = "default"  # Options: "default", "uppercase", "lowercase"

# Excel parsing
EXCEL_SAMPLE_SIZE = 5  # Rows to sample for structure detection

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Ensure directories exist
QUIZ_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
