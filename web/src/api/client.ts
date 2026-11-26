// Capa de acceso al backend local. Cada pantalla llama solo a `api.*`.
import type {
  Agenda,
  Analisis,
  Caso,
  CasoResumen,
  Control,
  Denuncia,
  DenunciaPublica,
  Ejecutivo,
  EntradaBitacora,
  Fuente,
  Grafo,
  Inteligencia,
  ListaAnalisis,
  PaginaAnomalias,
  PuntoSerie,
  Riesgo,
  Rol,
  Sesion,
  Tendencia,
  Verificacion,
} from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'
const CLAVE_TOKEN = 'sentinel.token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let token: string | null = (() => {
  try {
    return sessionStorage.getItem(CLAVE_TOKEN)
  } catch {
    return null
  }
})()
let alVencer: (() => void) | null = null

export function fijarToken(t: string | null) {
  token = t
  try {
    if (t) sessionStorage.setItem(CLAVE_TOKEN, t)
    else sessionStorage.removeItem(CLAVE_TOKEN)
  } catch {
    /* almacenamiento no disponible: la sesión vive solo en memoria */
  }
}
export const hayToken = () => Boolean(token)
export function onSesionVencida(fn: () => void) {
  alVencer = fn
}

async function crudo(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(BASE + path, { ...init, headers })
  } catch {
    throw new ApiError(0, 'No se pudo contactar al servidor local. Comprueba que el backend esté encendido.')
  }
  if (!res.ok) {
    const texto = await res.text().catch(() => '')
    if (res.status === 401 && token && !path.startsWith('/acceso/ingresar')) alVencer?.()
    throw new ApiError(res.status, texto || `El servidor respondió ${res.status}.`)
  }
  return res
}

const get = <T>(path: string) => crudo(path).then((r) => r.json() as Promise<T>)
const post = <T>(path: string, body?: unknown) =>
  crudo(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) }).then(
    (r) => r.json() as Promise<T>,
  )

/** Subida con barra de progreso (fetch no informa el avance de envío). */
function subir<T>(path: string, fd: FormData, onAvance: (fraccion: number) => void): Promise<T> {
  return new Promise((ok, mal) => {
    const x = new XMLHttpRequest()
    x.open('POST', BASE + path)
    if (token) x.setRequestHeader('Authorization', `Bearer ${token}`)
    x.upload.onprogress = (e) => e.lengthComputable && onAvance(e.loaded / e.total)
    x.onload = () => {
      if (x.status >= 200 && x.status < 300) ok(JSON.parse(x.responseText) as T)
      else mal(new ApiError(x.status, x.responseText || `El servidor respondió ${x.status}.`))
    }
    x.onerror = () => mal(new ApiError(0, 'Se cortó la conexión con el servidor local durante la subida.'))
    x.send(fd)
  })
}

async function descargarArchivo(path: string, nombre: string) {
  const r = await crudo(path)
  const url = URL.createObjectURL(await r.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const api = {
  // acceso
  roles: () => get<Rol[]>('/acceso/roles'),
  ingresar: (usuario: string, clave: string) =>
    post<{ token: string; sesion: Sesion }>('/acceso/ingresar', { usuario, clave }),
  yo: () => get<Sesion>('/acceso/yo'),
  salir: () => post<{ ok: boolean }>('/acceso/salir'),

  // cargar datos
  analisis: () => get<ListaAnalisis>('/analisis'),
  analisisUno: (id: string) => get<Analisis>(`/analisis/${encodeURIComponent(id)}`),
  fuentes: () => get<{ carpeta: string; archivos: Fuente[] }>('/analisis/fuentes'),
  desdeCarpeta: (fw: Fuente, med: Fuente, citas: Fuente | null) => {
    const fd = new FormData()
    fd.append('fw_origen', fw.origen)
    fd.append('fw', fw.nombre)
    fd.append('med_origen', med.origen)
    fd.append('med', med.nombre)
    if (citas) {
      fd.append('citas_origen', citas.origen)
      fd.append('citas', citas.nombre)
    }
    return post<Analisis>('/analisis/desde-carpeta', fd)
  },
  subirArchivos: (fw: File, med: File, citas: File | null, onAvance: (f: number) => void) => {
    const fd = new FormData()
    fd.append('firewall', fw)
    fd.append('sistema_medico', med)
    if (citas) fd.append('agendamiento', citas)
    return subir<Analisis>('/analisis/subir', fd, onAvance)
  },
  activar: (id: string) => post<{ ok: boolean }>(`/analisis/${encodeURIComponent(id)}/activar`),

  // estratégico
  ejecutivo: () => get<Ejecutivo>('/ejecutivo'),
  riesgos: () => get<{ riesgos: Riesgo[]; controles: Control[]; analisis: string | null }>('/riesgos'),
  tendencias: () => get<{ nota: string; tendencias: Tendencia[] }>('/threatpulse'),

  // operativo
  casos: () => get<CasoResumen[]>('/casos'),
  caso: (id: string) => get<Caso>(`/casos/${encodeURIComponent(id)}`),
  decidir: (id: string, estado: 'confirmado' | 'descartado', motivo: string) =>
    post<{ estado: string; motivo: string; analista: string; fecha: string }>(`/casos/${encodeURIComponent(id)}/decision`, {
      estado,
      motivo,
    }),
  serie: () => get<PuntoSerie[]>('/serie'),
  anomalias: (fuente: 'firewall' | 'sistema_medico') => get<PaginaAnomalias>(`/anomalias?fuente=${fuente}`),
  grafo: () => get<Grafo>('/grafo'),
  agenda: () => get<Agenda>('/agendamiento'),
  revisarAgenda: (id: string, decision: string, nota: string) =>
    post<{ decision: string; nota: string; analista: string; fecha: string }>(
      `/agendamiento/${encodeURIComponent(id)}/revision`,
      { decision, nota },
    ),
  reidentificar: (seudonimo: string, motivo: string) =>
    post<{ seudonimo: string; nombre: string; registradoEn: string }>('/reidentificar', { seudonimo, motivo }),

  // denuncias
  denunciar: (d: Record<string, unknown>) => post<{ codigo: string; fecha: string }>('/publico/denuncias', d),
  seguimiento: (codigo: string) => get<DenunciaPublica>(`/publico/denuncias/${encodeURIComponent(codigo)}`),
  denuncias: () => get<Denuncia[]>('/denuncias'),
  gestionar: (codigo: string, estado: string, respuesta_publica: string, nota_interna: string) =>
    post<Denuncia>(`/denuncias/${encodeURIComponent(codigo)}/gestion`, { estado, respuesta_publica, nota_interna }),

  // técnico
  inteligencia: () => get<Inteligencia>('/inteligencia'),
  exportar: (tipo: 'stix' | 'misp' | 'sigma') =>
    descargarArchivo(`/exportes/${tipo}`, tipo === 'sigma' ? 'reglas_sigma.zip' : `sentinel_${tipo}.json`),

  // personal de salud
  verificarEnlace: (url: string) => post<Verificacion>('/verificar/enlace', { url }),
  verificarImagen: (archivo: File) => {
    const fd = new FormData()
    fd.append('imagen', archivo)
    return post<Verificacion>('/verificar/imagen', fd)
  },
  reportar: (entrada: string, veredicto: string, comentario: string) =>
    post<{ codigo: string; fecha: string }>('/verificar/reportar', { entrada, veredicto, comentario }),

  // auditoría
  bitacora: () => get<EntradaBitacora[]>('/bitacora'),
}
