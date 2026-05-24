from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from jarvis.exercises import add_exercise, exercises_context, find_similar
from jarvis.memory import record_session, summarize_memory
from jarvis.planner import today_plan_summary
from jarvis.query import search_notes_with_references
from jarvis.screen import capture_screenshot

load_dotenv()

CONTEXT_DIR = Path(__file__).parent.parent / "context"
_EXIT_KEYWORDS = {"salir", "exit", "quit", "adiós", "bye"}
_MEMORY_KEYWORDS = {"memoria", "progreso", "qué hemos visto"}

_CONTINUATION_RE = re.compile(
    r"^("
    r"sigue|continúa|continua|siguiente|próximo|ahora|"
    r"ok|vale|bien|entendido|de acuerdo|perfecto|claro|exacto|correcto|"
    r"sí|si\b|no\b|"
    r"y |pero |entonces |pues |así que |"
    r"(el |la |los |las )?(apartado|parte|sección|punto|ejercicio)\s+[a-zA-Z0-9]|"
    r"más|mas|explica más|repite|no entendí|no entiendo|no sé"
    r")",
    re.IGNORECASE,
)


def _needs_search(message: str) -> bool:
    """Return False for continuation/short messages that don't need a new NotebookLM query."""
    s = message.strip()
    # Very short with no question mark → likely a continuation or command
    if len(s) < 28 and "?" not in s:
        return False
    if _CONTINUATION_RE.match(s.lower()):
        return False
    return True


def _load_context(context_file: str, memory_summary: str, exercises_ctx: str, today_plan: str) -> str:
    path = CONTEXT_DIR / context_file
    if path.exists():
        template = path.read_text(encoding="utf-8")
        return (
            template
            .replace("{memory_summary}", memory_summary)
            .replace("{exercises_context}", exercises_ctx)
            .replace("{today_plan}", today_plan)
        )
    return f"Eres un tutor universitario.\n\nProgreso:\n{memory_summary}"


class TutorSession:
    def __init__(self, notebook_name: str, context_file: str = "PE_tutor.md"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY no encontrada.\n"
                "Añádela al archivo .env del proyecto:\n"
                "  echo 'GEMINI_API_KEY=tu_key' > .env"
            )

        self.client = genai.Client(api_key=api_key)
        self.notebook_name = notebook_name
        self.history: list[types.Content] = []
        self.last_context = ""
        self.last_screenshot_path: str | None = None
        self.last_references: list[dict] = []
        self._notation_detected = False

        memory_summary = summarize_memory(notebook_name)
        exercises_ctx = exercises_context(notebook_name)
        today_plan = today_plan_summary(notebook_name)
        self.system_prompt = _load_context(context_file, memory_summary, exercises_ctx, today_plan)

    def start(self) -> str:
        plan = today_plan_summary(self.notebook_name)
        if plan:
            topic_line = next((l for l in plan.splitlines() if "Tema" in l), "")
            topic = topic_line.replace("**Tema**:", "").strip() if topic_line else ""
            if topic:
                return (
                    f"Hola. Hoy toca trabajar **{topic}** según tu plan de estudio. "
                    "¿Empezamos con la teoría o prefieres ir directo a un ejercicio?"
                )
        return (
            f"Hola, soy tu tutor de {self.notebook_name}. "
            "¿Qué ejercicio o tema quieres trabajar hoy?"
        )

    def _detect_and_apply_notation(self, sample: str) -> None:
        """Extract notation conventions from a notes sample and append to system prompt."""
        if not sample or len(sample) < 100:
            return
        prompt = (
            "Del siguiente fragmento de apuntes, extrae la notación matemática que se usa. "
            "Lista únicamente los símbolos y variables clave con su significado. "
            "Sé muy conciso (máximo 12 líneas). Si no hay notación clara, responde vacío.\n\n"
            "Formato de respuesta:\n- $símbolo$: significado\n\n"
            f"Fragmento:\n{sample[:2500]}"
        )
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(temperature=0.1),
            )
            notation = response.text.strip()
            if notation and len(notation) > 20:
                self.system_prompt += (
                    f"\n\n## Notación de los apuntes del alumno\n"
                    f"Usa SIEMPRE esta notación en tus respuestas:\n{notation}"
                )
        except Exception:
            pass

    def _fetch_context(self, message: str) -> str:
        if not _needs_search(message):
            return self.last_context if self.last_context else ""
        try:
            result, references = asyncio.run(
                search_notes_with_references(message, notebook_name=self.notebook_name)
            )
            self.last_context = result
            self.last_references = references

            if not self._notation_detected:
                # Use cited texts (raw source passages) for notation detection
                sample = " ".join(
                    t for ref in references for t in ref.get("cited_texts", [])
                ) or result
                self._detect_and_apply_notation(sample)
                self._notation_detected = True

            return result
        except Exception as e:
            self.last_context = (
                f"⚠️ NotebookLM no disponible: {e}\n"
                "Ejecuta 'notebooklm auth' desde PowerShell para conectar tus apuntes."
            )
            return ""

    def _send(self, parts: list) -> str:
        self.history.append(
            types.Content(
                role="user",
                parts=[types.Part(text=str(p)) if isinstance(p, str) else p for p in parts],
            )
        )

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=self.history,
            config=types.GenerateContentConfig(system_instruction=self.system_prompt),
        )

        reply = response.text
        self.history.append(types.Content(role="model", parts=[types.Part(text=reply)]))
        return reply

    def chat_text(self, message: str, image_path: str | None = None) -> str:
        context = self._fetch_context(message)
        parts: list = []

        if context:
            parts.append(f"[Contexto de tus apuntes]\n{context}\n")

        if image_path:
            try:
                img_bytes = Path(image_path).read_bytes()
                parts.append(
                    types.Part(inline_data=types.Blob(mime_type="image/png", data=img_bytes))
                )
                parts.append("Aquí tienes el estado actual de la pantalla del alumno.")
            except Exception as e:
                parts.append(f"[No se pudo cargar el screenshot: {e}]")

        parts.append(message)
        return self._send(parts)

    def handle(self, message: str) -> tuple[str, bool]:
        lower = message.lower().strip()

        if any(k in lower for k in _EXIT_KEYWORDS):
            return "", True

        if any(k in lower for k in _MEMORY_KEYWORDS):
            return summarize_memory(self.notebook_name), False

        screenshot_path = None
        try:
            screenshot_path = capture_screenshot()
            self.last_screenshot_path = screenshot_path
        except RuntimeError:
            self.last_screenshot_path = None

        return self.chat_text(message, image_path=screenshot_path), False

    def _extract_session_data(self) -> dict:
        if not self.history:
            return {"topics": [], "exercises": [], "weak_areas": [], "strengths": []}

        conversation = "\n".join(
            f"{msg.role.upper()}: {msg.parts[0].text}"
            for msg in self.history
            if msg.parts and hasattr(msg.parts[0], "text") and msg.parts[0].text
        )

        prompt = f"""Analiza esta sesión de tutoría y extrae la siguiente información en JSON:

{{
  "topics": ["lista de temas matemáticos o de la asignatura trabajados"],
  "exercises": [
    {{
      "problem": "descripción del ejercicio (max 200 chars)",
      "topic": "tema principal",
      "concepts": ["concepto1", "concepto2"],
      "key_steps": ["paso clave 1", "paso clave 2"],
      "difficulty": "baja|media|alta",
      "understood": true
    }}
  ],
  "weak_areas": [
    {{"area": "nombre del área", "detail": "descripción específica del problema"}}
  ],
  "strengths": ["cosa que el alumno domina bien"]
}}

Reglas:
- Solo incluye ejercicios que realmente se trabajaron en la sesión
- "understood" es false si el alumno tuvo dificultades significativas
- Los "key_steps" deben ser útiles para recordar cómo resolver ejercicios similares
- Si no hay datos suficientes para un campo, pon lista vacía
- Responde SOLO el JSON

SESIÓN:
{conversation[:6000]}"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(temperature=0.1),
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("```").strip()
            return json.loads(text)
        except Exception:
            return {"topics": [], "exercises": [], "weak_areas": [], "strengths": []}

    def save(self) -> None:
        data = self._extract_session_data()

        for ex in data.get("exercises", []):
            similar = find_similar(
                self.notebook_name,
                ex.get("topic", ""),
                ex.get("concepts", []),
            )
            if similar:
                ex["similar_to"] = [s["id"] for s in similar]
            add_exercise(self.notebook_name, ex)

        record_session(
            self.notebook_name,
            topics=data.get("topics", []),
            weak_areas=data.get("weak_areas"),
            strengths=data.get("strengths"),
        )
