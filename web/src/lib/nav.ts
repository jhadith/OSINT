import {
  Activity,
  BellRing,
  BookLock,
  CalendarClock,
  FileSearch,
  FolderInput,
  Gauge,
  Grid3x3,
  HeartPulse,
  type LucideIcon,
  ListChecks,
  Megaphone,
  Network,
  Radar,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  Siren,
  Ticket,
  Waypoints,
} from 'lucide-react'
import type { Permiso } from '../api/types'

export interface Item {
  ruta: string
  nombre: string
  icono: LucideIcon
  permiso: Permiso
  /** Permiso alternativo: la pantalla se abre con cualquiera de los dos. */
  tambien?: Permiso
  ayuda: string
}
export interface Grupo {
  nivel: string
  para: string
  items: Item[]
}

/** Navegación por nivel de inteligencia de amenazas (CTI): de lo estratégico a lo técnico.
 * Los grupos primeros son pantallas de la consola SOC (internas, con login); el grupo
 * «Complementos» reúne módulos externos al SOC que solo alimentan hipótesis. */
export const NAV: Grupo[] = [
  {
    nivel: 'Estratégico',
    para: 'para decidir',
    items: [
      { ruta: '/inicio', nombre: 'Tablero', icono: Gauge, permiso: 'estrategico', ayuda: 'Todo el mes en una pantalla' },
      { ruta: '/riesgos', nombre: 'Matriz de riesgos', icono: Grid3x3, permiso: 'estrategico', ayuda: 'Cambia con cada análisis' },
      { ruta: '/tendencias', nombre: 'Tendencias', icono: Radar, permiso: 'estrategico', ayuda: 'Amenazas del sector salud' },
    ],
  },
  {
    nivel: 'Operativo',
    para: 'para actuar',
    items: [
      { ruta: '/casos', nombre: 'Casos', icono: Siren, permiso: 'operativo', ayuda: 'Incidentes por gravedad' },
      {
        ruta: '/denuncias',
        nombre: 'Denuncias',
        icono: Megaphone,
        permiso: 'ver_denuncias',
        ayuda: 'Gestión interna de lo que llega del portal Proteger (externo)',
      },
    ],
  },
  {
    nivel: 'Complementos',
    para: 'externos al SOC',
    items: [
      {
        ruta: '/agendamiento',
        nombre: 'Citas del chatbot (HBVF)',
        icono: CalendarClock,
        permiso: 'operativo',
        ayuda: 'Módulo externo: solo alimenta hipótesis, nada automático',
      },
    ],
  },
  {
    nivel: 'Táctico',
    para: 'para investigar',
    items: [
      { ruta: '/linea', nombre: 'Línea de tiempo', icono: Activity, permiso: 'operativo', ayuda: 'Hora por hora' },
      { ruta: '/anomalias', nombre: 'Anomalías', icono: ScanSearch, permiso: 'operativo', ayuda: 'Lo que el modelo ve raro' },
      { ruta: '/correlaciones', nombre: 'Correlaciones', icono: Waypoints, permiso: 'operativo', ayuda: 'Firewall y sistema médico, unidos' },
    ],
  },
  {
    nivel: 'Técnico',
    para: 'para configurar',
    items: [
      { ruta: '/cargar', nombre: 'Cargar datos', icono: FolderInput, permiso: 'cargar_datos', ayuda: 'Subir y procesar registros' },
      { ruta: '/inteligencia', nombre: 'Reglas e indicadores', icono: Network, permiso: 'tecnico', ayuda: 'Sigma, STIX y MISP' },
      {
        ruta: '/tickets',
        nombre: 'Tickets de reglas',
        icono: Ticket,
        permiso: 'pedir_reglas',
        tambien: 'gestionar_reglas',
        ayuda: 'El SOC pide cambios de reglas y TI los aplica',
      },
      {
        ruta: '/listas',
        nombre: 'Listas de comparación',
        icono: ListChecks,
        permiso: 'tecnico',
        ayuda: 'Listas blanca y negra de «Verificar contenido», editables sin reiniciar',
      },
      {
        ruta: '/realimentacion',
        nombre: 'Realimentación',
        icono: RefreshCw,
        permiso: 'tecnico',
        ayuda: 'Métricas precision/recall/F1, recalibración de umbrales y reentrenamiento',
      },
      {
        ruta: '/ci',
        nombre: 'Estado de CI',
        icono: ShieldCheck,
        permiso: 'ver_ci',
        ayuda: 'Resultado de los checks de GitHub Actions en la última ejecución',
      },
    ],
  },
  {
    nivel: 'Protección',
    para: 'para el personal',
    items: [
      { ruta: '/mi-panorama', nombre: 'Mi panorama', icono: HeartPulse, permiso: 'panorama_salud', ayuda: 'Avisos y lo que pasa en el mes' },
      { ruta: '/verificar', nombre: 'Verificar contenido', icono: FileSearch, permiso: 'verificar', ayuda: 'Enlaces e imágenes' },
    ],
  },
  {
    nivel: 'Control',
    para: 'para auditar',
    items: [{ ruta: '/accesos', nombre: 'Accesos y bitácora', icono: BookLock, permiso: 'auditar', ayuda: 'Quién hizo qué' }],
  },
]

export const TODAS = NAV.flatMap((g) => g.items)

/** Primera pantalla a la que el rol tiene acceso. */
export function accede(i: Item, permisos: Permiso[]) {
  return permisos.includes(i.permiso) || Boolean(i.tambien && permisos.includes(i.tambien))
}

export function inicioDe(permisos: Permiso[]) {
  return TODAS.find((i) => accede(i, permisos))?.ruta ?? '/inicio'
}

/** Áreas que se muestran en las tarjetas de rol del ingreso. */
export const AREAS: { permiso: Permiso; nombre: string; icono: LucideIcon }[] = [
  { permiso: 'estrategico', nombre: 'Panorama y riesgos', icono: Gauge },
  { permiso: 'operativo', nombre: 'Casos e investigación', icono: Siren },
  { permiso: 'reidentificar', nombre: 'Ver nombres reales', icono: ShieldCheck },
  { permiso: 'cargar_datos', nombre: 'Cargar datos', icono: FolderInput },
  { permiso: 'ver_denuncias', nombre: 'Denuncias', icono: Megaphone },
  { permiso: 'panorama_salud', nombre: 'Avisos y panorama del mes', icono: BellRing },
  { permiso: 'verificar', nombre: 'Verificar contenido', icono: FileSearch },
  { permiso: 'auditar', nombre: 'Bitácora', icono: BookLock },
]
