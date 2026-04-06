# Guia: Crear aplicaciones con LocalForge

> Crea landing pages, APIs, apps React y mas — todo desde WhatsApp.

---

## Prerequisitos

Antes de crear tu primera app, asegurate de tener configurado:

### 1. Variables de entorno

En tu `.env`, habilita estas variables:

```bash
# Obligatorio: habilita escritura de archivos por el agente
AGENT_WRITE_ENABLED=true

# Obligatorio: directorio donde se crearan los proyectos
PROJECTS_ROOT=/home/appuser/projects   # o cualquier ruta writable

# Opcional pero recomendado: habilita comandos shell (npm, python, etc)
AGENT_SHELL_ALLOWLIST=pytest,ruff,mypy,make,npm,git,cat,head,tail,wc,ls,find,grep,echo,python,node

# Opcional: para publicar en GitHub automaticamente
GITHUB_TOKEN=ghp_xxxxx
```

### 2. Reiniciar LocalForge

Despues de cambiar el `.env`:

```bash
make run
# o si estas en Docker:
docker compose restart
```

### 3. Verificar configuracion

Desde WhatsApp, envia:

```
Cual es tu configuracion runtime?
```

Verifica que aparezcan:
- `agent_write_enabled: True`
- `projects_root: /home/appuser/projects` (o tu ruta)

---

## Tu primera landing page

### Paso 1: Iniciar el agente

Envia por WhatsApp:

```
/agent Creame una landing page para una cafeteria llamada "Cafe Aroma"
```

El agente va a:
1. Crear un plan con tareas
2. Scaffoldear el proyecto desde el template `html-static`
3. Personalizar el HTML/CSS/JS con el contenido de tu cafeteria
4. Mostrarte el progreso paso a paso

### Paso 2: Ver el progreso

El agente te va informando mientras trabaja:

> *Sesion agentica iniciada*
> Objetivo: Creame una landing page para una cafeteria...
>
> *Tarea 1/4*: Scaffoldeando proyecto "cafe-aroma" desde template html-static...
> *Tarea 2/4*: Personalizando contenido — menu, horarios, ubicacion...
> *Tarea 3/4*: Mejorando estilos CSS...
> *Tarea 4/4*: Proyecto listo.

### Paso 3: Previsualizar la landing

Una vez creada, pedi:

```
Mostra un preview de la landing
```

El agente ejecuta `deliver_project("preview")` y te responde:

> Preview server started: http://localhost:8342

Abri esa URL en tu navegador para ver la landing.

> **Nota**: El preview server solo funciona si tenes acceso al servidor donde corre LocalForge. Si estas en un server remoto, podes usar un tunnel (ngrok, cloudflared) o descargar el ZIP.

### Paso 4: Descargar o publicar

**Opcion A — Descargar como ZIP:**

```
Descargame el proyecto como ZIP
```

**Opcion B — Publicar en GitHub:**

```
Publica el proyecto en GitHub
```

Requiere `GITHUB_TOKEN` configurado. Crea un repo privado y pushea.

---

## Templates disponibles

| Template | Comando ejemplo | Stack |
|---|---|---|
| `html-static` | "Creame una landing page para..." | HTML5 + CSS + JS vanilla |
| `python-fastapi` | "Creame una API REST para..." | FastAPI + Pydantic + SQLite |
| `react-vite` | "Creame una app React para..." | React + TypeScript + Vite |
| `nextjs` | "Creame una app Next.js para..." | Next.js 14 App Router + TypeScript |

Para ver los templates disponibles en cualquier momento:

```
Que templates de proyecto tenes?
```

---

## Ejemplos por tipo de proyecto

### Landing page para negocio

```
/agent Crea una landing page profesional para un estudio juridico llamado "Lopez & Asociados". 
Debe tener: hero con titulo, seccion de servicios (civil, penal, laboral), 
equipo con fotos placeholder, formulario de contacto, y footer con direccion.
Colores: azul oscuro y dorado. Tipografia elegante.
```

### API REST

```
/agent Crea una API REST con FastAPI para un sistema de inventario. 
Necesito endpoints CRUD para productos (nombre, precio, stock, categoria), 
validaciones con Pydantic, y un endpoint de busqueda por categoria.
Incluir tests.
```

### App React

```
/agent Crea una app React con TypeScript para un dashboard de tareas. 
Componentes: TaskList, TaskCard, AddTaskForm. 
Estado con useState. Estilos con CSS modules.
```

### App Next.js

```
/agent Crea un blog con Next.js 14 App Router. 
Paginas: home (lista de posts), post individual (slug dinamico), about. 
Datos hardcodeados en un archivo data.ts. Estilos con Tailwind-like CSS.
```

---

## Flujo completo: de idea a deploy

```
1. /agent Creame una landing para mi barberia "Cortes Pro"
   → El agente planifica, scaffoldea y personaliza

2. Mostra un preview del proyecto
   → Abris http://localhost:XXXX y ves la landing

3. Cambia el color principal a rojo oscuro y agrega un boton de WhatsApp
   → El agente usa apply_patch para editar archivos

4. Mostra el preview de nuevo
   → Verificas los cambios

5. Publica el proyecto en GitHub como "cortes-pro-landing"
   → Repo creado: https://github.com/tuuser/cortes-pro-landing

6. /cancel
   → Termina la sesion agentica
```

---

## Comandos utiles durante el desarrollo

| Comando | Que hace |
|---|---|
| `/agent <objetivo>` | Inicia sesion agentica |
| `/code <objetivo>` | Sesion de codigo (mas iteraciones, tools optimizados) |
| `/agent` (sin args) | Ver estado de la sesion activa |
| `/cancel` | Cancelar sesion agentica |

### Interactuar con el proyecto existente

Una vez creado, podes pedirle al agente cosas como:

```
Mostra la estructura del proyecto
```
```
Lee el archivo index.html
```
```
Agrega una seccion de testimonios
```
```
Cambia la fuente a Inter de Google Fonts
```
```
Corre los tests
```

---

## Gestion de workspaces

Si creas multiples proyectos, podes manejarlos:

```
Lista mis workspaces
```

```
Cambia al workspace cafe-aroma
```

```
Cual es el workspace activo?
```

Cada workspace es un directorio independiente con su propio git.

---

## Troubleshooting

### "Error: PROJECTS_ROOT is not configured"

Agrega `PROJECTS_ROOT=/ruta/a/directorio` en tu `.env` y reinicia.

### "Error: Write operations are disabled"

Agrega `AGENT_WRITE_ENABLED=true` en tu `.env` y reinicia.

### "Error: 'gh' CLI not found"

Para publicar en GitHub necesitas el CLI de GitHub:
```bash
# macOS
brew install gh

# Linux
# Ver: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

### El preview no carga

- Si estas en un server remoto, el puerto solo es accesible localmente
- Opciones:
  - Usar `ssh -L 8342:localhost:8342 tuserver` para tunnel SSH
  - Descargar como ZIP y abrir localmente
  - Usar ngrok: `ngrok http 8342`

### El agente se traba o no termina

```
/cancel
```

Y volve a intentar con un objetivo mas especifico.

---

## Tips para mejores resultados

1. **Se especifico**: "Landing page para cafeteria con menu, horarios y mapa" funciona mejor que "Haceme una pagina"

2. **Menciona el stack**: Si queres React en vez de HTML vanilla, decilo explicitamente

3. **Itera**: Crea la base y despues pedi cambios puntuales — es mas eficiente que pedir todo de una

4. **Usa `/code`** para tareas de programacion pura: tiene mas iteraciones (20 vs 15) y tools optimizados para codigo

5. **Revisa el plan**: El agente te muestra su plan antes de ejecutar. Si no te convence, podes cancelar y replantear

---

## Arquitectura interna (para curiosos)

```
WhatsApp → /agent "crea landing..."
              │
              ▼
         Planner (LLM)
              │ Genera plan con TaskSteps
              ▼
         Agent Loop (rounds × tool calls)
              │
              ├─ scaffold_project("mi-cafe", "html-static")
              │     → WorkspaceEngine.create_workspace()
              │     → templates.scaffold() escribe archivos
              │
              ├─ write_source_file("index.html", "...")
              │     → Escribe contenido personalizado
              │     → check_code_security() (seguridad)
              │
              ├─ apply_patch("styles.css", search, replace)
              │     → Edicion quirurgica de archivos
              │
              └─ deliver_project("preview")
                    → serve_preview() HTTP server temporal
                    → Retorna URL al usuario
```

Archivos fuente:
- `app/workspace/engine.py` — Lifecycle de workspaces
- `app/workspace/templates.py` — 4 templates in-memory
- `app/workspace/delivery.py` — GitHub push, ZIP, preview
- `app/skills/tools/workspace_tools.py` — Tools del agente
- `app/agent/loop.py` — Loop agentico con paralelismo
