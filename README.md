# Fulgencio Agent

Servicio de voz en Python que conecta el protocolo WebSocket existente con
`gpt-realtime-1.5` mediante LiteLLM. El modelo conversa y solicita herramientas;
el backend valida el flujo y ejecuta Azure SQL/Firebase de forma determinista.

## Desarrollo nativo

Requisitos: Python 3.11 y Microsoft ODBC Driver 18 for SQL Server.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run_litellm_proxy.py
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

Completa `.env` antes de arrancar. El WebSocket es `ws://localhost:8010/ws` y
requiere Basic Auth. La entrada es PCM16 mono a 16 kHz; la salida `tts_chunk`
es PCM16 a 24 kHz codificado en Base64.

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Solo el agente se publica en `localhost:8010`; LiteLLM queda dentro de la red de
Compose.

## Verificación

```powershell
python -m unittest discover -s tests -v
```

- `GET /health/live`: proceso activo.
- `GET /health/ready`: comprueba LiteLLM, Azure SQL y Firebase.
- `WS /ws`: una única sesión activa.

## Despliegue

El directorio `terraform/` crea recursos aislados y una Container App de una
réplica con dos contenedores: `agent` y `litellm`. El workflow
`.github/workflows/deploy.yml` ejecuta pruebas, valida Terraform, publica la
imagen en ACR, despliega y comprueba readiness.

El estado de Terraform usa un backend `azurerm` independiente. Configura en el
repositorio los secretos descritos en `terraform/terraform.tfvars.example` y
los secretos de GitHub indicados al final de este documento.

### GitHub Secrets

- `AZURE_CREDENTIALS`: JSON de una service principal.
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`.
- `LITELLM_MASTER_KEY`.
- `FIREBASE_DATABASE_URL`, `FIREBASE_SERVICE_ACCOUNT_JSON`.
- `AZURE_SQL_CONNECTION_STRING`.
- `WS_BASIC_USERNAME`, `WS_BASIC_PASSWORD`.
- `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`, `TFSTATE_CONTAINER`.

### Backend existente

Configura `VOICE_AGENT_TYPE=fulgencio_agent` y
`FULGENCIO_AGENT_URL=wss://<usuario>:<clave-codificada>@<fqdn>/ws`.
