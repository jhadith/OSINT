import { Download } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Carga, Pagina, Panel } from '../components/ui'
import { useApi } from '../lib/useApi'

export default function Inteligencia() {
  const { st, reintentar } = useApi(api.inteligencia)
  const [regla, setRegla] = useState(0)
  const [error, setError] = useState('')
  const bajar = (t: 'stix' | 'misp' | 'sigma') => api.exportar(t).catch((e: Error) => setError(e.message))
  return (
    <Pagina
      titulo="Reglas e indicadores"
      bajada="Lo que se aprendió de los casos, listo para que TI lo cargue en sus herramientas y para compartirlo con otras instituciones."
      acciones={
        <div className="botones">
          <button className="boton boton--secundario" onClick={() => bajar('sigma')}>
            <Download size={16} aria-hidden /> Reglas Sigma
          </button>
          <button className="boton boton--secundario" onClick={() => bajar('stix')}>
            <Download size={16} aria-hidden /> STIX 2.1
          </button>
          <button className="boton boton--secundario" onClick={() => bajar('misp')}>
            <Download size={16} aria-hidden /> MISP
          </button>
        </div>
      }
    >
      {error && <p className="error-linea">{error}</p>}
      <Carga st={st} reintentar={reintentar} filas={8}>
        {(i) => (
          <>
            <div className="rejilla rejilla--reglas">
              <Panel titulo="Reglas de detección (Sigma)" bajada="Cada regla describe un ataque para que cualquier SIEM lo reconozca.">
                <ul className="reglas">
                  {i.sigma.map((r, k) => (
                    <li key={r.id}>
                      <button className={`regla ${regla === k ? 'regla--sel' : ''}`} onClick={() => setRegla(k)}>
                        <strong>{r.titulo}</strong>
                        <span className="muted">
                          Nivel {r.nivel}, técnica <span className="mono">{r.tecnica}</span>
                          {r.casos.length ? `, casos ${r.casos.join(', ')}` : ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </Panel>
              <Panel titulo={i.sigma[regla]?.titulo ?? ''}>
                <pre className="codigo">{i.sigma[regla]?.yaml}</pre>
              </Panel>
            </div>
            <Panel titulo="Indicadores de compromiso" bajada="Direcciones, cuentas y puertos ligados a los casos.">
              <div className="tabla-scroll">
                <table className="tabla">
                  <thead>
                    <tr>
                      <th>Tipo</th>
                      <th>Valor</th>
                      <th>Qué es</th>
                      <th>Caso</th>
                      <th className="num">Confianza</th>
                    </tr>
                  </thead>
                  <tbody>
                    {i.iocs.map((x) => (
                      <tr key={x.tipo + x.valor}>
                        <td>{x.tipo}</td>
                        <td className="mono">{x.valor}</td>
                        <td>{x.descripcion}</td>
                        <td>
                          <Link className="enlace" to={`/casos/${x.casoId}`}>
                            {x.casoId}
                          </Link>
                        </td>
                        <td className="num">{x.confianza} %</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </>
        )}
      </Carga>
    </Pagina>
  )
}
