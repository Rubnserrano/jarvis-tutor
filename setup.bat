@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════╗
echo ║     Jarvis Tutor — Setup inicial     ║
echo ╚══════════════════════════════════════╝
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python no encontrado.
    echo  Instala Python 3.10+ desde https://python.org
    echo  Marca la opcion "Add to PATH" durante la instalacion.
    pause & exit /b 1
)

REM Create venv if needed
if not exist .venv-win (
    echo  [1/5] Creando entorno virtual...
    python -m venv .venv-win
) else (
    echo  [1/5] Entorno virtual ya existe, continuando...
)

REM Activate
call .venv-win\Scripts\activate.bat

REM Install deps
echo  [2/5] Instalando dependencias ^(puede tardar un minuto^)...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo  ERROR al instalar dependencias.
    pause & exit /b 1
)

REM Install Playwright browser
echo  [3/5] Instalando navegador para NotebookLM...
playwright install chromium
if errorlevel 1 (
    echo  ERROR al instalar Chromium.
    pause & exit /b 1
)

REM Gemini API key
echo.
echo  [4/5] Configuracion de Gemini API
echo  Necesitas una API key gratuita de Google AI Studio.
echo  Obtenla en: https://aistudio.google.com/apikey
echo  ^(crea una nueva key en un proyecto nuevo^)
echo.
set /p GEMINI_KEY=" Pega tu Gemini API key aqui: "
if "%GEMINI_KEY%"=="" (
    echo  ERROR: No introdujiste ninguna key.
    pause & exit /b 1
)
echo GEMINI_API_KEY=%GEMINI_KEY%> .env
echo  API key guardada.

REM NotebookLM auth
echo.
echo  [5/5] Conexion con NotebookLM
echo  Se abrira el navegador para que inicies sesion con tu cuenta Google.
echo  NotebookLM es donde se guardaran tus apuntes de estudio.
echo.
pause
notebooklm auth login
if errorlevel 1 (
    echo  ERROR en la autenticacion. Puedes reintentarlo luego con:
    echo    notebooklm auth login
)

echo.
echo ╔══════════════════════════════════════╗
echo ║          Setup completado!           ║
echo ║                                      ║
echo ║  Para iniciar Jarvis:                ║
echo ║    .venv-win\Scripts\activate        ║
echo ║    python app.py                     ║
echo ║                                      ║
echo ║  Abre Chrome en http://localhost:8000║
echo ╚══════════════════════════════════════╝
echo.
pause
