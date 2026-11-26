import {
  Activity,
  BookLock,
  CalendarClock,
  FileSearch,
  FolderInput,
  Gauge,
  Grid3x3,
  type LucideIcon,
  Megaphone,
  Network,
  Radar,
  ScanSearch,
  ShieldCheck,
  Siren,
  Waypoints,
} from 'lucide-react'
import type { Permiso } from '../api/types'

export interface Item {
  ruta: string
  nombre: string
  icono: LucideIcon
  permiso: Permiso
  ayuda: string
}
export interface Grupo {
  nivel: string
  para: string
  items: Item[]
}

/** Navegación por nivel de inteligencia de amenazas (CTI): de lo estratégico a lo técnico. */
export const NAV: Grupo[] = [
  {
    nivel: 'Estratégico',
    para: 'para decidir',
    items: [
      { ruta: '/inicio', nombre: 'Vista ejecutiva', icono: Gauge, permiso: 'estrategico', ayuda: 'El mes en una página' },
      { ruta: '/riesgos', nombre: 'Matriz de riesgos', icono: Grid3x3, permiso: 'estrategico', ayuda: 'Cambia con cada análisis' },
      { ruta: '/tendencias', nombre: 'Tendencias', icono: Radar, permiso: 'estrategico', ayuda: 'Amenazas del sector salud' },
    ],
  },
  {
    nivel: 'Operativo',
    para: 'para actuar',
    items: [
      { ruta: '/casos', nombre: 'Casos', icono: Siren, permiso: 'operativo', ayuda: 'Incidentes por gravedad' },
      { ruta: '/agendamiento', nombre: 'Citas del chatbot', icono: CalendarClock, permiso: 'operativo', ayuda: 'Posibles tramitadores' },
      { ruta: '/denuncias', nombre: 'Denuncias', icono: Megaphone, permiso: 'ver_denuncias', ayuda: 'Lo que reportan afiliados y personal' },
    ],
  },
  {
    nivel: 'Táctico',
    para: 'para investigar',
    items: [
      { ruta: '/linea', nombre: 'Línea de tiempo', icono: Activity, permiso: 'operativo', ayuda: 'Hora por hora' },
      { ruta: '/anomalias', nombre: 'Anomalías', icono: ScanSearch, permiso: 'operativo', ayuda: 'Lo que el modelo ve raro' },
      { ruta: '/relaciones', nombre: 'Relaciones', icono: Waypoints, permiso: 'operativo', ayuda: 'Quién se conectó con qué' },
    ],
  },
  {
    nivel: 'Técnico',
    para: 'para configurar',
    items: [
      { ruta: '/cargar', nombre: 'Cargar datos', icono: FolderInput, permiso: 'cargar_datos', ayuda: 'Subir y procesar registros' },
      { ruta: '/inteligencia', nombre: 'Reglas e indicadores', icono: Network, permiso: 'tecnico', ayuda: 'Sigma, STIX y MISP' },
    ],
  },
  {
    nivel: 'Protección',
    para: 'para el personal',
    items: [
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
export function inicioDe(permisos: Permiso[]) {
  return TODAS.find((i) => permisos.includes(i.permiso))?.ruta ?? '/inicio'
}

/** Áreas que se muestran en las tarjetas de rol del ingreso. */
export const AREAS: { permiso: Permiso; nombre: string; icono: LucideIcon }[] = [
  { permiso: 'estrategico', nombre: 'Panorama y riesgos', icono: Gauge },
  { permiso: 'operativo', nombre: 'Casos e investigación', icono: Siren },
  { permiso: 'reidentificar', nombre: 'Ver nombres reales', icono: ShieldCheck },
  { permiso: 'cargar_datos', nombre: 'Cargar datos', icono: FolderInput },
  { permiso: 'ver_denuncias', nombre: 'Denuncias', icono: Megaphone },
  { permiso: 'verificar', nombre: 'Verificar contenido', icono: FileSearch },
  { permiso: 'auditar', nombre: 'Bitácora', icono: BookLock },
]
