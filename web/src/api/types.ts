export type Gravedad = 'critica' | 'alta' | 'media' | 'baja'
export type Permiso =
  | 'estrategico'
  | 'operativo'
  | 'decidir'
  | 'reidentificar'
  | 'cargar_datos'
  | 'tecnico'
  | 'ver_ci'
  | 'ver_denuncias'
  | 'gestionar_denuncias'
  | 'verificar'
  | 'auditar'

export interface Rol {
  rol: string
  nombre: string
  descripcion: string
  permisos: Permiso[]
}

export interface Sesion {
  usuario: string
  nombre: string
  rol: string
  rolNombre: string
  permisos: Permiso[]
  vence: number
}

// ---------- análisis ----------
export interface Paso {
  id: string
  nombre: string
  explicacion: string
  estado: 'pendiente' | 'en_curso' | 'listo' | 'omitido' | 'error'
  datos: Record<string, unknown>
}
export interface ResumenAnalisis {
  registros: number
  minutos: number
  periodo: { desde: string; hasta: string }
}
export interface Analisis {
  id: string
  creado: string
  autor: string
  estado: 'en_curso' | 'listo' | 'error'
  archivos: { firewall: string; sistema_medico: string; agendamiento: string | null }
  activo?: boolean
  resumen?: ResumenAnalisis | null
  pasos?: Paso[]
  error?: string | null
  registro?: string[]
}
export interface ListaAnalisis {
  activo: string | null
  ocupado: boolean
  analisis: Analisis[]
}
export interface Fuente {
  origen: 'datos' | 'ejemplo'
  nombre: string
  etiqueta: string
  mb: number
  tipo: 'firewall' | 'sistema_medico' | 'agendamiento' | 'desconocido'
}

// ---------- estratégico ----------
export interface Riesgo {
  id: string
  nombre: string
  probabilidad: number
  impacto: number
  nivel: number
  tratamiento: string
  evidencia: string[]
  casos: string[]
}
export interface Control {
  id: string
  nombre: string
  hallazgo: string
  estado: string
}
export interface HistoriaItem {
  id: string
  fecha: string
  inicio: string
  titulo: string
  gravedad: Gravedad
  frase: string
  accion: string
  estado: EstadoCaso
  avisoTelegram: boolean
}
export interface Ejecutivo {
  periodo: { desde: string; hasta: string }
  archivos: Record<string, string | null>
  registros: number
  minutos: number
  jornadasManuales: number
  anosManuales: number
  incidentes: number
  criticos: number
  pendientes: number
  confirmados: number
  extraccionesExitosas: number
  historia: HistoriaItem[]
  riesgosPrincipales: Riesgo[]
  riesgosCriticos: number
  agendamiento: { origenesEnRevision: number; citasAConfirmar: number; reservas: number; explicadosLegitimos: number } | null
  denuncias: { recibidas: number; abiertas: number }
  pulso: { ts: string; v: number }[]
}
export interface Tendencia {
  id: string
  titulo: string
  fuente: string
  fecha: string
  relevancia: number
  exposicion: number
  impacto: number
  tecnicas: string[]
  resumen: string
  serie: number[]
  exposicionLocal: string
}

// ---------- operativo ----------
export type EstadoCaso = 'pendiente' | 'confirmado' | 'descartado'
export interface Medicion {
  nombre: string
  valor: number
  refMin: number
  refMax: number
  unidad: string
  nota?: string
}
export interface AlertaTelegram {
  enviada: boolean
  fecha: string
  texto: string
  modo: string
}
export interface CasoResumen {
  id: string
  titulo: string
  tipo: string
  gravedad: Gravedad
  inicio: string
  duracion: string
  ipOrigen: string
  cuenta: string
  protocolo: string
  estado: EstadoCaso
  detectadoPor: string[]
  alerta: AlertaTelegram | null
  resumen: string
}
export interface Evidencia {
  fuente: string
  resumen: string
  mediciones: Medicion[]
  registros: { ts: string; campos: Record<string, string> }[]
}
export interface Caso extends CasoResumen {
  ipDestino: string
  seudonimo: string
  tecnicas: { id: string; nombre: string }[]
  riesgos: string[]
  modelo: { puntuacion: number; puesto: number; total: number } | null
  explicacion: Medicion[]
  firewall: Evidencia | null
  sistemaMedico: Evidencia | null
  recorrido: { paso: string; detalle: string }[]
  acciones: string[]
  calidadDatos: string[]
  decision: { estado: EstadoCaso; motivo: string; analista: string; fecha: string } | null
}
export interface PuntoSerie {
  ts: string
  puntuacion: number
  fallidos: number
  ssh: number
  transferencias: number
}
export interface FilaAnomalia {
  puesto: number
  id: string
  seudonimo: string
  fuente: string
  puntuacion: number
  eventos: number
  fallidos: number
  diversidad: number
  motivo: string
  sospechosa: boolean
  casoId: string | null
}
export interface PaginaAnomalias {
  fuente: string
  total: number
  umbral: number
  filas: FilaAnomalia[]
}
export interface Nodo {
  id: string
  tipo: 'servidor' | 'ip' | 'cuenta'
  etiqueta: string
  detalle: string
  casoId: string | null
  gravedad: Gravedad | null
}
export interface Grafo {
  nodos: Nodo[]
  aristas: { origen: string; destino: string; etiqueta: string; eventos: number }[]
}

// ---------- agendamiento (HBVF) ----------
export type EstadoHBVF =
  | 'Sin hallazgo'
  | 'Observación'
  | 'Requiere revisión'
  | 'Revisión prioritaria'
  | 'Indeterminado: falta información'
  | 'Explicado por contexto legítimo'
export interface Patron {
  id: string
  nombre: string
  familia: string
  fuente: string
  contexto_legitimo: string
  validacion: string
}
export interface CasoAgenda {
  case_id: string
  pattern_ids: string[]
  patrones: Record<string, 'presente' | 'ausente' | 'desconocido' | 'explicado'>
  anomaly_score: number
  confidence: number
  risk_score: number
  probabilidad: number
  impacto: number
  status: EstadoHBVF
  review_required: boolean
  evidence_refs: string[]
  legitimate_explanations: string[]
  recommendations: { id: string; texto: string }[]
  dataset_origin: string
  resumen: {
    sesiones: number
    canales: string
    ips: number
    contactos: number
    reservas: number
    pacientes: number
    cancelaciones: number
    reasignaciones: number
    reservas_al_abrir: number
    respuesta_mediana_ms: number | null
    rol_declarado: string | null
    representacion_autorizada: boolean
    inicio: string
    fin: string
  }
  citas_en_revision: string[]
  denuncias_vinculadas: string[]
  revision: { decision: string; nota: string; analista: string; fecha: string } | null
}
export interface Agenda {
  dataset_origin: string
  catalogo: Patron[]
  mitigaciones: Record<string, string>
  vinculos_de_agrupacion: Record<string, number>
  resumen: {
    eventos: number
    sesiones: number
    puntos: number
    reservas: number
    estados: Partial<Record<EstadoHBVF, number>>
    revision_requerida: number
    citas_en_revision: number
    periodo: { desde: string; hasta: string }
  }
  casos: CasoAgenda[]
  evaluacion: {
    nota: string
    matriz: { vp: number; fp: number; fn: number; vn: number }
    precision: number | null
    sensibilidad: number | null
    tasa_falsos_positivos: number | null
    f1: number | null
  } | null
  principios: string[]
}

// ---------- denuncias ----------
export type EstadoDenuncia = 'recibida' | 'en_revision' | 'atendida' | 'descartada'
export interface Denuncia {
  codigo: string
  fecha: string
  origen: string
  tipo: string
  tipo_texto: string
  descripcion: string
  cuando: string
  medio: string
  contacto_sospechoso_mascara: string
  enlace: string
  verificacion: Verificacion | null
  responder_a: string
  estado: EstadoDenuncia
  respuesta_publica: string
  nota_interna: string
  gestionado_por: string
  actualizado?: string
  origenesAgendamiento: string[]
}
export interface DenunciaPublica {
  codigo: string
  fecha: string
  tipo: string
  estado: string
  respuesta: string
}

// ---------- técnico / salud / auditoría ----------
export interface Inteligencia {
  sigma: { id: string; titulo: string; nivel: string; tecnica: string; casos: string[]; yaml: string }[]
  iocs: { tipo: string; valor: string; descripcion: string; casoId: string; confianza: number }[]
  stix: string
  misp: string
}

/** Resultado de un job de GitHub Actions, tal como lo escribe el pipeline. */
export type ResultadoCI = 'success' | 'failure' | 'cancelled' | 'skipped'
export interface CheckCI {
  id: string
  nombre: string
  resultado: ResultadoCI
  detalle: string
}
export interface EstadoCI {
  disponible: boolean
  generado: string
  ejecucion: string
  rama: string
  commit: string
  origen: string
  estado: 'correcto' | 'parcial' | 'fallido' | 'sin_datos'
  checks: CheckCI[]
}
export interface Verificacion {
  entrada: string
  tipo: 'enlace' | 'imagen'
  veredicto: 'seguro' | 'sospechoso' | 'malicioso'
  puntuacion: number
  lista: string | null
  senales: { texto: string; tipo: 'riesgo' | 'confianza'; peso: number }[]
  recomendacion: string
}
export interface EntradaBitacora {
  id: string
  fecha: string
  actor: string
  rol: string
  accion: string
  objetivo: string
  detalle: string
}
