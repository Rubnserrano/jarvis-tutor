import json
import re
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path.home() / ".jarvis" / "memory"


def _slug(notebook: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", notebook.lower()).strip("_")


def _path(notebook: str) -> Path:
    return MEMORY_DIR / f"{_slug(notebook)}.json"


def get_memory(notebook: str) -> dict:
    p = _path(notebook)
    if p.exists():
        return json.loads(p.read_text())
    return {
        "notebook": notebook,
        "last_session": None,
        "session_count": 0,
        "topics_covered": [],
        "weak_areas": [],
    }


def save_memory(notebook: str, data: dict) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _path(notebook).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def summarize_memory(notebook: str) -> str:
    mem = get_memory(notebook)
    if mem["session_count"] == 0:
        return "Es la primera sesión del alumno con este material."

    lines = [f"Sesiones completadas: {mem['session_count']}"]
    if mem["last_session"]:
        lines.append(f"Última sesión: {mem['last_session']}")
    if mem["topics_covered"]:
        lines.append(f"Temas trabajados: {', '.join(mem['topics_covered'])}")
    if mem["weak_areas"]:
        lines.append(f"Áreas donde necesita refuerzo: {', '.join(mem['weak_areas'])}")
    return "\n".join(lines)


def record_session(notebook: str, topics: list[str]) -> None:
    mem = get_memory(notebook)
    mem["last_session"] = datetime.now().strftime("%Y-%m-%d")
    mem["session_count"] += 1
    for t in topics:
        if t and t not in mem["topics_covered"]:
            mem["topics_covered"].append(t)
    save_memory(notebook, mem)
