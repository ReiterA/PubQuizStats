"""Web based GUI for PubQuizStats (standard library HTTP server + JSON API)."""

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from contextlib import redirect_stdout
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("MPLBACKEND", "Agg")  # server threads must never open a GUI backend
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import db_report  # noqa: E402
import import_quiz_results  # noqa: E402
import report_export  # noqa: E402
from round_config import CATEGORY_NAMES  # noqa: E402

WEB_DIR = PROJECT_ROOT / "web"
CONFIG_FILE = PROJECT_ROOT / "data" / "config.json"
QUIZ_DIR = PROJECT_ROOT / "data" / "quizzes"
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
DEFAULT_DB = "data/quiz_results.db"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Public hosting: with PQS_ADMIN_PASSWORD set, visitors are read-only guests and only a
# logged-in admin may import, change settings or generate reports/exports.
# Without it (local use) everybody is admin.
ADMIN_PASSWORD = os.environ.get("PQS_ADMIN_PASSWORD", "")
SESSION_SECRET = (os.environ.get("PQS_SECRET") or "").encode() or secrets.token_bytes(32)
TRUST_PROXY = os.environ.get("PQS_TRUST_PROXY", "") == "1"
ALLOWED_HOSTS = {h.strip().lower() for h in os.environ.get("PQS_ALLOWED_HOSTS", "").split(",") if h.strip()}
SESSION_COOKIE = "pqs_session"
SESSION_TTL = 12 * 3600
LOGIN_WINDOW = 600
LOGIN_MAX_FAILS = 5
LOGIN_FAILS: dict[str, list[float]] = {}
LOGIN_LOCK = threading.Lock()


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def make_session_token() -> str:
    expires = str(int(time.time()) + SESSION_TTL)
    return f"{expires}.{_sign(expires)}"


def valid_session_token(token: str) -> bool:
    expires, _, signature = (token or "").partition(".")
    if not expires.isdigit() or not hmac.compare_digest(signature, _sign(expires)):
        return False
    return int(expires) > time.time()

REPORT_TYPES = [
    "list",
    "result",
    "Event Result Team",
    "standings",
    "standing-progress",
    "leaders",
    "team",
    "averages",
    "team-puzzle-details",
    "radar",
    "bonus-efficiency",
    "Bonus Details",
    "consistency",
    "Theme Difficulties",
    "puzzle-categories",
    "difficulty",
    "event-difficulty",
    "round-strength",
    "team-category-detail",
]


class ApiError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def current_db() -> str:
    return str(load_settings().get("db_path") or DEFAULT_DB)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _capture(fn, *args, **kwargs) -> str:
    buf = StringIO()
    with redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


class Params:
    """Typed accessors for query-string parameters."""

    def __init__(self, query: dict[str, list[str]]):
        self._q = query

    def str(self, name: str, default: str = "") -> str:
        values = self._q.get(name)
        return values[0].strip() if values and values[0] is not None else default

    def int(self, name: str, default: int | None = None) -> int | None:
        raw = self.str(name)
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            raise ApiError(f"Parameter '{name}' must be an integer.")

    def year(self) -> int:
        return self.int("year", time.localtime().tm_year)

    def team(self, required: bool = True) -> str:
        team = self.str("team")
        if required and not team:
            raise ApiError("Please select a team.")
        return team


def run_report(report: str, p: Params) -> dict:
    """Return ``{"data": <structured result>, "text": <plain text or None>}``."""
    db = current_db()
    year = p.year()
    min_events = p.int("min_events", 2)
    top = p.int("top", 10)
    event_kwargs = {
        "db_path": db,
        "event_id": p.int("event_id") or None,
        "source_file": p.str("source_file") or None,
        "event_date": p.str("event_date") or None,
        "location": p.str("location") or None,
    }

    if report == "list":
        return {"data": db_report.get_event_list(db), "text": _capture(db_report.print_event_list, db)}
    if report == "result":
        return {
            "data": db_report.get_event_result(**event_kwargs),
            "text": _capture(db_report.print_event_results, **event_kwargs),
        }
    if report == "Event Result Team":
        team = p.team()
        return {
            "data": db_report.get_event_team_result(team, **event_kwargs),
            "text": _capture(db_report.print_event_team_result, team, **event_kwargs),
        }
    if report == "standings":
        return {
            "data": db_report.get_championship_standings(year, db),
            "text": _capture(db_report.print_championship_standings, year, db),
        }
    if report == "standing-progress":
        # The print variant renders a PDF as a side effect, so no text output here.
        return {"data": db_report.get_standing_progress_report(year, top, db), "text": None}
    if report == "leaders":
        return {
            "data": db_report.get_leaders_report(year, min_events, db),
            "text": _capture(db_report.print_leaders_report, year, min_events, db),
        }
    if report == "team":
        team = p.team()
        return {
            "data": db_report.get_team_season_results(team, year, db),
            "text": _capture(db_report.print_team_season_results, team, year, db),
        }
    if report == "averages":
        team = p.team()
        return {
            "data": {
                "team": db_report.get_team_round_averages(team, year, db),
                "overall": db_report.get_overall_round_averages(year, db),
            },
            "text": _capture(db_report.print_team_round_averages, team, year, db),
        }
    if report == "team-puzzle-details":
        team = p.team()
        result = db_report.get_team_puzzle_category_report(team, year, db)
        return {
            "data": result,
            "text": _capture(db_report.print_team_puzzle_category_report, team, year, db),
        }
    if report == "radar":
        # The print variant writes an SVG file as a side effect, so no text output here.
        team = p.team()
        return {"data": db_report.get_team_radar_report(team, year, min_events, db), "text": None}
    if report == "bonus-efficiency":
        team = p.team()
        return {
            "data": db_report.get_team_bonus_efficiency_report(team, year, db),
            "text": _capture(db_report.print_team_bonus_efficiency_report, team, year, db),
        }
    if report == "Bonus Details":
        team = p.team()
        return {
            "data": db_report.get_bonus_details_report(team, year, db),
            "text": _capture(db_report.print_bonus_details_report, team, year, db),
        }
    if report == "consistency":
        return {
            "data": db_report.get_consistency_report(year, min_events, db),
            "text": _capture(db_report.print_consistency_report, year, min_events, db),
        }
    if report == "Theme Difficulties":
        return {
            "data": db_report.get_theme_difficulty_report(year, db),
            "text": _capture(db_report.print_theme_difficulty_report, year, db),
        }
    if report == "puzzle-categories":
        return {
            "data": db_report.get_puzzle_category_report(year, db),
            "text": _capture(db_report.print_puzzle_category_report, year, db),
        }
    if report == "difficulty":
        return {
            "data": db_report.get_round_difficulty_report(year, db),
            "text": _capture(db_report.print_round_difficulty_report, year, db),
        }
    if report == "event-difficulty":
        return {
            "data": db_report.get_event_difficulty_report(**event_kwargs),
            "text": _capture(db_report.print_event_difficulty_report, **event_kwargs),
        }
    if report == "round-strength":
        round_name = p.str("round_name") or None
        team = p.team(required=False) or None
        return {
            "data": db_report.get_round_strength_ranking(year, round_name, min_events, db),
            "text": _capture(
                db_report.print_round_strength_ranking, year, round_name, min_events, top, team, db
            ),
        }
    if report == "team-category-detail":
        team = p.team()
        return {
            "data": db_report.get_team_event_theme_report(team, db, year),
            "text": _capture(db_report.print_team_event_theme_report, team, db, year),
        }
    raise ApiError(f"Unknown report '{report}'.")


# ---------------------------------------------------------------------------
# Exports (files returned as downloads)
# ---------------------------------------------------------------------------

def _render_to_bytes(render) -> bytes:
    """Run ``render(path)`` in the Qt thread against a temp file and return its bytes."""
    with tempfile.TemporaryDirectory(prefix="pqs-export-") as tmp:
        path = os.path.join(tmp, "out.pdf")
        report_export.run_in_qt_thread(render, path)
        with open(path, "rb") as f:
            return f.read()


def build_export(kind: str, p: Params) -> tuple[bytes, str, str]:
    """Return ``(content, filename, content_type)`` for an export request."""
    db = current_db()
    year = p.year()

    if kind == "team-pdf":
        team = p.team()
        min_events = p.int("min_events", 2)
        content = _render_to_bytes(lambda path: report_export.team_report_pdf(team, year, min_events, db, path))
        return content, f"{report_export.safe_filename(team)}_{year}_team_report.pdf", "application/pdf"
    if kind == "team-category-pdf":
        team = p.team()
        content = _render_to_bytes(lambda path: report_export.team_category_detail_pdf(team, year, db, path))
        return content, f"{report_export.safe_filename(team)}_{year}_team_category_detail.pdf", "application/pdf"
    if kind == "theme-pdf":
        content = _render_to_bytes(lambda path: report_export.theme_difficulty_pdf(year, db, path))
        return content, f"theme_difficulties_{year}.pdf", "application/pdf"
    if kind == "text-pdf":
        report = p.str("report")
        text = run_report(report, p).get("text") if report in REPORT_TYPES else None
        if not text or not text.strip():
            raise ApiError("This report has no text output to export.")
        content = _render_to_bytes(lambda path: report_export.text_report_pdf(text, path))
        return content, f"{report_export.safe_filename(report, 'report')}_{year}.pdf", "application/pdf"
    if kind == "standing-progress-pdf":
        result = db_report.get_standing_progress_report(year, p.int("top", 10), db)
        if not result["events"] or not result["teams"]:
            raise ApiError("No event/team data found for this year.")
        with tempfile.TemporaryDirectory(prefix="pqs-export-") as tmp:
            path = db_report.render_standing_progress_pdf(result, os.path.join(tmp, "progress.pdf"))
            content = Path(path).read_bytes()
        return content, f"standing_progress_{year}.pdf", "application/pdf"
    if kind == "radar-svg":
        team = p.team()
        result = db_report.get_team_radar_report(team, year, p.int("min_events", 2), db)
        with tempfile.TemporaryDirectory(prefix="pqs-export-") as tmp:
            path = db_report.render_team_radar_svg(result, os.path.join(tmp, "radar.svg"))
            content = Path(path).read_bytes()
        return content, f"{report_export.safe_filename(team)}_{year}_radar.svg", "image/svg+xml"
    raise ApiError(f"Unknown export '{kind}'.", HTTPStatus.NOT_FOUND)


# ---------------------------------------------------------------------------
# Batch job: all team reports
# ---------------------------------------------------------------------------

JOBS: dict[str, dict] = {}


def start_all_team_reports(year: int, min_events: int) -> str:
    db = current_db()
    standings = db_report.get_championship_standings(year, db)["standings"]
    if not standings:
        raise ApiError(f"No teams found for {year}.")

    job_id = uuid.uuid4().hex[:12]
    out_dir = EXPORT_DIR / f"team_reports_{year}"
    job = {
        "id": job_id,
        "year": year,
        "status": "running",
        "total": len(standings),
        "done": 0,
        "current": None,
        "log": [],
        "successes": 0,
        "failures": 0,
        "folder": str(out_dir.relative_to(PROJECT_ROOT)),
        "zip": None,
    }
    JOBS[job_id] = job

    def worker():
        out_dir.mkdir(parents=True, exist_ok=True)
        for index, team in enumerate(standings, start=1):
            name = team["team_name"]
            job["current"] = name
            target = out_dir / f"{report_export.safe_filename(name)}_{year}_team_report.pdf"
            try:
                report_export.run_in_qt_thread(
                    report_export.team_report_pdf, name, year, min_events, db, str(target)
                )
                job["successes"] += 1
                job["log"].append(f"[{index}/{len(standings)}] OK: {name} -> {target.name}")
            except Exception as exc:
                job["failures"] += 1
                job["log"].append(f"[{index}/{len(standings)}] FAIL: {name}: {exc}")
            job["done"] = index

        if job["successes"]:
            zip_path = out_dir.parent / f"team_reports_{year}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for pdf in sorted(out_dir.glob("*.pdf")):
                    zf.write(pdf, pdf.name)
            job["zip"] = str(zip_path)
        job["current"] = None
        job["status"] = "finished"

    threading.Thread(target=worker, daemon=True, name=f"job-{job_id}").start()
    return job_id


def public_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "zip"} | {"has_zip": bool(job.get("zip"))}


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

def _uploaded_name(handler) -> str:
    name = os.path.basename(unquote(handler.headers.get("X-Filename", "")))
    if not name or not re.search(r"\.(xlsx|xlsm|xltx|xltm)$", name, re.IGNORECASE):
        raise ApiError("Please provide an Excel file (.xlsx).")
    return name


def _read_body(handler) -> bytes:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        raise ApiError("Empty request body.")
    if length > MAX_UPLOAD_BYTES:
        raise ApiError("File too large.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    return handler.rfile.read(length)


def import_file_upload(handler) -> dict:
    name = _uploaded_name(handler)
    body = _read_body(handler)
    QUIZ_DIR.mkdir(parents=True, exist_ok=True)
    target = QUIZ_DIR / name
    target.write_bytes(body)
    try:
        return import_quiz_results.import_quiz_file(str(target), current_db())
    except Exception:
        target.unlink(missing_ok=True)
        raise


def import_themes_upload(handler) -> dict:
    name = _uploaded_name(handler)
    body = _read_body(handler)
    with tempfile.TemporaryDirectory(prefix="pqs-themes-") as tmp:
        path = Path(tmp) / name
        path.write_bytes(body)
        return import_quiz_results.import_event_themes(str(path), current_db())


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "PubQuizStats"

    def log_message(self, fmt, *args):
        if os.environ.get("PQS_VERBOSE"):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str, extra_headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-ancestors 'none'",
        )
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: int = HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if ALLOWED_HOSTS:
            return host in ALLOWED_HOSTS or host in {"localhost", "127.0.0.1", "::1"}
        return host in {"localhost", "127.0.0.1", "::1"} or self.server.allow_remote

    def _client_ip(self) -> str:
        if TRUST_PROXY:
            forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if forwarded:
                return forwarded
        return self.client_address[0]

    def _cookie(self, name: str) -> str:
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return ""

    def _is_admin(self) -> bool:
        return not ADMIN_PASSWORD or valid_session_token(self._cookie(SESSION_COOKIE))

    def _require_admin(self):
        if not self._is_admin():
            raise ApiError("Admin login required.", HTTPStatus.FORBIDDEN)

    def _session_cookie_header(self, token: str, max_age: int) -> dict:
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" and TRUST_PROXY else ""
        return {"Set-Cookie": f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{secure}"}

    def _login(self):
        ip = self._client_ip()
        now = time.time()
        with LOGIN_LOCK:
            fails = [t for t in LOGIN_FAILS.get(ip, []) if now - t < LOGIN_WINDOW]
            LOGIN_FAILS[ip] = fails
            if len(fails) >= LOGIN_MAX_FAILS:
                raise ApiError("Too many failed attempts. Try again later.", HTTPStatus.TOO_MANY_REQUESTS)
        password = str(self._json_body().get("password") or "")
        if not ADMIN_PASSWORD or not hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
            with LOGIN_LOCK:
                LOGIN_FAILS.setdefault(ip, []).append(now)
            time.sleep(0.5)
            raise ApiError("Wrong password.", HTTPStatus.UNAUTHORIZED)
        body = json.dumps({"ok": True}).encode()
        self._send(HTTPStatus.OK, body, "application/json", self._session_cookie_header(make_session_token(), SESSION_TTL))

    def _dispatch(self, method: str):
        if not self._host_allowed():
            return self._json({"error": "Forbidden host."}, HTTPStatus.FORBIDDEN)

        url = urlparse(self.path)
        try:
            if url.path.startswith("/api/"):
                if method == "POST" and self.headers.get("X-Requested-With") != "pubquizstats":
                    raise ApiError("Missing X-Requested-With header.", HTTPStatus.FORBIDDEN)
                return self._api(method, url.path, Params(parse_qs(url.query)))
            if method == "GET":
                return self._static(url.path)
            raise ApiError("Not found.", HTTPStatus.NOT_FOUND)
        except ApiError as exc:
            self._json({"error": str(exc)}, exc.status)
        except db_report.TeamNotInEventError as exc:
            self._json(
                {
                    "error": f"{exc.team_name} hat an diesem Event nicht teilgenommen.",
                    "code": "team_not_in_event",
                    "team": exc.team_name,
                    "event_date": exc.event_date,
                    "location": exc.location,
                },
                HTTPStatus.NOT_FOUND,
            )
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _static(self, path: str):
        rel = "index.html" if path in ("", "/") else unquote(path).lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in target.parents or not target.is_file():
            raise ApiError("Not found.", HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(HTTPStatus.OK, target.read_bytes(), ctype)

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length))
        except ValueError:
            raise ApiError("Invalid JSON body.")
        return data if isinstance(data, dict) else {}

    def _api(self, method: str, path: str, p: Params):
        route = path[len("/api/"):].strip("/")

        if route == "login" and method == "POST":
            return self._login()
        if route == "logout" and method == "POST":
            body = json.dumps({"ok": True}).encode()
            return self._send(HTTPStatus.OK, body, "application/json", self._session_cookie_header("", 0))

        if method == "POST" or route.startswith(("export/", "jobs/")):
            self._require_admin()

        if method == "GET":
            if route == "meta":
                return self._json(self._meta())
            if route == "teams":
                standings = db_report.get_championship_standings(p.year(), current_db()).get("standings", [])
                names = sorted({str(r.get("team_name", "")).strip() for r in standings} - {""}, key=str.casefold)
                return self._json({"teams": names})
            if route == "report":
                report = p.str("type")
                if report not in REPORT_TYPES:
                    raise ApiError(f"Unknown report '{report}'.")
                return self._json(run_report(report, p))
            if route.startswith("export/"):
                content, filename, ctype = build_export(route[len("export/"):], p)
                disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
                return self._send(HTTPStatus.OK, content, ctype, {"Content-Disposition": disposition})
            if route.startswith("jobs/"):
                parts = route.split("/")
                job = JOBS.get(parts[1])
                if job is None:
                    raise ApiError("Unknown job.", HTTPStatus.NOT_FOUND)
                if len(parts) == 3 and parts[2] == "zip":
                    if not job.get("zip"):
                        raise ApiError("No archive available.", HTTPStatus.NOT_FOUND)
                    zip_path = Path(job["zip"])
                    return self._send(
                        HTTPStatus.OK,
                        zip_path.read_bytes(),
                        "application/zip",
                        {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_path.name)}"},
                    )
                return self._json(public_job(job))
            raise ApiError("Not found.", HTTPStatus.NOT_FOUND)

        if route == "settings":
            body = self._json_body()
            settings = load_settings()
            for key in ("default_team", "db_path"):
                if key == "db_path" and ADMIN_PASSWORD:
                    continue  # remote deployments keep a fixed database
                if key in body:
                    settings[key] = str(body[key]).strip()
            save_settings(settings)
            return self._json({"ok": True, "settings": settings})
        if route == "import/file":
            return self._json(import_file_upload(self))
        if route == "import/themes":
            return self._json(import_themes_upload(self))
        if route == "import/folder":
            folder = str(self._json_body().get("path") or "").strip() or str(QUIZ_DIR)
            if ADMIN_PASSWORD:
                folder = str(QUIZ_DIR)
            if not os.path.isdir(folder):
                raise ApiError(f"Folder not found: {folder}")
            return self._json(import_quiz_results.import_quiz_folder(folder, current_db()))
        if route == "jobs/all-team-reports":
            body = self._json_body()
            year = int(body.get("year") or time.localtime().tm_year)
            return self._json({"job_id": start_all_team_reports(year, int(body.get("min_events") or 2))})
        raise ApiError("Not found.", HTTPStatus.NOT_FOUND)

    def _meta(self) -> dict:
        settings = load_settings()
        db = current_db()
        try:
            events = db_report.get_event_list(db)
            error = None
        except Exception as exc:
            events, error = [], str(exc)
        years = sorted({int(str(e["event_date"])[:4]) for e in events if e.get("event_date")}, reverse=True)
        admin = self._is_admin()
        return {
            "role": "admin" if admin else "guest",
            "auth_required": bool(ADMIN_PASSWORD),
            "db_path": db if admin else "",
            "db_error": error if admin else None,
            "default_team": settings.get("default_team", ""),
            "events": events,
            "years": years or [time.localtime().tm_year],
            "rounds": list(CATEGORY_NAMES),
            "converter": report_export.detect_office_converter() if admin else None,
        }


def main():
    parser = argparse.ArgumentParser(description="Start the PubQuizStats web GUI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)  # db_report/import use paths relative to the project root
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.allow_remote = args.host not in {"127.0.0.1", "localhost", "::1"}
    url = f"http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}/"
    print(f"PubQuizStats web GUI running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
