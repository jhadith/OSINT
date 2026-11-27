import { useMemo, useState } from 'react'
import type { Gravedad, HistoriaItem } from '../api/types'
import { fFechaHora, GRAVEDAD } from '../lib/format'

const HORAS_POR_LATIDO = 6
const ANCHO_LATIDO = 8
const ALTO = 236
const BASE = 172
const MARGEN = 10

interface Latido {
  x: number
  inicio: string
  amplitud: number
  incidente: HistoriaItem | null
}

/** Dibuja un latido PQRST a partir de x con la amplitud dada (0–1). */
function trazo(x: number, a: number, primero: boolean) {
  const s = 1 + a * 1.4
  const r = 7 + a * 96
  const p: [number, number][] = [
    [x, BASE],
    [x + 1.2, BASE - 2 * s],
    [x + 2.1, BASE],
    [x + 3, BASE + 2 * s],
    [x + 3.8, BASE - r],
    [x + 4.6, BASE + 5 * s + a * 16],
    [x + 5.4, BASE],
    [x + 6.6, BASE - 3.5 * s],
    [x + 7.7, BASE],
  ]
  return p.map(([px, py], i) => `${i === 0 && primero ? 'M' : 'L'}${px.toFixed(1)},${py.toFixed(1)}`).join(' ')
}

/**
 * "Pulso del mes": la actividad hora a hora como un electrocardiograma.
 * La altura de cada latido sale de la puntuación de anomalía del modelo; los latidos que contienen
 * un incidente detectado se dibujan como espigas con el color de su gravedad.
 */
export function Pulso({
  pulso,
  historia,
  onElegir,
}: {
  pulso: { ts: string; v: number }[]
  historia: HistoriaItem[]
  onElegir?: (id: string) => void
}) {
  const [foco, setFoco] = useState<string | null>(null)
  const latidos = useMemo<Latido[]>(() => {
    if (!pulso.length) return []
    const orden = pulso.map((p) => p.v).sort((a, b) => a - b)
    const mediana = orden[Math.floor(orden.length / 2)]
    const tope = orden[orden.length - 1] || 1
    const out: Latido[] = []
    for (let i = 0; i < pulso.length; i += HORAS_POR_LATIDO) {
      const tramo = pulso.slice(i, i + HORAS_POR_LATIDO)
      const desde = new Date(tramo[0].ts).getTime()
      const hasta = desde + HORAS_POR_LATIDO * 3600_000
      const inc =
        historia
          .filter((h) => {
            const t = new Date(h.inicio).getTime()
            return t >= desde && t < hasta
          })
          .sort((a, b) => GRAVEDAD[a.gravedad].orden - GRAVEDAD[b.gravedad].orden)[0] ?? null
      const v = Math.max(...tramo.map((p) => p.v))
      const norm = tope > mediana ? Math.max(0, (v - mediana) / (tope - mediana)) : 0
      out.push({
        x: MARGEN + (i / HORAS_POR_LATIDO) * ANCHO_LATIDO,
        inicio: tramo[0].ts,
        amplitud: inc ? (inc.gravedad === 'critica' ? 1 : 0.82) : norm * 0.22,
        incidente: inc,
      })
    }
    return out
  }, [pulso, historia])

  if (!latidos.length) return null
  const ancho = MARGEN * 2 + latidos.length * ANCHO_LATIDO
  const linea = latidos.map((l, i) => trazo(l.x, l.amplitud, i === 0)).join(' ')
  const dias = latidos.filter((l) => l.inicio.endsWith('T00:00:00') && [1, 8, 15, 22, 29].includes(Number(l.inicio.slice(8, 10))))
  const mes = new Intl.DateTimeFormat('es-EC', { month: 'short' }).format(new Date(latidos[0].inicio))
  // Etiquetas en filas escalonadas para que no se encimen cuando dos incidentes están cerca.
  const filas: Record<string, number> = {}
  const ultimos: number[] = []
  latidos
    .filter((l) => l.incidente)
    .forEach((l) => {
      let f = 0
      while (ultimos[f] !== undefined && l.x - ultimos[f] < 170) f++
      ultimos[f] = l.x
      filas[(l.incidente as HistoriaItem).id] = f
    })

  return (
    <figure className="pulso">
      <svg viewBox={`0 0 ${ancho} ${ALTO}`} role="img" aria-label={`Pulso del mes con ${historia.length} incidentes`}>
        <defs>
          <pattern id="papel-fino" width="8" height="8" patternUnits="userSpaceOnUse">
            <path d="M8 0H0V8" fill="none" className="pulso__rejilla-fina" />
          </pattern>
          <pattern id="papel" width="40" height="40" patternUnits="userSpaceOnUse">
            <rect width="40" height="40" fill="url(#papel-fino)" />
            <path d="M40 0H0V40" fill="none" className="pulso__rejilla" />
          </pattern>
        </defs>
        <rect y={BASE - 120} width={ancho} height={142} fill="url(#papel)" />
        <path d={linea} className="pulso__linea" pathLength={1} />
        {latidos
          .filter((l) => l.incidente)
          .map((l) => {
            const h = l.incidente as HistoriaItem
            const activo = foco === h.id
            const pico = BASE - (7 + l.amplitud * 96)
            const yTexto = 18 + (filas[h.id] ?? 0) * 19
            const derecha = l.x > ancho - 150
            return (
              <g
                key={h.id}
                className={`pulso__incidente pulso__incidente--${h.gravedad as Gravedad} ${activo ? 'es-foco' : ''}`}
                onMouseEnter={() => setFoco(h.id)}
                onMouseLeave={() => setFoco(null)}
                onFocus={() => setFoco(h.id)}
                onBlur={() => setFoco(null)}
                onClick={() => onElegir?.(h.id)}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onElegir?.(h.id)}
                tabIndex={0}
                role="button"
                aria-label={`${h.titulo}, ${fFechaHora(h.inicio)}, gravedad ${GRAVEDAD[h.gravedad].texto}`}
              >
                <rect x={l.x - 6} y={BASE - 120} width={ANCHO_LATIDO + 12} height={142} className="pulso__zona" />
                <path d={trazo(l.x, l.amplitud, true)} className="pulso__espiga" />
                <line x1={l.x + 3.8} y1={yTexto + 4} x2={l.x + 3.8} y2={pico - 5} className="pulso__guia" />
                <circle cx={l.x + 3.8} cy={pico} r={4} />
                <text x={l.x + (derecha ? -2 : 9)} y={yTexto} textAnchor={derecha ? 'end' : 'start'}>
                  {h.titulo}
                </text>
              </g>
            )
          })}
        {dias.map((d) => (
          <text key={d.inicio} x={d.x} y={ALTO - 6} className="pulso__dia">
            {Number(d.inicio.slice(8, 10))} {mes}
          </text>
        ))}
      </svg>
    </figure>
  )
}
