import os
import sys
from html import escape as html_escape
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import db_report
import import_quiz_results


class ImportTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.db_path = QLineEdit(os.path.join("data", "quiz_results.db"))
        db_btn = QPushButton("Browse...")
        db_btn.clicked.connect(self._browse_db)

        file_box = QGroupBox("Import single file")
        file_layout = QHBoxLayout(file_box)
        self.file_path = QLineEdit()
        file_browse = QPushButton("Browse...")
        file_browse.clicked.connect(self._browse_file)
        file_import = QPushButton("Import File")
        file_import.clicked.connect(self._import_file)
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(file_browse)
        file_layout.addWidget(file_import)

        folder_box = QGroupBox("Import folder")
        folder_layout = QHBoxLayout(folder_box)
        self.folder_path = QLineEdit()
        folder_browse = QPushButton("Browse...")
        folder_browse.clicked.connect(self._browse_folder)
        folder_import = QPushButton("Import Folder")
        folder_import.clicked.connect(self._import_folder)
        folder_layout.addWidget(self.folder_path)
        folder_layout.addWidget(folder_browse)
        folder_layout.addWidget(folder_import)

        db_row = QHBoxLayout()
        db_row.addWidget(QLabel("Database:"))
        db_row.addWidget(self.db_path)
        db_row.addWidget(db_btn)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        layout.addLayout(db_row)
        layout.addWidget(file_box)
        layout.addWidget(folder_box)
        layout.addWidget(QLabel("Import log"))
        layout.addWidget(self.log)

    def _browse_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select database", self.db_path.text(), "SQLite DB (*.db)")
        if path:
            self.db_path.setText(path)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select quiz file",
            "",
            "Excel Files (*.xlsx *.xlsm *.xltx *.xltm)",
        )
        if path:
            self.file_path.setText(path)

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select quiz folder")
        if path:
            self.folder_path.setText(path)

    def _import_file(self):
        path = self.file_path.text().strip()
        db = self.db_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing input", "Please select a file.")
            return

        try:
            result = import_quiz_results.import_quiz_file(path, db)
            self.log.appendPlainText(
                f"Imported {result['teams_imported']} teams from {result['event_date']} @ {result['location']}"
            )
        except Exception as exc:
            self.log.appendPlainText(f"ERROR: {exc}")
            QMessageBox.critical(self, "Import failed", str(exc))

    def _import_folder(self):
        path = self.folder_path.text().strip()
        db = self.db_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing input", "Please select a folder.")
            return

        try:
            summary = import_quiz_results.import_quiz_folder(path, db)
            for item in summary["imports"]:
                self.log.appendPlainText(
                    f"Imported {item['teams_imported']} teams from {item['event_date']} @ {item['location']}"
                )

            if summary.get("errors"):
                self.log.appendPlainText("\nErrors during import:")
                for err in summary["errors"]:
                    self.log.appendPlainText(f"[{err['file']}]\n{err['message']}")

            self.log.appendPlainText(
                f"\nImported {summary['files_imported']} files. Failed: {summary.get('files_failed', 0)}"
            )
        except Exception as exc:
            self.log.appendPlainText(f"ERROR: {exc}")
            QMessageBox.critical(self, "Import failed", str(exc))


class ReportsTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        controls = QFormLayout()

        self.db_path = QLineEdit(os.path.join("data", "quiz_results.db"))

        self.report_type = QComboBox()
        self.report_type.addItems(
            [
                "list",
                "result",
                "standings",
                "team",
                "averages",
                "radar",
                "consistency",
                "difficulty",
                "event-difficulty",
                "round-strength",
            ]
        )

        self.year = QSpinBox()
        self.year.setRange(2000, 2100)
        self.year.setValue(2026)

        self.team = QLineEdit()
        self.round_name = QLineEdit()

        self.min_events = QSpinBox()
        self.min_events.setRange(1, 100)
        self.min_events.setValue(2)

        self.top = QSpinBox()
        self.top.setRange(1, 100)
        self.top.setValue(10)

        self.event_id = QSpinBox()
        self.event_id.setRange(0, 999999)
        self.event_id.setValue(0)

        self.source_file = QLineEdit()
        self.event_date = QLineEdit()
        self.location = QLineEdit()

        event_pick_row = QHBoxLayout()
        self.event_picker = QComboBox()
        self.event_picker.addItem("Select event...", None)
        refresh_events_btn = QPushButton("Refresh events")
        refresh_events_btn.clicked.connect(self._refresh_events)
        apply_event_btn = QPushButton("Use selected event")
        apply_event_btn.clicked.connect(self._apply_selected_event)
        event_pick_row.addWidget(self.event_picker)
        event_pick_row.addWidget(refresh_events_btn)
        event_pick_row.addWidget(apply_event_btn)

        controls.addRow("Database", self.db_path)
        controls.addRow("Report", self.report_type)
        controls.addRow("Year", self.year)
        controls.addRow("Team", self.team)
        controls.addRow("Round name", self.round_name)
        controls.addRow("Min events", self.min_events)
        controls.addRow("Top", self.top)
        controls.addRow("Event ID (0=off)", self.event_id)
        controls.addRow("Source file", self.source_file)
        controls.addRow("Event date (YYYY-MM-DD)", self.event_date)
        controls.addRow("Location", self.location)
        controls.addRow("Event helper", event_pick_row)

        btn_row = QHBoxLayout()
        run_btn = QPushButton("Run report")
        run_btn.clicked.connect(self._run_report)
        pdf_btn = QPushButton("Generate Text PDF")
        pdf_btn.clicked.connect(self._generate_pdf)
        team_pdf_btn = QPushButton("Generate Team PDF")
        team_pdf_btn.clicked.connect(self._generate_team_pdf)
        btn_row.addWidget(run_btn)
        btn_row.addWidget(pdf_btn)
        btn_row.addWidget(team_pdf_btn)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(10)
        self.output.setFont(mono_font)

        layout.addLayout(controls)
        layout.addLayout(btn_row)
        layout.addWidget(self.output)

        self._refresh_events()

    def _refresh_events(self):
        db = self.db_path.text().strip()
        try:
            events = db_report.get_event_list(db)
        except Exception as exc:
            self.output.setPlainText(f"ERROR while loading events:\n{exc}")
            return

        self.event_picker.clear()
        self.event_picker.addItem("Select event...", None)
        for event in events:
            label = f"#{event['id']} | {event['event_date']} | {event['location']} | {event.get('winner') or 'N/A'}"
            self.event_picker.addItem(label, event)

    def _apply_selected_event(self):
        data = self.event_picker.currentData()
        if not data:
            return
        self.event_id.setValue(int(data["id"]))
        self.event_date.setText(str(data["event_date"]))
        self.location.setText(str(data["location"]))

        # Keep source_file in sync when available.
        try:
            event_detail = db_report.get_event_result(
                db_path=self.db_path.text().strip(),
                event_id=int(data["id"]),
            )
            self.source_file.setText(str(event_detail["event"]["source_file"]))
        except Exception:
            # Non-fatal: user can still use id/date/location.
            pass

    def _capture(self, fn, *args, **kwargs):
        buf = StringIO()
        with redirect_stdout(buf):
            fn(*args, **kwargs)
        return buf.getvalue()

    def _generate_pdf(self):
        text = self.output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "No report", "Run a report first before generating a PDF.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)

        self.output.print_(printer)
        QMessageBox.information(self, "PDF saved", f"Report saved to:\n{path}")

    def _team_pdf_default_name(self, team_name: str, year: int) -> str:
        safe_team = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in team_name.strip()).strip("_")
        if not safe_team:
            safe_team = "team"
        return f"{safe_team}_{year}_team_report.pdf"

    def _build_team_pdf_html(self, report: dict) -> str:
        radar_uri = Path(report["radar_svg_path"]).resolve().as_uri()

        def format_value(value, suffix=""):
            if value is None:
                return "-"
            if isinstance(value, float):
                return f"{value:.2f}{suffix}"
            return f"{value}{suffix}"

        best_bonus = report.get("best_bonus_category")
        best_result = report.get("best_result")

        best_bonus_text = "-"
        if best_bonus is not None:
            best_bonus_text = f"{best_bonus['round_name']} ({best_bonus['avg_points']:.2f})"

        best_result_text = "-"
        if best_result is not None:
            best_result_text = (
                f"{best_result['total_points']} Punkte"
                f" - {html_escape(best_result['event_date'])} @ {html_escape(best_result['location'])}"
            )

        return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <style>
    body {{ font-family: Arial, sans-serif; color: #111827; margin: 0; padding: 28px; }}
    .title {{ font-size: 26px; font-weight: 700; margin: 0 0 8px 0; }}
    .subtitle {{ font-size: 13px; color: #6b7280; margin-bottom: 20px; }}
    .summary {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px 18px; margin-bottom: 18px; }}
    .item {{ padding: 12px 14px; border: 1px solid #dbe3ef; border-radius: 12px; background: #f8fbff; }}
    .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; margin-bottom: 6px; }}
    .value {{ font-size: 16px; font-weight: 600; color: #111827; }}
    .full {{ grid-column: 1 / -1; }}
    .chart {{ margin-top: 18px; border: 1px solid #dbe3ef; border-radius: 16px; padding: 10px; background: white; }}
    .chart img {{ width: 100%; height: auto; display: block; }}
  </style>
</head>
<body>
  <div class='title'>Team Report: {html_escape(report['team_name'])} ({report['year']})</div>
  <div class='subtitle'>Automatisch generierter PDF-Report mit Teamprofil und Radar-Plot.</div>
  <div class='summary'>
    <div class='item'><div class='label'>Teamname</div><div class='value'>{html_escape(report['team_name'])}</div></div>
    <div class='item'><div class='label'>Anzahl Teilnahmen</div><div class='value'>{format_value(report['participation_count'])}</div></div>
    <div class='item'><div class='label'>Meisterschaftspunkte insgesamt</div><div class='value'>{format_value(report['championship_points'])}</div></div>
    <div class='item'><div class='label'>Platzierung in der Meisterschaft</div><div class='value'>{format_value(report['championship_place'])}</div></div>
    <div class='item'><div class='label'>Durchschnittliche Punkte</div><div class='value'>{format_value(report['average_points'])}</div></div>
    <div class='item'><div class='label'>Beste Bonus-Kategorie</div><div class='value'>{html_escape(best_bonus_text)}</div></div>
    <div class='item full'><div class='label'>Bestes Ergebnis</div><div class='value'>{html_escape(best_result_text)}</div></div>
  </div>
  <div class='chart'>
    <img src='{radar_uri}' alt='Radar plot for {html_escape(report['team_name'])}'>
  </div>
</body>
</html>"""

    def _generate_team_pdf(self):
        team_name = self.team.text().strip()
        if not team_name:
            QMessageBox.warning(self, "Missing team", "Please enter a team name before generating the PDF.")
            return

        db = self.db_path.text().strip()
        default_name = self._team_pdf_default_name(team_name, self.year.value())
        path, _ = QFileDialog.getSaveFileName(self, "Save team PDF", default_name, "PDF Files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        radar_path = None
        try:
            report = db_report.get_team_profile_report(team_name, self.year.value(), self.min_events.value(), db)
            radar_path = report.get("radar_svg_path")

            doc = QTextDocument()
            doc.setHtml(self._build_team_pdf_html(report))

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
            printer.setPageOrientation(QPageLayout.Orientation.Portrait)

            doc.print_(printer)
            QMessageBox.information(self, "PDF saved", f"Team report saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Team PDF failed", str(exc))
            self.output.setPlainText(f"ERROR:\n{exc}")
        finally:
            if radar_path:
                try:
                    Path(radar_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _run_report(self):
        report = self.report_type.currentText()
        db = self.db_path.text().strip()

        kwargs_event = {
            "db_path": db,
            "event_id": self.event_id.value() if self.event_id.value() > 0 else None,
            "source_file": self.source_file.text().strip() or None,
            "event_date": self.event_date.text().strip() or None,
            "location": self.location.text().strip() or None,
        }

        try:
            if report == "list":
                text = self._capture(db_report.print_event_list, db)
            elif report == "result":
                text = self._capture(db_report.print_event_results, **kwargs_event)
            elif report == "standings":
                text = self._capture(db_report.print_championship_standings, self.year.value(), db)
            elif report == "team":
                text = self._capture(db_report.print_team_season_results, self.team.text().strip(), self.year.value(), db)
            elif report == "averages":
                text = self._capture(db_report.print_team_round_averages, self.team.text().strip(), self.year.value(), db)
            elif report == "radar":
                text = self._capture(
                    db_report.print_team_radar_report,
                    self.team.text().strip(),
                    self.year.value(),
                    self.min_events.value(),
                    None,
                    db,
                )
            elif report == "consistency":
                text = self._capture(db_report.print_consistency_report, self.year.value(), self.min_events.value(), db)
            elif report == "difficulty":
                text = self._capture(db_report.print_round_difficulty_report, self.year.value(), db)
            elif report == "event-difficulty":
                text = self._capture(db_report.print_event_difficulty_report, **kwargs_event)
            elif report == "round-strength":
                round_name = self.round_name.text().strip() or None
                team_name = self.team.text().strip() or None
                text = self._capture(
                    db_report.print_round_strength_ranking,
                    self.year.value(),
                    round_name,
                    self.min_events.value(),
                    self.top.value(),
                    team_name,
                    db,
                )
            else:
                text = "Unknown report"

            self.output.setPlainText(text)
        except Exception as exc:
            self.output.setPlainText(f"ERROR:\n{exc}")
            QMessageBox.critical(self, "Report failed", str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PubQuizStats")
        self.resize(1100, 750)

        tabs = QTabWidget()
        tabs.addTab(ImportTab(), "Import")
        tabs.addTab(ReportsTab(), "Reports")

        self.setCentralWidget(tabs)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
