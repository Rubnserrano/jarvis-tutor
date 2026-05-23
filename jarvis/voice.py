from __future__ import annotations
import asyncio
import os
import re
import sys
import tempfile
import threading

_VOICE = "es-ES-AlvaroNeural"
_RATE = "+40%"  # velocidad del TTS


def _clean_latex(text: str) -> str:
    steps = [
        (r'\\frac\{([^}]*)\}\{([^}]*)\}', r'\1 entre \2'),
        (r'\\sqrt\{([^}]*)\}', r'raíz de \1'),
        (r'\^\{2\}|\^2\b', ' al cuadrado'),
        (r'\^\{3\}|\^3\b', ' al cubo'),
        (r'\^\{([^}]*)\}', r' elevado a \1'),
        (r'_\{([^}]*)\}', r' \1'),
        (r'\\pi\b', 'pi'),
        (r'\\lambda\b', 'lambda'),
        (r'\\alpha\b', 'alfa'),
        (r'\\beta\b', 'beta'),
        (r'\\gamma\b', 'gamma'),
        (r'\\sigma\b', 'sigma'),
        (r'\\mu\b', 'mu'),
        (r'\\theta\b', 'theta'),
        (r'\\infty\b', 'infinito'),
        (r'\\sum\b', 'sumatorio'),
        (r'\\int\b', 'integral'),
        (r'\\leq\b', 'menor o igual que'),
        (r'\\geq\b', 'mayor o igual que'),
        (r'\\neq\b', 'distinto de'),
        (r'\\in\b', 'pertenece a'),
        (r'\\rightarrow\b|\\to\b', 'tiende a'),
        (r'\\mathbb\{R\}', 'los reales'),
        (r'\\mathbb\{P\}', 'probabilidad'),
        (r'\\mathbb\{N\}', 'los naturales'),
        (r'\$\$([^$]+)\$\$', r'\1'),
        (r'\$([^$]+)\$', r'\1'),
        (r'\\[a-zA-Z]+', ''),
        (r'[{}_\\]', ' '),
        (r'\s+', ' '),
    ]
    for pattern, repl in steps:
        text = re.sub(pattern, repl, text)
    return text.strip()


def listen(timeout: int = 8) -> str | None:
    try:
        import speech_recognition as sr

        r = sr.Recognizer()
        devnull = open(os.devnull, "w")
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:
            mic = sr.Microphone()
        finally:
            sys.stderr = old_stderr
            devnull.close()

        with mic as source:
            print("Escuchando...", flush=True)
            r.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = r.listen(source, timeout=timeout, phrase_time_limit=30)
            except sr.WaitTimeoutError:
                return None

        try:
            return r.recognize_google(audio, language="es-ES")
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"Error STT: {e}")
            return None
    except Exception as e:
        print(f"Error de micrófono: {e}")
        return None


def speak(text: str) -> bool:
    """Speak text aloud. Returns True if the user interrupted mid-speech."""
    text = _clean_latex(text)
    interrupted = threading.Event()
    done = threading.Event()

    async def _generate_audio(t: str) -> str:
        import edge_tts
        communicate = edge_tts.Communicate(t, _VOICE, rate=_RATE)
        tmp = tempfile.mktemp(suffix=".mp3")
        await communicate.save(tmp)
        return tmp

    try:
        tmp_file = asyncio.run(_generate_audio(text))
    except Exception:
        return False

    def _play():
        try:
            os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(tmp_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not interrupted.is_set():
                pygame.time.wait(100)
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        finally:
            done.set()
            try:
                os.unlink(tmp_file)
            except Exception:
                pass

    def _watch():
        try:
            import math
            import struct
            import pyaudio

            CHUNK = 512
            RATE = 16000

            devnull = open(os.devnull, "w")
            old_stderr = sys.stderr
            sys.stderr = devnull
            try:
                p = pyaudio.PyAudio()
                stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                                input=True, frames_per_buffer=CHUNK)
            finally:
                sys.stderr = old_stderr
                devnull.close()

            # Calibrate ambient noise level
            ambient = []
            for _ in range(int(RATE / CHUNK * 0.4)):
                data = stream.read(CHUNK, exception_on_overflow=False)
                samples = struct.unpack(f"{CHUNK}h", data)
                ambient.append(math.sqrt(sum(s * s for s in samples) / CHUNK))
            threshold = max(sum(ambient) / len(ambient) * 3, 150)

            while not done.is_set():
                data = stream.read(CHUNK, exception_on_overflow=False)
                samples = struct.unpack(f"{CHUNK}h", data)
                rms = math.sqrt(sum(s * s for s in samples) / CHUNK)
                if rms > threshold:
                    interrupted.set()
                    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
                    import pygame
                    pygame.mixer.music.stop()
                    done.set()
                    break

            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception:
            pass

    play_thread = threading.Thread(target=_play, daemon=True)
    watch_thread = threading.Thread(target=_watch, daemon=True)

    play_thread.start()
    watch_thread.start()
    play_thread.join()
    watch_thread.join(timeout=2)

    return interrupted.is_set()
