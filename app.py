import asyncio
import base64
import os
import tempfile
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import uvicorn
from dotenv import load_dotenv, set_key
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from jarvis.settings import get_active_notebook, set_active_notebook
from jarvis.tutor import TutorSession
from jarvis.voice import _VOICE, _RATE, _clean_latex

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

_executor = ThreadPoolExecutor()
_ENV_PATH = Path(__file__).parent / ".env"
_CONTEXT_DIR = Path(__file__).parent / "context"


# ── Config API ────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    load_dotenv(override=True)
    context_files = [f.name for f in sorted(_CONTEXT_DIR.glob("*.md"))]
    return JSONResponse({
        "has_api_key": bool(os.getenv("GEMINI_API_KEY")),
        "active_notebook": get_active_notebook(),
        "context_files": context_files,
    })


@app.post("/api/config")
async def save_config(data: dict):
    if api_key := data.get("api_key", "").strip():
        _ENV_PATH.touch()
        set_key(str(_ENV_PATH), "GEMINI_API_KEY", api_key)
        load_dotenv(override=True)
    if notebook := data.get("notebook", "").strip():
        set_active_notebook(notebook)
    return JSONResponse({"ok": True})


# ── Static / index ────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return HTMLResponse((_CONTEXT_DIR.parent / "static" / "index.html").read_text(encoding="utf-8"))


# ── TTS helper ────────────────────────────────────────────────────────────────

async def _tts_b64(text: str) -> str | None:
    try:
        import edge_tts
        communicate = edge_tts.Communicate(_clean_latex(text), _VOICE, rate=_RATE)
        tmp = tempfile.mktemp(suffix=".mp3")
        await communicate.save(tmp)
        data = Path(tmp).read_bytes()
        os.unlink(tmp)
        return base64.b64encode(data).decode()
    except Exception:
        return None


def _screenshot_b64(path: str | None) -> str | None:
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    except Exception:
        return None


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    load_dotenv(override=True)
    if not os.getenv("GEMINI_API_KEY"):
        await websocket.send_json({
            "type": "setup_required",
            "text": "Falta la API key de Gemini. Pulsa ⚙️ en la esquina superior derecha para configurarla.",
        })
        return

    loop = asyncio.get_event_loop()

    try:
        notebook = get_active_notebook()
        session = TutorSession(notebook_name=notebook)
    except RuntimeError as e:
        await websocket.send_json({"type": "error", "text": str(e)})
        return

    welcome = session.start()
    audio = await _tts_b64(welcome)
    await websocket.send_json({"type": "welcome", "text": welcome, "audio": audio})

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "reload":
                # Client requested session reload after config change
                await websocket.send_json({"type": "reload_ack"})
                return

            if data.get("type") != "message":
                continue

            user_text = data.get("text", "").strip()
            if not user_text:
                continue

            response, should_exit = await loop.run_in_executor(
                _executor, session.handle, user_text
            )

            screenshot = _screenshot_b64(session.last_screenshot_path)
            audio = await _tts_b64(response)

            await websocket.send_json({
                "type": "response",
                "text": response,
                "context": session.last_context,
                "screenshot": screenshot,
                "audio": audio,
                "exit": should_exit,
            })

            if should_exit:
                session.save()
                break

    except WebSocketDisconnect:
        session.save()


if __name__ == "__main__":
    webbrowser.open("http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
