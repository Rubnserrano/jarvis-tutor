import asyncio
from datetime import date

import click

from jarvis.ingest import add_note, ingest_file
from jarvis.notebook import create_notebook, get_notebook
from jarvis.query import ask_question, search_notes
from jarvis.settings import get_active_notebook, set_active_notebook


@click.group()
def cli():
    """Jarvis — your personal learning assistant."""


@cli.command()
@click.argument("text", required=False)
@click.option("--file", "-f", "filepath", default=None, help="Path to a .txt or .md file")
@click.option("--tag", "-t", "tags", multiple=True, help="Tags for this note (repeatable)")
@click.option("--notebook", "-n", default=None, help="Target notebook (default: active notebook)")
def add(text, filepath, tags, notebook):
    """Add a note from TEXT or --file."""
    if not text and not filepath:
        raise click.UsageError("Provide TEXT or --file PATH")

    tag_list = list(tags) if tags else None

    try:
        if filepath:
            title = asyncio.run(ingest_file(filepath, tags=tag_list, notebook_name=notebook))
            click.echo(f"Ingested: {title}")
        else:
            title = asyncio.run(add_note(text, tags=tag_list, notebook_name=notebook))
            click.echo(f"Added: {title}")
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e))


@cli.command()
@click.argument("query")
@click.option("--notebook", "-n", default=None, help="Target notebook (default: active notebook)")
def search(query, notebook):
    """Search notes by semantic similarity."""
    result = asyncio.run(search_notes(query, notebook_name=notebook))
    click.echo(result)


@cli.command()
@click.argument("query")
@click.option("--notebook", "-n", default=None, help="Target notebook (default: active notebook)")
def ask(query, notebook):
    """Ask a question answered from your notes."""
    click.echo("Thinking...\n")
    answer = asyncio.run(ask_question(query, notebook_name=notebook))
    click.echo(answer)


@cli.command("list")
@click.option("--notebook", "-n", default=None, help="Target notebook (default: active notebook)")
def list_notes(notebook):
    """Show all sources stored in the notebook."""

    async def _list():
        async with get_notebook(name=notebook) as (client, nb):
            return nb.title, await client.sources.list(notebook_id=nb.id)

    nb_title, sources = asyncio.run(_list())
    click.echo(f"Notebook: {nb_title}")

    if not sources:
        click.echo("No notes stored yet. Use `jarvis add` to get started.")
        return

    click.echo(f"Total sources: {len(sources)}\n")
    for i, s in enumerate(sources, 1):
        date = s.created_at.strftime("%Y-%m-%d") if s.created_at else "unknown"
        click.echo(f"[{i}] {s.title or 'Untitled'}  (added: {date})")


@cli.group()
def notebook():
    """Manage notebooks."""


@notebook.command("create")
@click.argument("name")
def notebook_create(name):
    """Create a new notebook."""
    title = asyncio.run(create_notebook(name))
    click.echo(f"Notebook ready: {title}")
    click.echo(f"Tip: run `python cli.py use \"{title}\"` to make it active.")


@cli.command()
@click.argument("name")
def use(name):
    """Set the active notebook."""
    set_active_notebook(name)
    click.echo(f"Active notebook: {name}")


@cli.command()
def status():
    """Show the active notebook."""
    click.echo(f"Active notebook: {get_active_notebook()}")


@cli.command()
@click.option("--notebook", "-n", default=None, help="Notebook to study (default: active)")
@click.option("--text", is_flag=True, default=False, help="Use keyboard instead of microphone")
@click.option("--context", "context_file", default="PE_tutor.md", help="Tutor context file in context/")
def study(notebook, text, context_file):
    """Start an interactive study session with voice + screen vision."""
    from jarvis.tutor import TutorSession
    from jarvis.voice import listen, speak

    nb_name = notebook or get_active_notebook()

    try:
        session = TutorSession(notebook_name=nb_name, context_file=context_file)
    except RuntimeError as e:
        raise click.ClickException(str(e))

    welcome = session.start()
    click.echo(f"\nJarvis> {welcome}\n")
    if not text:
        speak(welcome)

    while True:
        try:
            if text:
                user_input = input("Tú> ").strip()
            else:
                click.echo("Tú> ", nl=False)
                user_input = listen()
                if not user_input:
                    click.echo("[no te escuché, repite o escribe]")
                    continue
                click.echo(user_input)

            if not user_input:
                continue

            response, should_exit = session.handle(user_input)

            if should_exit:
                farewell = "¡Hasta la próxima! Guardando tu progreso..."
                click.echo(f"\nJarvis> {farewell}")
                if not text:
                    speak(farewell)
                session.save()
                break

            click.echo(f"\nJarvis> {response}\n")
            if not text:
                interrupted = speak(response)
                if interrupted:
                    click.echo("[interrumpido — escuchando...]\nTú> ", nl=False)

        except (KeyboardInterrupt, EOFError):
            click.echo("\n\nGuardando sesión...")
            session.save()
            break


@cli.command()
@click.option("--notebook", "-n", default=None, help="Notebook (default: active)")
@click.option("--exam-date", "-d", default=None, help="Exam date YYYY-MM-DD")
@click.option("--topics", "-t", default=None, help="Comma-separated list of topics")
@click.option("--strong", default=None, help="Topics you already know well (comma-separated)")
@click.option("--weak", default=None, help="Topics you struggle with (comma-separated)")
def plan(notebook, exam_date, topics, strong, weak):
    """Generate or show a study plan for an upcoming exam.

    Example:
      python cli.py plan --exam-date 2026-06-15 \\
        --topics "Tema 1, Tema 2, Tema 3, Tema 4" \\
        --strong "Tema 2, Tema 3" \\
        --weak "Tema 1, Tema 4"
    """
    from jarvis.memory import get_memory
    from jarvis.planner import generate_plan, get_plan, today_plan_summary

    nb_name = notebook or get_active_notebook()

    if not exam_date and not topics:
        existing = get_plan(nb_name)
        if existing:
            summary = today_plan_summary(nb_name)
            click.echo(f"Plan activo para: {nb_name}")
            click.echo(f"Examen: {existing['exam_date']} | Temas: {', '.join(existing.get('topics', []))}")
            if existing.get("strong_topics"):
                click.echo(f"Fuertes: {', '.join(existing['strong_topics'])}")
            if existing.get("weak_topics"):
                click.echo(f"Débiles: {', '.join(existing['weak_topics'])}")
            click.echo()
            if summary:
                click.echo(summary)
            else:
                click.echo("No hay sesión programada para hoy.")
            return
        click.echo("No hay plan activo. Usa --exam-date y --topics para crear uno.")
        return

    if not exam_date:
        exam_date = click.prompt("Fecha del examen (YYYY-MM-DD)")
    if not topics:
        topics = click.prompt("Temas del examen (separados por coma)")

    try:
        parsed_date = date.fromisoformat(exam_date)
    except ValueError:
        raise click.ClickException(f"Fecha inválida: {exam_date}. Usa formato YYYY-MM-DD.")

    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    if not topic_list:
        raise click.ClickException("Debes especificar al menos un tema.")

    strong_list = [t.strip() for t in strong.split(",") if t.strip()] if strong else []
    weak_list   = [t.strip() for t in weak.split(",") if t.strip()] if weak else []

    mem = get_memory(nb_name)
    weak_areas = [
        (a["area"] if isinstance(a, dict) else a) for a in mem.get("weak_areas", [])
    ]

    click.echo("Generando plan de estudio con IA...")
    plan_data = generate_plan(
        nb_name, topic_list, parsed_date,
        weak_areas=weak_areas or None,
        strong_topics=strong_list or None,
        weak_topics=weak_list or None,
    )

    days = plan_data.get("days", [])
    weeks = plan_data.get("weeks", [])
    click.echo(f"\nPlan generado: {len(days)} sesiones hasta el {exam_date}\n")
    for week in weeks:
        click.echo(f"  Semana {week['week']} ({week['start']} → {week['end']}): {', '.join(week['topics'])}")
    click.echo()
    for day in days[:5]:
        strength_tag = f" [{day.get('strength','').upper()}]" if day.get('strength') else ""
        click.echo(f"  {day['date']}  [{day['focus']:10}]{strength_tag}  {day['topic']}")
    if len(days) > 5:
        click.echo(f"  ... y {len(days) - 5} días más")
    click.echo(f"\nGuardado en ~/.jarvis/plans/. Ejecuta sin flags para ver el plan completo.")


if __name__ == "__main__":
    cli()
