from pathlib import Path

from src.db_report import render_team_report_event_bars_svg


def test_render_team_report_event_bars_svg_rotates_value_labels(tmp_path):
    result = {
        "team_name": "Test Team",
        "year": 2026,
        "season_events": [
            {
                "event_date": "2026-01-05",
                "location": "Test Location",
                "total_points": 120,
                "position": 2,
            }
        ],
    }

    output_path = tmp_path / "team_report.svg"
    svg_path = render_team_report_event_bars_svg(result, str(output_path))

    assert Path(svg_path).exists()
    svg = output_path.read_text(encoding="utf-8")
    assert "120 Pts" in svg
    assert "Pos. 2" in svg
    assert 'transform="rotate(-90' in svg
