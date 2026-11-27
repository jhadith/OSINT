import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Caso, Grafo, Nodo } from '../api/types'
import { Carga, Gravedad, Pagina, Panel } from '../components/ui'
import { fFechaHora, num } from '../lib/format'
import { useApi } from '../lib/useApi'

const COLOR = { critica: 'var(--critica)', alta: 'var(--alta)', media: 'var(--media-tinta)', baja: 'var(--baja)' }
const W = { ip: 150, cuenta: 150, servidor: 176 }
const H = 46

/** Posiciones a partir del grafo del motor: cuentas → equipos → servidor ← otras cuentas. */
function posiciones(g: Grafo): Record<string, [number, number]> {
  const pos: Record<string, [number, number]> = {}
  const reparte = (n: number, i: number) => (n <= 1 ? 258 : 100 + (i * 315) / (n - 1))
  const ips = g.nodos.filter((n) => n.tipo === 'ip').sort((a, b) => (a.casoId ?? '').localeCompare(b.casoId ?? ''))
  ips.forEach((n, i) => {
    pos[n.id] = [300, reparte(ips.length, i)]
    const cuenta = g.aristas.find((a) => a.origen === n.id && g.nodos.some((x) => x.id === a.destino && x.tipo === 'cuenta'))
    if (cuenta && !pos[cuenta.destino]) pos[cuenta.destino] = [90, reparte(ips.length, i)]
  })
  g.nodos.filter((n) => n.tipo === 'servidor').forEach((n) => (pos[n.id] = [535, 258]))
  const resto = g.nodos.filter((n) => !pos[n.id])
  resto.forEach((n, i) => (pos[n.id] = [725, reparte(resto.length, i)]))
  return pos
}

export default function Relaciones() {
  const { st, reintentar } = useApi(api.grafo)
  const [elegido, setSel] = useState<string | null>(null)
  return (
    <Pagina
      titulo="Correlaciones"
      bajada="Un ataque se confirma cuando aparece a la vez en el firewall y en el sistema médico. Aquí se ven esas coincidencias y qué cuenta usó qué equipo para llegar al servidor."
    >
      <TablaCorrelaciones />
      <Carga st={st} reintentar={reintentar} filas={8}>
        {(g) => {
          const sel = elegido ?? g.nodos.find((n) => n.tipo === 'ip')?.id ?? g.nodos[0]?.id ?? ''
          return (
            <div className="rejilla rejilla--grafo">
              <Panel titulo="Mapa de conexiones" bajada="Toca un nodo para ver sus conexiones.">
                <Lienzo g={g} sel={sel} setSel={setSel} />
              </Panel>
              {sel && <Detalle g={g} id={sel} />}
            </div>
          )
        }}
      </Carga>
    </Pagina>
  )
}

function Lienzo({ g, sel, setSel }: { g: Grafo; sel: string; setSel: (id: string) => void }) {
  const vecinos = new Set(g.aristas.flatMap((a) => (a.origen === sel ? [a.destino] : a.destino === sel ? [a.origen] : [])))
  const pos = posiciones(g)
  const centro = (id: string) => pos[id] ?? [0, 0]
  return (
    <svg viewBox="0 0 820 500" className="grafo" role="group" aria-label="Mapa de conexiones">
      <rect x="208" y="26" width="424" height="440" rx="10" className="grafo__segmento" />
      <text x="222" y="48" className="grafo__titulo-seg">
        Segmento de red del servidor
      </text>
      {g.aristas.map((a, i) => {
        const [x1, y1] = centro(a.origen)
        const [x2, y2] = centro(a.destino)
        const activa = a.origen === sel || a.destino === sel
        return (
          <g key={`${a.origen}-${a.destino}-${i}`}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} className={activa ? 'grafo__arista grafo__arista--activa' : 'grafo__arista'} strokeWidth={1 + Math.log10(a.eventos + 1) * 1.6} />
            {activa && a.etiqueta !== 'usa' && (
              <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 6} className="grafo__etiqueta" textAnchor="middle">
                {a.etiqueta}, {num(a.eventos)}
              </text>
            )}
          </g>
        )
      })}
      {g.nodos.map((n) => {
        const [x, y] = centro(n.id)
        const w = W[n.tipo]
        const activo = n.id === sel
        const tenue = !activo && !vecinos.has(n.id)
        return (
          <g
            key={n.id}
            transform={`translate(${x - w / 2}, ${y - H / 2})`}
            tabIndex={0}
            role="button"
            aria-pressed={activo}
            aria-label={`${n.etiqueta}: ${n.detalle}`}
            onClick={() => setSel(n.id)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setSel(n.id))}
            className={`nodo nodo--${n.tipo} ${tenue ? 'nodo--tenue' : ''} ${activo ? 'nodo--activo' : ''}`}
          >
            <rect width={w} height={H} rx={n.tipo === 'cuenta' ? H / 2 : 6} style={n.gravedad && !tenue ? { stroke: COLOR[n.gravedad] } : undefined} />
            <text x={w / 2} y={n.tipo === 'servidor' ? 20 : 28} textAnchor="middle" className="nodo__texto">
              {n.etiqueta}
            </text>
            {n.tipo === 'servidor' && (
              <text x={w / 2} y={36} textAnchor="middle" className="nodo__sub">
                Sistema médico
              </text>
            )}
            {n.casoId && (
              <g transform={`translate(${w - 14}, -9)`}>
                <rect width="30" height="18" rx="9" style={{ fill: n.gravedad ? COLOR[n.gravedad] : 'var(--verde)' }} className="nodo__caso" />
                <text x="15" y="13" textAnchor="middle" className="nodo__caso-texto">
                  {n.casoId}
                </text>
              </g>
            )}
          </g>
        )
      })}
      <g className="grafo__columnas">
        <text x="90" y="490" textAnchor="middle">
          Cuentas
        </text>
        <text x="300" y="490" textAnchor="middle">
          Equipos
        </text>
        <text x="535" y="490" textAnchor="middle">
          Servidor
        </text>
        <text x="725" y="490" textAnchor="middle">
          Otras cuentas
        </text>
      </g>
    </svg>
  )
}

function Detalle({ g, id }: { g: Grafo; id: string }) {
  const n = g.nodos.find((x) => x.id === id) as Nodo
  const conexiones = g.aristas.filter((a) => a.origen === id || a.destino === id)
  const tipo = { servidor: 'Servidor', ip: 'Equipo', cuenta: 'Cuenta' }[n.tipo]
  return (
    <Panel titulo={<span className="mono">{n.etiqueta}</span>} bajada={tipo}>
      <p>{n.detalle}</p>
      {n.gravedad && (
        <p>
          <Gravedad g={n.gravedad} />
        </p>
      )}
      <h3>Conexiones</h3>
      <table className="tabla">
        <tbody>
          {conexiones.map((a, i) => {
            const otro = g.nodos.find((x) => x.id === (a.origen === id ? a.destino : a.origen))
            return (
              <tr key={`${a.origen}-${a.destino}-${i}`}>
                <td className="mono">{otro?.etiqueta}</td>
                <td>{a.etiqueta}</td>
                <td className="num">{num(a.eventos)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {n.casoId && (
        <Link to={`/casos/${n.casoId}`} className="boton">
          Abrir el caso {n.casoId}
        </Link>
      )}
    </Panel>
  )
}

/** Por caso: lo que vio cada fuente y si coinciden (corrección de reloj incluida). */
function TablaCorrelaciones() {
  const { st, reintentar } = useApi(async () => {
    const lista = await api.casos()
    return Promise.all(lista.map((c) => api.caso(c.id)))
  })
  return (
    <Carga st={st} reintentar={reintentar} filas={4}>
      {(casos: Caso[]) => (
        <Panel
          titulo="Coincidencias entre fuentes"
          bajada="Misma persona, misma ventana de tiempo, dos fuentes distintas. Si los relojes no coinciden, el motor prueba desfases de 0, -12 y +12 horas."
        >
          <div className="tabla-scroll">
            <table className="tabla correlaciones">
              <thead>
                <tr>
                  <th>Caso</th>
                  <th>Firewall</th>
                  <th aria-label="se une con" />
                  <th>Sistema médico</th>
                  <th>Resultado</th>
                </tr>
              </thead>
              <tbody>
                {casos.map((c) => {
                  const reloj = c.recorrido.find((r) => /reloj|desfase/i.test(r.detalle))
                  const ambas = Boolean(c.firewall && c.sistemaMedico)
                  return (
                    <tr key={c.id}>
                      <td>
                        <Link to={`/casos/${c.id}`} className="enlace">
                          {c.id}
                        </Link>
                        <div>{c.titulo}</div>
                        <Gravedad g={c.gravedad} />
                      </td>
                      <td className="corr__fuente">
                        <span className="mono">{c.ipOrigen}</span>
                        <div className="muted">{fFechaHora(c.inicio)}</div>
                        <div>{c.firewall?.resumen ?? 'Sin evento en el firewall'}</div>
                      </td>
                      <td className="corr__union">
                        <span aria-hidden="true">{ambas ? '⟷' : '—'}</span>
                      </td>
                      <td className="corr__fuente">
                        <span className="mono">{c.seudonimo}</span>
                        <div>{c.sistemaMedico?.resumen ?? 'Sin evento en el sistema médico'}</div>
                      </td>
                      <td>
                        <span className={`etiqueta ${ambas ? 'etiqueta--verde' : 'etiqueta--alta'}`}>
                          {ambas ? 'Confirmado en las dos fuentes' : 'Solo una fuente'}
                        </span>
                        {reloj && <div className="nota">{reloj.detalle}</div>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </Carga>
  )
}
