---
name: projects
description: Project and task management — create projects, track tasks, monitor progress, and store project notes
tools:
  - create_project
  - list_projects
  - get_project
  - add_task
  - update_task
  - delete_task
  - project_progress
  - update_project_status
  - add_project_note
  - search_project_notes
---

# Projects Skill

Gestión de proyectos y tareas para el usuario. Te permite crear proyectos, agregar tareas, registrar progreso y almacenar notas por proyecto.

## Cuándo usar este skill

Usa este skill cuando el usuario mencione:
- Crear/empezar un proyecto, meta u objetivo
- Trackear tareas, pendientes, to-dos de un proyecto
- Ver el progreso o estado de un proyecto
- Marcar una tarea como hecha o en progreso
- Tomar notas sobre un proyecto específico

Triggers: "proyecto", "project", "tarea", "task", "progreso", "progress", "pendiente", "hito", "meta", "objetivo", "plan", "deadline", "avance"

## Guía de uso de tools

### create_project
Úsala cuando el usuario quiere crear un proyecto nuevo. Pide un nombre claro y conciso. Sugiere una descripción si el usuario no la da.

### list_projects
Muestra proyectos activos por defecto. Usa status="all" para ver todos los proyectos incluyendo archivados.

### get_project
Muestra detalles completos: descripción, barra de progreso, todas las tareas con status/prioridad, y actividad reciente. Úsala cuando el usuario pregunta por un proyecto específico.

### add_task
Agrega una tarea a un proyecto. Prioridad por defecto: medium. Usa high para cosas urgentes. El task_id se asigna automáticamente.

### update_task
Actualiza el status de una tarea. Flujo normal: pending → in_progress → done. Cuando se completa la última tarea, sugerirás marcar el proyecto como completado.

### delete_task
Elimina una tarea permanentemente. Pide confirmación al usuario antes de borrar.

### project_progress
Muestra barra visual de progreso + tareas de alta prioridad + actividad reciente. Ideal para reportes de estado.

### update_project_status
Cambia estado del proyecto a: active (en curso), archived (pausado/cancelado), completed (terminado exitosamente). Al completar/archivar se registra el resumen final automáticamente.

### add_project_note
Guarda notas contextuales en un proyecto. Útil para decisiones, links, referencias, aprendizajes. Las notas son búsquedas semánticas.

### search_project_notes
Busca notas dentro de un proyecto. Usa búsqueda semántica si está disponible.

## Templates implícitos

Si el usuario crea un proyecto sin especificar tareas, ofrece crear tareas típicas según el tipo:

**Proyecto de software:**
- Planning / Requirements
- Design / Architecture
- Implementation
- Testing
- Deployment

**Blog/Contenido:**
- Research
- Outline
- Draft
- Editing
- Publish

**Evento:**
- Venue / Logistics
- Invitations
- Agenda
- Execution
- Follow-up

**Meta de aprendizaje:**
- Define resources
- Study plan
- Practice exercises
- Assessment

## Cuándo sugerir archivar o completar

- Si todas las tareas están done → sugiere completar el proyecto
- Si un proyecto no tiene actividad reciente y el usuario dice que lo canceló → sugiere archivarlo
- Usa update_project_status para formalizar el cambio

## Comportamiento esperado

- Al crear un proyecto, confirma con: "Proyecto '[nombre]' creado."
- Al agregar tareas, lista las tareas pendientes del proyecto tras confirmar
- Siempre muestra el task_id al crear tareas (el usuario lo necesita para actualizar status)
- Al completar una tarea, muestra el progreso actualizado
- Responde en el idioma del usuario (español o inglés)
