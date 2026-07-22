# PulseOps

PulseOps es una plataforma de monitoreo HTTP e incidentes construida como proyecto de portafolio backend-first. Comprueba endpoints en paralelo, conserva su historial, aplica umbrales de latencia y abre o resuelve incidentes automáticamente.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-20232A?logo=react&logoColor=61DAFB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-ready-4169E1?logo=postgresql&logoColor=white)
![Cost](https://img.shields.io/badge/monthly_cost-$0-16885B)

## Qué demuestra

- API REST documentada automáticamente con OpenAPI.
- Comprobaciones HTTP concurrentes con límite de concurrencia.
- PostgreSQL en producción y SQLite para desarrollo rápido.
- Creación y resolución automática de incidentes.
- Reintentos del scheduler y protección mediante secreto.
- Dashboard responsive conectado a la API con modo demostración.
- Contenedores, pruebas y CI en cada push.
- Ejecución programada gratuita mediante GitHub Actions.

## Arquitectura

```text
React / vinext ───────► FastAPI ─────────► PostgreSQL
      │                    │
      │                    ├── comprobaciones concurrentes
      │                    └── motor de incidentes
      │
      └── modo demo si la API gratuita está dormida

GitHub Actions ───────► POST /api/checks/run cada 10 min
```

## Inicio rápido

### Opción A: Docker

```bash
docker compose up --build
```

Dashboard: `http://localhost:3000`  
API: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

### Opción B: desarrollo sin Docker

Frontend:

```bash
cp .env.example .env.local
npm install
npm run dev
```

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Variables de entorno

Frontend:

| Variable | Uso |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | URL pública de la API |

Backend:

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | SQLite local o conexión PostgreSQL de Supabase |
| `CORS_ORIGINS` | Orígenes autorizados, separados por comas |
| `CRON_SECRET` | Protege el endpoint ejecutado por el scheduler |
| `FAILURE_THRESHOLD` | Fallos consecutivos necesarios para abrir incidente |

## Despliegue gratuito

1. Publica el dashboard en Cloudflare Pages, Sites o Vercel.
2. Publica `backend/` como Web Service gratuito en Render usando su Dockerfile.
3. Crea un proyecto gratuito de Supabase y copia su cadena PostgreSQL en `DATABASE_URL`.
4. Añade `PULSEOPS_API_URL` y `PULSEOPS_CRON_SECRET` como secrets del repositorio.
5. Activa GitHub Actions; `uptime-checks.yml` ejecutará los monitores cada diez minutos.

Render puede dormir la API gratuita tras un período sin tráfico. El workflow programado funciona como entrada legítima para ejecutar las comprobaciones pendientes, aunque el primer intento puede tardar mientras el servicio despierta.

## Endpoints principales

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Estado de API y base de datos |
| `GET/POST` | `/api/monitors` | Listar o crear monitores |
| `PATCH/DELETE` | `/api/monitors/{id}` | Editar, pausar o eliminar |
| `POST` | `/api/monitors/{id}/check` | Comprobar un endpoint ahora |
| `POST` | `/api/checks/run` | Ejecutar comprobaciones pendientes |
| `GET` | `/api/incidents` | Historial de incidentes |
| `GET` | `/api/overview` | Métricas agregadas |

## Seguridad y límites

- No subas archivos `.env` ni secretos al repositorio.
- El scheduler requiere `X-Cron-Secret`.
- El checker limita la concurrencia a diez solicitudes.
- Los planes gratuitos son adecuados para demos y portafolio, no para monitoreo crítico.

## Próximas iteraciones

- Autenticación con JWT y workspaces multiusuario.
- Métricas de uptime calculadas desde `check_results`.
- Eventos con NATS JetStream y patrón transactional outbox.
- OpenTelemetry, Prometheus y Grafana para observabilidad local.
- Notificaciones mediante webhooks de Discord o Slack.
