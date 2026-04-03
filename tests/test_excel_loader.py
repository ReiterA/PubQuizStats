"""Test for Excel loader."""

import pytest
from datetime import datetime
from pathlib import Path
from pubquizstats.loaders.excel_loader import ExcelLoader
from pubquizstats.models.schemas import ParsedQuizData


@pytest.fixture
def excel_loader():
    """Create Excel loader instance."""
    return ExcelLoader()


@pytest.fixture
def sample_excel_path():
    """Path to sample Excel file."""
    return Path(__file__).parent / "fixtures" / "sample_quiz.xlsx"


def test_excel_loader_load_quiz(excel_loader, sample_excel_path):
    """Test loading quiz from Excel."""
    if not sample_excel_path.exists():
        pytest.skip("Sample Excel file not found")

    parsed = excel_loader.load_quiz(str(sample_excel_path))

    assert isinstance(parsed, ParsedQuizData)
    assert parsed.name is not None
    assert parsed.date is not None
    assert len(parsed.team_scores) > 0


def test_excel_loader_detects_structure(excel_loader, sample_excel_path):
    """Test structure detection."""
    if not sample_excel_path.exists():
        pytest.skip("Sample Excel file not found")

    import openpyxl
    wb = openpyxl.load_workbook(sample_excel_path, data_only=True)
    ws = wb.active

    structure = excel_loader._detect_structure(ws)

    assert "teams_col" in structure
    assert "round_cols" in structure
    assert "data_start_row" in structure
