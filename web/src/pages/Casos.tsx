import { BellRing, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Carga, Gravedad, Pagina } from '../components/ui'
import { ESTADO_CASO, fFechaHora, GRAVEDAD } from '../lib/format'
import { useApi } from '../lib/useApi'

export default function Casos() {
  const { st, reintentar } = useApi(api.casos)
  return (
    <Pagina
      titulo="Casos"
      bajada="Ordenados como en un triaje: primero lo crítico. Cada caso junta lo que pasó en la red y en el sistema médico."
    >
      <Carga st={st} reintentar={reintentar}>
        {(casos) => (
          <ul className="triaje">
            {[...casos]
              .sort((a, b) => GRAVEDAD[a.gravedad].orden - GRAVEDAD[b.gravedad].orden || a.inicio.localeCompare(b.inicio))
              .map((c) => (
                <li key={c.id}>
                  <Link to={`/casos/${c.id}`} className={`triaje__caso triaje__caso--${c.gravedad} ${c.estado === 'descartado' ? 'es-descartado' : ''}`}>
                    <div className="triaje__banda">
                      <Gravedad g={c.gravedad} />
                      <span className="triaje__id">{c.id}</span>
                    </div>
                    <div className="triaje__cuerpo">
                      <h2>
                        {c.titulo}
                        {c.alerta && (
                          <span className="etiqueta" title={c.alerta.modo}>
                            <BellRing size={14} aria-hidden /> Aviso por Telegram
                          </span>
                        )}
                      </h2>
                      <p>{c.resumen}</p>
                      <dl className="datos-fila">
                        <div>
                          <dt>Cuándo</dt>
                          <dd>
                            {fFechaHora(c.inicio)}, duró {c.duracion}
                          </dd>
                        </div>
                        <div>
                          <dt>Desde</dt>
                          <dd className="mono">{c.ipOrigen}</dd>
                        </div>
                        <div>
                          <dt>Cuenta</dt>
                          <dd className="mono">{c.cuenta}</dd>
                        </div>
                        <div>
                          <dt>Por dónde</dt>
                          <dd>{c.protocolo}</dd>
                        </div>
                        <div>
                          <dt>Lo detectó</dt>
                          <dd>{c.detectadoPor.join(', ')}</dd>
                        </div>
                      </dl>
                    </div>
                    <div className="triaje__estado">
                      <span className={`estado estado--${c.estado}`}>{ESTADO_CASO[c.estado]}</span>
                      <ChevronRight size={20} aria-hidden />
                    </div>
                  </Link>
                </li>
              ))}
          </ul>
        )}
      </Carga>
    </Pagina>
  )
}
