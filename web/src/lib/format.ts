import type { EstadoHBVF, Gravedad } from '../api/types'

const entero = new Intl.NumberFormat('es-EC', { useGrouping: 'always', maximumFractionDigits: 2 })
const compacto = new Intl.NumberFormat('es-EC', { notation: 'compact', maximumFractionDigits: 1 })
const hora = new Intl.DateTimeFormat('es-EC', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const fecha = new Intl.DateTimeFormat('es-EC', { day: 'numeric', month: 'short' })
const fechaLarga = new Intl.DateTimeFormat('es-EC', { day: 'numeric', month: 'long' })
const fechaHora = new Intl.DateTimeFormat('es-EC', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const mes = new Intl.DateTimeFormat('es-EC', { month: 'long', year: 'numeric' })

/** Las fechas sin hora (AAAA-MM-DD) se leen al mediodía local para que no salten al día anterior. */
const aFecha = (iso: string) => new Date(iso.length === 10 ? iso + 'T12:00:00' : iso)
export const num = (n: number) => entero.format(n)
export const corto = (n: number) => compacto.format(n)
/** 10 023 532 -> "10 millones"; 710 300 -> "710 mil". Para frases dirigidas a personas no técnicas. */
export function enPalabras(n: number) {
  if (n >= 1e6) {
    const m = Math.round(n / 1e5) / 10
    return `${entero.format(m)} ${m === 1 ? 'millón' : 'millones'}`
  }
  if (n >= 1e4) return `${entero.format(Math.round(n / 1e3))} mil`
  return entero.format(n)
}
/** 0.2 -> "12 segundos"; 2.9 -> "3 minutos". */
export function duracion(min: number) {
  if (min < 1) return `${Math.max(1, Math.round(min * 60))} segundos`
  const m = Math.round(min)
  return `${m} ${m === 1 ? 'minuto' : 'minutos'}`
}
export const pct = (n: number | null | undefined) => (n == null ? '—' : `${Math.round(n * 100)} %`)
export const fHora = (iso: string) => hora.format(aFecha(iso))
export const fFecha = (iso: string) => fecha.format(aFecha(iso))
export const fFechaLarga = (iso: string) => fechaLarga.format(aFecha(iso))
export const fFechaHora = (iso: string) => fechaHora.format(aFecha(iso))
/** "octubre de 2026" para usar dentro de una frase. */
export const fMes = (iso: string) => mes.format(aFecha(iso))
/** "Octubre de 2026" para empezar un título. */
export const fMesTitulo = (iso: string) => {
  const t = fMes(iso)
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export const GRAVEDAD: Record<Gravedad, { texto: string; orden: number }> = {
  critica: { texto: 'Crítica', orden: 0 },
  alta: { texto: 'Alta', orden: 1 },
  media: { texto: 'Media', orden: 2 },
  baja: { texto: 'Baja', orden: 3 },
}

/** Estados del módulo de agendamiento (informe §14.4), con su clase de color. */
export const ESTADO_HBVF: Record<EstadoHBVF, { clase: string; orden: number; corto: string }> = {
  'Revisión prioritaria': { clase: 'critica', orden: 0, corto: 'Prioritaria' },
  'Requiere revisión': { clase: 'alta', orden: 1, corto: 'Requiere revisión' },
  'Indeterminado: falta información': { clase: 'indeterminado', orden: 2, corto: 'Indeterminado' },
  Observación: { clase: 'observacion', orden: 3, corto: 'Observación' },
  'Explicado por contexto legítimo': { clase: 'legitimo', orden: 4, corto: 'Explicado' },
  'Sin hallazgo': { clase: 'neutro', orden: 5, corto: 'Sin hallazgo' },
}

export const ESTADO_CASO = {
  pendiente: 'Por decidir',
  confirmado: 'Confirmado',
  descartado: 'Descartado',
} as const

export const ESTADO_DENUNCIA = {
  recibida: 'Recibida',
  en_revision: 'En revisión',
  atendida: 'Atendida',
  descartada: 'Cerrada',
} as const

export const MEDIO: Record<string, string> = {
  '': 'Sin indicar',
  llamada: 'Llamada',
  whatsapp: 'WhatsApp',
  mensaje: 'Mensaje de texto',
  correo: 'Correo',
  en_persona: 'En persona',
  redes_sociales: 'Redes sociales',
}

/** Bandera de laboratorio: H si supera el rango, L si queda por debajo. */
export function bandera(valor: number, min: number, max: number): 'H' | 'L' | null {
  if (valor > max) return 'H'
  if (valor < min) return 'L'
  return null
}

export function plural(n: number, uno: string, varios: string) {
  return `${num(n)} ${n === 1 ? uno : varios}`
}
