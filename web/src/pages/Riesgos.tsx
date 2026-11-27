import { ArrowDown, ArrowUp } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Control, Riesgo } from '../api/types'
import { Carga, Pagina, Panel } from '../components/ui'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

const CLAVE = 'sentinel.riesgos.previos'
type Previos = Record<string, number>

function zona(nivel: number) {
  return nivel >= 20 ? 'critica' : nivel >= 12 ? 'alta' : nivel >= 6 ? 'media' : 'baja'
}
function leerPrevios(): Previos | null {
  try {
    return JSON.parse(sessionStorage.getItem(CLAVE) ?? 'null') as Previos | null
  } catch {
    return null
  }
}

export default function Riesgos() {
  const { st, reintentar } = useApi(api.riesgos)
  return (
    <Pagina
      titulo="Matriz de riesgos"
      bajada="Se recalcula con cada análisis y con cada decisión del analista. El impacto de cada riesgo es fijo; la probabilidad sale de la evidencia encontrada en los datos."
    >
      <Carga st={st} reintentar={reintentar} filas={8}>
        {(d) => <Matriz riesgos={d.riesgos} controles={d.controles} />}
      </Carga>
    </Pagina>
  )
}

function Matriz({ riesgos, controles }: { riesgos: Riesgo[]; controles: Control[] }) {
  const [previos] = useState<Previos | null>(leerPrevios)
  const [mostrarPrevios, setMostrarPrevios] = useState(Boolean(previos))
  const [sel, setSel] = useState<string>(() => [...riesgos].sort((a, b) => b.nivel - a.nivel)[0]?.id ?? '')

  // Primero se dibujan las posiciones de la visita anterior y luego se deslizan a las nuevas.
  useEffect(() => {
    const t = setTimeout(() => setMostrarPrevios(false), 450)
    try {
      sessionStorage.setItem(CLAVE, JSON.stringify(Object.fromEntries(riesgos.map((r) => [r.id, r.probabilidad]))))
    } catch {
      /* sin almacenamiento: no se muestran cambios */
    }
    return () => clearTimeout(t)
  }, [riesgos])

  const posiciones = useMemo(() => {
    const porCelda: Record<string, number> = {}
    const out: Record<string, { p: number; i: number; k: number }> = {}
    for (const r of [...riesgos].sort((a, b) => a.id.localeCompare(b.id, 'es', { numeric: true }))) {
      const p = mostrarPrevios && previos?.[r.id] ? previos[r.id] : r.probabilidad
      const celda = `${p}-${r.impacto}`
      const k = porCelda[celda] ?? 0
      porCelda[celda] = k + 1
      out[r.id] = { p, i: r.impacto, k }
    }
    return out
  }, [riesgos, previos, mostrarPrevios])

  const elegido = riesgos.find((r) => r.id === sel)
  const cambios = riesgos.filter((r) => previos?.[r.id] && previos[r.id] !== r.probabilidad)
  const ordenados = [...riesgos].sort((a, b) => b.nivel - a.nivel || a.id.localeCompare(b.id, 'es', { numeric: true }))

  return (
    <>
      {cambios.length > 0 && (
        <div className="aviso aviso--info" role="status">
          <div>
            <strong>La matriz cambió desde tu última visita.</strong>{' '}
            {cambios
              .map((r) => `${r.id} pasó de probabilidad ${previos?.[r.id]} a ${r.probabilidad}`)
              .join('; ')}
            .
          </div>
        </div>
      )}
      <div className="rejilla rejilla--matriz">
        <Panel titulo="Probabilidad por impacto" bajada="Toca un riesgo para ver de dónde sale su posición.">
          <div className="matriz">
            <div className="matriz__eje-y">Impacto</div>
            <div className="matriz__marco">
              <div className="matriz__celdas" aria-hidden>
                {[5, 4, 3, 2, 1].map((imp) =>
                  [1, 2, 3, 4, 5].map((pr) => <div key={`${pr}-${imp}`} className={`matriz__celda matriz__celda--${zona(pr * imp)}`} />),
                )}
              </div>
              {[5, 4, 3, 2, 1].map((imp) => (
                <span key={imp} className="matriz__num-y" style={{ top: `${(5 - imp) * 20 + 10}%` }}>
                  {imp}
                </span>
              ))}
              {riesgos.map((r) => {
                const { p, i, k } = posiciones[r.id]
                return (
                  <button
                    key={r.id}
                    className={`ficha ficha--${zona(r.nivel)} ${sel === r.id ? 'ficha--sel' : ''}`}
                    style={{
                      left: `calc(${(p - 1) * 20}% + ${6 + (k % 3) * 34}px)`,
                      top: `calc(${(5 - i) * 20}% + ${6 + Math.floor(k / 3) * 30}px)`,
                    }}
                    onClick={() => setSel(r.id)}
                    aria-pressed={sel === r.id}
                    aria-label={`${r.id} ${r.nombre}: probabilidad ${r.probabilidad}, impacto ${r.impacto}, nivel ${r.nivel}`}
                  >
                    {r.id}
                  </button>
                )
              })}
            </div>
            <div className="matriz__eje-x">
              {[1, 2, 3, 4, 5].map((p) => (
                <span key={p}>{p}</span>
              ))}
              <div>Probabilidad</div>
            </div>
          </div>
          <p className="leyenda">
            <span className="leyenda__item leyenda__item--baja">Baja, menos de 6</span>
            <span className="leyenda__item leyenda__item--media">Media, 6 a 11</span>
            <span className="leyenda__item leyenda__item--alta">Alta, 12 a 19</span>
            <span className="leyenda__item leyenda__item--critica">Crítica, 20 o más</span>
          </p>
        </Panel>

        {elegido && <Detalle r={elegido} previo={previos?.[elegido.id]} />}
      </div>

      <Panel titulo="Todos los riesgos" bajada="Ordenados por nivel. La probabilidad vuelve a 1 cuando no queda evidencia en el análisis activo.">
        <div className="tabla-scroll">
          <table className="tabla">
            <thead>
              <tr>
                <th>Riesgo</th>
                <th className="num">Probabilidad</th>
                <th className="num">Impacto</th>
                <th className="num">Nivel</th>
                <th>Evidencia en los datos</th>
              </tr>
            </thead>
            <tbody>
              {ordenados.map((r) => {
                const antes = previos?.[r.id]
                return (
                  <tr key={r.id} onClick={() => setSel(r.id)} className={`clic ${sel === r.id ? 'fila--activa' : ''}`}>
                    <td>
                      <strong>{r.id}</strong> {r.nombre}
                    </td>
                    <td className="num">
                      {r.probabilidad}
                      {antes && antes !== r.probabilidad && (
                        <span className={`cambio ${antes > r.probabilidad ? 'cambio--baja' : 'cambio--sube'}`}>
                          {antes > r.probabilidad ? <ArrowDown size={13} aria-hidden /> : <ArrowUp size={13} aria-hidden />}
                          antes {antes}
                        </span>
                      )}
                    </td>
                    <td className="num">{r.impacto}</td>
                    <td className="num">
                      <span className={`nivel nivel--${zona(r.nivel)}`}>{r.nivel}</span>
                    </td>
                    <td className="evidencia-corta">{r.evidencia.join('; ')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel
        titulo="Controles de la norma ISO/IEC 27002"
        bajada="Qué controles se relacionan con los hallazgos y en qué estado quedan con esta propuesta."
      >
        <div className="tabla-scroll">
          <table className="tabla">
            <thead>
              <tr>
                <th>Control</th>
                <th>Hallazgo relacionado</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {controles.map((c) => (
                <tr key={c.id}>
                  <td>
                    <strong>{c.id}</strong> {c.nombre}
                  </td>
                  <td>{c.hallazgo}</td>
                  <td>
                    <span className={`etiqueta ${c.estado === 'Brecha' ? 'etiqueta--alta' : c.estado.startsWith('Se implementa') ? 'etiqueta--verde' : ''}`}>
                      {c.estado}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  )
}

function Detalle({ r, previo }: { r: Riesgo; previo?: number }) {
  const { puede } = useSesion()
  return (
    <Panel className="detalle-riesgo" titulo={`${r.id}. ${r.nombre}`}>
      <div className="formula">
        <span>
          <b>{r.probabilidad}</b> probabilidad
        </span>
        <span aria-hidden>×</span>
        <span>
          <b>{r.impacto}</b> impacto
        </span>
        <span aria-hidden>=</span>
        <span className={`nivel nivel--${zona(r.nivel)} nivel--grande`}>{r.nivel}</span>
      </div>
      {previo && previo !== r.probabilidad && (
        <p className="nota">
          En tu visita anterior la probabilidad era {previo}. Cambió por las decisiones o el análisis nuevo.
        </p>
      )}
      <h3>Por qué está aquí</h3>
      <ul className="lista-evidencia">
        {r.evidencia.map((e) => (
          <li key={e}>{e}</li>
        ))}
      </ul>
      {r.casos.length > 0 && puede('operativo') && (
        <p className="casos-ligados">
          Casos:{' '}
          {r.casos.map((c) => (
            <Link key={c} to={`/casos/${c}`} className="enlace">
              {c}
            </Link>
          ))}
        </p>
      )}
      <h3>Tratamiento propuesto</h3>
      <p>{r.tratamiento}</p>
    </Panel>
  )
}
