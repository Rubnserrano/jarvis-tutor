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

load_dotenv()

CONTEXT_DIR = Path(__file__).parent.parent / "context"
_EXIT_KEYWORDS = {"salir", "exit", "quit", "adiós", "bye"}
_MEMORY_KEYWORDS = {"memoria", "progreso", "qué hemos visto"}

MODES = {"examen", "tutor", "explicacion", "companero", "pizarra"}

_MODE_INSTRUCTIONS: dict[str, str] = {
    "examen": (
        "MODO EXAMEN ACTIVO: Nunca reveles la respuesta completa. Tu función es únicamente "
        "validar si el razonamiento del alumno va bien o señalar el primer error. "
        "Si el alumno pide la solución directamente, dile que debe llegar solo. "
        "Solo haz preguntas de validación, no expliques el procedimiento."
    ),
    "tutor": (
        "MODO TUTOR: Guía al alumno paso a paso. Haz una sola pregunta intermedia por turno. "
        "Da pistas progresivas antes de revelar algo. No des el siguiente paso sin que el alumno intente el actual."
    ),
    "explicacion": (
        "MODO EXPLICACIÓN: Explica el concepto o problema de forma completa, directa y clara. "
        "Incluye ejemplos y razonamiento. No hagas preguntas Socráticas — explica tú."
    ),
    "companero": (
        "MODO COMPAÑERO: Resuelve el ejercicio como si fueras un compañero de estudio. "
        "Usa 'nosotros', piensa en voz alta, muestra tus dudas y razona junto al alumno. "
        "Sé natural, colaborativo y cercano."
    ),
    "pizarra": (
        "MODO PIZARRA: Estás observando periódicamente la pantalla o pizarra del alumno mientras trabaja. "
        "Sé MUY breve — máximo 2 frases. "
        "Si el trabajo parece correcto: di solo '✓ Bien, continúa.' "
        "Si ves un error obvio: señálalo en una frase directa sin explicar el procedimiento completo. "
        "Si no hay actividad visible: di 'Sin actividad visible.' "
        "Solo responde con más detalle si el alumno te pregunta algo directamente."
    ),
}

_HINT_INSTRUCTIONS: dict[int, str] = {
    1: (
        "El alumno pide una PISTA NIVEL 1 (muy pequeña). Da únicamente una orientación "
        "general sin mencionar el procedimiento ni la fórmula concreta. Máximo 2 frases."
    ),
    2: (
        "El alumno pide una PISTA NIVEL 2. Indica qué concepto o fórmula debe usar, "
        "sin mostrar cómo aplicarla. Máximo 3 frases."
    ),
    3: (
        "El alumno pide una PISTA NIVEL 3. Muestra el siguiente paso parcial sin completarlo. "
        "Máximo 4 frases."
    ),
    4: (
        "El alumno pide una PISTA NIVEL 4 (casi solución). Muestra el desarrollo hasta "
        "casi el final dejando el último paso al alumno."
    ),
}

_HINT_RE = re.compile(
    r"\b(pista|hint|ayuda un poco|clue|no\s+s[eé]|no\s+entiendo|atascad[oa]|"
    r"bloqueado|ayúdame|ayudame|una\s+pista|dame\s+una\s+pista|otra\s+pista|"
    r"pista\s+m[aá]s\s+grande|pista\s+m[aá]s\s+peque[ñn]a)\b",
    re.IGNORECASE,
)

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
        self.mode: str = "tutor"
        self.hint_level: int = 0

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

    def set_mode(self, mode: str) -> None:
        if mode in MODES:
            self.mode = mode
            self.hint_level = 0

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

    def chat_text(self, message: str, image_path: str | None = None, is_hint: bool = False) -> str:
        context = self._fetch_context(message)
        parts: list = []

        if context:
            parts.append(f"[Contexto de tus apuntes]\n{context}\n")

        mode_instr = _MODE_INSTRUCTIONS.get(self.mode, "")
        if mode_instr:
            parts.append(f"[INSTRUCCIÓN DE MODO: {mode_instr}]")

        if is_hint:
            hint_instr = _HINT_INSTRUCTIONS.get(self.hint_level, _HINT_INSTRUCTIONS[4])
            parts.append(f"[INSTRUCCIÓN DE PISTA: {hint_instr}]")

        if image_path:
            try:
                img_bytes = Path(image_path).read_bytes()
                mime = "image/png" if image_path.endswith(".png") else "image/jpeg"
                parts.append(
                    types.Part(inline_data=types.Blob(mime_type=mime, data=img_bytes))
                )
                if is_hint:
                    parts.append("El alumno ha enviado una imagen de su trabajo. Analiza dónde está el error o el punto de bloqueo.")
                else:
                    parts.append("Aquí tienes la imagen enviada por el alumno.")
            except Exception as e:
                parts.append(f"[No se pudo cargar la imagen: {e}]")

        parts.append(message if message != "__hint__" else "Dame una pista")
        return self._send(parts)

    def handle(self, message: str, uploaded_image_path: str | None = None) -> tuple[str, bool]:
        lower = message.lower().strip()

        if any(k in lower for k in _EXIT_KEYWORDS):
            return "", True

        if any(k in lower for k in _MEMORY_KEYWORDS):
            return summarize_memory(self.notebook_name), False

        is_hint = message.strip() == "__hint__" or bool(_HINT_RE.search(lower))
        if is_hint:
            self.hint_level = min(self.hint_level + 1, 4)

        image_path = uploaded_image_path
        self.last_screenshot_path = None

        return self.chat_text(message, image_path=image_path, is_hint=is_hint), False

    def handle_screen_capture(self, image_path: str) -> tuple[str, bool]:
        """User manually triggered a screen capture — analyse and provide feedback."""
        self.last_screenshot_path = image_path
        return self.chat_text(
            "El alumno acaba de capturar su pantalla para que la analices. "
            "Describe brevemente lo que ves y da feedback conciso.",
            image_path=image_path,
        ), False

    def _quick_analyze(self, parts: list) -> str:
        """One-shot Gemini call that does NOT modify conversation history."""
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part(text=str(p)) if isinstance(p, str) else p for p in parts],
            )],
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=0.2,
            ),
        )
        return response.text

    def handle_whiteboard(self, image_path: str) -> tuple[str, bool]:
        """Periodic whiteboard check — brief feedback only, does not pollute history."""
        parts: list = [
            f"[{_MODE_INSTRUCTIONS['pizarra']}]\n"
            "Observa la imagen de la pantalla/pizarra del alumno y da feedback MUY breve (máximo 2 frases).",
        ]
        try:
            img_bytes = Path(image_path).read_bytes()
            parts.append(types.Part(inline_data=types.Blob(mime_type="image/png", data=img_bytes)))
        except Exception as e:
            return f"No se pudo capturar la pantalla: {e}", False
        parts.append("¿El alumno va bien?")
        return self._quick_analyze(parts), False

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
