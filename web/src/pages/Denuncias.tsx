import { CalendarClock, ExternalLink, Stethoscope, User } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Denuncia, EstadoDenuncia } from '../api/types'
import { Carga, Pagina, Panel } from '../components/ui'
import { ESTADO_DENUNCIA, fFechaHora, MEDIO } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

const RESPUESTAS: Record<EstadoDenuncia, string> = {
  recibida: 'Recibimos tu denuncia. El equipo de seguridad la revisará.',
  en_revision: 'Estamos revisando tu denuncia junto con el área de agendamiento. Gracias por avisar.',
  atendida: 'Gracias. Con tu denuncia tomamos medidas sobre las reservas de ese origen. Recuerda: las citas son gratuitas.',
  descartada: 'Revisamos tu denuncia y no encontramos relación con las citas o los sistemas. Gracias por avisar.',
}

export default function Denuncias() {
  const { st, reintentar, actualizar } = useApi(api.denuncias)
  const [sel, setSel] = useState<string | null>(null)
  return (
    <Pagina
      titulo="Denuncias"
      bajada="Lo que reportan afiliados y jubilados desde el portal público y el personal de salud desde «Verificar contenido». Se cruzan con las citas del chatbot."
      acciones={
        <a className="boton boton--secundario" href="/denuncia" target="_blank" rel="noreferrer">
          Abrir el portal público <ExternalLink size={15} aria-hidden />
        </a>
      }
    >
      <Carga st={st} reintentar={reintentar}>
        {(lista) => {
          if (!lista.length)
            return (
              <div className="vacio">
                <h2>Aún no llegan denuncias</h2>
                <p>Cuando un afiliado use el portal público, su denuncia aparecerá aquí con un código para darle seguimiento.</p>
              </div>
            )
          const elegida = lista.find((d) => d.codigo === sel) ?? lista[0]
          return (
            <div className="rejilla rejilla--agenda">
              <ul className="origenes">
                {lista.map((d) => (
                  <li key={d.codigo}>
                    <button className={`origen ${elegida.codigo === d.codigo ? 'origen--sel' : ''}`} onClick={() => setSel(d.codigo)}>
                      <span className="origen__fila">
                        <span className={`estado-den estado-den--${d.estado}`}>{ESTADO_DENUNCIA[d.estado]}</span>
                        <span className="mono">{d.codigo}</span>
                        <span className="muted">{fFechaHora(d.fecha)}</span>
                      </span>
                      <span className="origen__frase">{d.tipo_texto}</span>
                      <span className="origen__pat">
                        <span className="pildora">
                          {d.origen === 'ciudadano' ? <User size={12} aria-hidden /> : <Stethoscope size={12} aria-hidden />} {d.origen}
                        </span>
                        {d.medio && <span className="pildora">{MEDIO[d.medio] ?? d.medio}</span>}
                        {d.origenesAgendamiento.length > 0 && (
                          <span className="pildora pildora--denuncia">
                            <CalendarClock size={12} aria-hidden /> ligada a citas
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <DetalleDenuncia
                key={elegida.codigo}
                d={elegida}
                alGestionar={(n) => actualizar((l) => l.map((x) => (x.codigo === n.codigo ? { ...x, ...n } : x)))}
              />
            </div>
          )
        }}
      </Carga>
    </Pagina>
  )
}

function DetalleDenuncia({ d, alGestionar }: { d: Denuncia; alGestionar: (d: Denuncia) => void }) {
  const { puede } = useSesion()
  const [estado, setEstado] = useState<EstadoDenuncia>(d.estado === 'recibida' ? 'en_revision' : d.estado)
  const [respuesta, setRespuesta] = useState(d.estado === 'recibida' ? RESPUESTAS.en_revision : d.respuesta_publica)
  const [nota, setNota] = useState(d.nota_interna)
  const [error, setError] = useState('')
  const [guardado, setGuardado] = useState(false)

  return (
    <Panel
      className="detalle-origen"
      titulo={
        <>
          <span className="mono">{d.codigo}</span> <span className={`estado-den estado-den--${d.estado}`}>{ESTADO_DENUNCIA[d.estado]}</span>
        </>
      }
      bajada={`Recibida el ${fFechaHora(d.fecha)} desde ${d.origen === 'ciudadano' ? 'el portal público' : 'Verificar contenido'}.`}
    >
      <h3>{d.tipo_texto}</h3>
      {d.descripcion ? <blockquote className="cita">{d.descripcion}</blockquote> : <p className="muted">Sin descripción.</p>}
      <dl className="ficha-datos">
        <div>
          <dt>Cuándo pasó</dt>
          <dd>{d.cuando || 'Sin indicar'}</dd>
        </div>
        <div>
          <dt>Por dónde</dt>
          <dd>{MEDIO[d.medio] ?? d.medio}</dd>
        </div>
        <div>
          <dt>Contacto sospechoso</dt>
          <dd className="mono">{d.contacto_sospechoso_mascara || 'No lo indicó'}</dd>
        </div>
        <div>
          <dt>Quiere respuesta en</dt>
          <dd>{d.responder_a || 'No dejó contacto'}</dd>
        </div>
      </dl>

      {d.origenesAgendamiento.length > 0 && (
        <div className="aviso aviso--info">
          <CalendarClock size={20} aria-hidden />
          <div>
            <strong>El contacto denunciado coincide con un origen de citas en revisión.</strong> Se suma como evidencia externa
            (patrón HG-07).{' '}
            {d.origenesAgendamiento.map((o) => (
              <Link key={o} to="/agendamiento" className="enlace mono">
                {o}
              </Link>
            ))}
          </div>
        </div>
      )}

      {d.enlace && (
        <div className={`aviso aviso--${d.verificacion?.veredicto === 'seguro' ? 'info' : 'critica'}`}>
          <div>
            <strong>Enlace reportado:</strong> <span className="mono quiebre">{d.enlace}</span>
            {d.verificacion && (
              <p>
                Revisión automática: <strong>{d.verificacion.veredicto}</strong>. {d.verificacion.recomendacion}
              </p>
            )}
          </div>
        </div>
      )}

      {puede('gestionar_denuncias') ? (
        <div className="revisar">
          <h3>Gestionar</h3>
          <div className="opciones">
            {(Object.keys(ESTADO_DENUNCIA) as EstadoDenuncia[]).map((k) => (
              <button
                key={k}
                type="button"
                className={`opcion ${estado === k ? 'opcion--sel' : ''}`}
                aria-pressed={estado === k}
                onClick={() => {
                  setEstado(k)
                  setRespuesta(RESPUESTAS[k])
                }}
              >
                {ESTADO_DENUNCIA[k]}
              </button>
            ))}
          </div>
          <label className="campo">
            Respuesta que verá el afiliado con su código
            <textarea rows={3} value={respuesta} onChange={(e) => setRespuesta(e.target.value)} maxLength={600} />
          </label>
          <label className="campo">
            Nota interna (solo el SOC)
            <textarea rows={2} value={nota} onChange={(e) => setNota(e.target.value)} maxLength={600} />
          </label>
          {error && <p className="error-linea">{error}</p>}
          <button
            className="boton"
            onClick={() =>
              api
                .gestionar(d.codigo, estado, respuesta, nota)
                .then((n) => {
                  alGestionar({ ...d, ...n, origenesAgendamiento: d.origenesAgendamiento })
                  setGuardado(true)
                })
                .catch((e: Error) => setError(e.message))
            }
          >
            Guardar y responder
          </button>
          {guardado && <p className="ok-linea">Guardado. El afiliado ya ve la respuesta con su código.</p>}
        </div>
      ) : (
        <p className="nota">Tu rol puede ver las denuncias, pero las gestiona el analista del SOC.</p>
      )}
      {d.gestionado_por && (
        <p className="nota">
          Última gestión: {d.gestionado_por}
          {d.actualizado ? `, ${fFechaHora(d.actualizado)}` : ''}.
        </p>
      )}
    </Panel>
  )
}
