import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDown,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Download,
  FileImage,
  ImagePlus,
  LoaderCircle,
  LogOut,
  Plus,
  RefreshCw,
  Scissors,
  ShieldCheck,
  Sparkles,
  Type,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import "./style.css";

const API_ROOT = "/api";
const TOKEN_KEY = "image-service-token";
const USER_KEY = "image-service-email";
const JOBS_KEY = "image-service-jobs";

type ApiError = Error & { status?: number };
type User = { id: string; email: string };
type AuthResponse = { access_token: string; user: User };
type ImageAsset = {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  width: number;
  height: number;
  created_at: string;
  original_url: string;
};
type ImagePage = { items: ImageAsset[]; page: number; limit: number; total: number };
type Job = {
  id: string;
  image_id: string;
  status: "queued" | "processing" | "succeeded" | "failed";
  attempt_count: number;
  max_attempts: number;
  error_code?: string | null;
  error_message?: string | null;
  status_url: string;
  result_url?: string | null;
  created_at?: string;
};
type OperationType = "resize" | "crop" | "watermark" | "format";
type Operation = {
  key: string;
  type: OperationType;
  width?: number;
  height?: number;
  x?: number;
  y?: number;
  text?: string;
  position?: string;
  format?: string;
};

async function api<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `La solicitud falló (${response.status}).`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch {
      // Keep the concise fallback for non-JSON server responses.
    }
    const error = new Error(message) as ApiError;
    error.status = response.status;
    throw error;
  }
  return response.json() as Promise<T>;
}

async function protectedBlob(path: string, token: string): Promise<string> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("No pudimos abrir esta imagen.");
  return URL.createObjectURL(await response.blob());
}

function ProtectedImage({
  path,
  token,
  alt,
  className,
}: {
  path: string;
  token: string;
  alt: string;
  className?: string;
}) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let active = true;
    let objectUrl = "";
    protectedBlob(path, token)
      .then((createdUrl) => {
        objectUrl = createdUrl;
        if (active) setUrl(createdUrl);
        else URL.revokeObjectURL(createdUrl);
      })
      .catch(() => setUrl(""));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path, token]);

  return url ? (
    <img className={className} src={url} alt={alt} />
  ) : (
    <div className={`${className ?? ""} image-loading`} aria-label="Cargando imagen">
      <LoaderCircle size={18} className="spin" />
    </div>
  );
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string, user: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await api<AuthResponse>(`/auth/${mode}`, undefined, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      onAuthenticated(result.access_token, result.user);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No fue posible iniciar sesión.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-story">
        <Brand />
        <div className="auth-message">
          <span className="eyebrow"><span className="eyebrow-line" /> PROCESAMIENTO EN SEGUNDO PLANO</span>
          <h1>Una imagen entra.<br /><em>Otra versión sale.</em></h1>
          <p>Sube un original, combina transformaciones y deja el trabajo pesado en manos de un worker.</p>
          <div className="auth-flow">
            <FlowStep number="01" title="Carga" caption="Tu original queda guardado" />
            <ArrowRight size={16} />
            <FlowStep number="02" title="Cola" caption="Un worker toma el trabajo" />
            <ArrowRight size={16} />
            <FlowStep number="03" title="Resultado" caption="Descarga cuando termine" />
          </div>
        </div>
        <p className="auth-footnote">UN PROYECTO DE PORTAFOLIO · FASTAPI / SQL SERVER</p>
      </section>

      <section className="auth-side">
        <div className="auth-topline"><span>ESPACIO DE TRABAJO</span><span>LOCAL · 01</span></div>
        <div className="auth-card">
          <div className="auth-card-icon"><FileImage size={21} strokeWidth={1.7} /></div>
          <span className="eyebrow">TU MESA DE TRABAJO</span>
          <h2>{mode === "register" ? "Empieza por aquí." : "Qué bueno verte."}</h2>
          <p className="muted">{mode === "register" ? "Crea una cuenta para guardar tus imágenes y trabajos." : "Inicia sesión para abrir tu biblioteca."}</p>

          <div className="auth-tabs" role="tablist" aria-label="Acceso">
            <button type="button" role="tab" aria-selected={mode === "register"} className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(""); }}>Crear cuenta</button>
            <button type="button" role="tab" aria-selected={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}>Iniciar sesión</button>
          </div>

          <form className="auth-form" onSubmit={submit}>
            <label htmlFor="email">Correo electrónico</label>
            <input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="hola@ejemplo.com" />
            <div className="label-row"><label htmlFor="password">Contraseña</label>{mode === "register" && <span>Mínimo 8 caracteres</span>}</div>
            <input id="password" type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} minLength={mode === "register" ? 8 : 1} required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••••" />
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button button-primary auth-submit" type="submit" disabled={busy}>
              {busy ? <LoaderCircle size={17} className="spin" /> : mode === "register" ? "Crear mi espacio" : "Entrar a mi espacio"}
              {!busy && <ArrowRight size={16} />}
            </button>
          </form>
          <div className="privacy-note"><ShieldCheck size={15} /><span>Tus imágenes son privadas y solo tú puedes consultarlas.</span></div>
        </div>
        <div className="auth-footer"><span>Una herramienta pequeña para un flujo que sí importa.</span><CircleHelp size={15} /></div>
      </section>
    </main>
  );
}

function Brand() {
  return <a className="brand" href="#inicio" aria-label="Imagen por imagen, inicio"><span className="brand-mark"><span /><span /><span /><span /></span><span>imagen por imagen<span className="brand-dot">.</span></span></a>;
}

function FlowStep({ number, title, caption }: { number: string; title: string; caption: string }) {
  return <div className="flow-step"><span>{number}</span><strong>{title}</strong><small>{caption}</small></div>;
}

function makeOperation(type: OperationType, image?: ImageAsset): Operation {
  const key = crypto.randomUUID();
  if (type === "resize") return { key, type, width: 1200, height: 1200 };
  if (type === "crop") return { key, type, x: 0, y: 0, width: Math.min(image?.width ?? 800, 800), height: Math.min(image?.height ?? 800, 800) };
  if (type === "watermark") return { key, type, text: "Mi marca", position: "bottom-right" };
  return { key, type, format: "webp" };
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) ?? "");
  const [email, setEmail] = useState(() => sessionStorage.getItem(USER_KEY) ?? "");
  const [images, setImages] = useState<ImageAsset[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState("");
  const [operations, setOperations] = useState<Operation[]>([]);
  const [jobs, setJobs] = useState<Job[]>(() => {
    try { return JSON.parse(sessionStorage.getItem(JOBS_KEY) ?? "[]") as Job[]; }
    catch { return []; }
  });
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [adding, setAdding] = useState(false);
  const activeImage = images.find((image) => image.id === selected) ?? null;
  const activeIds = useMemo(() => jobs.filter((job) => job.status === "queued" || job.status === "processing").map((job) => job.id).join(","), [jobs]);

  const refreshImages = useCallback(async (currentPage = page) => {
    if (!token) return;
    setLoading(true);
    try {
      const result = await api<ImagePage>(`/images?page=${currentPage}&limit=8`, token);
      setImages(result.items);
      setTotal(result.total);
      if (!result.items.some((image) => image.id === selected)) setSelected(result.items[0]?.id ?? "");
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "No pudimos cargar tus imágenes.");
    } finally {
      setLoading(false);
    }
  }, [page, selected, token]);

  useEffect(() => { if (token) void refreshImages(page); }, [page, token]);

  useEffect(() => {
    if (!token || !activeIds) return;
    const timer = window.setInterval(async () => {
      const currentJobs = jobs.filter((job) => job.status === "queued" || job.status === "processing");
      const updates = await Promise.all(currentJobs.map(async (job) => {
        try { return await api<Job>(`/jobs/${job.id}`, token); }
        catch { return job; }
      }));
      setJobs((previous) => {
        const byId = new Map(updates.map((job) => [job.id, job]));
        const next = previous.map((job) => byId.get(job.id) ?? job);
        sessionStorage.setItem(JOBS_KEY, JSON.stringify(next));
        return next;
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeIds, jobs, token]);

  function authenticated(nextToken: string, user: User) {
    sessionStorage.setItem(TOKEN_KEY, nextToken);
    sessionStorage.setItem(USER_KEY, user.email);
    setToken(nextToken);
    setEmail(user.email);
  }

  function signOut() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(JOBS_KEY);
    setToken(""); setEmail(""); setImages([]); setSelected(""); setJobs([]);
  }

  async function uploadFiles(file?: File) {
    if (!file || !token) return;
    setNotice("");
    if (!file.type.startsWith("image/")) { setNotice("Elige un archivo de imagen JPEG, PNG o WebP."); return; }
    const form = new FormData();
    form.append("file", file);
    setUploading(true);
    try {
      const image = await api<ImageAsset>("/images", token, { method: "POST", body: form });
      setPage(1);
      await refreshImages(1);
      setSelected(image.id);
      setOperations([]);
      setNotice("Original guardado. Ya puedes preparar una transformación.");
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "No pudimos guardar esa imagen.");
    } finally {
      setUploading(false);
    }
  }

  async function startJob() {
    if (!activeImage || operations.length === 0 || !token) return;
    setNotice("");
    setLoading(true);
    try {
      const payload = operations.map(({ key: _key, ...operation }) => operation);
      const job = await api<Job>(`/images/${activeImage.id}/transform`, token, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ operations: payload }),
      });
      const next = [job, ...jobs.filter((existing) => existing.id !== job.id)];
      setJobs(next);
      sessionStorage.setItem(JOBS_KEY, JSON.stringify(next));
      setNotice("Trabajo enviado. Puedes seguir preparando imágenes mientras se procesa.");
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "No se pudo crear el trabajo.");
    } finally {
      setLoading(false);
    }
  }

  function addOperation(type: OperationType) {
    setOperations((current) => [...current, makeOperation(type, activeImage ?? undefined)]);
    setAdding(false);
  }

  function updateOperation(key: string, field: string, value: string) {
    setOperations((current) => current.map((operation) => operation.key === key
      ? { ...operation, [field]: ["width", "height", "x", "y"].includes(field) ? Number(value) : value }
      : operation));
  }

  function moveOperation(index: number, direction: -1 | 1) {
    setOperations((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.length) return current;
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
  }

  if (!token) return <AuthScreen onAuthenticated={authenticated} />;

  const pageCount = Math.max(1, Math.ceil(total / 8));
  return (
    <div className="app-shell" id="inicio">
      <header className="topbar">
        <Brand />
        <nav className="top-nav" aria-label="Navegación principal"><a className="current" href="#biblioteca">Biblioteca</a><a href="#trabajos">Trabajos</a><a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">API <ArrowDownRight size={13} /></a></nav>
        <div className="user-menu"><span className="user-avatar">{email.slice(0, 1).toUpperCase() || "U"}</span><span className="user-email">{email}</span><button className="icon-button" type="button" onClick={signOut} aria-label="Cerrar sesión" title="Cerrar sesión"><LogOut size={16} /></button></div>
      </header>

      <main className="dashboard">
        <section className="welcome-row">
          <div>
            <div className="breadcrumb"><span>ESPACIO DE TRABAJO</span><span className="breadcrumb-sep">/</span><span>BIBLIOTECA</span></div>
            <h1>Buenas, <em>{email.split("@")[0] || "creador"}.</em></h1>
            <p className="welcome-caption">Tu mesa está lista. ¿Qué quieres cambiar hoy?</p>
          </div>
          <div className="welcome-stats"><div><strong>{total.toString().padStart(2, "0")}</strong><span>ORIGINALES</span></div><i /><div><strong>{jobs.filter((job) => job.status === "queued" || job.status === "processing").length.toString().padStart(2, "0")}</strong><span>EN COLA</span></div></div>
        </section>

        <section className="upload-strip" aria-label="Subir una imagen">
          <div className="upload-icon"><ImagePlus size={19} /></div>
          <div className="upload-copy"><strong>Empieza con un original</strong><span>JPEG, PNG o WebP · máximo 20 MB</span></div>
          <label className="button button-outline upload-button" htmlFor="file-upload">{uploading ? <LoaderCircle size={16} className="spin" /> : <Upload size={16} />}{uploading ? "Guardando" : "Subir imagen"}<input id="file-upload" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { void uploadFiles(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>
          <span className="upload-note"><ShieldCheck size={14} /> Privado por cuenta</span>
        </section>

        {notice && <div className="notice" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice("")} aria-label="Cerrar mensaje"><X size={15} /></button></div>}

        <div className="workbench-grid">
          <section className="panel library-panel" id="biblioteca">
            <div className="panel-head"><div><div className="section-kicker"><span className="green-dot" /> ARCHIVO PERSONAL</div><h2>Tu biblioteca</h2></div><button className="subtle-button" type="button" onClick={() => void refreshImages(page)} disabled={loading}><RefreshCw size={14} className={loading ? "spin" : ""} /> Actualizar</button></div>
            {images.length === 0 ? (
              <div className={`empty-library ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void uploadFiles(event.dataTransfer.files[0]); }}>
                <div className="empty-art"><div className="art-sun" /><div className="art-hill hill-back" /><div className="art-hill hill-front" /><div className="art-frame"><ImagePlus size={21} /></div></div>
                <h3>Tu primera imagen empieza aquí</h3><p>Arrastra un archivo a este espacio o usa el botón de arriba. El original se conserva sin cambios.</p>
                <label className="button button-dark" htmlFor="file-upload">Elegir imagen <ArrowRight size={15} /></label>
              </div>
            ) : (
              <>
                <div className="image-grid">
                  {images.map((image, index) => <button key={image.id} type="button" className={`image-card ${selected === image.id ? "selected" : ""}`} onClick={() => { setSelected(image.id); setOperations([]); }} aria-pressed={selected === image.id}>
                    <div className={`image-preview tile-tone-${index % 4}`}><ProtectedImage path={image.original_url} token={token} alt={image.original_name} /><span className="tile-check"><Check size={13} /></span></div>
                    <span className="image-meta"><strong title={image.original_name}>{image.original_name}</strong><small>{image.width} × {image.height} · {formatBytes(image.size_bytes)}</small></span>
                  </button>)}
                </div>
                <div className="library-footer"><span>{total} {total === 1 ? "original" : "originales"} guardados</span><div className="pagination"><button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page <= 1} aria-label="Página anterior"><ArrowLeft size={15} /></button><span>{page} / {pageCount}</span><button type="button" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page >= pageCount} aria-label="Página siguiente"><ArrowRight size={15} /></button></div></div>
              </>
            )}
          </section>

          <section className="panel recipe-panel" aria-labelledby="recipe-title">
            <div className="panel-head recipe-head"><div><div className="section-kicker"><span className="orange-dot" /> ESTUDIO DE TRANSFORMACIÓN</div><h2 id="recipe-title">Arma tu receta</h2></div><span className="recipe-number">01—04</span></div>
            {activeImage ? (
              <>
                <div className="selected-image"><ProtectedImage path={activeImage.original_url} token={token} alt={activeImage.original_name} /><div><span>IMAGEN SELECCIONADA</span><strong>{activeImage.original_name}</strong><small>{activeImage.width} × {activeImage.height} px</small></div><span className="selected-mark"><Check size={14} /></span></div>
                <div className="operations-title"><span>SECUENCIA</span><span>{operations.length} {operations.length === 1 ? "paso" : "pasos"}</span></div>
                {operations.length ? <div className="operation-list">{operations.map((operation, index) => <OperationCard key={operation.key} operation={operation} index={index} count={operations.length} onChange={updateOperation} onRemove={() => setOperations((current) => current.filter((item) => item.key !== operation.key))} onMove={moveOperation} />)}</div> : <div className="recipe-empty"><div className="recipe-empty-icon"><Sparkles size={18} /></div><div><strong>Tu secuencia está vacía</strong><span>Agrega una o más acciones. Se aplican en el orden que ves.</span></div></div>}
                <div className="add-operation-wrap">
                  <button className="add-operation" type="button" onClick={() => setAdding((open) => !open)} aria-expanded={adding}><Plus size={16} /> Agregar transformación <ChevronDown size={15} className={adding ? "rotate" : ""} /></button>
                  {adding && <div className="operation-menu">
                    <OperationChoice icon={<ArrowDownRight size={16} />} title="Escala" detail="Ajusta el tamaño máximo" onClick={() => addOperation("resize")} />
                    <OperationChoice icon={<Scissors size={16} />} title="Recorte" detail="Conserva una región de la imagen" onClick={() => addOperation("crop")} />
                    <OperationChoice icon={<Type size={16} />} title="Marca de agua" detail="Añade texto sobre la imagen" onClick={() => addOperation("watermark")} />
                    <OperationChoice icon={<FileImage size={16} />} title="Formato" detail="JPEG, PNG o WebP" onClick={() => addOperation("format")} />
                  </div>}
                </div>
                <button className="button button-primary run-button" type="button" disabled={!operations.length || loading} onClick={() => void startJob()}>{loading ? <LoaderCircle size={16} className="spin" /> : <WandSparkles size={16} />} Enviar a procesar <ArrowRight size={15} /></button>
                <p className="async-note"><Clock3 size={13} /> Se añade a la cola. Puedes seguir trabajando mientras se procesa.</p>
              </>
            ) : <div className="select-prompt"><div><ArrowUp size={20} /></div><strong>Primero elige una imagen</strong><span>Selecciona un original de tu biblioteca para diseñar la secuencia.</span></div>}
          </section>
        </div>

        <section className="panel jobs-panel" id="trabajos">
          <div className="panel-head jobs-head"><div><div className="section-kicker"><span className="blue-dot" /> COLA DE PROCESAMIENTO</div><h2>Trabajos recientes</h2></div><div className="queue-legend"><span><i className="legend-dot is-queued" /> En cola</span><span><i className="legend-dot is-processing" /> Procesando</span><span><i className="legend-dot is-done" /> Listo</span></div></div>
          {jobs.length === 0 ? <div className="jobs-empty"><div className="queue-icon"><Clock3 size={18} /></div><div><strong>Aún no hay trabajos</strong><span>Cuando envíes una receta, su progreso aparecerá aquí.</span></div><span className="quiet-tag">ESPERANDO</span></div> : <div className="job-list">{jobs.slice(0, 8).map((job) => <JobRow key={job.id} job={job} image={images.find((image) => image.id === job.image_id)} token={token} />)}</div>}
          <div className="durable-note"><span className="durable-mark"><ShieldCheck size={14} /></span><span>La cola vive en SQL Server. Si el worker se interrumpe, una reserva vencida permite recuperar el trabajo.</span><a href="http://localhost:8000/docs#/trabajos" target="_blank" rel="noreferrer">Ver API <ArrowRight size={12} /></a></div>
        </section>

        <footer className="site-footer"><Brand /><span>Originales intactos. Resultados listos cuando tú quieras.</span><span>FASTAPI · REACT · SQL SERVER</span></footer>
      </main>
    </div>
  );
}

function OperationChoice({ icon, title, detail, onClick }: { icon: ReactNode; title: string; detail: string; onClick: () => void }) {
  return <button type="button" className="operation-choice" onClick={onClick}><span className="choice-icon">{icon}</span><span><strong>{title}</strong><small>{detail}</small></span><Plus size={15} className="choice-plus" /></button>;
}

function OperationCard({ operation, index, count, onChange, onRemove, onMove }: {
  operation: Operation; index: number; count: number; onChange: (key: string, field: string, value: string) => void;
  onRemove: () => void; onMove: (index: number, direction: -1 | 1) => void;
}) {
  const titles = { resize: "Escala", crop: "Recorte", watermark: "Marca de agua", format: "Formato" };
  const icons = { resize: <ArrowDownRight size={15} />, crop: <Scissors size={15} />, watermark: <Type size={15} />, format: <FileImage size={15} /> };
  return <article className="operation-card">
    <div className="operation-card-top"><span className="operation-index">{String(index + 1).padStart(2, "0")}</span><span className="operation-type-icon">{icons[operation.type]}</span><strong>{titles[operation.type]}</strong><div className="operation-controls"><button type="button" aria-label="Mover arriba" disabled={index === 0} onClick={() => onMove(index, -1)}><ArrowUp size={13} /></button><button type="button" aria-label="Mover abajo" disabled={index === count - 1} onClick={() => onMove(index, 1)}><ArrowDown size={13} /></button><button type="button" aria-label="Quitar transformación" onClick={onRemove}><X size={14} /></button></div></div>
    <div className="operation-fields">
      {operation.type === "resize" && <><NumberField label="Ancho máx." value={operation.width ?? 1200} onChange={(value) => onChange(operation.key, "width", value)} /><span className="field-times">×</span><NumberField label="Alto máx." value={operation.height ?? 1200} onChange={(value) => onChange(operation.key, "height", value)} /></>}
      {operation.type === "crop" && <><NumberField label="X" value={operation.x ?? 0} onChange={(value) => onChange(operation.key, "x", value)} /><NumberField label="Y" value={operation.y ?? 0} onChange={(value) => onChange(operation.key, "y", value)} /><NumberField label="Ancho" value={operation.width ?? 800} onChange={(value) => onChange(operation.key, "width", value)} /><NumberField label="Alto" value={operation.height ?? 800} onChange={(value) => onChange(operation.key, "height", value)} /></>}
      {operation.type === "watermark" && <><label className="field-text"><span>Texto</span><input value={operation.text ?? ""} maxLength={80} onChange={(event) => onChange(operation.key, "text", event.target.value)} /></label><label className="field-text"><span>Posición</span><select value={operation.position ?? "bottom-right"} onChange={(event) => onChange(operation.key, "position", event.target.value)}><option value="bottom-right">Abajo · derecha</option><option value="bottom-left">Abajo · izquierda</option><option value="top-right">Arriba · derecha</option><option value="top-left">Arriba · izquierda</option><option value="center">Centro</option></select></label></>}
      {operation.type === "format" && <label className="field-text format-select"><span>Formato de salida</span><select value={operation.format ?? "webp"} onChange={(event) => onChange(operation.key, "format", event.target.value)}><option value="webp">WebP · ligero</option><option value="jpeg">JPEG · compatible</option><option value="png">PNG · sin pérdida</option></select></label>}
    </div>
  </article>;
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: string) => void }) {
  return <label className="field-number"><span>{label}</span><input type="number" min={label === "X" || label === "Y" ? 0 : 1} max={8000} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function JobRow({ job, image, token }: { job: Job; image?: ImageAsset; token: string }) {
  const statuses = { queued: "En cola", processing: "Procesando", succeeded: "Completado", failed: "Falló" };
  const statusIcons = { queued: <Clock3 size={14} />, processing: <LoaderCircle size={14} className="spin" />, succeeded: <Check size={14} />, failed: <X size={14} /> };
  return <article className="job-row">
    <div className={`job-thumb ${job.status}`}>
      {job.status === "succeeded" && job.result_url ? <ProtectedImage path={job.result_url} token={token} alt="Resultado de imagen" /> : image ? <ProtectedImage path={image.original_url} token={token} alt={image.original_name} /> : <FileImage size={18} />}
    </div>
    <div className="job-main"><strong>{image?.original_name ?? "Transformación de imagen"}</strong><span>Trabajo <code>{job.id.slice(0, 8)}</code> · intento {Math.max(job.attempt_count, 1)} de {job.max_attempts}</span>{job.status === "failed" && <small className="job-error">{job.error_message ?? "No se pudo completar la transformación."}</small>}</div>
    <div className={`job-status status-${job.status}`}>{statusIcons[job.status]}<span>{statuses[job.status]}</span></div>
    {job.status === "succeeded" && job.result_url ? <a className="download-link" href={`/api${job.result_url}`} onClick={(event) => { event.preventDefault(); void downloadResult(job.result_url! , token); }}><Download size={14} /> Descargar</a> : <span className="job-time">{job.status === "queued" ? "Esperando turno" : job.status === "processing" ? "Worker activo" : "Trabajo finalizado"}</span>}
  </article>;
}

async function downloadResult(path: string, token: string) {
  try {
    const url = await protectedBlob(path, token);
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = path.split("/").at(-1) ?? "resultado"; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch { window.alert("No pudimos descargar el resultado."); }
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

createRoot(document.getElementById("root")!).render(<App />);
