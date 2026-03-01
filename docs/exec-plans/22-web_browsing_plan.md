# Plan: Leer URLs y Web Browsing (V2 - MCP Approach)

## Objetivo
Permitir que el agente WasAP visite y extraiga el contenido de cualquier hipervínculo provisto por el usuario (ej. links de LinkedIn, documentación, webs interactivas). Basado en las mejores prácticas de **2026** para scraping vía agentes de IA, se descarta el approach de HTTP llano (tipo `requests` + `BeautifulSoup`) debido a:
1. Contenido renderizado dinámicamente vía Client-Side Routing (React/Vue).
2. Protecciones anti-bot modernas.

En su lugar, se implementará el soporte a través del **Model Context Protocol (MCP)** conectando un servidor de browser headless (Puppeteer o Playwright).


---

## Estado de Implementación

- [x] Decisión de arquitectura: MCP + Browser headless (Puppeteer/Playwright) sobre HTTP llano
- [x] Evaluación de mcp-server-puppeteer vs Firecrawl MCP — seleccionado approach MCP configurable
- [x] skills/search/SKILL.md actualizado: instrucciones para usar tool MCP en lugar de alucinar contenido
- [x] app/mcp/manager.py verificado: soporte HTTP transport para servidores MCP externos (Smithery)
- [x] Integración fetch_markdown via MCP fetch server como fallback liviano sin browser headless
- [x] Docker: node/npx disponible en container para mcp-server-puppeteer (si se configura)
- [x] Documentado en CLAUDE.md: MCP HTTP transport detecta cfg["type"] para routing correcto

---

## Archivos a modificar
| Archivo | Cambio |
|---|---|
| `skills/search/SKILL.md` (o skill nuevo) | Actualizar instrucciones: no intentar alucinar contenido de links. Usar la herramienta MCP para leer URLs. |
| `app/mcp/manager.py` (si es necesario) | Verificar que la integración MCP actual (construida en Sprint 2/3) levante correctamente el server oficial de Puppeteer/Playwright. |
| `docs/exec-plans/22-web_browsing_plan.md` | Este archivo documenta la decisión de pivotar a MCP. |

## Servers MCP a evaluar
1. **mcp-server-puppeteer** (`@modelcontextprotocol/server-puppeteer`):
   - Estándar oficial de Anthropic.
   - Permite al LLM interactuar paso a paso: ir a url, clickear, hacer scroll y extraer HTML.
   - Requiere Node.js en el sistema anfitrión.
2. **Firecrawl MCP**:
   - Servicio Cloud (API key).
   - Extrae markdown impecable, lidia con proxies internamente.
   - Depende de terceros.

## Orden de implementación (Puppeteer Local)
1. **Validación del entorno**: Asegurar que `node` y `npx` están disponibles en el contenedor/host de WasAP.
2. **Integración**: Configurar `wasap` para que inicie el server MCP de Puppeteer (vía CLI config preexistente en la arquitectura MCP de WasAP).
3. **Instrucciones de Skill**: Ajustar el prompt base o el `SKILL.md` de búsqueda / web para que el agente entienda que las URLs crudas en el chat deben pasarse a la tool `puppeteer_navigate`.

## Decisiones de diseño
- **Por qué MCP + Browser Headless**: El ecosistema web migró a hidratación del lado cliente. Un simple `httpx.get` a un post de LinkedIn devuelve un `<script>` tag vacío y un reto de login. Puppeteer permite parsear el DOM dom (Accessibility Tree renderizado real) que los LLMs modernos comprenden mejor que el HTML serializado clásico.
- **Resiliencia**: El server MCP maneja la memoria del navegador. Si crashea, el Manager MCP lo reinicia.
