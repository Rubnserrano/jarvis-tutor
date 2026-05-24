# Sazed — Design System

## Estética: "Late Night Study"

Inspiración: una habitación de estudio a las 2am, luz de escritorio cálida, lluvia suave afuera, música lofi de fondo. Sobria, enfocada, sin distracciones. Suficientemente acogedora para pasar horas estudiando.

Referencias visuales: Notion dark, Raycast, Linear, Lofi Girl artwork.

---

## Paleta de colores

### Fondos
| Token | Hex | Uso |
|-------|-----|-----|
| `--bg` | `#0e0e14` | Fondo principal |
| `--surface` | `#16161f` | Cards, sidebar |
| `--surface2` | `#1d1d28` | Inputs, elementos elevados |
| `--border` | `#27273a` | Bordes sutiles |
| `--border-strong` | `#3d3d5c` | Bordes activos |

### Acento primario — Violeta suave (calm, intellectual)
| Token | Hex | Uso |
|-------|-----|-----|
| `--violet` | `#a78bfa` | Iconos, títulos, links activos |
| `--violet-dim` | `#7c5cbf` | Hover states |
| `--violet-bg` | `#1e1a2e` | Fondos tintados |

### Acento cálido — Ámbar (warmth, desk lamp)
| Token | Hex | Uso |
|-------|-----|-----|
| `--amber` | `#f59e0b` | Radio playing, highlights, HOY |
| `--amber-dim` | `#b37208` | Hover warm |
| `--amber-bg` | `#2a1f08` | Fondos ámbar |

### Semánticos
| Token | Hex | Uso |
|-------|-----|-----|
| `--green` | `#34d399` | Éxito, entendido |
| `--orange` | `#fb923c` | Advertencias, débil |
| `--red` | `#f87171` | Errores |
| `--blue` | `#60a5fa` | Info, links secundarios |

### Texto
| Token | Hex | Uso |
|-------|-----|-----|
| `--text` | `#ede9fe` | Texto principal (slight violet tint) |
| `--text-muted` | `#6b6b8d` | Labels, timestamps |
| `--text-dim` | `#9898b8` | Texto secundario |

---

## Tipografía

- **UI**: `'Inter', 'Segoe UI', system-ui, sans-serif`
- **Código/math**: `'JetBrains Mono', 'Fira Code', monospace`
- **Tamaño base**: 14px
- **Line height**: 1.65

### Escala
| Rol | Size | Weight |
|-----|------|--------|
| Header título | 1rem | 600 |
| Label caps | 0.68rem | 700 |
| Body | 0.88rem | 400 |
| Small | 0.75rem | 400 |
| Badge | 0.62rem | 700 |

---

## Componentes

### Chat bubbles
- **Sazed**: fondo `--surface2`, borde izq `2px solid --violet`, sin borde exterior
- **Usuario**: fondo `--violet-bg`, borde `1px solid --violet-dim`
- **Border radius**: 10px (bottom-left/right 2px según lado)

### Cards (Plan, Ejercicios)
- Fondo `--surface`, borde `1px solid --border`
- Hover: borde `--border-strong`
- **HOY/active**: borde `--amber`, fondo `--amber-bg`

### Tabs (sidebar)
- Inactive: color `--text-muted`, sin borde
- Active: color `--violet`, underline `2px solid --violet`

### Badges
- FUERTE: fondo `rgba(52,211,153,0.12)`, texto `--green`
- DÉBIL: fondo `rgba(251,146,60,0.12)`, texto `--orange`
- MEDIO: fondo `rgba(107,107,141,0.15)`, texto `--text-muted`

---

## Lofi Radio

Streams (SomaFM, listener-supported, HTTPS):
- **Groove Salad** — ambient electronic `https://ice1.somafm.com/groovesalad-256-mp3`
- **Drone Zone** — atmospheric ambient `https://ice1.somafm.com/dronezone-256-mp3`
- **Beat Blender** — deep/chill beats `https://ice1.somafm.com/beatblender-128-mp3`
- **Suburbs of Goa** — indian/chill `https://ice1.somafm.com/suburbsofgoa-128-mp3`

Widget location: header, zona central
Comportamiento:
- Play/pause toggle — ícono animado (pulso ámbar) cuando suena
- Ciclo de estaciones con ‹ ›
- Volumen slider (default 30%)
- Independiente del TTS — conviven

---

## Animaciones

- Duración: 150ms ease por defecto, 300ms para modales
- Typing indicator: tres puntos con fade escalonado
- Radio pulse: `scale(1) → scale(1.3)` con color ámbar, 1.2s infinite
- Tab hover: color transition 150ms

---

## Espaciado

- Grid base: 4px
- Padding componentes: 8px, 12px, 16px, 20px
- Gap entre elementos: 6px, 8px, 12px
- Border radius: 6px (small), 10px (cards), 14px (modal)
