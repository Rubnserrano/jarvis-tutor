import tempfile
from pathlib import Path


def capture_screenshot() -> str:
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            img = sct.grab(monitor)
            path = Path(tempfile.mktemp(suffix=".png"))
            mss.tools.to_png(img.rgb, img.size, output=str(path))
            return str(path)
    except Exception as e:
        raise RuntimeError(
            f"No se pudo capturar la pantalla: {e}\n"
            "Asegúrate de que DISPLAY está configurado en WSL (WSLg requerido)."
        )
