import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

PLANS_DIR = Path.home() / ".jarvis" / "plans"


def _slug(notebook: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", notebook.lower()).strip("_")


def _path(notebook: str) -> Path:
    return PLANS_DIR / f"{_slug(notebook)}.json"


def get_plan(notebook: str) -> dict | None:
    p = _path(notebook)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def save_plan(notebook: str, plan: dict) -> None:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    _path(notebook).write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _group_weeks(days: list[dict]) -> list[dict]:
    """Attach week numbers and build a weeks summary list."""
    weeks: dict[int, dict] = {}
    for day in days:
        d = date.fromisoformat(day["date"])
        # ISO week number relative to the first day
        wnum = (d - date.fromisoformat(days[0]["date"])).days // 7 + 1
        day["week"] = wnum
        if wnum not in weeks:
            weeks[wnum] = {
                "week": wnum,
                "start": day["date"],
                "end": day["date"],
                "topics": [],
                "focus": day.get("focus", ""),
            }
        weeks[wnum]["end"] = day["date"]
        topic = day.get("topic", "")
        if topic and topic not in weeks[wnum]["topics"]:
            weeks[wnum]["topics"].append(topic)
    return list(weeks.values())


def generate_plan(
    notebook: str,
    topics: list[str],
    exam_date: date,
    weak_areas: list[str] | None = None,
    strong_topics: list[str] | None = None,
    weak_topics: list[str] | None = None,
) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    today = date.today()
    days_left = (exam_date - today).days

    # Build topic strength description
    topic_lines = []
    for t in topics:
        if strong_topics and t in strong_topics:
            topic_lines.append(f"  - {t} → FUERTE (el alumno lo domina bien)")
        elif weak_topics and t in weak_topics:
            topic_lines.append(f"  - {t} → DÉBIL (necesita refuerzo importante)")
        elif weak_areas and t in weak_areas:
            topic_lines.append(f"  - {t} → DÉBIL (área de mejora detectada)")
        else:
            topic_lines.append(f"  - {t} → nivel medio")
    topics_str = "\n".join(topic_lines)

    prompt = f"""Eres un planificador de estudio experto. El alumno tiene un examen el {exam_date.isoformat()} ({days_left} días desde hoy, {today.isoformat()}).

Nivel del alumno por tema:
{topics_str}

Crea un plan de estudio día a día en JSON con esta estructura exacta:
{{
  "exam_date": "{exam_date.isoformat()}",
  "generated": "{today.isoformat()}",
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "day_number": 1,
      "topic": "nombre del tema",
      "objective": "qué debe dominar el alumno al final de esta sesión (una frase concreta y accionable)",
      "focus": "teoría|ejercicios|repaso|simulacro",
      "exercises_suggested": ["tipo de ejercicio 1", "tipo de ejercicio 2"],
      "difficulty": "baja|media|alta",
      "strength": "fuerte|medio|débil"
    }}
  ]
}}

Reglas de planificación:
- Temas FUERTES: 1 sesión de repaso rápido + ejercicios, al principio del plan
- Temas DÉBILES: 2-3 sesiones (teoría → ejercicios → repaso), distribuidas a lo largo del plan
- Temas MEDIOS: 1-2 sesiones según el tiempo disponible
- Los últimos 3 días: repasos generales y simulacro de examen
- Incluye un día de descanso cada 6 días si hay suficiente tiempo (focus: "descanso", topic: "Descanso")
- Varía el focus: no pongas ejercicios todos los días seguidos
- Responde SOLO el JSON, sin texto adicional ni explicaciones"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(temperature=0.3),
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("```").strip()

    plan_data = json.loads(text)
    plan_data["notebook"] = notebook
    plan_data["topics"] = topics
    plan_data["strong_topics"] = strong_topics or []
    plan_data["weak_topics"] = weak_topics or []
    plan_data["weak_areas"] = weak_areas or []
    plan_data["weeks"] = _group_weeks(plan_data.get("days", []))
    save_plan(notebook, plan_data)
    return plan_data


def today_plan_summary(notebook: str) -> str:
    plan = get_plan(notebook)
    if not plan:
        return ""

    today_str = date.today().isoformat()
    exam_str = plan.get("exam_date", "")
    if not exam_str:
        return ""

    days_left = (date.fromisoformat(exam_str) - date.today()).days
    if days_left < 0:
        return ""

    for day in plan.get("days", []):
        if day.get("date") == today_str:
            lines = [
                f"## Plan de hoy ({today_str}) — {days_left} días para el examen",
                f"**Tema**: {day['topic']}",
                f"**Objetivo**: {day['objective']}",
                f"**Foco**: {day['focus']} | **Dificultad**: {day['difficulty']}",
            ]
            if day.get("exercises_suggested"):
                lines.append(f"**Ejercicios sugeridos**: {', '.join(day['exercises_suggested'])}")
            return "\n".join(lines)

    # Show the next scheduled day
    for day in plan.get("days", []):
        if day.get("date", "") >= today_str:
            return (
                f"## Próxima sesión ({day['date']}) — {days_left} días para el examen\n"
                f"**Tema**: {day['topic']}\n"
                f"**Objetivo**: {day['objective']}"
            )

    return ""
