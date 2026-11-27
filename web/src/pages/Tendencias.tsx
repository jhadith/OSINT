import { FlaskConical, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { Tendencia } from '../api/types'
import { Carga, Pagina } from '../components/ui'
import { fFecha } from '../lib/format'
import { useApi } from '../lib/useApi'
import { useSesion } from '../lib/sesion'

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

/** Sello de procedencia de cada tendencia: real (KEV) / real (NVD) / simulado. */
function Sello({ sello }: { sello?: string }) {
  const texto = sello ?? 'simulado'
  const tono = texto.startsWith('real (KEV)')
    ? 'chip--critica'
    : texto.startsWith('real')
      ? 'chip--alta'
      : 'chip--neutro'
  return (
    <span className={`chip ${tono}`} title={texto.startsWith('real') ? 'Lectura real de una fuente pública' : 'Hipótesis de ejemplo del feed fijo'}>
      {texto}
    </span>
  )
}

/** "3 h", "2 días"… para la línea «actualizado hace X». */
function hace(iso: string): string {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (min < 1) return 'unos segundos'
  if (min < 60) return `${min} min`
  const h = Math.round(min / 60)
  if (h < 48) return `${h} h`
  return `${Math.round(h / 24)} días`
}

export default function Tendencias() {
  const { st, reintentar } = useApi(api.tendencias)
  const { puede } = useSesion()
  const [actualizando, setActualizando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)

  async function actualizar() {
    setActualizando(true)
    setAviso(null)
    try {
      const r = await api.actualizarTendencias()
      setAviso(
        r.fallidas
          ? `${r.actualizadas} fuentes al día · ${r.fallidas} fallidas de ${r.totales}`
          : `${r.actualizadas} fuentes al día`,
      )
      reintentar()
    } catch (e) {
      setAviso(e instanceof Error ? e.message : 'No se pudo actualizar desde las fuentes públicas.')
    } finally {
      setActualizando(false)
    }
  }

  return (
    <Pagina
      titulo="Tendencias del sector salud"
      bajada="Amenazas que están golpeando a hospitales y aseguradoras, leídas solo de fuentes oficiales (CTI y TECHINT) y cruzadas con lo que tenemos expuesto aquí."
    >
      <Fuentes />
      <Carga st={st} reintentar={reintentar} filas={6}>
        {(d) => (
          <>
            <div className="aviso aviso--hipotesis">
              <FlaskConical size={20} aria-hidden />
              <p>{d.nota}</p>
            </div>
            <p className="muted" data-testid="linea-osint">
              {d.osint
                ? `Actualizado hace ${hace(d.osint.sincronizadoEn)} · ${d.osint.items} lecturas reales de ${d.osint.fuentes} fuentes públicas.`
                : 'Sin datos reales aún: pulsa «Actualizar desde fuentes» para leer los catálogos y avisos abiertos.'}
              {d.osint?.notas.length ? ` ${d.osint.notas.join(' · ')}` : ''}
            </p>
            {puede('tecnico') && (
              <div className="botones">
                <button className="boton boton--secundario" onClick={actualizar} disabled={actualizando}>
                  <RefreshCw size={16} aria-hidden />
                  {actualizando ? 'Actualizando…' : 'Actualizar desde fuentes'}
                </button>
                {aviso && <span className="muted">{aviso}</span>}
              </div>
            )}
            <div className="tendencias">
              {d.tendencias.map((t: Tendencia) => (
                <article key={t.id} className="tendencia">
                  <header>
                    <h2>{t.titulo}</h2>
                    <p className="muted">
                      {t.fuente}, {t.fecha ? fFecha(t.fecha) : 'sin fecha'} · <Sello sello={t.sello} />
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

/** Las fuentes abiertas que alimentan esta pantalla. */
function Fuentes() {
  const fuentes = [
    ['CISA KEV', 'Vulnerabilidades con explotación confirmada'],
    ['NVD (NIST)', 'Catálogo oficial de CVE'],
    ['CISA e INCIBE-CERT', 'Avisos oficiales de CERT nacionales'],
    ['PSIRT de fabricantes', 'Fortinet, Palo Alto y Ubuntu'],
    ['MITRE ATT&CK', 'Técnicas de ataque de referencia'],
  ]
  return (
    <ul className="fuentes-osint" aria-label="Fuentes abiertas">
      {fuentes.map(([n, d]) => (
        <li key={n}>
          <strong>{n}</strong>
          <span>{d}</span>
        </li>
      ))}
    </ul>
  )
}

