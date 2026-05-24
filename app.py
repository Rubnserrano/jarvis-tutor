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

from datetime import date as _date

from jarvis.exercises import detect_blocks, generate_adaptive_exercise, get_exercises
from jarvis.planner import generate_plan, get_plan, today_plan_summary
from jarvis.query import get_source_context
from jarvis.screen import capture_screenshot
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


# ── Exercises + Plan API ─────────────────────────────────────────────────────

@app.get("/api/exercises")
async def api_exercises():
    notebook = get_active_notebook()
    exercises = get_exercises(notebook)
    return JSONResponse({"exercises": exercises})


@app.get("/api/plan")
async def api_plan():
    notebook = get_active_notebook()
    plan = get_plan(notebook)
    summary = today_plan_summary(notebook)
    return JSONResponse({"plan": plan, "today_summary": summary})


@app.post("/api/plan")
async def api_create_plan(data: dict):
    from jarvis.memory import get_memory
    notebook = get_active_notebook()
    try:
        exam_date = _date.fromisoformat(data["exam_date"])
    except (KeyError, ValueError):
        return JSONResponse({"error": "exam_date inválida (usa YYYY-MM-DD)"}, status_code=400)
    topics = [t.strip() for t in data.get("topics", "").split(",") if t.strip()]
    if not topics:
        return JSONResponse({"error": "topics requerido"}, status_code=400)
    strong = [t.strip() for t in data.get("strong_topics", "").split(",") if t.strip()]
    weak   = [t.strip() for t in data.get("weak_topics", "").split(",") if t.strip()]
    mem = get_memory(notebook)
    weak_areas = [(a["area"] if isinstance(a, dict) else a) for a in mem.get("weak_areas", [])]
    plan = generate_plan(
        notebook, topics, exam_date,
        weak_areas=weak_areas or None,
        strong_topics=strong or None,
        weak_topics=weak or None,
    )
    return JSONResponse({"plan": plan, "today_summary": today_plan_summary(notebook)})


# ── Adaptive exercises ────────────────────────────────────────────────────────

@app.get("/api/blocks")
async def api_blocks():
    notebook = get_active_notebook()
    return JSONResponse({"blocks": detect_blocks(notebook)})


@app.post("/api/generate-exercise")
async def api_generate_exercise(data: dict):
    notebook = get_active_notebook()
    topic = data.get("topic", "").strip()
    level = data.get("level", "intermedio").strip()
    if not topic:
        return JSONResponse({"error": "topic required"}, status_code=400)
    try:
        exercise = await asyncio.get_event_loop().run_in_executor(
            _executor, generate_adaptive_exercise, notebook, topic, level
        )
        return JSONResponse(exercise)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Source image (cited text rendered as PNG) ─────────────────────────────────

async def _render_excerpt_image(title: str, text: str) -> bytes:
    import html as html_lib
    from playwright.async_api import async_playwright

    escaped_title = html_lib.escape(title)
    escaped_text  = html_lib.escape(text)
    page_html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0e0e14;font-family:-apple-system,'Segoe UI',sans-serif;padding:16px;}}
.card{{background:#16161f;border:1px solid #27273a;border-left:3px solid #7c5cbf;border-radius:8px;padding:18px 20px;}}
.label{{font-size:10px;font-weight:700;color:#6b6b8d;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px}}
.title{{font-size:13px;font-weight:600;color:#a78bfa;margin-bottom:14px}}
.text{{font-size:13px;line-height:1.8;color:#c8c4dc;white-space:pre-wrap;word-break:break-word}}
</style></head><body>
<div class="card">
  <div class="label">Extracto · fuente citada</div>
  <div class="title">{escaped_title}</div>
  <div class="text">{escaped_text}</div>
</div></body></html>"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 660, "height": 400})
        await page.set_content(page_html)
        img = await page.screenshot(full_page=True)
        await browser.close()
    return img


@app.post("/api/source-image")
async def api_source_image(data: dict):
    cited_text = data.get("cited_text", "").strip()
    title      = data.get("title", "Fuente").strip()
    if not cited_text:
        return JSONResponse({"error": "cited_text required"}, status_code=400)
    try:
        img_bytes = await _render_excerpt_image(title, cited_text)
        return JSONResponse({"image": base64.b64encode(img_bytes).decode()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Source context ────────────────────────────────────────────────────────────

@app.post("/api/source-context")
async def api_source_context(data: dict):
    source_id  = data.get("source_id", "").strip()
    cited_text = data.get("cited_text", "").strip()
    if not source_id:
        return JSONResponse({"error": "source_id required"}, status_code=400)
    notebook = get_active_notebook()
    try:
        ctx = await get_source_context(notebook, source_id, cited_text, context_chars=600)
        return JSONResponse(ctx)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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

    whiteboard_task: asyncio.Task | None = None

    def _stop_whiteboard() -> None:
        nonlocal whiteboard_task
        if whiteboard_task and not whiteboard_task.done():
            whiteboard_task.cancel()
        whiteboard_task = None

    async def _start_whiteboard(interval: int = 30) -> None:
        nonlocal whiteboard_task
        _stop_whiteboard()

        async def _worker() -> None:
            try:
                while True:
                    await asyncio.sleep(interval)
                    try:
                        path = await loop.run_in_executor(_executor, capture_screenshot)
                        resp, _ = await loop.run_in_executor(_executor, session.handle_whiteboard, path)
                        ss   = _screenshot_b64(path)
                        aud  = await _tts_b64(resp)
                        await websocket.send_json({
                            "type": "whiteboard_feedback",
                            "text": resp,
                            "screenshot": ss,
                            "audio": aud,
                        })
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        whiteboard_task = asyncio.create_task(_worker())

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "reload":
                await websocket.send_json({"type": "reload_ack"})
                return

            if data.get("type") == "set_mode":
                mode = data.get("mode", "tutor")
                session.set_mode(mode)
                if mode == "pizarra":
                    interval = int(data.get("interval", 30))
                    await _start_whiteboard(interval)
                else:
                    _stop_whiteboard()
                await websocket.send_json({"type": "mode_ack", "mode": session.mode})
                continue

            if data.get("type") == "capture_screen":
                try:
                    path = await loop.run_in_executor(_executor, capture_screenshot)
                    resp, _ = await loop.run_in_executor(_executor, session.handle_screen_capture, path)
                    ss  = _screenshot_b64(path)
                    aud = await _tts_b64(resp)
                    await websocket.send_json({
                        "type": "screen_capture_response",
                        "text": resp,
                        "screenshot": ss,
                        "audio": aud,
                        "context": session.last_context,
                        "references": session.last_references,
                        "hint_level": session.hint_level,
                        "mode": session.mode,
                    })
                except Exception as e:
                    await websocket.send_json({"type": "error", "text": f"No se pudo capturar: {e}"})
                continue

            msg_type = data.get("type")
            if msg_type == "hint":
                user_text = "__hint__"
            elif msg_type == "message":
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue
            else:
                continue

            # Handle user-uploaded image (base64)
            uploaded_path: str | None = None
            if data.get("image"):
                try:
                    img_bytes = base64.b64decode(data["image"])
                    uploaded_path = tempfile.mktemp(suffix=".png")
                    Path(uploaded_path).write_bytes(img_bytes)
                except Exception:
                    uploaded_path = None

            response, should_exit = await loop.run_in_executor(
                _executor, session.handle, user_text, uploaded_path
            )

            if uploaded_path:
                try:
                    os.unlink(uploaded_path)
                except Exception:
                    pass

            audio = await _tts_b64(response)

            await websocket.send_json({
                "type": "response",
                "text": response,
                "context": session.last_context,
                "references": session.last_references,
                "audio": audio,
                "exit": should_exit,
                "hint_level": session.hint_level,
                "mode": session.mode,
            })

            if should_exit:
                session.save()
                break

    except WebSocketDisconnect:
        session.save()
    finally:
        _stop_whiteboard()


if __name__ == "__main__":
    webbrowser.open("http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
