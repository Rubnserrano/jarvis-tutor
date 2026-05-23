from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from jarvis.memory import record_session, summarize_memory
from jarvis.query import search_notes
from jarvis.screen import capture_screenshot

load_dotenv()

CONTEXT_DIR = Path(__file__).parent.parent / "context"
_SCREENSHOT_KEYWORDS = {"screenshot", "mira mi pantalla", "captura", "ve mi pantalla"}
_HINT_KEYWORDS = {"pista", "hint", "no sé", "no entiendo", "estoy atascado"}
_MEMORY_KEYWORDS = {"memoria", "progreso", "qué hemos visto"}
_EXIT_KEYWORDS = {"salir", "exit", "quit", "adiós", "bye"}


def _load_context(context_file: str, memory_summary: str) -> str:
    path = CONTEXT_DIR / context_file
    if path.exists():
        template = path.read_text(encoding="utf-8")
        return template.replace("{memory_summary}", memory_summary)
    return f"Eres un tutor universitario. Progreso del alumno:\n{memory_summary}"


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
        self.topics_this_session: list[str] = []
        self.history: list[types.Content] = []

        memory_summary = summarize_memory(notebook_name)
        self.system_prompt = _load_context(context_file, memory_summary)
        self.last_context = ""
        self.last_screenshot_path: str | None = None

    def start(self) -> str:
        return (
            f"Hola, soy tu tutor de {self.notebook_name}. "
            "Dime qué ejercicio o tema quieres practicar hoy. "
            "Puedes escribir 'screenshot' para que vea tu pantalla, "
            "'pista' si estás atascado, o 'salir' para terminar."
        )

    def _is_command(self, message: str) -> str | None:
        lower = message.lower().strip()
        if any(k in lower for k in _SCREENSHOT_KEYWORDS):
            return "screenshot"
        if any(k in lower for k in _HINT_KEYWORDS):
            return "hint"
        if any(k in lower for k in _MEMORY_KEYWORDS):
            return "memory"
        if any(k in lower for k in _EXIT_KEYWORDS):
            return "exit"
        return None

    def _fetch_context(self, message: str) -> str:
        try:
            result = asyncio.run(search_notes(message, notebook_name=self.notebook_name))
            self.last_context = result
            return result
        except Exception as e:
            self.last_context = f"⚠️ NotebookLM no disponible: {e}\nEjecuta 'notebooklm auth' desde PowerShell para conectar tus apuntes."
            return ""

    def _send(self, parts: list) -> str:
        self.history.append(types.Content(role="user", parts=[types.Part(text=str(p)) if isinstance(p, str) else p for p in parts]))

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
                parts.append(types.Part(inline_data=types.Blob(mime_type="image/png", data=img_bytes)))
                parts.append("El alumno ha compartido un screenshot de su pantalla.")
            except Exception as e:
                parts.append(f"[No se pudo cargar el screenshot: {e}]")

        parts.append(message)
        return self._send(parts)

    def handle(self, message: str) -> tuple[str, bool]:
        cmd = self._is_command(message)

        if cmd == "exit":
            return "", True

        if cmd == "memory":
            return summarize_memory(self.notebook_name), False

        # Capture screen on every turn for continuous visual context
        screenshot_path = None
        try:
            screenshot_path = capture_screenshot()
            self.last_screenshot_path = screenshot_path
        except RuntimeError:
            self.last_screenshot_path = None

        if cmd == "hint":
            response = self.chat_text(
                "El alumno pide una pista. Da una pequeña pista socrática sin revelar la respuesta.",
                image_path=screenshot_path,
            )
            return response, False

        return self.chat_text(message, image_path=screenshot_path), False

    def save(self) -> None:
        record_session(self.notebook_name, self.topics_this_session)
