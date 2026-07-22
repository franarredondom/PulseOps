"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type MonitorStatus = "operational" | "degraded" | "down" | "paused";

type Monitor = {
  id: string;
  name: string;
  url: string;
  status: MonitorStatus;
  uptime: number;
  latency: number | null;
  checked: string;
  history: MonitorStatus[];
};

const initialMonitors: Monitor[] = [
  {
    id: "checkout",
    name: "Checkout API",
    url: "https://api.acme.dev/checkout",
    status: "operational",
    uptime: 99.98,
    latency: 184,
    checked: "hace 38 s",
    history: ["operational", "operational", "operational", "operational", "operational", "operational", "operational", "operational", "operational", "operational", "operational", "operational"],
  },
  {
    id: "storefront",
    name: "Tienda principal",
    url: "https://acme.dev",
    status: "operational",
    uptime: 99.94,
    latency: 241,
    checked: "hace 1 min",
    history: ["operational", "operational", "degraded", "operational", "operational", "operational", "operational", "operational", "operational", "operational", "operational", "operational"],
  },
  {
    id: "auth",
    name: "Servicio de identidad",
    url: "https://auth.acme.dev/health",
    status: "degraded",
    uptime: 98.72,
    latency: 892,
    checked: "hace 22 s",
    history: ["operational", "operational", "operational", "operational", "operational", "degraded", "degraded", "operational", "degraded", "degraded", "degraded", "degraded"],
  },
  {
    id: "docs",
    name: "Documentación",
    url: "https://docs.acme.dev",
    status: "paused",
    uptime: 100,
    latency: null,
    checked: "pausado hace 2 h",
    history: ["operational", "operational", "operational", "operational", "operational", "operational", "operational", "paused", "paused", "paused", "paused", "paused"],
  },
];

const statusCopy: Record<MonitorStatus, string> = {
  operational: "Operativo",
  degraded: "Degradado",
  down: "Caído",
  paused: "Pausado",
};

const apiUrl = (
  process.env.NEXT_PUBLIC_API_URL || "https://pulseops-api-qlqu.onrender.com"
).replace(/\/$/, "");

type ApiMonitor = {
  id: string;
  name: string;
  url: string;
  status: string;
  is_active: boolean;
  last_latency_ms: number | null;
  last_checked_at: string | null;
};

function fromApi(monitor: ApiMonitor): Monitor {
  const knownStatus = ["operational", "degraded", "down", "paused"].includes(monitor.status)
    ? (monitor.status as MonitorStatus)
    : monitor.is_active ? "operational" : "paused";
  return {
    id: monitor.id,
    name: monitor.name,
    url: monitor.url,
    status: knownStatus,
    uptime: knownStatus === "down" ? 98.4 : 100,
    latency: monitor.last_latency_ms ? Math.round(monitor.last_latency_ms) : null,
    checked: monitor.last_checked_at ? new Date(monitor.last_checked_at).toLocaleString("es-CL") : "sin comprobar",
    history: Array.from({ length: 12 }, () => knownStatus),
  };
}

export function Dashboard() {
  const [monitors, setMonitors] = useState(initialMonitors);
  const [activeView, setActiveView] = useState("Resumen");
  const [showNewMonitor, setShowNewMonitor] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!apiUrl) return;
    fetch(`${apiUrl}/api/monitors`)
      .then((response) => response.ok ? response.json() as Promise<ApiMonitor[]> : Promise.reject())
      .then((items) => setMonitors(items.map(fromApi)))
      .catch(() => setNotice("La API está iniciando; mostramos datos de demostración."));
  }, []);

  const activeMonitors = useMemo(
    () => monitors.filter((monitor) => monitor.status !== "paused"),
    [monitors],
  );
  const averageUptime = activeMonitors.length
    ? activeMonitors.reduce((total, monitor) => total + monitor.uptime, 0) /
      activeMonitors.length
    : 0;

  async function addMonitor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "Nuevo servicio");
    const url = String(form.get("url") || "https://example.com");
    let newMonitor: Monitor =
      {
        id: crypto.randomUUID(),
        name,
        url,
        status: "operational",
        uptime: 100,
        latency: 126,
        checked: "ahora",
        history: Array.from({ length: 12 }, () => "operational" as const),
      };
    if (apiUrl) {
      try {
        const response = await fetch(`${apiUrl}/api/monitors`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, url, interval_minutes: Number(form.get("interval") || 5) }),
        });
        if (!response.ok) throw new Error("create failed");
        newMonitor = fromApi(await response.json() as ApiMonitor);
      } catch {
        setNotice("No pudimos conectar con la API; el monitor quedó solo en esta demostración.");
      }
    }
    setMonitors((current) => [
      ...current,
      newMonitor,
    ]);
    setShowNewMonitor(false);
    setNotice(`${name} quedó en observación.`);
  }

  async function runCheck(monitor: Monitor) {
    if (apiUrl) {
      try {
        const response = await fetch(`${apiUrl}/api/monitors/${monitor.id}/check`, { method: "POST" });
        if (!response.ok) throw new Error("check failed");
        const result = await response.json() as { status: MonitorStatus; latency_ms: number | null };
        setMonitors((current) => current.map((item) => item.id === monitor.id ? { ...item, status: result.status, latency: result.latency_ms ? Math.round(result.latency_ms) : null, checked: "ahora" } : item));
        setNotice(`Comprobación real de ${monitor.name} completada.`);
        return;
      } catch {
        setNotice("La API no respondió; conservamos el último estado conocido.");
        return;
      }
    }
    setNotice(`Comprobación de ${monitor.name} completada en ${monitor.latency ?? 0} ms.`);
    setMonitors((current) =>
      current.map((item) =>
        item.id === monitor.id ? { ...item, checked: "ahora" } : item,
      ),
    );
  }

  async function toggleMonitor(monitor: Monitor) {
    const nextStatus = monitor.status === "paused" ? "operational" : "paused";
    setMonitors((current) =>
      current.map((item) =>
        item.id === monitor.id ? { ...item, status: nextStatus } : item,
      ),
    );
    if (apiUrl) {
      fetch(`${apiUrl}/api/monitors/${monitor.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: nextStatus !== "paused" }),
      }).catch(() => setNotice("El cambio se verá solo en esta sesión."));
    }
    setNotice(
      nextStatus === "paused"
        ? `${monitor.name} fue pausado.`
        : `${monitor.name} volvió a estar activo.`,
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <span className="brand-mark" aria-hidden="true"><i /></span>
          <span>PulseOps</span>
        </div>

        <nav aria-label="Navegación principal">
          <p className="nav-label">Workspace</p>
          {["Resumen", "Monitores", "Incidentes"].map((item) => (
            <button
              className={`nav-item ${activeView === item ? "active" : ""}`}
              key={item}
              onClick={() => setActiveView(item)}
            >
              <span className={`nav-glyph ${item.toLowerCase()}`} aria-hidden="true" />
              {item}
              {item === "Incidentes" && <em>1</em>}
            </button>
          ))}
          <p className="nav-label second">Gestionar</p>
          {["Páginas de estado", "Integraciones", "Configuración"].map((item) => (
            <button className="nav-item" key={item} onClick={() => setNotice(`${item} estará disponible en la próxima iteración.`)}>
              <span className="nav-glyph" aria-hidden="true" />
              {item}
            </button>
          ))}
        </nav>

        <div className="free-plan">
          <span>Plan gratuito</span>
          <strong>{monitors.length} de 10 monitores</strong>
          <div><i style={{ width: `${Math.min(monitors.length * 10, 100)}%` }} /></div>
          <small>$0 al mes · Sin tarjeta</small>
        </div>

        <button className="profile-card" onClick={() => setNotice("Perfil de demostración activo.")}>
          <span className="avatar">FC</span>
          <span><strong>Fran Castillo</strong><small>Workspace personal</small></span>
          <b>···</b>
        </button>
      </aside>

      <section className="content">
        <header className="topbar">
          <div className="mobile-brand">
            <span className="brand-mark"><i /></span> PulseOps
          </div>
          <div className="header-actions">
            <button className="icon-button" aria-label="Notificaciones"><span className="notification-dot" />♢</button>
            <button className="primary-button" onClick={() => setShowNewMonitor(true)}><span>＋</span> Nuevo monitor</button>
          </div>
        </header>

        <div className="page-wrap">
          <div className="page-heading">
            <div>
              <span className="eyebrow">CENTRO DE OPERACIONES</span>
              <h1>{activeView}</h1>
              <p>Todo tu sistema, entendido de un vistazo.</p>
            </div>
            <div className="all-systems"><span /> Todos los sistemas operativos</div>
          </div>

          {activeView === "Resumen" && (
            <>
              <section className="metrics" aria-label="Métricas generales">
                <article>
                  <div className="metric-head"><span>Disponibilidad</span><i className="metric-icon green">↗</i></div>
                  <strong>{averageUptime.toFixed(2)}<small>%</small></strong>
                  <p><b>+0,04%</b> frente al mes anterior</p>
                  <div className="micro-bars green-bars">{[38,44,41,52,49,58,55,62,61,70,66,76,73,79,82,78,86,84,91,88].map((height, index) => <i key={index} style={{ height }} />)}</div>
                </article>
                <article>
                  <div className="metric-head"><span>Latencia media</span><i className="metric-icon blue">⌁</i></div>
                  <strong>274<small>ms</small></strong>
                  <p><b className="blue-text">−18 ms</b> en las últimas 24 horas</p>
                  <div className="latency-track"><i /><span style={{ left: "46%" }} /></div>
                  <div className="track-labels"><span>0 ms</span><span>600 ms</span></div>
                </article>
                <article>
                  <div className="metric-head"><span>Incidentes</span><i className="metric-icon amber">!</i></div>
                  <strong>1<small>abierto</small></strong>
                  <p><b className="amber-text">Identidad</b> presenta latencia alta</p>
                  <button className="text-link" onClick={() => setActiveView("Incidentes")}>Ver incidente <span>→</span></button>
                </article>
              </section>

              <section className="panel monitors-panel">
                <div className="panel-heading">
                  <div><h2>Monitores</h2><p>Estado actual de tus servicios esenciales</p></div>
                  <button className="secondary-button" onClick={() => setActiveView("Monitores")}>Ver todos <span>→</span></button>
                </div>
                <MonitorTable monitors={monitors} onCheck={runCheck} onToggle={toggleMonitor} />
              </section>

              <div className="bottom-grid">
                <section className="panel incident-panel">
                  <div className="panel-heading"><div><h2>Incidente activo</h2><p>Requiere tu atención</p></div><span className="severity">DEGRADADO</span></div>
                  <div className="incident-content">
                    <div className="incident-line"><span className="pulse-dot" /><div><strong>Latencia elevada en identidad</strong><p>Servicio de identidad · Desde las 14:38</p></div></div>
                    <div className="incident-meta"><span><small>Duración</small><strong>24 min</strong></span><span><small>Impacto</small><strong>Inicio de sesión lento</strong></span></div>
                    <button className="incident-button" onClick={() => setActiveView("Incidentes")}>Abrir línea de tiempo</button>
                  </div>
                </section>
                <section className="panel activity-panel">
                  <div className="panel-heading"><div><h2>Actividad reciente</h2><p>Últimos eventos del sistema</p></div></div>
                  <ul>
                    <li><span className="activity-icon success">✓</span><div><strong>Checkout API recuperado</strong><p>Respuesta estable bajo 200 ms</p></div><time>14:42</time></li>
                    <li><span className="activity-icon warning">⌁</span><div><strong>Umbral de latencia superado</strong><p>Servicio de identidad · 892 ms</p></div><time>14:38</time></li>
                    <li><span className="activity-icon neutral">Ⅱ</span><div><strong>Documentación pausada</strong><p>Acción manual por Fran</p></div><time>12:21</time></li>
                  </ul>
                </section>
              </div>
            </>
          )}

          {activeView === "Monitores" && (
            <section className="panel standalone-panel">
              <div className="panel-heading"><div><h2>Todos los monitores</h2><p>Comprueba, pausa y administra cada endpoint</p></div><button className="primary-button compact" onClick={() => setShowNewMonitor(true)}>＋ Agregar</button></div>
              <MonitorTable monitors={monitors} onCheck={runCheck} onToggle={toggleMonitor} />
            </section>
          )}

          {activeView === "Incidentes" && (
            <section className="panel standalone-panel incident-list">
              <div className="panel-heading"><div><h2>Línea de tiempo</h2><p>Eventos agrupados para entender el impacto rápidamente</p></div><span className="severity">1 ACTIVO</span></div>
              <div className="timeline">
                <article><i className="now" /><time>14:42</time><div><strong>La latencia comienza a estabilizarse</strong><p>Tres comprobaciones consecutivas bajo 500 ms. PulseOps seguirá observando antes de cerrar el incidente.</p></div></article>
                <article><i /><time>14:39</time><div><strong>Incidente creado automáticamente</strong><p>La regla “3 respuestas lentas consecutivas” alcanzó su umbral.</p></div></article>
                <article><i /><time>14:38</time><div><strong>Se detectó degradación</strong><p>El endpoint de identidad respondió en 892 ms.</p></div></article>
              </div>
            </section>
          )}
        </div>
      </section>

      {notice && <button className="toast" onClick={() => setNotice("")} aria-live="polite">{notice}<span>×</span></button>}

      {showNewMonitor && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setShowNewMonitor(false)}>
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="monitor-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowNewMonitor(false)} aria-label="Cerrar">×</button>
            <span className="eyebrow">NUEVO ENDPOINT</span>
            <h2 id="monitor-title">¿Qué quieres observar?</h2>
            <p>PulseOps comprobará disponibilidad, latencia y códigos de respuesta.</p>
            <form onSubmit={addMonitor}>
              <label>Nombre del servicio<input name="name" placeholder="Ej. API de pagos" required autoFocus /></label>
              <label>URL pública<input name="url" type="url" placeholder="https://api.ejemplo.com/health" required /></label>
              <label>Frecuencia<select name="interval" defaultValue="5"><option value="5">Cada 5 minutos</option><option value="10">Cada 10 minutos</option><option value="30">Cada 30 minutos</option></select></label>
              <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowNewMonitor(false)}>Cancelar</button><button className="primary-button" type="submit">Crear monitor</button></div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}

function MonitorTable({ monitors, onCheck, onToggle }: { monitors: Monitor[]; onCheck: (monitor: Monitor) => void; onToggle: (monitor: Monitor) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Servicio</th><th>Estado</th><th>Uptime 30 d</th><th>Latencia</th><th>Última revisión</th><th><span className="sr-only">Acciones</span></th></tr></thead>
        <tbody>{monitors.map((monitor) => (
          <tr key={monitor.id}>
            <td><div className="service-cell"><span className={`service-badge ${monitor.status}`}>{monitor.name.slice(0, 1)}</span><span><strong>{monitor.name}</strong><small>{monitor.url}</small></span></div></td>
            <td><span className={`status ${monitor.status}`}><i />{statusCopy[monitor.status]}</span></td>
            <td><div className="uptime-cell"><span>{monitor.uptime.toFixed(2)}%</span><div>{monitor.history.map((state, index) => <i className={state} key={index} />)}</div></div></td>
            <td><span className={monitor.status === "degraded" ? "latency-high" : ""}>{monitor.latency ? `${monitor.latency} ms` : "—"}</span></td>
            <td className="muted">{monitor.checked}</td>
            <td><div className="row-actions"><button onClick={() => onCheck(monitor)} disabled={monitor.status === "paused"}>Comprobar</button><button onClick={() => onToggle(monitor)}>{monitor.status === "paused" ? "Activar" : "Pausar"}</button></div></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
