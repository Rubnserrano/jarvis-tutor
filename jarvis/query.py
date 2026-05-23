from jarvis.notebook import get_notebook


async def ask_question(query: str, notebook_name: str | None = None) -> str:
    async with get_notebook(name=notebook_name) as (client, notebook):
        result = await client.chat.ask(
            notebook_id=notebook.id,
            question=query,
        )
    return result.answer


async def search_notes(query: str, notebook_name: str | None = None) -> str:
    prompt = f"Find and summarize all notes related to: {query}"
    async with get_notebook(name=notebook_name) as (client, notebook):
        result = await client.chat.ask(
            notebook_id=notebook.id,
            question=prompt,
        )
    return result.answer
