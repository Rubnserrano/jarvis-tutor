from jarvis.notebook import get_notebook


async def ask_question(query: str, notebook_name: str | None = None) -> str:
    async with get_notebook(name=notebook_name) as (client, notebook):
        result = await client.chat.ask(notebook_id=notebook.id, question=query)
    return result.answer


async def search_notes(query: str, notebook_name: str | None = None) -> str:
    prompt = f"Find and summarize all notes related to: {query}"
    async with get_notebook(name=notebook_name) as (client, notebook):
        result = await client.chat.ask(notebook_id=notebook.id, question=prompt)
    return result.answer


async def search_notes_with_references(
    query: str, notebook_name: str | None = None
) -> tuple[str, list[dict]]:
    """Search notes and return the answer plus structured source citations.

    Each reference dict has:
        source_id: str — UUID for follow-up context fetching
        title: str — PDF / document filename
        citation_number: int | None
        cited_texts: list[str] — exact passages cited from that source
    """
    prompt = f"Find and summarize all notes related to: {query}"
    async with get_notebook(name=notebook_name) as (client, notebook):
        result = await client.chat.ask(notebook_id=notebook.id, question=prompt)

        references: list[dict] = []
        if result.references:
            sources_list = await client.sources.list(notebook_id=notebook.id)
            source_titles = {s.id: s.title for s in sources_list}

            seen: dict[str, int] = {}
            for ref in result.references:
                title = source_titles.get(ref.source_id, "Fuente desconocida")
                if ref.source_id not in seen:
                    seen[ref.source_id] = len(references)
                    references.append({
                        "source_id": ref.source_id,
                        "title": title,
                        "citation_number": ref.citation_number,
                        "cited_texts": [],
                    })
                idx = seen[ref.source_id]
                if ref.cited_text and ref.cited_text not in references[idx]["cited_texts"]:
                    references[idx]["cited_texts"].append(ref.cited_text)

    return result.answer, references


async def get_source_context(
    notebook_name: str,
    source_id: str,
    cited_text: str,
    context_chars: int = 500,
) -> dict:
    """Return expanded context around a cited passage, plus the source title."""
    async with get_notebook(name=notebook_name) as (client, notebook):
        fulltext = await client.sources.get_fulltext(
            notebook_id=notebook.id, source_id=source_id
        )
        title = fulltext.title
        content = ""
        if cited_text:
            matches = fulltext.find_citation_context(cited_text, context_chars=context_chars)
            if matches:
                content = matches[0][0]
        if not content and fulltext.content:
            content = fulltext.content[:1000]

    return {"title": title, "content": content}
