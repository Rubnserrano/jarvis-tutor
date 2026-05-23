import json

from jarvis.config import DEFAULT_NOTEBOOK, SETTINGS_PATH


def get_active_notebook() -> str:
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text())
        return data.get("active_notebook", DEFAULT_NOTEBOOK)
    return DEFAULT_NOTEBOOK


def set_active_notebook(name: str) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps({"active_notebook": name}, indent=2))
