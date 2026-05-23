from datetime import datetime
from pathlib import Path

from jarvis.notebook import get_notebook


async def add_note(text: str, tags: list[str] | None = None, notebook_name: str | None = None) -> str:
    title = f"Note {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if tags:
        title += f" [{', '.join(tags)}]"

    async with get_notebook(name=notebook_name) as (client, notebook):
        source = await client.sources.add_text(
            notebook_id=notebook.id,
            title=title,
            content=text,
            wait=True,
        )
    return source.title or title


async def ingest_file(path: str, tags: list[str] | None = None, notebook_name: str | None = None) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if file_path.suffix not in (".txt", ".md"):
        raise ValueError(f"Unsupported file type: {file_path.suffix}. Use .txt or .md")

    title = file_path.stem
    if tags:
        title += f" [{', '.join(tags)}]"

    async with get_notebook(name=notebook_name) as (client, notebook):
        source = await client.sources.add_file(
            notebook_id=notebook.id,
            file_path=str(file_path),
            title=title,
            wait=True,
        )
    return source.title or title
