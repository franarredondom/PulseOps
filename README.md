<div align="center">

# PulseOps

### Inteligencia técnica y observabilidad para sitios web

Analiza páginas reales, convierte señales técnicas en recomendaciones claras y monitorea su disponibilidad desde un espacio privado.

[**Abrir PulseOps →**](https://pulseops-dashboard.onrender.com/) · [Documentación de la API](https://pulseops-api-qlqu.onrender.com/docs)

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-20232A?logo=react&logoColor=61DAFB)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-4169E1?logo=postgresql&logoColor=white)
![Render](https://img.shields.io/badge/Deploy-Render-6C47FF?logo=render&logoColor=white)

</div>

---

## Qué es PulseOps

PulseOps reúne auditoría web y monitoreo HTTP en una misma plataforma. Cada usuario puede analizar páginas públicas, consultar informes persistentes, vigilar servicios y revisar incidentes sin compartir información con otras cuentas.

El análisis se ejecuta desde el backend contra la URL solicitada. Los resultados no son ejemplos precargados: proceden del HTML y de la respuesta HTTP observados durante cada auditoría.

## Funcionalidades

| Área | Capacidades |
| --- | --- |
| **Auditoría técnica** | Puntajes de rendimiento, SEO, accesibilidad básica y seguridad |
| **SEO y contenido** | Título, descripción, H1, canonical, idioma, Open Graph, enlaces e imágenes |
| **Infraestructura web** | Estado HTTP, latencia, peso del HTML, redirecciones y compresión |
| **Seguridad** | HTTPS y cabeceras como CSP, HSTS, Referrer-Policy y Permissions-Policy |
| **Descubrimiento** | `robots.txt`, `sitemap.xml` y tecnologías visibles en el código público |
| **Recomendaciones** | Mejoras ordenadas por categoría, severidad e impacto |
| **Monitoreo** | Comprobaciones periódicas de disponibilidad y latencia |
| **Incidentes** | Apertura y resolución automática después de fallos consecutivos |
| **Cuentas** | Registro, confirmación de correo, login, recuperación y cambio de contraseña |
| **Privacidad** | Auditorías, monitores e incidentes aislados por usuario |

## Cómo funciona

1. El usuario crea una cuenta o inicia sesión mediante Supabase Auth.
2. Ingresa la URL pública que desea analizar.
3. FastAPI valida la sesión y comprueba que el destino no pertenezca a una red privada.
4. El auditor descarga el HTML, inspecciona la respuesta y calcula los puntajes.
5. El informe se guarda en PostgreSQL asociado exclusivamente a su propietario.
6. Si crea un monitor, el scheduler continúa comprobando el servicio y registra incidentes.

## Alcance del análisis

PulseOps analiza el documento HTML inicial y las cabeceras entregadas por el servidor. Esto permite detectar problemas técnicos y estructurales sin ejecutar código de terceros.

No sustituye una auditoría manual ni una ejecución completa de Lighthouse: las métricas de experiencia real, el contraste visual, la navegación con teclado y el contenido generado exclusivamente con JavaScript requieren herramientas adicionales.

## Arquitectura

```text
                                    ┌─────────────────┐
                                    │  Supabase Auth  │
                                    └────────┬────────┘
                                             │ JWT
┌─────────────────┐                 ┌────────▼────────┐
│  React + Vite   │ ──────────────► │     FastAPI     │
│    Dashboard    │                 │  API + Auditor  │
└─────────────────┘                 └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │   PostgreSQL    │
                                    │    Supabase     │
                                    └─────────────────┘

GitHub Actions ─────────► Scheduler ─────────► Monitores HTTP
```

FastAPI valida el token de acceso antes de procesar rutas privadas. El identificador autenticado se aplica a todas las consultas interactivas para impedir el acceso cruzado entre cuentas.

## Tecnologías

| Capa | Tecnología |
| --- | --- |
| Frontend | React 19, TypeScript y Vite |
| Backend | Python, FastAPI, SQLAlchemy y HTTPX |
| Autenticación | Supabase Auth con sesiones JWT |
| Persistencia | PostgreSQL en Supabase |
| Despliegue | Render Blueprint |
| Automatización | GitHub Actions |
| Pruebas | Pytest, TypeScript y build de Vite |

## Desarrollo local

### Requisitos

- Node.js 22 o superior.
- Python 3.12 o superior.
- Un proyecto de Supabase con autenticación por correo habilitada.

### 1. Clonar e instalar el frontend

```bash
git clone https://github.com/franarredondom/PulseOps.git
cd PulseOps
cp .env.example .env.local
npm install
npm run dev
```

El dashboard estará disponible en `http://localhost:5173`.

### 2. Preparar el backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

La API estará disponible en `http://localhost:8000` y OpenAPI en `http://localhost:8000/docs`.

## Variables de entorno

### Frontend

| Variable | Descripción |
| --- | --- |
| `VITE_API_URL` | Dirección de la API FastAPI |
| `VITE_SUPABASE_URL` | URL del proyecto Supabase |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Clave pública utilizada por Supabase Auth |

### Backend

| Variable | Descripción |
| --- | --- |
| `DATABASE_URL` | Conexión PostgreSQL o SQLite local |
| `CORS_ORIGINS` | Orígenes autorizados, separados por comas |
| `SUPABASE_URL` | URL utilizada para validar las sesiones |
| `SUPABASE_PUBLISHABLE_KEY` | Clave pública para consultar Supabase Auth |
| `CRON_SECRET` | Secreto del scheduler de monitores |
| `FAILURE_THRESHOLD` | Fallos consecutivos necesarios para abrir un incidente |

La clave publicable de Supabase puede utilizarse en el navegador. La contraseña de PostgreSQL y cualquier clave `service_role` deben mantenerse fuera del repositorio.

## Configuración de Supabase Auth

En **Authentication → URL Configuration** configura:

```text
Site URL
https://pulseops-dashboard.onrender.com

Redirect URL
https://pulseops-dashboard.onrender.com/**
```

Estas direcciones permiten que la confirmación de correo y la recuperación de contraseña regresen a la aplicación.

## Despliegue

[`render.yaml`](render.yaml) describe los dos servicios de PulseOps:

- `pulseops-dashboard`: aplicación estática React/Vite.
- `pulseops-api`: servicio Docker con FastAPI.

`DATABASE_URL` se configura directamente en Render. El resto de los valores públicos de integración se declara en el Blueprint.

Las comprobaciones programadas utilizan [`.github/workflows/uptime-checks.yml`](.github/workflows/uptime-checks.yml) y requieren los secretos `PULSEOPS_API_URL` y `PULSEOPS_CRON_SECRET` en GitHub Actions.

## API principal

Las rutas de producto requieren `Authorization: Bearer <access_token>`. `/health` y el scheduler utilizan mecanismos independientes.

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Comprueba la API y la conexión de base de datos |
| `GET` | `/api/account` | Devuelve la identidad de la sesión |
| `GET / POST` | `/api/audits` | Lista o crea auditorías del usuario |
| `GET / DELETE` | `/api/audits/{id}` | Consulta o elimina un informe propio |
| `GET / POST` | `/api/monitors` | Lista o crea monitores propios |
| `PATCH / DELETE` | `/api/monitors/{id}` | Actualiza o elimina un monitor |
| `POST` | `/api/monitors/{id}/check` | Ejecuta una comprobación inmediata |
| `GET` | `/api/checks/recent` | Lista comprobaciones recientes |
| `GET` | `/api/incidents` | Lista incidentes asociados a la cuenta |
| `GET` | `/api/overview` | Calcula métricas del espacio personal |
| `POST` | `/api/checks/run` | Ejecuta comprobaciones pendientes mediante secreto |

## Seguridad

- Supabase Auth gestiona credenciales, confirmaciones y recuperación de acceso.
- FastAPI valida cada token privado con el servidor de autenticación.
- Las consultas se filtran por el propietario autenticado.
- El auditor bloquea direcciones privadas, loopback, link-local y redes reservadas.
- Cada redirección se valida nuevamente para reducir riesgos de SSRF.
- El HTML descargado está limitado a 2 MB.
- El scheduler exige `X-Cron-Secret`.
- Los archivos `.env` y las credenciales de infraestructura no se versionan.

## Pruebas

Frontend:

```bash
npm test
```

Backend:

```bash
cd backend
pytest
```

Las pruebas cubren el ciclo de monitores, persistencia de auditorías, protección de rutas, señales HTML, restricciones de red y separación de recursos entre usuarios.

---

<div align="center">

[**Ir a PulseOps**](https://pulseops-dashboard.onrender.com/) · [Explorar la API](https://pulseops-api-qlqu.onrender.com/docs)

</div>
