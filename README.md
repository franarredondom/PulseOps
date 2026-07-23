# PulseOps

PulseOps es un auditor web y plataforma de observabilidad HTTP. Recibe una página pública, examina su HTML y respuesta real, puntúa SEO, seguridad, accesibilidad y rendimiento, detecta tecnologías y entrega mejoras concretas. El monitoreo continuo conserva además disponibilidad, latencia e incidentes en PostgreSQL.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-20232A?logo=react&logoColor=61DAFB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-4169E1?logo=postgresql&logoColor=white)
![Cost](https://img.shields.io/badge/monthly_cost-$0-16885B)

## Funcionalidades

- Auditoría técnica real de páginas HTML públicas, sin datos ficticios.
- Puntajes de rendimiento HTTP, SEO, accesibilidad básica y seguridad.
- Revisión de títulos, descripciones, H1, canonical, idioma, imágenes, enlaces y Open Graph.
- Comprobación de robots.txt, sitemap.xml, HTTPS, compresión y cabeceras de seguridad.
- Detección no invasiva de tecnologías visibles y recomendaciones ordenadas por impacto.
- Historial persistente de informes y eliminación individual.
- Monitoreo inmediato de cualquier URL HTTP/HTTPS pública.
- Estado operativo, degradado o caído basado en respuesta y latencia reales.
- Historial de comprobaciones y disponibilidad calculada desde PostgreSQL.
- Creación y resolución automática de incidentes después de fallos consecutivos.
- Pausa, reactivación, eliminación y nueva comprobación de monitores.
- Protección contra objetivos de red privados o reservados.
- Scheduler protegido mediante secreto y ejecutado con GitHub Actions.
- Dashboard público responsive sin datos ficticios ni modo de demostración.

## Arquitectura

```text
React + Vite ───────► FastAPI ─────────► PostgreSQL / Supabase
                            │
                            ├── auditor de HTML, SEO y accesibilidad
                            ├── análisis HTTP y cabeceras de seguridad
                            ├── comprobaciones concurrentes de monitores
                            └── motor automático de incidentes

GitHub Actions ─────► POST /api/checks/run cada 10 minutos
```

## Ejecución local

### Docker

```bash
docker compose up --build
```

Dashboard: `http://localhost:5173`

API: `http://localhost:8000`

Swagger: `http://localhost:8000/docs`

### Sin Docker

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
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Variables de entorno

Frontend:

| Variable | Uso |
| --- | --- |
| `VITE_API_URL` | URL pública de FastAPI |

Backend:

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | SQLite local o conexión PostgreSQL de Supabase |
| `CORS_ORIGINS` | Orígenes web autorizados, separados por comas |
| `CRON_SECRET` | Protege la ejecución programada |
| `FAILURE_THRESHOLD` | Fallos consecutivos para abrir un incidente |

## Despliegue gratuito

El Blueprint [`render.yaml`](render.yaml) define dos recursos:

1. `pulseops-api`: Web Service Docker con FastAPI.
2. `pulseops-dashboard`: Static Site con React/Vite.

La base de datos usa el Session Pooler de Supabase. Render solicita `DATABASE_URL` al crear el Blueprint; nunca guardes esa cadena en GitHub.

Para activar las comprobaciones programadas, agrega en GitHub los secretos `PULSEOPS_API_URL` y `PULSEOPS_CRON_SECRET`. El workflow `uptime-checks.yml` ejecuta los monitores pendientes cada diez minutos.

## API principal

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Salud de API y base de datos |
| `POST` | `/api/audits` | Audita una página real y guarda el informe |
| `GET` | `/api/audits` | Historial reciente de auditorías |
| `GET/DELETE` | `/api/audits/{id}` | Consulta o elimina un informe |
| `POST` | `/api/analyze` | Guarda un monitor y lo comprueba inmediatamente |
| `GET/POST` | `/api/monitors` | Lista o crea monitores |
| `PATCH/DELETE` | `/api/monitors/{id}` | Actualiza o elimina un monitor |
| `POST` | `/api/monitors/{id}/check` | Ejecuta una comprobación inmediata |
| `GET` | `/api/checks/recent` | Historial reciente con datos del monitor |
| `POST` | `/api/checks/run` | Ejecuta comprobaciones pendientes |
| `GET` | `/api/incidents` | Incidentes reales abiertos y resueltos |
| `GET` | `/api/overview` | Disponibilidad, latencia y conteos agregados |

## Seguridad

- Los secretos y archivos `.env` están excluidos del repositorio.
- El scheduler exige `X-Cron-Secret`.
- El checker rechaza IP privadas, loopback, link-local y redes reservadas.
- El auditor vuelve a validar cada destino durante las redirecciones y limita el HTML a 2 MB.
- La concurrencia está limitada a diez solicitudes.
- La instancia pública es un workspace compartido. Para múltiples usuarios independientes, la siguiente evolución recomendada es autenticación y aislamiento por workspace.
