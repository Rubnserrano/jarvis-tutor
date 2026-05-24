import json
import os
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


def detect_blocks(notebook: str) -> list[dict]:
    """Cross-reference memory weak_areas + failed exercises to find recurring blocks."""
    from jarvis.memory import get_memory
    mem = get_memory(notebook)
    exercises = get_exercises(notebook)

    blocks: dict[str, dict] = {}

    for area in mem.get("weak_areas", []):
        label = area["area"] if isinstance(area, dict) else area
        detail = area.get("detail", "") if isinstance(area, dict) else ""
        blocks[label] = {"topic": label, "detail": detail, "fail_count": 1}

    for ex in exercises:
        if not ex.get("understood", True):
            topic = ex.get("topic", "")
            if topic:
                if topic in blocks:
                    blocks[topic]["fail_count"] += 1
                else:
                    blocks[topic] = {"topic": topic, "detail": "", "fail_count": 1}

    return sorted(blocks.values(), key=lambda x: -x["fail_count"])


def generate_adaptive_exercise(notebook: str, topic: str, level: str = "intermedio") -> dict:
    """Ask Gemini to generate an exercise tailored to the user's weak area."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    exercises = get_exercises(notebook)
    past = [ex.get("problem", "") for ex in exercises if ex.get("topic", "").lower() == topic.lower()]

    levels = {"basico": "básico (conceptos fundamentales)", "intermedio": "intermedio", "examen": "dificultad de examen", "mixto": "problema mixto que combina varios conceptos"}
    level_desc = levels.get(level, "intermedio")

    past_block = "\n".join(f"- {p}" for p in past[-5:]) if past else "Ninguno todavía."
    prompt = f"""Genera un ejercicio de nivel {level_desc} sobre el tema: **{topic}**

Ejercicios anteriores sobre este tema (no repetir):
{past_block}

Responde SOLO el siguiente JSON (sin texto extra, sin markdown):
{{
  "problem": "Enunciado completo del ejercicio",
  "topic": "{topic}",
  "level": "{level}",
  "concepts": ["concepto1", "concepto2"],
  "hint_1": "Pista muy general, sin mencionar procedimiento",
  "hint_2": "Qué concepto o fórmula usar",
  "hint_3": "Primer paso parcial del desarrollo",
  "hint_4": "Desarrollo casi completo, dejando el último paso al alumno",
  "solution_outline": "Esquema completo de la solución (solo para el tutor)"
}}"""

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(temperature=0.7),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("```").strip()
    return json.loads(text)


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
