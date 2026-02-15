# WasAP - Guía de Setup y Testing

## Requisitos previos

- Docker y Docker Compose
- Cuenta de Meta Developer (gratis): https://developers.facebook.com
- Cuenta de ngrok (gratis): https://ngrok.com
- (Opcional) GPU NVIDIA con `nvidia-container-toolkit` instalado

### Instalar nvidia-container-toolkit (solo si tenés GPU NVIDIA)

```bash
# Agregar clave GPG
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes

# Agregar repositorio
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Instalar
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit

# Configurar Docker y reiniciar
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
```

---

## Paso 1: ngrok

1. Crear cuenta en https://dashboard.ngrok.com/signup
2. Ir a **Your Authtoken** (https://dashboard.ngrok.com/get-started/your-authtoken)
3. Copiar el authtoken

Vas a necesitar:
- `NGROK_AUTHTOKEN` = el authtoken

> **Nota:** Con el plan free, ngrok asigna una URL random cada vez que se reinicia el servicio. Esto implica reconfigurar el webhook en Meta después de cada restart. Si necesitás una URL fija, podés crear un dominio estático en **Universal Gateway > Domains** (requiere plan pago o dominio free limitado).

---

## Paso 2: Meta Developer - Crear App

### 2.1 Crear la app

1. Ir a https://developers.facebook.com/apps
2. Clickear **"Create App"**
3. Seleccionar **"Other"** como caso de uso, luego **"Business"** como tipo
4. Ponerle un nombre (ej: "WasAP") y clickear **"Create App"**

### 2.2 Agregar WhatsApp

1. En el dashboard de la app, buscar **"WhatsApp"** en la lista de productos
2. Clickear **"Set Up"**
3. Te lleva a **WhatsApp > Getting Started**

### 2.3 Obtener credenciales

En la página **WhatsApp > API Setup** (https://developers.facebook.com/apps/YOUR_APP_ID/whatsapp-business/wa-dev-console/):

1. **Phone Number ID**: aparece debajo de "From" en la sección de envío de prueba. Es un número largo (ej: `123456789012345`)
2. **Temporary Access Token**: clickear **"Generate"** -- este token expira en 24hs. Para uno permanente, ver la sección más abajo
3. **Agregar destinatario de prueba**: clickear **"Manage phone number list"**, agregar tu número personal y confirmar con el código de verificación que te llega por WhatsApp

Vas a necesitar:
- `WHATSAPP_ACCESS_TOKEN` = el token generado
- `WHATSAPP_PHONE_NUMBER_ID` = el Phone Number ID

### 2.4 App Secret

1. Ir a **App Settings > Basic** (https://developers.facebook.com/apps/YOUR_APP_ID/settings/basic/)
2. En **"App Secret"**, clickear **"Show"** y copiar

Vas a necesitar:
- `WHATSAPP_APP_SECRET` = el App Secret

### 2.5 Verify Token

Elegí un string secreto cualquiera. Va a ser usado para que Meta verifique que tu webhook es legítimo.

Ejemplo: `mi_token_secreto_123`

Vas a necesitar:
- `WHATSAPP_VERIFY_TOKEN` = el string que elegiste

### 2.6 Tu número de WhatsApp

Tu número personal con código de país y el 9 para móviles argentinos, sin `+` ni espacios.

Ejemplo: si tu número es +54 9 11 1234-5678, usás `5491112345678`

> **Nota Argentina:** WhatsApp envía los números con el formato `549XXXXXXXXXX` pero la API de Meta espera `54XXXXXXXXXX` (sin el 9). La app maneja esta conversión automáticamente.

Vas a necesitar:
- `ALLOWED_PHONE_NUMBERS` = tu número (ej: `5491112345678`). Se pueden poner varios separados por coma.

---

## Paso 3: Configurar .env

```bash
cd wasap
cp .env.example .env
```

Editar `.env` con los valores obtenidos:

```env
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxx...
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_VERIFY_TOKEN=mi_token_secreto_123
WHATSAPP_APP_SECRET=abcdef1234567890

ALLOWED_PHONE_NUMBERS=5491112345678

OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:8b
SYSTEM_PROMPT=You are a helpful personal assistant on WhatsApp. Be concise and friendly. Answer in the same language the user writes in.
CONVERSATION_MAX_MESSAGES=20

NGROK_AUTHTOKEN=2xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

LOG_LEVEL=INFO
```

---

## Paso 4: Levantar los servicios

### Sin GPU (CPU only)

```bash
docker compose up -d
```

### Con GPU NVIDIA

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### Descargar el modelo LLM

```bash
docker compose exec ollama ollama pull qwen3:8b
```

Esto descarga ~5GB. Solo se hace la primera vez (queda persistido en el volume `ollama_data`).

### Verificar que todo levantó

```bash
# Ver estado de los containers
docker compose ps

# Verificar health check
curl http://localhost:8000/health
```

Respuesta esperada:
```json
{"status":"ok","checks":{"available":true}}
```

Si Ollama todavía está descargando el modelo, `available` va a ser `true` pero el modelo no va a responder hasta que termine el pull. Si el check da `"available": false`, verificá que el container de Ollama esté corriendo (`docker compose logs ollama`).

### Verificar ngrok

```bash
docker compose logs ngrok
```

Deberías ver algo como:
```
t=... lvl=info msg="started tunnel" ... url=https://xxxx-xx-xx.ngrok-free.app
```

Copiar esa URL, la vas a necesitar para el paso siguiente.

---

## Paso 5: Configurar Webhook en Meta

1. Ir a **WhatsApp > Configuration** en tu app de Meta (https://developers.facebook.com/apps/YOUR_APP_ID/whatsapp-business/wa-settings/)
2. En la sección **Webhook**, clickear **"Edit"**
3. Completar:
   - **Callback URL**: `https://TU-URL-NGROK/webhook`
   - **Verify Token**: el mismo string que pusiste en `WHATSAPP_VERIFY_TOKEN` en el `.env`
4. Clickear **"Verify and Save"**

Si todo está bien, Meta envía un GET a tu webhook, recibe el challenge de vuelta, y guarda la configuración. Si falla, revisá:
- Que los 3 containers estén corriendo (`docker compose ps`)
- Que ngrok esté conectado (`docker compose logs ngrok`)
- Que el verify token coincida exactamente
- Que la URL sea correcta (con `https://` y `/webhook` al final)

5. **Suscribirse a mensajes**: en la misma página, en el campo **"Webhook fields"**, clickear **"Manage"** y activar **"messages"**

> **Nota:** Con ngrok free, la URL cambia en cada restart. Tenés que reconfigurar el webhook en Meta cada vez.

---

## Paso 6: Probar end-to-end

1. Abrí WhatsApp en tu celular
2. Mandá un mensaje al número de test de Meta (el que aparece en API Setup como "From")
   - Si nunca le escribiste, primero tenés que iniciar la conversación enviando el mensaje template que Meta sugiere en la sección de test
3. Esperá la respuesta del LLM

### Ver logs en tiempo real

```bash
docker compose logs -f wasap
```

Deberías ver el flujo:
```
INFO app.webhook.router: Incoming [5491112345678]: Hola!
INFO app.whatsapp.client: Outgoing  [541112345678]: Hola! En qué puedo ayudarte?
```

### Probar comandos

Una vez que el chat funciona, probá los comandos:

1. Mandá `/remember mi cumple es el 15 de marzo` → debería responder "Remembered: ..."
2. Mandá `/memories` → debería listar el dato guardado
3. Mandá un mensaje normal preguntando por tu cumpleaños → el LLM debería saberlo
4. Mandá `/help` → debería listar todos los comandos disponibles
5. Mandá `/clear` → borra el historial (las memorias persisten)

### Verificar persistencia

1. Verificar que existe `data/wasap.db` con datos:
   ```bash
   sqlite3 data/wasap.db "SELECT * FROM memories;"
   ```
2. Verificar que `data/MEMORY.md` refleja las memorias guardadas
3. Reiniciar la app (`docker compose restart wasap`) y verificar que el historial y memorias persisten

### Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| No llegan mensajes al webhook | Webhook no configurado o ngrok caído | Verificar `docker compose logs ngrok` y config en Meta |
| `"available": false` en /health | Ollama no está corriendo | `docker compose logs ollama`, verificar que el container esté up |
| Respuesta muy lenta (>60s) | CPU sin GPU, modelo grande | Usar modelo más chico: `OLLAMA_MODEL=qwen3:4b` |
| Error 403 en webhook verify | Verify token no coincide | Comparar `.env` con lo puesto en Meta |
| Mensaje no se responde | Número no en whitelist | Verificar `ALLOWED_PHONE_NUMBERS` en `.env` |
| `Invalid webhook signature` en logs | App Secret incorrecto | Verificar `WHATSAPP_APP_SECRET` en `.env` |
| Meta no envía mensajes | No suscrito a "messages" | Activar "messages" en Webhook fields |
| Error 131030 "Recipient not in allowed list" | Número no registrado como destinatario de prueba en Meta | Agregar número en API Setup > "Manage phone number list" |
| Error 401 Unauthorized | Access token expirado | Generar nuevo token en API Setup o usar token permanente (ver abajo) |
| Error 400 "permission" | Token sin permisos correctos | Verificar que el System User tenga `whatsapp_business_messaging` |
| Ollama 404 "model not found" | Modelo no descargado | `docker compose exec ollama ollama pull <modelo>` |
| Docker build falla con "Temporary failure resolving" | DNS no funciona dentro de Docker (común en hosts IPv6-only) | Buildear con `docker build --network host -t wasap-wasap .` y luego `docker compose up -d` (ver abajo) |

---

## Tests automatizados

```bash
# Desde la máquina host (con el venv)
.venv/bin/python -m pytest tests/ -v

# O desde el container
docker compose exec wasap pytest tests/ -v
```

Para correr tests dentro del container, el Dockerfile ya incluye las dependencias. Si querés correr los tests de dev, podés agregar un step de build o montar el directorio:

```bash
docker compose run --rm wasap python -m pytest tests/ -v
```

---

## Token permanente (opcional)

El token temporal de Meta expira en 24hs. Para obtener uno permanente:

1. Ir a **Business Settings** (https://business.facebook.com/settings/)
2. **System Users** > **Add** > crear un System User con rol Admin
3. Clickear en el System User > **Generate New Token**
4. Seleccionar tu app y los permisos: `whatsapp_business_messaging`, `whatsapp_business_management`
5. Copiar el token generado y reemplazar `WHATSAPP_ACCESS_TOKEN` en `.env`
6. Reiniciar: `docker compose restart wasap`

---

## Comandos útiles

```bash
# Levantar todo
docker compose up -d

# Levantar con GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Parar todo
docker compose down

# Ver logs de un servicio
docker compose logs -f wasap
docker compose logs -f ollama
docker compose logs -f ngrok

# Reiniciar solo wasap (después de cambiar .env)
docker compose restart wasap

# Cambiar modelo
docker compose exec ollama ollama pull qwen3:8b
# Luego cambiar OLLAMA_MODEL en .env y reiniciar wasap

# Listar modelos descargados
docker compose exec ollama ollama list

# Rebuild después de cambiar código
docker compose up -d --build wasap

# Si el build falla con "Temporary failure resolving" (problema DNS/IPv6):
docker build --network host -t wasap-wasap .
docker compose up -d
# Con GPU:
docker build --network host -t wasap-wasap .
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```
