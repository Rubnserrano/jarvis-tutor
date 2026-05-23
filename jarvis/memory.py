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
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "notebook": notebook,
        "last_session": None,
        "session_count": 0,
        "topics_covered": [],
        "weak_areas": [],
        "strengths": [],
    }


def save_memory(notebook: str, data: dict) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _path(notebook).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def summarize_memory(notebook: str) -> str:
    mem = get_memory(notebook)
    if mem["session_count"] == 0:
        return "Es la primera sesión del alumno con este material."

    lines = [f"Sesiones completadas: {mem['session_count']}"]
    if mem["last_session"]:
        lines.append(f"Última sesión: {mem['last_session']}")
    if mem["topics_covered"]:
        lines.append(f"Temas trabajados: {', '.join(mem['topics_covered'])}")
    if mem.get("strengths"):
        lines.append(f"Puntos fuertes: {', '.join(mem['strengths'])}")
    if mem["weak_areas"]:
        areas = mem["weak_areas"]
        if areas and isinstance(areas[0], dict):
            formatted = [f"{a['area']} ({a.get('detail', '')})" for a in areas]
        else:
            formatted = areas
        lines.append(f"Áreas de mejora: {', '.join(formatted)}")
    return "\n".join(lines)


def record_session(
    notebook: str,
    topics: list[str],
    weak_areas: list[str | dict] | None = None,
    strengths: list[str] | None = None,
) -> None:
    mem = get_memory(notebook)
    mem["last_session"] = datetime.now().strftime("%Y-%m-%d")
    mem["session_count"] += 1

    for t in topics:
        if t and t not in mem["topics_covered"]:
            mem["topics_covered"].append(t)

    if weak_areas:
        existing_labels = {
            (a["area"] if isinstance(a, dict) else a)
            for a in mem["weak_areas"]
        }
        for area in weak_areas:
            label = area["area"] if isinstance(area, dict) else area
            if label not in existing_labels:
                mem["weak_areas"].append(area)
                existing_labels.add(label)
            else:
                # Update detail if richer info provided
                if isinstance(area, dict):
                    for i, existing in enumerate(mem["weak_areas"]):
                        existing_label = existing["area"] if isinstance(existing, dict) else existing
                        if existing_label == label:
                            mem["weak_areas"][i] = area
                            break

    if strengths:
        for s in strengths:
            if s and s not in mem.get("strengths", []):
                mem.setdefault("strengths", []).append(s)

    save_memory(notebook, mem)
