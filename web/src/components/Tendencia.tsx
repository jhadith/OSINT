import { TrendingDown, TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Gravedad, HistoriaItem } from '../api/types'
import { fFecha, num } from '../lib/format'

export interface DiaActividad {
  dia: string
  fallidos: number
  ssh: number
  transferencias: number
}

const MEDIDAS = {
  alerta: { nombre: 'Horas en alerta', unidad: 'horas', ayuda: 'Horas del día que el modelo marcó para revisar (puntuación de 0,8 o más)' },
  fallidos: { nombre: 'Accesos fallidos', unidad: 'intentos', ayuda: 'Intentos de ingreso con clave equivocada' },
  transferencias: { nombre: 'Transferencias', unidad: 'transferencias', ayuda: 'Datos que salieron del servidor médico' },
  ssh: { nombre: 'Conexiones remotas', unidad: 'conexiones', ayuda: 'Conexiones SSH hacia el servidor médico' },
} as const
type Medida = keyof typeof MEDIDAS

const COLOR: Record<Gravedad, string> = {
  critica: 'var(--critica)',
  alta: 'var(--alta-relleno)',
  media: 'var(--media)',
  baja: 'var(--baja)',
}
const VENTANA = 7
const UMBRAL = 0.8 // mismo umbral con el que el motor marca una hora para revisión

interface Punto {
  dia: string
  valor: number
  promedio: number | null
}

/** Serie diaria + promedio móvil de 7 días (la tendencia) para la medida elegida. */
function armar(pulso: { ts: string; v: number }[], porDia: DiaActividad[], m: Medida): Punto[] {
  let base: { dia: string; valor: number }[]
  if (m === 'alerta') {
    const horas = new Map<string, number>()
    for (const p of pulso) horas.set(p.ts.slice(0, 10), (horas.get(p.ts.slice(0, 10)) ?? 0) + (p.v >= UMBRAL ? 1 : 0))
    base = [...horas.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([dia, valor]) => ({ dia, valor }))
  } else {
    base = porDia.map((x) => ({ dia: x.dia, valor: x[m] }))
  }
  return base.map((x, i) => {
    const tramo = base.slice(Math.max(0, i - VENTANA + 1), i + 1)
    return { ...x, promedio: i >= VENTANA - 1 ? Math.round((tramo.reduce((s, y) => s + y.valor, 0) / tramo.length) * 10) / 10 : null }
  })
}

/** Últimos 7 días contra los 7 anteriores. */
function cambio(p: Punto[]) {
  if (p.length < VENTANA * 2) return null
  const suma = (a: Punto[]) => a.reduce((s, x) => s + x.valor, 0)
  const ult = suma(p.slice(-VENTANA))
  const ant = suma(p.slice(-VENTANA * 2, -VENTANA))
  if (!ant) return null
  return Math.round(((ult - ant) / ant) * 100)
}

export function Tendencia({
  pulso,
  porDia,
  historia,
  grande,
  onElegir,
}: {
  pulso: { ts: string; v: number }[]
  porDia: DiaActividad[]
  historia: HistoriaItem[]
  grande?: boolean
  onElegir?: (id: string) => void
}) {
  const [m, setM] = useState<Medida>('alerta')
  const puntos = useMemo(() => armar(pulso, porDia, m), [pulso, porDia, m])
  const delta = cambio(puntos)
  const porFecha = new Map(puntos.map((p) => [p.dia, p.valor]))
  const marcas = historia.filter((h) => porFecha.has(h.inicio.slice(0, 10)))
  const sube = (delta ?? 0) > 0

  return (
    <div className={`tend-mes ${grande ? 'tend-mes--grande' : ''}`}>
      <div className="tend-mes__cab">
        <div className="tend-mes__medidas" role="group" aria-label="Qué medir">
          {(Object.keys(MEDIDAS) as Medida[]).map((k) => (
            <button
              key={k}
              type="button"
              className={`tend-mes__medida ${m === k ? 'tend-mes__medida--sel' : ''}`}
              aria-pressed={m === k}
              title={MEDIDAS[k].ayuda}
              onClick={() => setM(k)}
            >
              {MEDIDAS[k].nombre}
            </button>
          ))}
        </div>
        {delta !== null && (
          <span
            className={`tend-mes__delta tend-mes__delta--${delta === 0 ? 'igual' : sube ? 'sube' : 'baja'}`}
            title="Suma de los últimos 7 días comparada con los 7 anteriores"
          >
            {delta === 0 ? (
              'Igual que la semana anterior'
            ) : (
              <>
                {sube ? <TrendingUp size={15} aria-hidden /> : <TrendingDown size={15} aria-hidden />}
                {delta > 0 ? '+' : ''}
                {delta} % vs semana anterior
              </>
            )}
          </span>
        )}
      </div>
      <div className="tend-mes__grafico">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={puntos} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--linea-suave)" />
            <XAxis
              dataKey="dia"
              tickFormatter={(x: string) => String(Number(x.slice(8)))}
              tick={{ fontSize: 11, fill: 'var(--tinta-3)' }}
              interval={grande ? 1 : 3}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              width={44}
              tick={{ fontSize: 11, fill: 'var(--tinta-3)' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => num(v)}
              domain={[0, 'auto']}
              allowDecimals={false}
            />
            <Tooltip
              labelFormatter={(x) => fFecha(String(x))}
              formatter={(v, n) => [`${num(Number(v))} ${MEDIDAS[m].unidad}`, n === 'promedio' ? 'Tendencia (promedio 7 días)' : MEDIDAS[m].nombre]}
            />
            <Line type="linear" dataKey="valor" stroke="var(--verde)" strokeWidth={1.6} dot={false} isAnimationActive={false} />
            <Line
              type="linear"
              dataKey="promedio"
              stroke="var(--verde-profundo)"
              strokeWidth={2.6}
              strokeDasharray="6 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            {marcas.map((h) => (
              <ReferenceDot
                key={h.id}
                x={h.inicio.slice(0, 10)}
                y={porFecha.get(h.inicio.slice(0, 10))}
                r={grande ? 7 : 5.5}
                fill={COLOR[h.gravedad]}
                stroke="var(--superficie)"
                strokeWidth={2}
                label={grande ? { value: h.titulo, position: 'top', fontSize: 12, fill: 'var(--tinta-2)' } : undefined}
                onClick={onElegir ? () => onElegir(h.id) : undefined}
                style={onElegir ? { cursor: 'pointer' } : undefined}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="tend-mes__leyenda" aria-hidden>
        <span>
          <i className="tend-mes__l tend-mes__l--dia" /> {MEDIDAS[m].nombre} por día
        </span>
        <span>
          <i className="tend-mes__l tend-mes__l--prom" /> Tendencia (promedio de 7 días)
        </span>
        <span>
          <i className="tend-mes__l tend-mes__l--inc" /> Incidente
        </span>
      </div>
    </div>
  )
}
