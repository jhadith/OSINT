import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Carga, Pagina, Panel } from '../components/ui'
import { num } from '../lib/format'
import { useApi } from '../lib/useApi'

type Fuente = 'firewall' | 'sistema_medico'

export default function Anomalias() {
  const [f, setF] = useState<Fuente>('firewall')
  const { st, reintentar } = useApi(() => api.anomalias(f), [f])
  const [todas, setTodas] = useState(false)
  return (
    <Pagina
      titulo="Anomalías"
      bajada="El modelo (Isolation Forest) no sabe qué es un ataque: mide qué tan fácil es separar a un usuario del resto. Lo que se aísla rápido es raro y merece una mirada."
      acciones={
        <div className="pestanas" role="tablist">
          <button role="tab" aria-selected={f === 'firewall'} onClick={() => setF('firewall')}>
            Usuarios de red
          </button>
          <button role="tab" aria-selected={f === 'sistema_medico'} onClick={() => setF('sistema_medico')}>
            Cuentas del sistema médico
          </button>
        </div>
      }
    >
      <Carga st={st} reintentar={reintentar} filas={10}>
        {(p) => {
          const filas = todas ? p.filas : p.filas.slice(0, 25)
          return (
            <Panel
              titulo={`Los más raros de ${num(p.total)} ${f === 'firewall' ? 'usuarios de red' : 'cuentas'}`}
              bajada={`Desde ${Math.round(p.umbral * 100)} de 100 se marcan como sospechosos. Las personas aparecen con seudónimo.`}
            >
              <div className="tabla-scroll">
                <table className="tabla">
                  <thead>
                    <tr>
                      <th className="num">Puesto</th>
                      <th>Quién</th>
                      <th>Rareza</th>
                      <th>Por qué destaca</th>
                      <th className="num">Eventos</th>
                      <th>Caso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas.map((r) => (
                      <tr key={r.id + r.puesto} className={r.sospechosa ? 'fila--alerta' : ''}>
                        <td className="num">{r.puesto}</td>
                        <td>
                          <span className="mono">{r.seudonimo}</span>
                          {r.id !== r.seudonimo && <div className="muted mono">{r.id}</div>}
                        </td>
                        <td className="celda-barra">
                          <div className="mini-barra" aria-hidden>
                            <div className={r.puntuacion >= p.umbral ? 'mini-barra__v mini-barra__v--alta' : 'mini-barra__v'} style={{ width: `${r.puntuacion * 100}%` }} />
                          </div>
                          <span>{Math.round(r.puntuacion * 100)}</span>
                        </td>
                        <td>{r.motivo}</td>
                        <td className="num">{num(r.eventos)}</td>
                        <td>
                          {r.casoId ? (
                            <Link className="enlace" to={`/casos/${r.casoId}`}>
                              {r.casoId}
                            </Link>
                          ) : r.sospechosa ? (
                            <span className="muted">Solo el modelo</span>
                          ) : (
                            ''
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {p.filas.length > 25 && (
                <button className="boton boton--fantasma" onClick={() => setTodas((v) => !v)}>
                  {todas ? 'Ver solo los 25 primeros' : `Ver los ${p.filas.length}`}
                </button>
              )}
            </Panel>
          )
        }}
      </Carga>
    </Pagina>
  )
}
