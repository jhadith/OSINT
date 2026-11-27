import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { CasoResumen, PuntoSerie } from '../api/types'
import { Carga, Pagina, Panel } from '../components/ui'
import { fFechaHora, num } from '../lib/format'
import { useApi } from '../lib/useApi'

type Metrica = 'puntuacion' | 'fallidos' | 'ssh' | 'transferencias'
const METRICAS: Record<Metrica, { nombre: string; corto: string; ayuda: string }> = {
  fallidos: { nombre: 'Accesos fallidos por hora', corto: 'Accesos fallidos', ayuda: 'Contraseñas equivocadas o conexiones rechazadas.' },
  transferencias: { nombre: 'Transferencias del sistema médico por hora', corto: 'Transferencias', ayuda: 'Descargas o envíos de información del sistema.' },
  ssh: { nombre: 'Conexiones remotas (SSH) permitidas por hora', corto: 'Conexiones remotas', ayuda: 'Entradas de administración remota al servidor.' },
  puntuacion: { nombre: 'Rareza de cada hora según el modelo', corto: 'Rareza', ayuda: 'De 0 a 1: qué tan distinta fue esa hora del resto del mes.' },
}
const COLOR = { critica: 'var(--critica)', alta: 'var(--alta)', media: 'var(--media-tinta)', baja: 'var(--baja)' }

/** Percentiles 5–95 como franja normal del mes. */
function franja(d: PuntoSerie[], m: Metrica): [number, number] {
  const v = d.map((p) => p[m]).sort((a, b) => a - b)
  return [v[Math.floor(v.length * 0.05)] ?? 0, v[Math.floor(v.length * 0.95)] ?? 0]
}

export default function LineaTiempo() {
  const serie = useApi(api.serie)
  const casos = useApi(api.casos)
  const [m, setM] = useState<Metrica>('fallidos')
  const ir = useNavigate()
  return (
    <Pagina titulo="Línea de tiempo" bajada="El mes hora por hora. La franja verde es lo normal; las líneas punteadas marcan cuándo empezó cada caso.">
      <Carga st={serie.st} reintentar={serie.reintentar} filas={6}>
        {(d) => {
          const cs: CasoResumen[] = casos.st.estado === 'listo' ? casos.st.datos : []
          const [lo, hi] = franja(d, m)
          const ticks = d.filter((p) => p.ts.endsWith('T00:00:00') && [1, 5, 10, 15, 20, 25, 30].includes(Number(p.ts.slice(8, 10)))).map((p) => p.ts)
          return (
            <Panel
              titulo={METRICAS[m].nombre}
              bajada={METRICAS[m].ayuda}
              extra={
                <div className="pestanas" role="tablist">
                  {(Object.keys(METRICAS) as Metrica[]).map((k) => (
                    <button key={k} role="tab" aria-selected={m === k} onClick={() => setM(k)}>
                      {METRICAS[k].corto}
                    </button>
                  ))}
                </div>
              }
            >
              <div style={{ width: '100%', height: 340 }}>
                <ResponsiveContainer>
                  <AreaChart data={d} margin={{ top: 24, right: 14, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke="var(--linea-suave)" vertical={false} />
                    <ReferenceArea y1={lo} y2={hi} fill="var(--verde)" fillOpacity={0.08} stroke="none" ifOverflow="extendDomain" />
                    <XAxis
                      dataKey="ts"
                      ticks={ticks}
                      interval={0}
                      tickFormatter={(t: string) => `${Number(t.slice(8, 10))} ${new Date(t).toLocaleDateString('es-EC', { month: 'short' })}`}
                      tick={{ fill: 'var(--tinta-2)', fontSize: 13 }}
                      axisLine={{ stroke: 'var(--linea)' }}
                      tickLine={false}
                    />
                    <YAxis width={52} tick={{ fill: 'var(--tinta-2)', fontSize: 13 }} tickFormatter={(v: number) => num(v)} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ stroke: 'var(--verde)', strokeDasharray: '3 3' }}
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null
                        const v = Number(payload[0].value)
                        return (
                          <div className="tooltip">
                            <div className="muted">{fFechaHora(String(label))}</div>
                            <div>
                              {METRICAS[m].corto}: <strong className={v > hi ? 't-critica' : ''}>{num(v)}</strong>
                            </div>
                            <div className="muted">
                              Normal del mes: {num(lo)} a {num(hi)}
                            </div>
                          </div>
                        )
                      }}
                    />
                    <Area type="linear" dataKey={m} stroke="var(--verde-profundo)" strokeWidth={1.5} fill="var(--verde)" fillOpacity={0.1} isAnimationActive={false} dot={false} activeDot={{ r: 4 }} />
                    {cs.map((c) => (
                      <ReferenceLine
                        key={c.id}
                        x={c.inicio.slice(0, 13) + ':00:00'}
                        stroke={COLOR[c.gravedad]}
                        strokeWidth={1.5}
                        strokeDasharray="4 3"
                        ifOverflow="extendDomain"
                        label={{ value: c.id, position: 'top', fill: COLOR[c.gravedad], fontSize: 13, fontWeight: 700, cursor: 'pointer', onClick: () => ir(`/casos/${c.id}`) }}
                      />
                    ))}
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <ul className="leyenda leyenda--casos">
                {cs.map((c) => (
                  <li key={c.id}>
                    <button className="enlace" onClick={() => ir(`/casos/${c.id}`)}>
                      <span className={`punto fondo--${c.gravedad}`} aria-hidden /> {c.id} {c.titulo}, {fFechaHora(c.inicio)}
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
          )
        }}
      </Carga>
    </Pagina>
  )
}
