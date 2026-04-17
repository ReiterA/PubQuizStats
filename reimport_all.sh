#!/bin/bash
# Script to reimport all quiz files from data/quizzes folder

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
else
    echo "Error: Virtual environment not found at $SCRIPT_DIR/.venv"
    exit 1
fi

# Run the import with folder flag
python "$SCRIPT_DIR/src/import_quiz_results.py" --folder "$SCRIPT_DIR/data/quizzes" --db "$SCRIPT_DIR/data/quiz_results.db"

echo ""
echo "Reimport complete!"
