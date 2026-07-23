import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "./supabase";

type View = "Auditorías" | "Monitoreo" | "Incidentes" | "Cuenta";
type AuthMode = "login" | "register" | "forgot" | "update";
type MonitorStatus = "unknown" | "operational" | "degraded" | "down" | "paused";
type Recommendation = { category: string; severity: "alta" | "media" | "baja"; title: string; detail: string };
type Report = {
  page: { title: string; description: string; language: string; canonical: string; h1Count: number };
  http: { redirects: string[]; compressed: boolean };
  seo: { robotsTxt: boolean; sitemapXml: boolean };
  content: { images: number; imagesWithAlt: number; internalLinks: number; externalLinks: number };
  security: { https: boolean; presentHeaders: string[]; missingHeaders: string[] };
  technologies: string[]; recommendations: Recommendation[]; scope: string;
};
type Audit = { id:string; url:string; final_url:string; hostname:string; status_code:number; latency_ms:number; size_bytes:number; overall_score:number; performance_score:number; seo_score:number; accessibility_score:number; security_score:number; report:Report; created_at:string };
type Monitor = { id:string; name:string; url:string; is_active:boolean; status:MonitorStatus; last_latency_ms:number|null; last_checked_at:string|null };
type Check = { id:string; monitor_id:string; status:MonitorStatus };
type Incident = { id:string; monitor_name:string; title:string; status:"open"|"resolved"; cause:string|null; started_at:string; resolved_at:string|null };
type Overview = { activeMonitors:number; openIncidents:number; averageLatencyMs:number|null; availabilityPercent:number|null; totalChecks:number };

const API = (import.meta.env.VITE_API_URL || "https://pulseops-api-qlqu.onrender.com").replace(/\/$/, "");
const statuses: Record<MonitorStatus,string> = { unknown:"Sin revisar", operational:"Operativo", degraded:"Lento", down:"Caído", paused:"Pausado" };

async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const { data } = await supabase.auth.getSession();
  if (!data.session?.access_token) throw new Error("Inicia sesión para continuar");
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${data.session.access_token}`);
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as {detail?:string}|null;
    if (response.status === 401) await supabase.auth.signOut();
    throw new Error(data?.detail || `La API respondió con estado ${response.status}`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
const normalize = (url:string) => /^https?:\/\//i.test(url) ? url : `https://${url}`;
const age = (value:string|null) => {
  if (!value) return "Sin comprobaciones";
  const minutes = Math.max(0, Math.floor((Date.now()-new Date(value).getTime())/60000));
  if (minutes < 1) return "Ahora"; if (minutes < 60) return `Hace ${minutes} min`; if (minutes < 1440) return `Hace ${Math.floor(minutes/60)} h`;
  return new Date(value).toLocaleDateString("es-CL");
};
const bytes = (value:number) => value < 1e6 ? `${(value/1e3).toFixed(1)} KB` : `${(value/1e6).toFixed(2)} MB`;
const tone = (score:number) => score >= 80 ? "good" : score >= 55 ? "medium" : "poor";

function authMessage(message:string) {
  const translations:Record<string,string> = {
    "Invalid login credentials":"Correo o contraseña incorrectos.",
    "Email not confirmed":"Confirma tu correo antes de iniciar sesión.",
    "User already registered":"Ya existe una cuenta con ese correo.",
    "Password should be at least 6 characters":"La contraseña debe tener al menos 8 caracteres.",
    "Unable to validate email address: invalid format":"Escribe un correo válido.",
  };
  return translations[message] || message;
}

export default function App() {
  const [session,setSession] = useState<Session|null>(null);
  const [ready,setReady] = useState(false);
  const [recovering,setRecovering] = useState(false);

  useEffect(()=>{
    void supabase.auth.getSession().then(({data})=>{ setSession(data.session); setReady(true); });
    const { data } = supabase.auth.onAuthStateChange((event,nextSession)=>{
      setSession(nextSession);
      if (event === "PASSWORD_RECOVERY") setRecovering(true);
      if (event === "SIGNED_OUT") setRecovering(false);
      setReady(true);
    });
    return ()=>data.subscription.unsubscribe();
  },[]);

  if (!ready) return <div className="auth-loading"><Logo/><span>Preparando tu espacio…</span></div>;
  if (recovering || (session && new URLSearchParams(location.search).has("password-reset"))) {
    return <AuthScreen initialMode="update" onPasswordUpdated={()=>{ setRecovering(false); history.replaceState({},"",location.pathname); }}/>;
  }
  if (!session) return <AuthScreen initialMode="login"/>;
  return <Dashboard session={session}/>;
}

function AuthScreen({initialMode,onPasswordUpdated}:{initialMode:AuthMode;onPasswordUpdated?:()=>void}) {
  const [mode,setMode] = useState<AuthMode>(initialMode);
  const [busy,setBusy] = useState(false); const [error,setError] = useState(""); const [message,setMessage] = useState("");

  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form=event.currentTarget,data=new FormData(form); const email=String(data.get("email")||"").trim(); const password=String(data.get("password")||""); const confirmPassword=String(data.get("confirmPassword")||"");
    setBusy(true); setError(""); setMessage("");
    try {
      if ((mode === "register" || mode === "update") && password.length < 8) throw new Error("La contraseña debe tener al menos 8 caracteres.");
      if ((mode === "register" || mode === "update") && password !== confirmPassword) throw new Error("Las contraseñas no coinciden.");
      if (mode === "login") {
        const {error:authError}=await supabase.auth.signInWithPassword({email,password}); if(authError)throw authError;
      } else if (mode === "register") {
        const name=String(data.get("name")||"").trim();
        const {data:result,error:authError}=await supabase.auth.signUp({email,password,options:{data:{full_name:name},emailRedirectTo:location.origin}}); if(authError)throw authError;
        if (!result.session) { setMessage("Cuenta creada. Revisa tu correo para confirmar el acceso."); form.reset(); }
      } else if (mode === "forgot") {
        const {error:authError}=await supabase.auth.resetPasswordForEmail(email,{redirectTo:`${location.origin}/?password-reset=1`}); if(authError)throw authError;
        setMessage("Si el correo pertenece a una cuenta, recibirás un enlace para cambiar la contraseña."); form.reset();
      } else {
        const {error:authError}=await supabase.auth.updateUser({password}); if(authError)throw authError;
        setMessage("Contraseña actualizada correctamente."); onPasswordUpdated?.();
      }
    } catch(err) { setError(authMessage(err instanceof Error?err.message:"No fue posible completar la solicitud.")); }
    finally { setBusy(false); }
  }

  const copy = mode === "login" ? ["Bienvenido de nuevo","Accede a tus auditorías y monitores."] : mode === "register" ? ["Crea tu cuenta","Organiza el historial de tus sitios en un espacio personal."] : mode === "forgot" ? ["Recupera tu acceso","Te enviaremos un enlace seguro para elegir otra contraseña."] : ["Elige otra contraseña","Crea una contraseña nueva para tu cuenta."];
  return <main className="auth-shell"><section className="auth-brand"><div><div className="auth-logo"><Logo/><strong>PulseOps</strong></div><span className="eyebrow">INTELIGENCIA WEB</span><h1>Decisiones más claras<br/>para cada sitio.</h1><p>Auditoría técnica, monitoreo continuo e historial privado en un solo lugar.</p><ul><li>SEO, seguridad y accesibilidad</li><li>Rendimiento y tecnología</li><li>Monitoreo e incidentes</li></ul></div><small>PulseOps · Web Intelligence</small></section><section className="auth-panel"><div className="auth-card"><div className="auth-mobile-logo"><Logo/><strong>PulseOps</strong></div><span className="eyebrow">CUENTA PERSONAL</span><h2>{copy[0]}</h2><p>{copy[1]}</p>{message&&<div className="auth-message">{message}</div>}{error&&<div className="auth-error">{error}</div>}<form onSubmit={submit}>
    {mode === "register"&&<label>Nombre<input name="name" autoComplete="name" placeholder="Tu nombre" required/></label>}
    {mode !== "update"&&<label>Correo electrónico<input name="email" type="email" autoComplete="email" placeholder="nombre@correo.com" required autoFocus/></label>}
    {mode !== "forgot"&&<label>Contraseña<input name="password" type="password" autoComplete={mode==="login"?"current-password":"new-password"} placeholder="Mínimo 8 caracteres" required autoFocus={mode==="update"}/></label>}
    {(mode === "register" || mode === "update")&&<label>Confirmar contraseña<input name="confirmPassword" type="password" autoComplete="new-password" placeholder="Repite la contraseña" required/></label>}
    {mode === "login"&&<button type="button" className="text-action" onClick={()=>{setMode("forgot");setError("");setMessage("")}}>¿Olvidaste tu contraseña?</button>}
    <button className="auth-submit" disabled={busy}>{busy?"Procesando…":mode==="login"?"Iniciar sesión":mode==="register"?"Crear cuenta":mode==="forgot"?"Enviar enlace":"Guardar contraseña"}</button>
  </form>{mode !== "update"&&<div className="auth-switch">{mode==="login"?<>¿No tienes cuenta? <button onClick={()=>{setMode("register");setError("");setMessage("")}}>Crear cuenta</button></>:<>¿Ya tienes cuenta? <button onClick={()=>{setMode("login");setError("");setMessage("")}}>Iniciar sesión</button></>}</div>}</div></section></main>;
}

function Dashboard({session}:{session:Session}) {
  const [view,setView] = useState<View>("Auditorías");
  const [audits,setAudits] = useState<Audit[]>([]); const [selected,setSelected] = useState<Audit|null>(null);
  const [monitors,setMonitors] = useState<Monitor[]>([]); const [checks,setChecks] = useState<Check[]>([]);
  const [incidents,setIncidents] = useState<Incident[]>([]); const [overview,setOverview] = useState<Overview|null>(null);
  const [loading,setLoading] = useState(true); const [auditing,setAuditing] = useState(false); const [monitorModal,setMonitorModal] = useState(false);
  const [error,setError] = useState(""); const [notice,setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [a,m,c,i,o] = await Promise.all([request<Audit[]>("/api/audits?limit=40"),request<Monitor[]>("/api/monitors"),request<Check[]>("/api/checks/recent?limit=120"),request<Incident[]>("/api/incidents"),request<Overview>("/api/overview")]);
      setAudits(a); setSelected(current => current ? a.find(item=>item.id===current.id)||a[0]||null : a[0]||null);
      setMonitors(m); setChecks(c); setIncidents(i); setOverview(o); setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "No fue posible conectar con PulseOps"); }
    finally { setLoading(false); }
  },[]);
  useEffect(()=>{ void refresh(); },[refresh]);

  async function audit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form=event.currentTarget; const url=normalize(String(new FormData(form).get("url")||"").trim());
    setAuditing(true); setError("");
    try { const result=await request<Audit>("/api/audits",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url})}); setAudits(current=>[result,...current]); setSelected(result); form.reset(); setNotice(`Auditoría completada para ${result.hostname}`); }
    catch(err){ setError(err instanceof Error?err.message:"No fue posible auditar el sitio"); }
    finally{ setAuditing(false); }
  }
  async function deleteAudit(item:Audit){ if(!confirm(`¿Eliminar la auditoría de ${item.hostname}?`))return; try{await request(`/api/audits/${item.id}`,{method:"DELETE"});const next=audits.filter(a=>a.id!==item.id);setAudits(next);setSelected(next[0]||null);}catch(err){setNotice(err instanceof Error?err.message:"No fue posible eliminarla");} }
  async function createMonitor(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget,data=new FormData(form);setAuditing(true);try{await request("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:normalize(String(data.get("url")||"")),name:String(data.get("name")||"")})});setMonitorModal(false);form.reset();await refresh();setNotice("Monitor creado y comprobado.");}catch(err){setNotice(err instanceof Error?err.message:"No fue posible crear el monitor");}finally{setAuditing(false);}}
  async function monitorAction(item:Monitor, action:"check"|"toggle"|"delete") { try { if(action==="delete"&&!confirm(`¿Eliminar ${item.name} y su historial?`))return; const path=action==="check"?`/api/monitors/${item.id}/check`:`/api/monitors/${item.id}`; await request(path,{method:action==="check"?"POST":action==="delete"?"DELETE":"PATCH",headers:action==="toggle"?{"Content-Type":"application/json"}:undefined,body:action==="toggle"?JSON.stringify({is_active:!item.is_active}):undefined});await refresh();}catch(err){setNotice(err instanceof Error?err.message:"La operación falló");} }

  const userName=String(session.user.user_metadata.full_name||session.user.email?.split("@")[0]||"Usuario");

  return <main className="app">
    <aside><button className="brand" onClick={()=>setView("Auditorías")}><Logo/><span>PulseOps<small>WEB INTELLIGENCE</small></span></button><nav><p>ANÁLISIS</p><Nav active={view==="Auditorías"} icon="◎" label="Auditorías" onClick={()=>setView("Auditorías")}/><p>OPERACIÓN</p><Nav active={view==="Monitoreo"} icon="⌁" label="Monitoreo" badge={monitors.length} onClick={()=>setView("Monitoreo")}/><Nav active={view==="Incidentes"} icon="!" label="Incidentes" badge={overview?.openIncidents||0} onClick={()=>setView("Incidentes")}/><p>ESPACIO PERSONAL</p><Nav active={view==="Cuenta"} icon="○" label="Mi cuenta" onClick={()=>setView("Cuenta")}/></nav><button className="user-card" onClick={()=>setView("Cuenta")}><b>{userName.slice(0,1).toUpperCase()}</b><span><strong>{userName}</strong><small>{session.user.email}</small></span></button></aside>
    <section className="workspace"><header><button className="mobile-brand"><Logo/>PulseOps</button><span className={`api-state ${error?"bad":""}`}>● {error?"Revisa la conexión":"Sistema conectado"}</span><button className="header-account" onClick={()=>setView("Cuenta")}><b>{userName.slice(0,1).toUpperCase()}</b>{userName}</button></header>
      {view==="Auditorías"&&<AuditPage audits={audits} selected={selected} loading={loading} auditing={auditing} error={error} onAudit={audit} onSelect={setSelected} onDelete={deleteAudit}/>}
      {view==="Monitoreo"&&<MonitorPage monitors={monitors} checks={checks} overview={overview} onCreate={()=>setMonitorModal(true)} onAction={monitorAction}/>}
      {view==="Incidentes"&&<IncidentPage incidents={incidents}/>}
      {view==="Cuenta"&&<AccountPage session={session}/>}
    </section>
    {notice&&<button className="toast" onClick={()=>setNotice("")}>{notice}<b>×</b></button>}
    {monitorModal&&<Modal onClose={()=>setMonitorModal(false)}><span className="eyebrow">MONITOREO CONTINUO</span><h2>Crear monitor HTTP</h2><p>Comprueba disponibilidad y latencia periódicamente. Es independiente de la auditoría web.</p><form onSubmit={createMonitor}><label>URL pública<input name="url" placeholder="https://ejemplo.com" required autoFocus/></label><label>Nombre<input name="name" placeholder="Mi sitio" required/></label><div><button type="button" onClick={()=>setMonitorModal(false)}>Cancelar</button><button className="primary" disabled={auditing}>{auditing?"Comprobando…":"Crear y comprobar"}</button></div></form></Modal>}
  </main>;
}

function Logo(){return <span className="logo"><i/><i/><i/></span>}
function Nav({active,icon,label,badge,onClick}:{active:boolean;icon:string;label:string;badge?:number;onClick:()=>void}){return <button className={active?"active":""} onClick={onClick}><i>{icon}</i>{label}{badge? <em>{badge}</em>:null}</button>}

function AuditPage({audits,selected,loading,auditing,error,onAudit,onSelect,onDelete}:{audits:Audit[];selected:Audit|null;loading:boolean;auditing:boolean;error:string;onAudit:(e:FormEvent<HTMLFormElement>)=>void;onSelect:(a:Audit)=>void;onDelete:(a:Audit)=>void}){
  return <div className="page"><section className="hero"><div><span className="eyebrow">— AUDITORÍA WEB REAL</span><h1>Entiende qué está<br/>frenando tu sitio.</h1><p>Analizamos el HTML público y convertimos SEO, seguridad, accesibilidad y rendimiento en acciones concretas.</p></div><form onSubmit={onAudit}><label>Pega la dirección de tu página</label><div><b>⌕</b><input name="url" placeholder="tusitio.com" required disabled={auditing}/><button disabled={auditing}>{auditing?"Analizando…":"Analizar sitio →"}</button></div><small>Análisis técnico · Historial privado · Resultados persistentes</small></form></section>
    {error&&<div className="error"><strong>No pudimos completar la solicitud</strong><p>{error}</p></div>}
    {auditing&&<div className="progress"><i/><div><strong>Visitando y examinando el sitio…</strong><p>Revisamos HTML, metadatos, enlaces, imágenes, cabeceras, robots.txt y sitemap.xml.</p></div></div>}
    {!auditing&&selected&&<AuditResult audit={selected} onDelete={()=>onDelete(selected)}/>}
    {!auditing&&!selected&&!loading&&<div className="empty"><b>◎</b><h2>Tu primera auditoría empieza aquí</h2><p>Pega arriba una página real. Este espacio se llenará únicamente con resultados obtenidos desde ese sitio.</p><div><span>SEO técnico</span><span>Seguridad</span><span>Accesibilidad</span><span>Rendimiento</span></div></div>}
    {audits.length>0&&<section className="history"><div><span className="eyebrow">HISTORIAL</span><h2>Auditorías recientes</h2></div><div className="history-grid">{audits.map(item=><button className={selected?.id===item.id?"active":""} key={item.id} onClick={()=>onSelect(item)}><b className={tone(item.overall_score)}>{item.overall_score}</b><span><strong>{item.hostname}</strong><small>{age(item.created_at)} · HTTP {item.status_code}</small></span><em>Ver →</em></button>)}</div></section>}
  </div>
}

function AuditResult({audit,onDelete}:{audit:Audit;onDelete:()=>void}){const r=audit.report;return <section className="result">
  <div className="result-title"><div><span className="eyebrow">INFORME TÉCNICO</span><h2>{r.page.title||audit.hostname}</h2><a href={audit.final_url} target="_blank" rel="noreferrer">{audit.final_url} ↗</a><p>Analizado {new Date(audit.created_at).toLocaleString("es-CL")}</p></div><button onClick={onDelete}>Eliminar</button></div>
  <div className="scores"><div className={`overall ${tone(audit.overall_score)}`} style={{"--score":`${audit.overall_score*3.6}deg`} as never}><b>{audit.overall_score}<small>/100</small></b><span>Puntaje general</span></div><div className="score-list"><Score name="Rendimiento" value={audit.performance_score}/><Score name="SEO" value={audit.seo_score}/><Score name="Accesibilidad" value={audit.accessibility_score}/><Score name="Seguridad" value={audit.security_score}/></div></div>
  <div className="facts"><Fact name="Respuesta HTTP" value={String(audit.status_code)} detail={audit.status_code<400?"Página accesible":"Requiere atención"}/><Fact name="Tiempo del servidor" value={`${Math.round(audit.latency_ms)} ms`} detail={audit.latency_ms<=800?"Respuesta rápida":"Puede mejorar"}/><Fact name="Peso del HTML" value={bytes(audit.size_bytes)} detail={r.http.compressed?"Con compresión":"Sin compresión detectada"}/><Fact name="Redirecciones" value={String(r.http.redirects.length)} detail={r.http.redirects.length<=1?"Ruta directa":"Cadena mejorable"}/></div>
  <div className="report-grid"><Card number="01" title="Qué mejorar primero" subtitle="Ordenado por impacto"><div className="recommendations">{r.recommendations.length?r.recommendations.map((item,index)=><article key={index}><b className={item.severity}>{item.severity}</b><div><small>{item.category}</small><h4>{item.title}</h4><p>{item.detail}</p></div></article>):<div className="all-good">✓ No detectamos mejoras urgentes.</div>}</div></Card>
  <Card number="02" title="SEO y contenido" subtitle="Señales para buscadores"><dl><Detail name="Título" value={r.page.title||"No encontrado"} ok={!!r.page.title}/><Detail name="Descripción" value={r.page.description||"No encontrada"} ok={!!r.page.description}/><Detail name="H1 principal" value={`${r.page.h1Count} detectado(s)`} ok={r.page.h1Count===1}/><Detail name="Idioma" value={r.page.language||"No declarado"} ok={!!r.page.language}/><Detail name="URL canónica" value={r.page.canonical||"No declarada"} ok={!!r.page.canonical}/><Detail name="robots.txt" value={r.seo.robotsTxt?"Disponible":"No encontrado"} ok={r.seo.robotsTxt}/><Detail name="sitemap.xml" value={r.seo.sitemapXml?"Disponible":"No encontrado"} ok={r.seo.sitemapXml}/></dl></Card>
  <Card number="03" title="Seguridad HTTP" subtitle="Protecciones del servidor"><div className="security"><b className={r.security.https?"ok":"bad"}>{r.security.https?"✓ HTTPS activo":"× Sin HTTPS"}</b><p>{r.security.presentHeaders.length} de {r.security.presentHeaders.length+r.security.missingHeaders.length} cabeceras recomendadas presentes</p><strong>Presentes</strong><div>{r.security.presentHeaders.map(x=><span className="ok" key={x}>✓ {x}</span>)}</div><strong>Ausentes</strong><div>{r.security.missingHeaders.map(x=><span key={x}>– {x}</span>)}</div></div></Card>
  <Card number="04" title="Estructura y tecnología" subtitle="Señales del HTML público"><div className="structure"><div><b>{r.content.images}</b><span>Imágenes</span><small>{r.content.imagesWithAlt} con texto alternativo</small></div><div><b>{r.content.internalLinks}</b><span>Enlaces internos</span><small>{r.content.externalLinks} externos</small></div><strong>Tecnologías detectadas</strong><p>{r.technologies.length?r.technologies.map(x=><em key={x}>{x}</em>):"Sin firmas concluyentes"}</p></div></Card></div><p className="scope">ⓘ {r.scope}</p>
  </section>}
function Score({name,value}:{name:string;value:number}){return <article><span>{name}</span><b>{value}<small>/100</small></b><div><i className={tone(value)} style={{width:`${value}%`}}/></div></article>}
function Fact({name,value,detail}:{name:string;value:string;detail:string}){return <article><small>{name}</small><b>{value}</b><span>{detail}</span></article>}
function Card({number,title,subtitle,children}:{number:string;title:string;subtitle:string;children:ReactNode}){return <section className="card"><header><b>{number}</b><div><h3>{title}</h3><p>{subtitle}</p></div></header>{children}</section>}
function Detail({name,value,ok}:{name:string;value:string;ok:boolean}){return <div><dt>{name}</dt><dd title={value}><b className={ok?"ok":"bad"}>{ok?"✓":"!"}</b>{value}</dd></div>}

function MonitorPage({monitors,checks,overview,onCreate,onAction}:{monitors:Monitor[];checks:Check[];overview:Overview|null;onCreate:()=>void;onAction:(m:Monitor,a:"check"|"toggle"|"delete")=>void}){return <div className="page operations"><div className="operation-title"><div><span className="eyebrow">OPERACIÓN CONTINUA</span><h1>Monitoreo HTTP</h1><p>Comprueba periódicamente que tus sitios y APIs sigan respondiendo.</p></div><button onClick={onCreate}>＋ Crear monitor</button></div><div className="facts metrics"><Fact name="Disponibilidad" value={overview?.availabilityPercent==null?"Sin datos":`${overview.availabilityPercent.toFixed(1)}%`} detail={`${overview?.totalChecks||0} comprobaciones`}/><Fact name="Latencia media" value={overview?.averageLatencyMs==null?"Sin datos":`${Math.round(overview.averageLatencyMs)} ms`} detail="Respuestas registradas"/><Fact name="Monitores activos" value={String(overview?.activeMonitors||0)} detail={`${monitors.length} configurados`}/><Fact name="Incidentes abiertos" value={String(overview?.openIncidents||0)} detail="Fallos consecutivos"/></div><section className="data"><header><h2>Servicios observados</h2><span>{monitors.length}/10 monitores</span></header><div className="table"><table><thead><tr><th>Servicio</th><th>Estado</th><th>Disponibilidad reciente</th><th>Latencia</th><th>Última revisión</th><th/></tr></thead><tbody>{!monitors.length&&<tr><td colSpan={6}><div className="table-empty"><b>No hay monitores todavía</b><p>La auditoría examina una web una vez; un monitor vigila su disponibilidad.</p><button onClick={onCreate}>Crear el primero</button></div></td></tr>}{monitors.map(m=>{const own=checks.filter(c=>c.monitor_id===m.id);const healthy=own.filter(c=>c.status==="operational"||c.status==="degraded").length;return <tr key={m.id}><td><div className="service"><b>{m.name[0]}</b><span><strong>{m.name}</strong><small>{m.url}</small></span></div></td><td><span className={`status ${m.status}`}>● {statuses[m.status]}</span></td><td>{own.length?`${(healthy/own.length*100).toFixed(1)}%`:"—"}</td><td>{m.last_latency_ms?`${Math.round(m.last_latency_ms)} ms`:"—"}</td><td>{age(m.last_checked_at)}</td><td><div className="actions"><button disabled={!m.is_active} onClick={()=>onAction(m,"check")}>Revisar</button><button onClick={()=>onAction(m,"toggle")}>{m.is_active?"Pausar":"Activar"}</button><button onClick={()=>onAction(m,"delete")}>Eliminar</button></div></td></tr>})}</tbody></table></div></section></div>}

function IncidentPage({incidents}:{incidents:Incident[]}){return <div className="page operations"><div className="operation-title"><div><span className="eyebrow">HISTORIAL OPERATIVO</span><h1>Incidentes</h1><p>Fallos reales detectados por los monitores.</p></div></div><section className="data"><header><h2>Registro</h2><span>{incidents.filter(i=>i.status==="open").length} abiertos</span></header>{!incidents.length?<div className="incident-empty"><b>✓</b><h3>No hay incidentes registrados</h3><p>Esta lista seguirá vacía hasta que un monitor acumule fallos reales.</p></div>:<div className="timeline">{incidents.map(i=><article key={i.id}><time>{new Date(i.started_at).toLocaleString("es-CL")}</time><div><span className={i.status}>{i.status}</span><h3>{i.title}</h3><p>{i.monitor_name} · {i.cause||"Sin causa informada"}</p>{i.resolved_at&&<small>Recuperado {age(i.resolved_at)}</small>}</div></article>)}</div>}</section></div>}

function AccountPage({session}:{session:Session}) {
  const [notice,setNotice]=useState(""); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
  const currentName=String(session.user.user_metadata.full_name||"");
  async function updateProfile(event:FormEvent<HTMLFormElement>){event.preventDefault();const name=String(new FormData(event.currentTarget).get("name")||"").trim();setBusy(true);setError("");const {error:authError}=await supabase.auth.updateUser({data:{full_name:name}});setBusy(false);if(authError)setError(authMessage(authError.message));else setNotice("Perfil actualizado.");}
  async function updatePassword(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget,data=new FormData(form),current=String(data.get("current")||""),password=String(data.get("password")||""),confirmation=String(data.get("confirmation")||"");setError("");setNotice("");if(password.length<8){setError("La contraseña debe tener al menos 8 caracteres.");return}if(password!==confirmation){setError("Las contraseñas no coinciden.");return}setBusy(true);const {error:authError}=await supabase.auth.updateUser({password,current_password:current});setBusy(false);if(authError)setError(authMessage(authError.message));else{setNotice("Contraseña actualizada.");form.reset();}}
  return <div className="page account-page"><div className="operation-title"><div><span className="eyebrow">ESPACIO PERSONAL</span><h1>Mi cuenta</h1><p>Administra tu identidad y la seguridad de tu acceso.</p></div><button className="signout" onClick={()=>void supabase.auth.signOut()}>Cerrar sesión</button></div>{notice&&<div className="account-notice">{notice}</div>}{error&&<div className="auth-error account-error">{error}</div>}<div className="account-grid"><section><header><h2>Perfil</h2><p>Información visible dentro de tu espacio.</p></header><form onSubmit={updateProfile}><label>Nombre<input name="name" defaultValue={currentName} required/></label><label>Correo electrónico<input value={session.user.email||""} disabled/></label><button disabled={busy}>Guardar perfil</button></form></section><section><header><h2>Seguridad</h2><p>Cambia tu contraseña de acceso.</p></header><form onSubmit={updatePassword}><label>Contraseña actual<input name="current" type="password" autoComplete="current-password" required/></label><label>Nueva contraseña<input name="password" type="password" autoComplete="new-password" minLength={8} required/></label><label>Confirmar contraseña<input name="confirmation" type="password" autoComplete="new-password" minLength={8} required/></label><button disabled={busy}>Actualizar contraseña</button></form></section></div><section className="privacy-card"><b>Datos privados por cuenta</b><p>Las auditorías, monitores, comprobaciones e incidentes se consultan usando tu identidad. Otras cuentas no pueden ver ni modificar este espacio.</p></section></div>;
}
function Modal({children,onClose}:{children:ReactNode;onClose:()=>void}){return <div className="modal-bg" onMouseDown={onClose}><section className="modal" onMouseDown={e=>e.stopPropagation()}><button className="close" onClick={onClose}>×</button>{children}</section></div>}
