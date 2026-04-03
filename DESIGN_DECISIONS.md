# Design Decisions & Rationale

## Why SQLite?

**Choice**: SQLite over PostgreSQL, MySQL, etc.

**Rationale**:
- Pub quiz data analysis is typically single-user or small team
- No server setup required - file-based database
- Perfect for local development and testing
- Can migrate to PostgreSQL later without code changes (SQLAlchemy abstraction)
- Zero configuration needed
- Good performance for typical quiz data volumes (hundreds to thousands of records)

**Migration Path**: If needed, changing to PostgreSQL requires only changing one line in `config.py`.

---

## Why Repository Pattern?

**Choice**: Repository pattern for data access

**Alternatives Considered**:
- Direct SQLAlchemy in business logic ❌ (tight coupling)
- Data mapper pattern ❌ (too complex for this project)
- Generic data access ✅ (chosen)

**Rationale**:
- Decouples business logic from database implementation
- Easy to mock for testing
- Can swap databases without changing application code
- Clear separation between persistence and domain logic
- Reduces SQL scattered throughout codebase

**Example**:
```python
# Good - abstracted
quiz_repo = QuizRepository(session)
quiz = quiz_repo.get_by_name("Spring Quiz 2024")

# Bad - tight coupling
quiz = session.query(Quiz).filter_by(name="Spring Quiz 2024").first()
```

---

## Why Pydantic for Validation?

**Choice**: Pydantic v2 for schema validation

**Alternatives Considered**:
- Manual validation ❌ (error-prone, verbose)
- Marshmallow ❌ (older, more boilerplate)
- Pydantic ✅ (modern, strict, great DX)

**Rationale**:
- Modern Python type hints
- Strict validation by default
- Great error messages for users
- Can be used for API responses (future web UI)
- Serialization/deserialization out of the box

**Example**:
```python
# Bad - easy to introduce bugs
def validate_quiz(name, date, location):
    if not name or len(name) < 1:
        raise ValueError("Name required")
    if not isinstance(date, datetime):
        raise ValueError("Date must be datetime")
    # ... dozens more checks

# Good - declarative
class ParsedQuizData(BaseModel):
    name: str = Field(..., min_length=1)
    date: datetime
    location: Optional[str]
```

---

## Why Fuzzy Matching with Configurable Threshold?

**Choice**: `rapidfuzz.token_set_ratio` with 85% threshold

**Why token_set_ratio**:
- Handles typos: "Team A" vs "Team A " (extra space)
- Handles reordering: "London Eagles" vs "Eagles London"
- Order-independent matching
- Fast (C library backend)

**Why configurable threshold**:
- 85% is good default (catches real typos)
- Users might want stricter (95%) or looser (75%) depending on data quality
- Easy to adjust in `config.py`

**Why fuzzy at all vs exact match**:
Real data has variations:
- "Team A" typed as "Team A " (trailing space)
- "The Eagles" vs "Eagles"
- OCR errors when scanning forms
- Manual data entry typos

**Example**:
```
"London Eagles" (existing)
"Lndon Eagles" (new entry)
→ token_set_ratio = 95% → AUTO MERGED

"London Eagles" (existing)  
"London Hawks" (new entry)
→ token_set_ratio = 40% → NOT MERGED (below 85% threshold)
```

---

## Why Non-Destructive Team Merging?

**Choice**: Use `TeamGroup` canonical names, don't delete teams

**Alternatives Considered**:
- Delete secondary team ❌ (lose history)
- Rename team ❌ (lose original name)
- Canonical grouping ✅ (chosen)

**Rationale**:
- Preserves complete history
- Reversible (can unmerge if mistake)
- Can query original names
- Analytics work automatically with canonical names
- No data loss

**How it works**:
```
BEFORE:
- Team("London Eagles") → group=null
- Team("Lndon Eagles") → group=null

AFTER MERGE:
- Team("London Eagles") → group=TeamGroup("London Eagles")
- Team("Lndon Eagles") → group=TeamGroup("London Eagles")

QUERY:
SELECT canonical_name, COUNT(*) FROM teams WHERE group_id = 1
→ "London Eagles": 2 teams (both merged)
```

---

## Why Layered Architecture?

**Structure**:
```
CLI Layer
    ↓
Business Logic Layer (Analytics, Processing)
    ↓
Repository Layer (Data Access)
    ↓
ORM Layer (SQLAlchemy)
    ↓
Database Layer (SQLite)
```

**Rationale**:
- **Clear separation**: Each layer has one responsibility
- **Testable**: Can test each layer independently
- **Replaceable**: Can swap CLI for Web UI, SQLite for PostgreSQL
- **Scalable**: Can add caching, logging, monitoring at any layer

**Example of why this matters**:
```
# Bad architecture - everything mixed
def import_quiz_command(file_path):
    wb = openpyxl.load_workbook(file_path)  # Loading
    # ... parsing ...
    session.query(Quiz).add(...)  # Database
    # ... validation ...
    return "Done"

# Good architecture - clear separation
cli.py:
    result = pipeline.import_quiz(file_path)
    
importer.py (processing):
    parsed_data = loader.load_quiz(file_path)
    repo.create_quiz(parsed_data)

excel_loader.py (loading):
    return ParsedQuizData(...)
```

---

## Why Pydantic Schemas Separate from Database Models?

**Choice**: Two model types - `database.py` (SQLAlchemy) and `schemas.py` (Pydantic)

**Alternatives Considered**:
- Single model for both ❌ (mixing concerns)
- Only SQLAlchemy ❌ (no validation)
- Only Pydantic ❌ (no persistence)

**Rationale**:
- **SQLAlchemy models**: Define database schema, relationships, persistence
- **Pydantic models**: Validate input, define API contracts
- Different concerns, different needs
- Decoupled: Can change DB schema without breaking API

**Example**:
```python
# Database model (SQLAlchemy)
class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)  # DB concern
    created_at = Column(DateTime)  # DB concern

# API schema (Pydantic)
class TeamSchema(BaseModel):
    id: int
    name: str
    # No DB details here
    
    class Config:
        from_attributes = True  # Can create from ORM objects
```

---

## Why Repository Pattern Over Direct ORM Queries?

**Choice**: Repositories vs scattered SQLAlchemy queries

**Before (Bad)**:
```python
# In CLI
quizzes = session.query(Quiz).join(QuizParticipation).group_by(Quiz.id).all()

# In Analytics
quizzes = session.query(Quiz).filter_by(...).all()

# In Reports
quizzes = session.query(Quiz).order_by(Quiz.date).all()

# Query logic scattered everywhere!
```

**After (Good)**:
```python
# In CLI
quizzes = quiz_repo.get_all_with_participations()

# In Analytics
quizzes = quiz_repo.list_all()

# In Reports
quizzes = quiz_repo.get_all_ordered_by_date()

# Single source of truth for each query
```

**Benefits**:
- Queries in one place (easier to optimize)
- Easy to add logging/caching
- Can change query without touching calling code
- Better testability

---

## Why Click for CLI?

**Choice**: Click framework for command-line interface

**Alternatives Considered**:
- argparse ❌ (verbose, boilerplate-heavy)
- typer ❌ (newer, less mature)
- Click ✅ (chosen)

**Rationale**:
- Professional, mature framework
- Decorator-based (clean syntax)
- Built-in help generation
- Type validation
- Chainable commands
- Excellent error messages

**Example**:
```python
# Bad - argparse
parser = argparse.ArgumentParser(description='...')
parser.add_argument('file_path', help='...')
parser.add_argument('--auto-merge', action='store_true', help='...')
args = parser.parse_args()

# Good - Click
@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--auto-merge/--no-auto-merge", default=True)
def import_quiz(file_path: str, auto_merge: bool):
    ...
```

---

## Why pandas for Analytics?

**Choice**: pandas for statistical calculations

**Rationale**:
- Industry standard for data analysis
- Excellent for tabular data (quiz results are tabular)
- Easy aggregations (group by team, round)
- Good export to CSV
- Can easily add visualization (matplotlib, plotly)

---

## Why Import Pipeline Pattern?

**Choice**: Single `ImportPipeline` class managing full import workflow

**Benefits**:
- Single entry point
- Clear step-by-step process
- Easy to add validation steps
- Can generate detailed reports
- Transactions handled in one place

**Workflow**:
1. Load Excel
2. Validate structure
3. Check duplicates
4. Parse data
5. Deduplicate teams
6. Create database records
7. Return report

---

## Why Configuration in Separate Module?

**Choice**: `config.py` for centralized configuration

**Rationale**:
- Single source of truth for settings
- Easy to test (can mock config)
- Can load from `.env` file
- Clear what's configurable
- Environment-specific settings

**Example**:
```python
# config.py
DATABASE_URL = "sqlite:///./data/pubquizstats.db"
FUZZY_MATCH_THRESHOLD = 0.85

# Can be overridden:
import os
FUZZY_MATCH_THRESHOLD = float(os.getenv("FUZZY_MATCH_THRESHOLD", "0.85"))
```

---

## Summary of Architectural Principles

1. **Separation of Concerns**: Each module does one thing well
2. **Single Responsibility**: Classes have one reason to change
3. **Open/Closed**: Open for extension, closed for modification
4. **Dependency Inversion**: Depend on abstractions, not concrete implementations
5. **DRY**: Don't repeat yourself (avoid code duplication)
6. **YAGNI**: You aren't gonna need it (don't over-engineer)

---

## How to Extend

### Adding a new analysis feature

```python
# In analytics/analyzer.py
class QuizAnalyzer:
    def get_team_winning_percentage(self, team_id: int) -> float:
        stats = self.get_team_stats(team_id)
        # Your logic here
        return percentage
```

### Adding a new CLI command

```python
# In cli.py
@cli.command()
@click.argument("team_name")
def win_rate(team_name: str):
    session = get_session()
    analyzer = QuizAnalyzer(session)
    # Get team and calculate win rate
```

### Adding a new loader (e.g., CSV)

```python
# Create loaders/csv_loader.py
class CSVLoader:
    def load_quiz(self, file_path: str) -> ParsedQuizData:
        # Your CSV parsing logic
        return ParsedQuizData(...)

# In cli.py
from pubquizstats.loaders import ExcelLoader, CSVLoader

def detect_format(file_path):
    if file_path.endswith('.xlsx'):
        return ExcelLoader()
    elif file_path.endswith('.csv'):
        return CSVLoader()
```

These principles make extending the system easy without breaking existing code.
