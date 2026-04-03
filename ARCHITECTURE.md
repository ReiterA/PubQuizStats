# PubQuizStats - Software Architecture

## Overview
PubQuizStats is a data analysis tool for pub quiz results that:
- Loads quiz data from Excel files
- Stores results in a normalized database
- Deduplicates and merges teams across multiple quizzes
- Provides analytics on team performance

## 1. Technology Stack

### Database
**Choice: SQLite**
- Lightweight, no server setup needed
- Good for local data analysis
- Can easily migrate to PostgreSQL if needed
- SQLAlchemy ORM for clean abstractions

### Python Packages
- **openpyxl** or **pandas**: Excel file reading
- **SQLAlchemy**: ORM and database abstraction
- **alembic**: Database migrations
- **pydantic**: Data validation and serialization
- **fuzzywuzzy** or **rapidfuzz**: Fuzzy string matching for team names
- **click**: CLI framework
- **sqlalchemy-utils**: Database utilities

## 2. Database Schema

### Core Tables

```
QUIZZES
├── id (PK)
├── name (string, unique)
├── date (datetime)
├── location (string)
└── created_at (timestamp)

TEAMS
├── id (PK)
├── name (string)
├── canonical_name (string, FK to TEAM_GROUPS)
└── created_at (timestamp)

TEAM_GROUPS
├── id (PK)
├── canonical_name (string, unique)
└── created_at (timestamp)

QUIZ_PARTICIPATIONS
├── id (PK)
├── quiz_id (FK)
├── team_id (FK)
├── rank_overall (int)
└── total_points (int)

ROUNDS
├── id (PK)
├── quiz_id (FK)
├── round_number (int)
├── round_name (string) [e.g., "General Knowledge"]
├── max_points (int)
└── unique(quiz_id, round_number)

TEAM_ROUND_SCORES
├── id (PK)
├── participation_id (FK)
├── round_id (FK)
└── points (int)
```

### Relationship Model
```
QUIZ → ROUNDS (one-to-many)
QUIZ → QUIZ_PARTICIPATIONS (one-to-many)
TEAMS → QUIZ_PARTICIPATIONS (one-to-many)
QUIZ_PARTICIPATIONS → TEAM_ROUND_SCORES (one-to-many)
ROUNDS → TEAM_ROUND_SCORES (one-to-many)
TEAMS → TEAM_GROUPS (many-to-one)
```

## 3. Project Structure

```
pubquizstats/
├── src/
│   ├── pubquizstats/
│   │   ├── __init__.py
│   │   ├── config.py                 # Configuration & paths
│   │   ├── cli.py                    # CLI entry point
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── database.py           # SQLAlchemy models
│   │   │   └── schemas.py            # Pydantic schemas (for validation)
│   │   ├── loaders/
│   │   │   ├── __init__.py
│   │   │   └── excel_loader.py       # Excel file parsing
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py         # DB connection setup
│   │   │   └── repositories/
│   │   │       ├── __init__.py
│   │   │       ├── base_repository.py
│   │   │       ├── quiz_repository.py
│   │   │       ├── team_repository.py
│   │   │       └── analytics_repository.py
│   │   ├── processing/
│   │   │   ├── __init__.py
│   │   │   ├── deduplicator.py       # Team name merging logic
│   │   │   └── importer.py           # Import pipeline
│   │   └── analytics/
│   │       ├── __init__.py
│   │       └── analyzer.py           # Analytics queries & calculations
│   ├── migrations/                   # Alembic migrations
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   │   ├── test_excel_loader.py
│   │   ├── test_deduplicator.py
│   │   ├── test_analytics.py
│   │   └── fixtures/
│   │       └── sample_quiz.xlsx
├── data/
│   ├── quizzes/                      # Input Excel files
│   └── pubquizstats.db               # SQLite database
├── pyproject.toml
├── README.md
└── ARCHITECTURE.md
```

## 4. Key Components

### 4.1 Excel Loader (`loaders/excel_loader.py`)
```
ExcelLoader
├── load_quiz(file_path: str) -> ParsedQuiz
│   ├── Read Excel structure
│   ├── Parse quiz metadata (name, date)
│   ├── Parse teams and scores
│   └── Validate data
└── guess_structure(workbook) -> Dict[str, int]
    └── Auto-detect sheet layout variations
```

**Input Format Flexibility:**
- Support multiple Excel layouts (detect columns automatically)
- Typical format: Quiz name, Teams (one per row), Rounds (one per column)

### 4.2 Deduplicator (`processing/deduplicator.py`)
```
TeamDeduplicator
├── find_similar_teams(new_team: str, existing_teams: List[str], threshold=0.8)
├── merge_teams(old_team_id: int, new_team_id: int)
├── suggest_merges() -> List[Tuple[Team, Team, score]]
└── get_canonical_name(team_id: int) -> str
```

**Fuzzy Matching:**
- Use token_set_ratio (handles typos, reordering)
- Configurable similarity threshold
- Manual override capability

### 4.3 Database Layer (Repository Pattern)
```
BaseRepository
├── create(obj)
├── update(id, obj)
├── delete(id)
├── get_by_id(id)
└── list_all()

QuizRepository
├── create_quiz_with_data(quiz_data, team_scores)
└── get_quiz_with_scores(quiz_id)

TeamRepository
├── get_or_create_team(name)
├── merge_teams(primary_id, secondary_id)
└── get_all_teams_by_group()

AnalyticsRepository
├── get_team_stats(team_id) -> TeamStats
├── get_round_stats(round_id) -> RoundStats
├── get_head_to_head(team1_id, team2_id) -> [scores]
└── get_performance_by_round(team_id) -> Dict[round_num, avg_points]
```

### 4.4 Analytics Engine (`analytics/analyzer.py`)
```
QuizAnalyzer
├── team_statistics(team_id: int) -> TeamStats
│   ├── average_points
│   ├── average_rank
│   ├── wins_count
│   ├── podium_count (top 3)
│   └── points_by_round (dict)
├── quiz_statistics(quiz_id: int) -> QuizStats
│   └── team_rankings, round_difficulty
├── comparison(team_ids: List[int]) -> ComparisonStats
├── trend_analysis(team_id: int, date_range) -> Trends
└── ranking_history() -> Dict[date, List[TeamRank]]
```

### 4.5 Import Pipeline (`processing/importer.py`)
```
ImportPipeline
├── import_quiz(file_path)
│   ├── Load Excel (ExcelLoader)
│   ├── Validate data (Pydantic schemas)
│   ├── Check for team duplicates (Deduplicator)
│   ├── Store in DB (Repositories)
│   └── Return import report
```

## 5. Data Flow

### Import Flow
```
Excel File
    ↓
[ExcelLoader] → ParsedQuiz (raw data)
    ↓
[Validator] → Validated QuizData (Pydantic)
    ↓
[Deduplicator] → Deduplicated teams
    ↓
[Repositories] → Store in SQLite
    ↓
ImportReport (success/warnings)
```

### Analysis Flow
```
User Query
    ↓
[AnalyticsRepository] → Raw data from DB
    ↓
[Analyzer] → Calculate statistics
    ↓
Results (DataFrame or dict)
    ↓
[CLI/API] → Display/Export
```

## 6. Team Deduplication Strategy

### Three-Level Approach

1. **Automatic Fuzzy Matching**
   - On import, compare against existing team names
   - Use token_set_ratio (order-independent)
   - Flag potential matches above threshold (e.g., 0.85)
   - Update `canonical_name` for new team

2. **Manual Review UI**
   - CLI command to review suggestions
   - Accept/reject merges interactively
   - Merge secondary team into primary (combine scores)

3. **Manual Merging**
   - CLI command: `merge-teams <old_name> <new_name>`
   - Updates all historical scores
   - Archives old team record

### Database Approach
```
Instead of deleting teams, use TEAM_GROUPS table:
- TEAMS.canonical_name → TEAM_GROUPS.canonical_name
- Query uses canonical_name for aggregations
- History preserved in TEAMS
- Reversible via migrations
```

## 7. CLI Interface

```bash
# Import quiz
pubquizstats import data/quizzes/quiz_2024_03.xlsx

# Review team duplicates
pubquizstats review-merges

# Merge teams manually
pubquizstats merge-teams "Team A" "Team A " --yes

# View statistics
pubquizstats stats team "Team A"
pubquizstats stats quiz 42
pubquizstats stats compare "Team A" "Team B" "Team C"

# Export data
pubquizstats export stats.csv --format csv
pubquizstats export stats.json --format json

# Database
pubquizstats db init
pubquizstats db migrate
pubquizstats db reset
```

## 8. Configuration

Create `config.py`:
```python
DATABASE_URL = "sqlite:///./data/pubquizstats.db"
FUZZY_MATCH_THRESHOLD = 0.85
EXCEL_SAMPLE_SIZE = 5  # Rows to preview
LOG_LEVEL = "INFO"
```

Alternatively use `.env` file with python-dotenv.

## 9. Testing Strategy

- **Unit tests**: Excel parser, deduplicator, analyzer functions
- **Integration tests**: Import pipeline with sample Excel files
- **Database tests**: Repository operations (use in-memory SQLite)
- **Fixtures**: Sample Excel files in tests/fixtures/

## 10. Future Enhancements

- Web UI (Flask/FastAPI)
- Export to PDF reports
- Visualization (matplotlib/plotly)
- Multi-user support
- Team ratings/ELO system
- Predictions
- API endpoint

## 11. Advantages of This Architecture

✅ **Separation of Concerns**: Clear module boundaries
✅ **Testability**: Easy to mock/test each layer
✅ **Extensibility**: Add new loaders (CSV, JSON) or analytics easily
✅ **Maintainability**: Repository pattern prevents tight coupling to DB
✅ **Scalability**: Can migrate to larger DB or API without major refactoring
✅ **User Friendly**: CLI for common operations
✅ **Data Integrity**: Schema enforces relationships
✅ **Team Management**: Flexible deduplication without data loss
