# PulseOps

PulseOps es una plataforma de inteligencia y observabilidad web. Analiza páginas públicas, transforma señales técnicas en recomendaciones priorizadas y mantiene un historial privado por cuenta. También permite monitorear disponibilidad, latencia e incidentes de sitios y APIs.

[Aplicación](https://pulseops-dashboard.onrender.com/) · [API](https://pulseops-api-qlqu.onrender.com/docs)

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-20232A?logo=react&logoColor=61DAFB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-4169E1?logo=postgresql&logoColor=white)

## Producto

### Auditoría web

- Puntajes de rendimiento HTTP, SEO, accesibilidad básica y seguridad.
- Revisión de títulos, descripciones, H1, canonical, idioma, imágenes, enlaces y Open Graph.
- Comprobación de `robots.txt`, `sitemap.xml`, HTTPS, compresión y cabeceras de seguridad.
- Detección no invasiva de tecnologías visibles.
- Recomendaciones ordenadas por impacto e historial persistente de informes.

### Observabilidad

- Monitores HTTP configurables para sitios y APIs.
- Historial de disponibilidad, estado y latencia.
- Creación y resolución automática de incidentes.
- Ejecución programada mediante un scheduler protegido.

### Identidad y privacidad

- Registro e inicio de sesión mediante Supabase Auth.
- Confirmación de correo y recuperación de contraseña.
- Renovación y persistencia automática de sesiones.
- Auditorías, monitores, comprobaciones e incidentes aislados por usuario.
- Gestión de perfil, cambio de contraseña y cierre de sesión.

## Arquitectura

```text
                         ┌── Supabase Auth
React + Vite ── JWT ───► FastAPI ─────────► PostgreSQL / Supabase
                            │
                            ├── auditor de HTML, SEO y accesibilidad
                            ├── análisis HTTP y cabeceras de seguridad
                            ├── comprobaciones concurrentes de monitores
                            └── motor automático de incidentes

GitHub Actions ─────────► scheduler de comprobaciones
```

FastAPI valida el token de Supabase antes de acceder a los recursos. El identificador autenticado se aplica en todas las consultas para mantener separados los espacios de trabajo.

## Desarrollo local

### Frontend

```bash
cp .env.example .env.local
npm install
npm run dev
```

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Dashboard: `http://localhost:5173`

API: `http://localhost:8000`

OpenAPI: `http://localhost:8000/docs`

## Configuración

Frontend:

| Variable | Uso |
| --- | --- |
| `VITE_API_URL` | URL de FastAPI |
| `VITE_SUPABASE_URL` | URL del proyecto Supabase |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Clave pública utilizada por Supabase Auth |

Backend:

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | Conexión PostgreSQL o SQLite local |
| `CORS_ORIGINS` | Orígenes web autorizados |
| `SUPABASE_URL` | URL utilizada para validar sesiones |
| `SUPABASE_PUBLISHABLE_KEY` | Clave pública para consultar Supabase Auth |
| `CRON_SECRET` | Protege la ejecución del scheduler |
| `FAILURE_THRESHOLD` | Fallos consecutivos necesarios para abrir un incidente |

Para que las confirmaciones y recuperaciones regresen a la aplicación, configura en Supabase Auth:

- **Site URL:** `https://pulseops-dashboard.onrender.com`
- **Redirect URL:** `https://pulseops-dashboard.onrender.com/**`

## Despliegue

El Blueprint [`render.yaml`](render.yaml) define:

1. `pulseops-api`: servicio Docker con FastAPI.
2. `pulseops-dashboard`: aplicación estática React/Vite.

La base de datos utiliza PostgreSQL en Supabase. `DATABASE_URL` debe configurarse directamente en Render y nunca almacenarse en el repositorio.

## API

Salvo `/health` y el scheduler, las rutas requieren `Authorization: Bearer <access_token>`.

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Salud de API y base de datos |
| `GET` | `/api/account` | Identidad asociada a la sesión |
| `POST/GET` | `/api/audits` | Crea o lista auditorías propias |
| `GET/DELETE` | `/api/audits/{id}` | Consulta o elimina un informe propio |
| `GET/POST` | `/api/monitors` | Lista o crea monitores propios |
| `PATCH/DELETE` | `/api/monitors/{id}` | Actualiza o elimina un monitor |
| `POST` | `/api/monitors/{id}/check` | Ejecuta una comprobación inmediata |
| `GET` | `/api/checks/recent` | Historial de comprobaciones del usuario |
| `GET` | `/api/incidents` | Incidentes asociados a sus monitores |
| `GET` | `/api/overview` | Métricas agregadas del espacio personal |
| `POST` | `/api/checks/run` | Ejecuta comprobaciones pendientes mediante secreto |

## Seguridad

- Las contraseñas y los correos de autenticación son gestionados por Supabase Auth.
- Los tokens se validan contra el servidor de autenticación antes de acceder a datos.
- Todas las consultas interactivas se filtran por propietario.
- Los archivos `.env` y secretos permanecen fuera del repositorio.
- El auditor rechaza redes privadas, loopback, link-local y destinos reservados.
- Cada redirección se vuelve a validar y el HTML descargado está limitado a 2 MB.
- El scheduler exige `X-Cron-Secret`.
