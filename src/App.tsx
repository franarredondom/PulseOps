import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type MonitorStatus = "unknown" | "operational" | "degraded" | "down" | "paused";

type Monitor = {
  id: string;
  name: string;
  url: string;
  interval_minutes: number;
  timeout_seconds: number;
  expected_status: number;
  latency_threshold_ms: number;
  is_active: boolean;
  status: MonitorStatus;
  consecutive_failures: number;
  last_latency_ms: number | null;
  last_checked_at: string | null;
  created_at: string;
};

type Check = {
  id: string;
  monitor_id: string;
  monitor_name: string;
  monitor_url: string;
  status: MonitorStatus;
  status_code: number | null;
  latency_ms: number | null;
  error: string | null;
  checked_at: string;
};

type Incident = {
  id: string;
  monitor_id: string;
  monitor_name: string;
  monitor_url: string;
  title: string;
  status: "open" | "resolved";
  cause: string | null;
  started_at: string;
  resolved_at: string | null;
};

type Overview = {
  monitors: number;
  activeMonitors: number;
  openIncidents: number;
  averageLatencyMs: number | null;
  availabilityPercent: number | null;
  totalChecks: number;
  statusCounts: Record<MonitorStatus, number>;
};

type Analysis = {
  monitor: Monitor;
  check: Omit<Check, "monitor_name" | "monitor_url">;
};

const apiUrl = (import.meta.env.VITE_API_URL || "https://pulseops-api-qlqu.onrender.com").replace(/\/$/, "");

const statusCopy: Record<MonitorStatus, string> = {
  unknown: "Sin analizar",
  operational: "Operativo",
  degraded: "Degradado",
  down: "Caído",
  paused: "Pausado",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `La API respondió con estado ${response.status}`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

function relativeTime(value: string | null): string {
  if (!value) return "Sin comprobaciones";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `Hace ${seconds} s`;
  if (seconds < 3600) return `Hace ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `Hace ${Math.floor(seconds / 3600)} h`;
  return new Date(value).toLocaleDateString("es-CL");
}

function durationSince(value: string): string {
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} h`;
  return `${Math.floor(minutes / 1440)} d`;
}

function checkMessage(check: Check): string {
  if (check.error) return check.error;
  const http = check.status_code ? `HTTP ${check.status_code}` : "Sin código HTTP";
  const latency = check.latency_ms != null ? ` · ${Math.round(check.latency_ms)} ms` : "";
  return `${http}${latency}`;
}

export default function App() {
  const [activeView, setActiveView] = useState("Resumen");
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [checks, setChecks] = useState<Check[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [showAnalyzer, setShowAnalyzer] = useState(false);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [monitorData, overviewData, incidentData, checkData] = await Promise.all([
        request<Monitor[]>("/api/monitors"),
        request<Overview>("/api/overview"),
        request<Incident[]>("/api/incidents"),
        request<Check[]>("/api/checks/recent?limit=120"),
      ]);
      setMonitors(monitorData);
      setOverview(overviewData);
      setIncidents(incidentData);
      setChecks(checkData);
      setError("");
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "No fue posible conectar con PulseOps API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const checksByMonitor = useMemo(() => {
    const grouped = new Map<string, Check[]>();
    for (const check of checks) {
      const current = grouped.get(check.monitor_id) || [];
      current.push(check);
      grouped.set(check.monitor_id, current);
    }
    return grouped;
  }, [checks]);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const url = String(form.get("url") || "").trim();
    const name = String(form.get("name") || "").trim();
    setAnalyzing(true);
    setNotice("");
    try {
      const result = await request<Analysis>("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          name: name || undefined,
          latency_threshold_ms: Number(form.get("latency") || 750),
        }),
      });
      const latency = result.check.latency_ms == null ? "sin latencia disponible" : `${Math.round(result.check.latency_ms)} ms`;
      setNotice(`${result.monitor.name}: ${statusCopy[result.check.status]} · ${latency}`);
      setShowAnalyzer(false);
      await refresh();
    } catch (analysisError) {
      setNotice(analysisError instanceof Error ? analysisError.message : "No fue posible analizar la URL");
    } finally {
      setAnalyzing(false);
    }
  }

  async function runCheck(monitor: Monitor) {
    setNotice(`Analizando ${monitor.name}…`);
    try {
      const result = await request<Omit<Check, "monitor_name" | "monitor_url">>(`/api/monitors/${monitor.id}/check`, { method: "POST" });
      const latency = result.latency_ms == null ? "sin respuesta" : `${Math.round(result.latency_ms)} ms`;
      setNotice(`${monitor.name}: ${statusCopy[result.status]} · ${latency}`);
      await refresh();
    } catch (checkError) {
      setNotice(checkError instanceof Error ? checkError.message : "La comprobación falló");
    }
  }

  async function toggleMonitor(monitor: Monitor) {
    try {
      await request<Monitor>(`/api/monitors/${monitor.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !monitor.is_active }),
      });
      setNotice(`${monitor.name} fue ${monitor.is_active ? "pausado" : "activado"}.`);
      await refresh();
    } catch (toggleError) {
      setNotice(toggleError instanceof Error ? toggleError.message : "No fue posible actualizar el monitor");
    }
  }

  async function removeMonitor(monitor: Monitor) {
    if (!window.confirm(`¿Eliminar ${monitor.name} y todo su historial?`)) return;
    try {
      await request<void>(`/api/monitors/${monitor.id}`, { method: "DELETE" });
      setNotice(`${monitor.name} fue eliminado.`);
      await refresh();
    } catch (removeError) {
      setNotice(removeError instanceof Error ? removeError.message : "No fue posible eliminar el monitor");
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-row"><span className="brand-mark" aria-hidden="true"><i /></span><span>PulseOps</span></div>
        <nav aria-label="Navegación principal">
          <p className="nav-label">Operación</p>
          {["Resumen", "Monitores", "Incidentes"].map((item) => (
            <button className={`nav-item ${activeView === item ? "active" : ""}`} key={item} onClick={() => setActiveView(item)}>
              <span className={`nav-glyph ${item.toLowerCase()}`} aria-hidden="true" />
              {item}
              {item === "Incidentes" && overview && overview.openIncidents > 0 && <em>{overview.openIncidents}</em>}
            </button>
          ))}
        </nav>
        <div className="free-plan">
          <span>Workspace real</span>
          <strong>{monitors.length} de 10 monitores</strong>
          <div><i style={{ width: `${Math.min(monitors.length * 10, 100)}%` }} /></div>
          <small>{overview?.totalChecks || 0} comprobaciones almacenadas</small>
        </div>
        <div className="profile-card profile-static"><span className="avatar">PO</span><span><strong>PulseOps Cloud</strong><small>Render + Supabase</small></span></div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div className="mobile-brand"><span className="brand-mark"><i /></span> PulseOps</div>
          <div className="header-actions">
            <span className={`connection-state ${error ? "offline" : ""}`}><i />{error ? "API sin conexión" : "API conectada"}</span>
            <button className="primary-button" onClick={() => setShowAnalyzer(true)}><span>＋</span> Analizar URL</button>
          </div>
        </header>

        <div className="page-wrap">
          <div className="page-heading">
            <div><span className="eyebrow">OBSERVABILIDAD HTTP REAL</span><h1>{activeView}</h1><p>Disponibilidad, latencia e incidentes calculados desde comprobaciones reales.</p></div>
            <button className="refresh-button" onClick={() => void refresh()} disabled={loading}>{loading ? "Actualizando…" : "Actualizar"}</button>
          </div>

          {error && <section className="api-error" role="alert"><strong>No podemos leer la API</strong><p>{error}</p><button onClick={() => void refresh()}>Reintentar</button></section>}

          {activeView === "Resumen" && (
            <>
              <section className="metrics" aria-label="Métricas reales">
                <MetricCard label="Disponibilidad" value={overview?.availabilityPercent == null ? "Sin datos" : `${overview.availabilityPercent.toFixed(2)}%`} detail={overview ? `${overview.totalChecks} comprobaciones acumuladas` : "Esperando a la API"} tone="green" />
                <MetricCard label="Latencia media" value={overview?.averageLatencyMs == null ? "Sin datos" : `${Math.round(overview.averageLatencyMs)} ms`} detail="Promedio de respuestas con latencia registrada" tone="blue" />
                <MetricCard label="Incidentes abiertos" value={String(overview?.openIncidents ?? 0)} detail={overview?.openIncidents ? "Requieren revisión" : "No hay incidentes activos"} tone="amber" />
              </section>

              <section className="panel monitors-panel">
                <div className="panel-heading"><div><h2>Monitores</h2><p>Último estado obtenido para cada URL</p></div><button className="secondary-button" onClick={() => setActiveView("Monitores")}>Ver todos →</button></div>
                <MonitorTable monitors={monitors.slice(0, 5)} checksByMonitor={checksByMonitor} onCheck={runCheck} onToggle={toggleMonitor} onRemove={removeMonitor} />
              </section>

              <div className="bottom-grid">
                <section className="panel incident-panel">
                  <div className="panel-heading"><div><h2>Incidentes recientes</h2><p>Generados automáticamente después de fallos consecutivos</p></div></div>
                  <IncidentSummary incidents={incidents.slice(0, 3)} />
                </section>
                <section className="panel activity-panel">
                  <div className="panel-heading"><div><h2>Actividad reciente</h2><p>Respuestas observadas por el backend</p></div></div>
                  <CheckActivity checks={checks.slice(0, 5)} />
                </section>
              </div>
            </>
          )}

          {activeView === "Monitores" && (
            <section className="panel standalone-panel">
              <div className="panel-heading"><div><h2>Todos los monitores</h2><p>Analiza, pausa o elimina endpoints persistidos en Supabase</p></div><button className="primary-button compact" onClick={() => setShowAnalyzer(true)}>＋ Analizar URL</button></div>
              <MonitorTable monitors={monitors} checksByMonitor={checksByMonitor} onCheck={runCheck} onToggle={toggleMonitor} onRemove={removeMonitor} />
            </section>
          )}

          {activeView === "Incidentes" && (
            <section className="panel standalone-panel incident-list">
              <div className="panel-heading"><div><h2>Incidentes registrados</h2><p>Solo aparecen cuando las comprobaciones reales alcanzan el umbral de fallos</p></div><span className="severity">{overview?.openIncidents || 0} ABIERTOS</span></div>
              <IncidentTimeline incidents={incidents} />
            </section>
          )}
        </div>
      </section>

      {notice && <button className="toast" onClick={() => setNotice("")} aria-live="polite">{notice}<span>×</span></button>}

      {showAnalyzer && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !analyzing && setShowAnalyzer(false)}>
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="analyzer-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowAnalyzer(false)} disabled={analyzing} aria-label="Cerrar">×</button>
            <span className="eyebrow">ANÁLISIS EN TIEMPO REAL</span>
            <h2 id="analyzer-title">¿Qué URL quieres comprobar?</h2>
            <p>El backend realizará una solicitud HTTP ahora, medirá su latencia y conservará el resultado para calcular disponibilidad e incidentes.</p>
            <form onSubmit={analyze}>
              <label>URL pública<input name="url" type="url" placeholder="https://ejemplo.com/health" required autoFocus disabled={analyzing} /></label>
              <label>Nombre opcional<input name="name" placeholder="Ej. API de pagos" disabled={analyzing} /></label>
              <label>Umbral de latencia<select name="latency" defaultValue="750" disabled={analyzing}><option value="300">300 ms</option><option value="750">750 ms</option><option value="1500">1.500 ms</option><option value="3000">3.000 ms</option></select></label>
              <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowAnalyzer(false)} disabled={analyzing}>Cancelar</button><button className="primary-button" type="submit" disabled={analyzing}>{analyzing ? "Analizando…" : "Analizar y guardar"}</button></div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}

function MetricCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: "green" | "blue" | "amber" }) {
  return <article><div className="metric-head"><span>{label}</span><i className={`metric-icon ${tone}`}>{tone === "amber" ? "!" : "↗"}</i></div><strong className={value === "Sin datos" ? "empty-value" : ""}>{value}</strong><p>{detail}</p></article>;
}

function MonitorTable({ monitors, checksByMonitor, onCheck, onToggle, onRemove }: { monitors: Monitor[]; checksByMonitor: Map<string, Check[]>; onCheck: (monitor: Monitor) => void; onToggle: (monitor: Monitor) => void; onRemove: (monitor: Monitor) => void }) {
  return (
    <div className="table-wrap"><table><thead><tr><th>Servicio</th><th>Estado</th><th>Disponibilidad</th><th>Latencia</th><th>Última revisión</th><th><span className="sr-only">Acciones</span></th></tr></thead>
      <tbody>
        {monitors.length === 0 && <tr><td colSpan={6}><div className="empty-state"><strong>Aún no hay URLs analizadas</strong><p>Usa “Analizar URL” para realizar la primera comprobación real.</p></div></td></tr>}
        {monitors.map((monitor) => {
          const monitorChecks = checksByMonitor.get(monitor.id) || [];
          const healthy = monitorChecks.filter((check) => check.status === "operational" || check.status === "degraded").length;
          const uptime = monitorChecks.length ? (healthy / monitorChecks.length) * 100 : null;
          const history = [...monitorChecks].slice(0, 12).reverse();
          return <tr key={monitor.id}>
            <td><div className="service-cell"><span className={`service-badge ${monitor.status}`}>{monitor.name.slice(0, 1).toUpperCase()}</span><span><strong>{monitor.name}</strong><small>{monitor.url}</small></span></div></td>
            <td><span className={`status ${monitor.status}`}><i />{statusCopy[monitor.status]}</span></td>
            <td><div className="uptime-cell"><span>{uptime == null ? "—" : `${uptime.toFixed(1)}%`}</span><div>{history.length ? history.map((check) => <i className={check.status} key={check.id} title={checkMessage(check)} />) : <span className="no-history">Sin historial</span>}</div></div></td>
            <td><span className={monitor.status === "degraded" ? "latency-high" : ""}>{monitor.last_latency_ms == null ? "—" : `${Math.round(monitor.last_latency_ms)} ms`}</span></td>
            <td className="muted">{relativeTime(monitor.last_checked_at)}</td>
            <td><div className="row-actions"><button onClick={() => onCheck(monitor)} disabled={!monitor.is_active}>Analizar</button><button onClick={() => onToggle(monitor)}>{monitor.is_active ? "Pausar" : "Activar"}</button><button className="danger-action" onClick={() => onRemove(monitor)}>Eliminar</button></div></td>
          </tr>;
        })}
      </tbody>
    </table></div>
  );
}

function IncidentSummary({ incidents }: { incidents: Incident[] }) {
  if (!incidents.length) return <div className="empty-state roomy"><strong>Sin incidentes registrados</strong><p>PulseOps creará uno cuando una URL acumule los fallos configurados.</p></div>;
  return <div className="incident-cards">{incidents.map((incident) => <article key={incident.id}><span className={`incident-dot ${incident.status}`} /><div><strong>{incident.title}</strong><p>{incident.monitor_name} · {incident.cause || "Sin causa informada"}</p></div><small>{incident.status === "open" ? durationSince(incident.started_at) : "Resuelto"}</small></article>)}</div>;
}

function CheckActivity({ checks }: { checks: Check[] }) {
  if (!checks.length) return <div className="empty-state roomy"><strong>Sin actividad todavía</strong><p>Las comprobaciones aparecerán aquí con su respuesta HTTP real.</p></div>;
  return <ul>{checks.map((check) => <li key={check.id}><span className={`activity-icon ${check.status}`}>{check.status === "operational" ? "✓" : check.status === "degraded" ? "!" : "×"}</span><div><strong>{check.monitor_name}</strong><p>{checkMessage(check)}</p></div><time>{relativeTime(check.checked_at)}</time></li>)}</ul>;
}

function IncidentTimeline({ incidents }: { incidents: Incident[] }) {
  if (!incidents.length) return <div className="empty-state page-empty"><strong>No existen incidentes</strong><p>Esto no es un ejemplo: la lista permanecerá vacía hasta que una URL falle repetidamente.</p></div>;
  return <div className="timeline">{incidents.map((incident) => <article key={incident.id}><i className={incident.status === "open" ? "now" : "resolved"} /><time>{new Date(incident.started_at).toLocaleString("es-CL")}</time><div><strong>{incident.title}</strong><p>{incident.monitor_name} · {incident.cause || "Sin causa informada"}</p>{incident.resolved_at && <small>Resuelto {relativeTime(incident.resolved_at)}</small>}</div></article>)}</div>;
}
