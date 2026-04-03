# PubQuizStats

A Python application for analyzing and managing pub quiz results. Load quiz data from Excel files, track team performance across multiple events, and generate comprehensive statistics.

## Features

- **Excel Import**: Load quiz results from Excel files with automatic format detection
- **Team Management**: Deduplication and merging of team names with fuzzy matching
- **Data Analysis**: Calculate team statistics, rankings, and performance metrics
- **Multi-Quiz Support**: Combine results from different quizzes and analyze trends
- **Database Storage**: SQLite database for persistent data storage
- **CLI Interface**: Command-line tools for common operations
- **Export**: Export statistics to CSV and JSON formats

## Installation

1. Clone the repository:
```bash
cd PubQuizStats
```

2. Install with uv:
```bash
uv sync
```

Or with pip:
```bash
pip install -e .
```

## Quick Start

### Initialize Database

```bash
pubquizstats init
```

### Import Quiz Data

```bash
pubquizstats import-quiz data/quizzes/quiz_2024_03.xlsx
```

### View Team Rankings

```bash
pubquizstats ranking
```

### Get Team Statistics

```bash
pubquizstats stats-team "Team Name"
```

### List All Quizzes

```bash
pubquizstats list-quizzes
```

### Export Data

```bash
pubquizstats export --format csv --output ranking.csv
```

## Excel File Format

The Excel file should contain:
- **Column A**: Team names
- **Column B onwards**: Points per round
- **Rank column** (optional): Final ranking (1, 2, 3, etc.)
- **Total column** (optional): Total points earned

Example structure:
```
Team Name | Round 1 | Round 2 | Round 3 | Rank | Total
Team A    |   15    |   12    |   18    |  1   |  45
Team B    |   14    |   15    |   16    |  2   |  45
Team C    |   12    |   10    |   14    |  3   |  36
```

The loader supports variations in structure and will attempt to auto-detect headers.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design:

- **Database Layer**: Repository pattern with SQLAlchemy ORM
- **Data Models**: Pydantic schemas for validation
- **Import Pipeline**: Excel parsing and data validation
- **Team Deduplication**: Fuzzy matching for similar team names
- **Analytics Engine**: Comprehensive statistics and analysis
- **CLI Interface**: Command-line tools for operations

## Database

PubQuizStats uses SQLite for data storage. The database includes:
- Quizzes and their metadata
- Teams and team groupings
- Quiz participations and rankings
- Round scores and team performance

Database file: `data/pubquizstats.db`

## Team Deduplication

Similar team names are automatically detected using fuzzy matching:
- Handles typos (e.g., "Team A" vs "Team A ")
- Handles abbreviations
- Configurable similarity threshold (default: 85%)

You can manually review and approve merges:
```bash
pubquizstats review-merges
```

## Statistics Available

### Team Statistics
- Average points per quiz
- Average ranking position
- Number of wins (1st place finishes)
- Podium finishes (top 3)
- Performance by round

### Quiz Statistics
- Final rankings
- Team scores per round
- Round difficulty metrics

### Comparative Analysis
- Head-to-head team comparisons
- Performance trends across quizzes
- Round-specific performance

## Command Reference

```bash
# Database
pubquizstats init                                    # Initialize database

# Import
pubquizstats import-quiz <file_path>               # Import quiz from Excel
pubquizstats import-quiz <file_path> --no-auto-merge  # Import without auto-merging

# Teams
pubquizstats list-teams                             # List all teams
pubquizstats review-merges                          # Review team merges

# Statistics
pubquizstats ranking                                # Show overall ranking
pubquizstats stats-team <team_name>                # Get team statistics
pubquizstats list-quizzes                          # List all quizzes
pubquizstats quiz-details <quiz_id>                # Show quiz details

# Export
pubquizstats export --format csv --output ranking.csv  # Export ranking as CSV
pubquizstats export --format json --output ranking.json # Export ranking as JSON
```

## Development

### Project Structure

```
src/pubquizstats/
├── models/              # Data models and schemas
├── database/            # Database layer and repositories
├── loaders/             # Excel file loading
├── processing/          # Data processing pipeline
├── analytics/           # Analytics and statistics
└── cli.py              # Command-line interface
```

### Running Tests

```bash
# Install dev dependencies
uv pip install pytest pytest-cov

# Run tests
pytest tests/
```

## Future Enhancements

- Web dashboard for data visualization
- PDF report generation
- Team rating/ELO system
- Performance predictions
- API endpoint
- Multi-user support
- Automatic data synchronization

## License

MIT

## Support

For issues or questions, please refer to [ARCHITECTURE.md](ARCHITECTURE.md) for system design details.
