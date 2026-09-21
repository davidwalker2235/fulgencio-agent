# Fulgencio Agent

Servicio de voz en Python que conecta el protocolo WebSocket existente directamente con
`gpt-realtime-1.5` en Azure OpenAI. El modelo conversa y solicita herramientas;
el backend valida el flujo y ejecuta Azure SQL/Firebase de forma determinista.

## Desarrollo nativo

Requisitos: Python 3.11 y Microsoft ODBC Driver 18 for SQL Server.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

Completa `.env` antes de arrancar. El WebSocket es `ws://localhost:8010/ws` y
requiere Basic Auth. La entrada es PCM16 mono a 16 kHz; la salida `tts_chunk`
es PCM16 a 24 kHz codificado en Base64.

La clave del modelo se configura únicamente en `AZURE_OPENAI_API_KEY`. En
producción debe existir como GitHub Actions repository secret con ese mismo nombre.

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

El agente se publica en `localhost:8010` y se conecta directamente al endpoint
Realtime GA de Azure OpenAI.

## Verificación

```powershell
python -m unittest discover -s tests -v
```

- `GET /health/live`: proceso activo.
- `GET /health/ready`: comprueba Azure OpenAI, Azure SQL y Firebase.
- `WS /ws`: una única sesión activa.

## Despliegue

El directorio `terraform/` usa el Resource Group `fulgencio-rg`, el ACR
`fulgencioacr`, la identidad `fulgencio-identity` y el entorno
`fulgencio-env` ya existentes. Solo crea la Container App `fulgencio-agent`,
con una réplica y un contenedor `agent`. El workflow
`.github/workflows/deploy.yml` ejecuta pruebas, valida Terraform, publica la
imagen en el ACR compartido, despliega y comprueba readiness.

El estado de Terraform usa un backend `azurerm` independiente. Configura en el
repositorio los secretos descritos en `terraform/terraform.tfvars.example` y
los secretos de GitHub indicados al final de este documento.

### GitHub Secrets

- `AZURE_CREDENTIALS`: JSON de una service principal.
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`.
- `FIREBASE_DATABASE_URL`, `FIREBASE_SERVICE_ACCOUNT_JSON`.
- `AZURE_SQL_CONNECTION_STRING`.
- `FULGENCIO_WS_BASIC_USERNAME`, `FULGENCIO_WS_BASIC_PASSWORD`.

El estado remoto reutiliza automáticamente la cuenta que usa el proyecto
existente y la clave independiente `fulgencio-agent.terraform.tfstate`.

### Backend existente

Configura en el proyecto existente la variable `VOICE_AGENT_TYPE=fulgencio_agent`
y el secret `FULGENCIO_AGENT_URL=wss://<usuario>:<clave-codificada>@<fqdn>/ws`.
