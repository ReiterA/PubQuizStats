import os
import sys
from contextlib import redirect_stdout
from io import StringIO

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
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

        run_btn = QPushButton("Run report")
        run_btn.clicked.connect(self._run_report)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(10)
        self.output.setFont(mono_font)

        layout.addLayout(controls)
        layout.addWidget(run_btn)
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
