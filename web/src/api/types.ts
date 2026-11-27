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
  | 'pedir_reglas'
  | 'gestionar_reglas'
  | 'panorama_salud'
  | 'avisar_personal'

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
  /** Sello de procedencia: «real (KEV)» / «real (NVD)» / «simulado» (se añade solo cuando hay caché OSINT). */
  sello?: string
  kev?: boolean
  exploitPublico?: boolean
  cvss?: number | null
}

/** Metadatos OSINT que el backend adjunta a /threatpulse solo si hay lecturas reales en caché. */
export interface OsintMeta {
  sincronizadoEn: string
  items: number
  fuentes: number
  notas: string[]
}

/** Resultado de POST /threatpulse/actualizar (sincronización manual). */
export interface ResultadoOsint {
  actualizadas: number
  fallidas: number
  totales: number
  sincronizado_en: string
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
  /** Cómo la contó además de escribir (Nota de voz, Video, Foto): llega ya como texto protegido en la descripción. */
  contadoCon: string[]
  estado: EstadoDenuncia
  respuesta_publica: string
  nota_interna: string
  gestionado_por: string
  actualizado?: string
  origenesAgendamiento: string[]
}
// ---------- avisos al personal de salud y «Mi panorama» ----------
export type NivelAviso = 'alto' | 'medio' | 'info'
export interface Aviso {
  codigo: string
  fecha: string
  nivel: NivelAviso
  titulo: string
  texto: string
  consejo: string
  origen: 'automatico' | 'manual'
  leido?: boolean
  autor?: string
  caso?: string
  telegram?: string
}
export interface AvisoBorrador {
  titulo: string
  texto: string
  consejo: string
  nivel: NivelAviso
}
export interface PanoramaSalud {
  hayAnalisis: boolean
  periodo: { desde: string; hasta: string } | null
  avisos: Aviso[]
  amenazas: { id: string; nombre: string; n: number }[]
  total: number
  porDia: { dia: string; intentos: number }[]
  dimensiones: { id: string; nombre: string; pregunta: string; nivel: Gravedad; exposicion: number; explicacion: string }[]
  sector: { titulo: string; resumen: string; fuente: string; fecha: string }[]
  misReportes: { codigo: string; fecha: string; que: string; estado: string; respuesta: string }[]
  consejos: string[]
}

export interface DenunciaPublica {
  codigo: string
  fecha: string
  tipo: string
  estado: string
  respuesta: string
}

// ---------- técnico / salud / auditoría ----------
/** Productos descargables de la página de inteligencia: CTI existentes (S6), difusión Power BI/Maltego (S10)
 *  e informes HTML autocontenidos (S14). */
export type Exporte = 'stix' | 'misp' | 'sigma' | 'powerbi' | 'maltego' | 'gerencial' | 'presentacion'
export interface Inteligencia {
  sigma: { id: string; titulo: string; nivel: string; tecnica: string; casos: string[]; yaml: string }[]
  iocs: { tipo: string; valor: string; descripcion: string; casoId: string; confianza: number }[]
  stix: string
  misp: string
}
export interface Verificacion {
  entrada: string
  tipo: 'enlace' | 'imagen'
  veredicto: 'seguro' | 'sospechoso' | 'malicioso'
  puntuacion: number
  lista: string | null
  /** Clasificación del enlace contra las listas dinámicas del SOC (5 estados; solo enlaces). */
  clasificacion?: 'blanca' | 'negra' | 'desconocido' | 'typosquatting' | 'conflicto'
  /** Técnicas MITRE ATT&CK que apliquen (solo enlaces). */
  tecnicas?: { id: string; nombre: string }[]
  /** Dominio de la lista blanca que el enlace imita (cuando hay typosquatting). */
  referencia?: string | null
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

// ---------- listas de comparación (S15/T17b) ----------
export type TipoLista = 'blanca' | 'negra'
export type EstadoSolicitud = 'PENDIENTE' | 'APROBADA' | 'RECHAZADA'
/** Indicador del catálogo dinámico (SQLite del SOC), editable sin reiniciar. */
export interface IndicadorLista {
  id: number
  tipo: TipoLista
  valor: string
  etiqueta: string
  activo: number
}
/** Solicitud de inclusión/exclusión: PENDIENTE → APROBADA | RECHAZADA con motivo. */
export interface SolicitudLista {
  id: number
  tipo: TipoLista
  valor: string
  justificacion: string
  fuente: string
  estado: EstadoSolicitud
  resolucion: string
  creado_en: string
  resuelto_en: string | null
  resuelto_por: string | null
}

// ---------- realimentación (S9/T18) ----------
/** Métrica del bucle de realimentación: `valor: null` + explicación cuando no es calculable. */
export interface Metrica {
  formula: string
  valor: number | null
  explicacion: string
  confirmadas?: number
  descartadas?: number
  casosConocidos?: number
  decididos?: number
  confirmados?: number
}
export interface CasoReferencia {
  caso: string
  titulo: string
  estado: 'confirmada' | 'descartada' | 'pendiente'
}
export interface CambioUmbral {
  archivo: string
  clave: string
  antes: number
  despues: number
  direccion: 'subir' | 'bajar'
  fps: string[]
}
/** Resultado del reentrenamiento junto a la recalibración (solo cuando hubo cambio de umbrales). */
export interface Reentrenamiento {
  firewall?: { ventanas: number; semilla: number; modelo: string }
  sistema_medico?: { ventanas: number; semilla: number; modelo: string }
  notas: string[]
}
export interface Recalibracion {
  fecha: string
  actor: string
  rol: string
  motivo: string
  fps: string[]
  cambios: CambioUmbral[]
  reentrenamiento: Reentrenamiento | null
}
export interface Realimentacion {
  precision: Metrica
  recall: Metrica
  f1: Metrica
  casosConocidos: CasoReferencia[]
  analisis: string | null
  recalibraciones: Recalibracion[]
  historico: { firewall: number; sistema_medico: number }
}
export interface ResultadoRecalibrar {
  cambios: CambioUmbral[]
  sinUmbral: { fps: string[]; nota: string }[]
  aplicadas: string[]
  reentrenamiento: Reentrenamiento | null
  nota: string
}

// ---------- OSINT y tickets de reglas ----------
export type EstadoTicket = 'abierto' | 'en_progreso' | 'aplicado' | 'rechazado'
export interface TicketRegla {
  codigo: string
  fecha: string
  autor: string
  tipo: 'nueva' | 'ajustar' | 'desactivar' | 'indicador'
  tipo_texto: string
  regla: string
  titulo: string
  descripcion: string
  prioridad: 'alta' | 'media' | 'baja'
  caso: string
  estado: EstadoTicket
  respuesta: string
  atendido_por: string
  actualizado: string
}
export interface ListaTickets {
  tickets: TicketRegla[]
  reglas: string[]
  tipos: Record<string, string>
  estados: Record<EstadoTicket, string>
}

// ---------- estado de CI (solo TI) ----------
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
