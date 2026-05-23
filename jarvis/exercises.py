import json
import re
from datetime import datetime
from pathlib import Path

EXERCISES_DIR = Path.home() / ".jarvis" / "exercises"


def _slug(notebook: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", notebook.lower()).strip("_")


def _path(notebook: str) -> Path:
    return EXERCISES_DIR / f"{_slug(notebook)}.json"


def get_exercises(notebook: str) -> list[dict]:
    p = _path(notebook)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get("exercises", [])
    return []


def add_exercise(notebook: str, exercise: dict) -> str:
    EXERCISES_DIR.mkdir(parents=True, exist_ok=True)
    exercises = get_exercises(notebook)
    ex_id = f"ex_{len(exercises) + 1:03d}"
    exercise = {"id": ex_id, "date": datetime.now().strftime("%Y-%m-%d"), **exercise}
    exercises.append(exercise)
    _path(notebook).write_text(
        json.dumps({"notebook": notebook, "exercises": exercises}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return ex_id


def find_similar(notebook: str, topic: str, concepts: list[str]) -> list[dict]:
    exercises = get_exercises(notebook)
    scored = []
    topic_lower = topic.lower()
    concept_set = {c.lower() for c in concepts}
    for ex in exercises:
        score = 3 if ex.get("topic", "").lower() == topic_lower else 0
        score += len({c.lower() for c in ex.get("concepts", [])} & concept_set)
        if score > 0:
            scored.append((score, ex))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [ex for _, ex in scored[:3]]


def exercises_context(notebook: str) -> str:
    exercises = get_exercises(notebook)
    if not exercises:
        return ""
    by_topic: dict[str, list] = {}
    for ex in exercises:
        by_topic.setdefault(ex.get("topic", "General"), []).append(ex)

    lines = ["## Ejercicios resueltos en sesiones anteriores"]
    for topic, exs in by_topic.items():
        lines.append(f"\n**{topic}** ({len(exs)} ejercicios):")
        for ex in exs[-3:]:
            status = "✓" if ex.get("understood", True) else "✗ (pendiente de repasar)"
            problem = ex.get("problem", "")[:100]
            lines.append(f"  [{ex['id']}] {status} {problem}")
            if ex.get("key_steps"):
                lines.append(f"    → Clave: {ex['key_steps'][0]}")
    return "\n".join(lines)
