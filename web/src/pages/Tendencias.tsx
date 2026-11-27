import { FlaskConical } from 'lucide-react'
import { api } from '../api/client'
import type { Tendencia } from '../api/types'
import { Carga, Pagina } from '../components/ui'
import { fFecha } from '../lib/format'
import { useApi } from '../lib/useApi'

function Linea({ serie }: { serie: number[] }) {
  if (serie.length < 2) return null
  const max = Math.max(...serie, 1)
  const pts = serie.map((v, i) => `${(i / (serie.length - 1)) * 120},${36 - (v / max) * 32}`).join(' ')
  return (
    <svg viewBox="0 0 120 40" className="sparkline" aria-hidden>
      <polyline points={pts} />
    </svg>
  )
}

function Puntos({ n, texto }: { n: number; texto: string }) {
  return (
    <div className="puntos" aria-label={`${texto}: ${n} de 5`}>
      <span>{texto}</span>
      <span className="puntos__fila" aria-hidden>
        {[1, 2, 3, 4, 5].map((k) => (
          <i key={k} className={k <= n ? 'lleno' : ''} />
        ))}
      </span>
    </div>
  )
}

export default function Tendencias() {
  const { st, reintentar } = useApi(api.tendencias)
  return (
    <Pagina titulo="Tendencias del sector salud" bajada="Amenazas que están golpeando a hospitales y aseguradoras, cruzadas con lo que tenemos expuesto aquí.">
      <Carga st={st} reintentar={reintentar} filas={6}>
        {(d) => (
          <>
            <div className="aviso aviso--hipotesis">
              <FlaskConical size={20} aria-hidden />
              <p>{d.nota}</p>
            </div>
            <div className="tendencias">
              {d.tendencias.map((t: Tendencia) => (
                <article key={t.id} className="tendencia">
                  <header>
                    <h2>{t.titulo}</h2>
                    <p className="muted">
                      {t.fuente}, {fFecha(t.fecha)}
                    </p>
                  </header>
                  <p>{t.resumen}</p>
                  <p className="tendencia__local">
                    <strong>Aquí:</strong> {t.exposicionLocal}
                  </p>
                  <div className="tendencia__pie">
                    <div>
                      <Puntos n={t.relevancia} texto="Relevancia" />
                      <Puntos n={t.exposicion} texto="Exposición" />
                      <Puntos n={t.impacto} texto="Impacto" />
                    </div>
                    <Linea serie={t.serie} />
                  </div>
                  <p className="mono muted">{t.tecnicas.join(', ')}</p>
                </article>
              ))}
            </div>
          </>
        )}
      </Carga>
    </Pagina>
  )
}
