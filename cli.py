import asyncio

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


if __name__ == "__main__":
    cli()
