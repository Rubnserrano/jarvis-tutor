from contextlib import asynccontextmanager

from notebooklm import NotebookLMClient

from jarvis.settings import get_active_notebook


@asynccontextmanager
async def get_notebook(name: str | None = None):
    notebook_name = name or get_active_notebook()
    async with await NotebookLMClient.from_storage() as client:
        notebooks = await client.notebooks.list()
        notebook = next((nb for nb in notebooks if nb.title == notebook_name), None)
        if not notebook:
            notebook = await client.notebooks.create(title=notebook_name)
        yield client, notebook


async def create_notebook(name: str) -> str:
    async with await NotebookLMClient.from_storage() as client:
        notebooks = await client.notebooks.list()
        existing = next((nb for nb in notebooks if nb.title == name), None)
        if existing:
            return existing.title
        notebook = await client.notebooks.create(title=name)
        return notebook.title
