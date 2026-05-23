# Jarvis — Tutor de Estudio con IA

Tutor personal de estudio con voz, visión de pantalla y acceso a tus apuntes. Powered by Google Gemini + NotebookLM.

---

## Instalación (primera vez)

### Requisitos
- Windows 10/11
- Python 3.10+ → [python.org](https://python.org/downloads) *(marca "Add to PATH")*
- Chrome para la interfaz web

### Setup automático

Descarga el proyecto y haz doble clic en **`setup.bat`**.

El script te guiará para:
1. Instalar las dependencias
2. Pedir tu **Gemini API key** gratuita ([aistudio.google.com/apikey](https://aistudio.google.com/apikey))
3. Conectar tu cuenta Google con NotebookLM

---

## Uso diario

```powershell
# En PowerShell, dentro de la carpeta del proyecto:
.venv-win\Scripts\activate
python app.py
```

Abre **Chrome** en `http://localhost:8000`.

---

## Interfaz web

| Elemento | Función |
|----------|---------|
| 🎤 / **F2** | Iniciar/parar grabación de voz |
| ⏹ | Interrumpir a Jarvis mientras habla |
| 🔊 Voz | Activar/desactivar texto a voz |
| ⚙️ Ajustes | Cambiar API key, notebook activo |
| Panel derecho | Fragmento de tus apuntes usado en la respuesta |

---

## Añadir apuntes

Tus apuntes se guardan en **NotebookLM**. Puedes subirlos desde la CLI o directamente en [notebooklm.google.com](https://notebooklm.google.com).

```powershell
# Añadir texto directo
python cli.py add "Las cadenas de Markov tienen la propiedad de Markov..."

# Añadir desde fichero
python cli.py add --file mis_apuntes.md --tag tema1

# Ver todo lo guardado
python cli.py list
```

---

## Usar Jarvis para varios proyectos o asignaturas

Puedes tener notebooks separados en NotebookLM — uno por asignatura o proyecto. Cada uno tiene sus propios apuntes y su historial de sesiones independiente.

```powershell
# Ver qué notebook está activo ahora
python cli.py status

# Cambiar a otro notebook (se crea en NotebookLM automáticamente si no existe)
python cli.py use "Álgebra Lineal"
python cli.py use "Proyecto TFG"

# Añadir apuntes al notebook activo
python cli.py add --file apuntes_algebra.md

# Estudiar con ese notebook
python app.py   # y cambia el notebook en ⚙️ Ajustes, o usa:
python cli.py study --text
```

También puedes cambiar el notebook activo desde la interfaz web sin salir: **⚙️ Ajustes → Nombre del notebook**.

Cada notebook guarda su progreso por separado en `~/.jarvis/memory/`.

---

## Crear un tutor para otra asignatura

Los tutores están en la carpeta `context/`. Crea un fichero `.md` con:

```markdown
# Tutor de [Tu asignatura]

## Tu rol
Eres un tutor especializado en [asignatura]...

## Contexto del progreso
{memory_summary}
```

Y pásaselo al CLI: `python cli.py study --context mi_tutor.md`

---

## Problemas frecuentes

**"NotebookLM no disponible"** → Ejecuta `notebooklm auth login` en PowerShell  
**Sin audio** → Asegúrate de usar Chrome (no Firefox/Edge)  
**API key inválida** → Pulsa ⚙️ y pega una key nueva de [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
