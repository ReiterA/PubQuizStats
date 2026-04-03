#!/bin/bash
# Quick start guide for PubQuizStats

set -e

echo "================================"
echo "PubQuizStats - Quick Start Guide"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "Error: Run this script from the PubQuizStats root directory"
    exit 1
fi

echo "1. Installing dependencies..."
if command -v uv &> /dev/null; then
    uv sync
else
    pip install -e ".[dev]"
fi
echo "✓ Dependencies installed"
echo ""

echo "2. Creating sample Excel file..."
python tests/fixtures/create_sample.py
echo "✓ Sample Excel file created at tests/fixtures/sample_quiz.xlsx"
echo ""

echo "3. Initializing database..."
pubquizstats init
echo "✓ Database initialized"
echo ""

echo "4. Importing sample quiz..."
pubquizstats import-quiz tests/fixtures/sample_quiz.xlsx
echo "✓ Quiz imported"
echo ""

echo "5. Viewing rankings..."
pubquizstats ranking
echo ""

echo "6. Getting team statistics..."
pubquizstats stats-team "London Eagles"
echo ""

echo "7. Listing all quizzes..."
pubquizstats list-quizzes
echo ""

echo "================================"
echo "✓ Setup Complete!"
echo "================================"
echo ""
echo "You can now use the following commands:"
echo "  pubquizstats import-quiz <file>    # Import a new quiz"
echo "  pubquizstats ranking               # Show team rankings"
echo "  pubquizstats stats-team <name>     # Get team statistics"
echo "  pubquizstats list-teams            # List all teams"
echo "  pubquizstats review-merges         # Manage team merges"
echo "  pubquizstats export --format csv --output ranking.csv"
echo ""
echo "For more information, see README.md or ARCHITECTURE.md"
