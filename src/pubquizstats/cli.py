"""Command-line interface for PubQuizStats."""

import logging
import sys
from pathlib import Path
import click
from tabulate import tabulate
from pubquizstats.database import get_session, init_db
from pubquizstats.processing import ImportPipeline, TeamDeduplicator
from pubquizstats.analytics import QuizAnalyzer
from pubquizstats.config import QUIZ_DIR

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """PubQuizStats - Analyze pub quiz results."""
    pass


@cli.command()
def init():
    """Initialize database."""
    click.echo("Initializing database...")
    try:
        init_db()
        click.echo("✓ Database initialized successfully")
    except Exception as e:
        click.echo(f"✗ Error initializing database: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--auto-merge/--no-auto-merge", default=True, help="Auto-merge similar team names")
def import_quiz(file_path: str, auto_merge: bool):
    """Import quiz from Excel file."""
    session = get_session()
    pipeline = ImportPipeline(session)

    click.echo(f"Importing quiz from: {file_path}")
    result = pipeline.import_quiz(file_path, auto_merge=auto_merge)

    if result.success:
        click.echo(f"✓ Quiz imported successfully (ID: {result.quiz_id})")
        click.echo(f"  New teams: {result.new_teams}")
        click.echo(f"  Merged teams: {result.merged_teams}")
    else:
        click.echo("✗ Import failed:", err=True)
        for error in result.errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)

    if result.warnings:
        click.echo("Warnings:")
        for warning in result.warnings:
            click.echo(f"  - {warning}")

    session.close()


@cli.command()
def review_merges():
    """Review and approve potential team merges."""
    session = get_session()
    deduplicator = TeamDeduplicator(session)

    suggestions = deduplicator.suggest_merges()

    if not suggestions:
        click.echo("No potential merges found")
        return

    click.echo(f"Found {len(suggestions)} potential team merges:\n")

    for i, (team1, team2, score) in enumerate(suggestions, 1):
        click.echo(f"{i}. Merge '{team1.name}' into '{team2.name}'? (similarity: {score:.1%})")
        response = click.prompt("  [y]es, [n]o, [s]kip all", type=click.Choice(["y", "n", "s"]))

        if response == "y":
            deduplicator.merge_teams(team2.id, team1.id)
            click.echo(f"   ✓ Merged")
        elif response == "s":
            break

    session.close()


@cli.command()
@click.option("--team", type=str, help="Filter by team name")
def list_teams(team: str):
    """List all teams."""
    session = get_session()
    deduplicator = TeamDeduplicator(session)

    teams_by_group = deduplicator.session.query(
        __import__("pubquizstats.models.database", fromlist=["Team"]).Team
    ).all()

    if not teams_by_group:
        click.echo("No teams found")
        return

    data = []
    for t in teams_by_group:
        canonical = deduplicator.get_team_canonical_name(t.id)
        participations = (
            session.query(
                __import__("pubquizstats.models.database", fromlist=["QuizParticipation"]).QuizParticipation
            )
            .filter_by(team_id=t.id)
            .count()
        )
        data.append([t.id, t.name, canonical, participations])

    headers = ["ID", "Name", "Canonical Name", "Quizzes"]
    click.echo(tabulate(data, headers=headers))
    session.close()


@cli.command()
@click.argument("team_name", type=str)
def stats_team(team_name: str):
    """Get statistics for a team."""
    session = get_session()
    analyzer = QuizAnalyzer(session)
    team_repo = __import__("pubquizstats.database.repositories", fromlist=["TeamRepository"]).TeamRepository(session)

    team = team_repo.get_by_name(team_name)
    if not team:
        click.echo(f"✗ Team '{team_name}' not found", err=True)
        sys.exit(1)

    stats = analyzer.get_team_stats(team.id)
    if not stats:
        click.echo(f"✗ No statistics available for team '{team_name}'", err=True)
        sys.exit(1)

    click.echo(f"\nStatistics for: {stats.canonical_name or stats.team_name}")
    click.echo(f"{'=' * 50}")
    click.echo(f"Quizzes participated: {stats.quizzes_participated}")
    click.echo(f"Total points: {stats.total_points}")
    click.echo(f"Average points: {stats.average_points}")
    click.echo(f"Average rank: {stats.average_rank}")
    click.echo(f"Wins: {stats.wins}")
    click.echo(f"Podium finishes: {stats.podium_finishes}")

    if stats.points_by_round:
        click.echo(f"\nAverage points by round:")
        for round_num in sorted(stats.points_by_round.keys()):
            points = stats.points_by_round[round_num]
            click.echo(f"  Round {round_num}: {points}")

    session.close()


@cli.command()
def ranking():
    """Show overall team ranking."""
    session = get_session()
    analyzer = QuizAnalyzer(session)

    df = analyzer.get_team_ranking()

    if df.empty:
        click.echo("No team statistics available")
        return

    click.echo("\nOverall Team Ranking")
    click.echo("=" * 80)
    click.echo(tabulate(df, headers="keys", tablefmt="grid", showindex=False))
    session.close()


@cli.command()
def list_quizzes():
    """List all imported quizzes."""
    session = get_session()
    from pubquizstats.models.database import Quiz

    quizzes = session.query(Quiz).order_by(Quiz.date.desc()).all()

    if not quizzes:
        click.echo("No quizzes found")
        return

    data = []
    for quiz in quizzes:
        participant_count = len(quiz.participations)
        data.append([quiz.id, quiz.name, quiz.date.date(), quiz.location or "-", participant_count])

    headers = ["ID", "Name", "Date", "Location", "Teams"]
    click.echo("\nImported Quizzes")
    click.echo("=" * 80)
    click.echo(tabulate(data, headers=headers))
    session.close()


@cli.command()
@click.argument("quiz_id", type=int)
def quiz_details(quiz_id: int):
    """Show details for a specific quiz."""
    session = get_session()
    analyzer = QuizAnalyzer(session)

    quiz_stats = analyzer.get_quiz_statistics(quiz_id)

    if not quiz_stats:
        click.echo(f"✗ Quiz {quiz_id} not found", err=True)
        sys.exit(1)

    click.echo(f"\nQuiz: {quiz_stats.get('quiz_id', 'Unknown')}")
    click.echo(f"{'=' * 50}")
    click.echo(f"Total teams: {quiz_stats['total_teams']}")
    click.echo(f"\nRanking:")

    data = []
    for entry in quiz_stats["ranking"]:
        data.append([entry["rank"], entry["team"], entry["points"]])

    headers = ["Rank", "Team", "Points"]
    click.echo(tabulate(data, headers=headers))
    session.close()


@cli.command()
@click.option("--format", type=click.Choice(["csv", "json"]), default="csv", help="Output format")
@click.option("--output", type=click.Path(), required=True, help="Output file path")
def export(format: str, output: str):
    """Export ranking data."""
    session = get_session()
    analyzer = QuizAnalyzer(session)

    click.echo(f"Exporting ranking as {format}...")

    if format == "csv":
        df = analyzer.get_team_ranking()
        if analyzer.export_to_csv(df, output):
            click.echo(f"✓ Exported to {output}")
        else:
            click.echo("✗ Export failed", err=True)
            sys.exit(1)
    elif format == "json":
        stats = [s.__dict__ for s in analyzer.get_all_team_stats()]
        if analyzer.export_to_json({"teams": stats}, output):
            click.echo(f"✓ Exported to {output}")
        else:
            click.echo("✗ Export failed", err=True)
            sys.exit(1)

    session.close()


if __name__ == "__main__":
    cli()
