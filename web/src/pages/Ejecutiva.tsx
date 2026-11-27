import { BellRing, CalendarClock, ChevronRight, Megaphone, ShieldAlert } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Ejecutivo } from '../api/types'
import { Pulso } from '../components/Pulso'
import { Carga, Gravedad, Pagina, Panel } from '../components/ui'
import { duracion, enPalabras, ESTADO_CASO, fMesTitulo, num, plural } from '../lib/format'
import { useSesion } from '../lib/sesion'
import { useApi } from '../lib/useApi'

export default function Ejecutiva() {
  const { st, reintentar } = useApi(api.ejecutivo)
  return (
    <Carga st={st} reintentar={reintentar} filas={7}>
      {(e) => <Vista e={e} />}
    </Carga>
  )
}

function Vista({ e }: { e: Ejecutivo }) {
  const { puede } = useSesion()
  const ir = useNavigate()
  const verCaso = puede('operativo') ? (id: string) => ir(`/casos/${id}`) : undefined
  const mes = fMesTitulo(e.periodo.desde)

  return (
    <Pagina titulo={`${mes} en una página`} bajada="Qué pasó, qué significa para la institución y qué conviene decidir.">
      <section className="titular">
        <p className="titular__frase">
          Revisamos <strong>{enPalabras(e.registros)}{e.registros >= 1e6 ? ' de' : ''} registros</strong> en {duracion(e.minutos)} y encontramos{' '}
          <strong>{plural(e.incidentes, 'incidente', 'incidentes')}</strong>
          {e.criticos > 0 && (
            <>
              ; <strong className="t-critica">{e.criticos} son críticos</strong>
            </>
          )}
          .
        </p>
        <p className="titular__nota">
          Una persona leyendo un registro por segundo habría necesitado {plural(e.jornadasManuales, 'jornada', 'jornadas')} de 8
          horas para revisar lo mismo.
        </p>
      </section>

      <Panel
        className="panel--pulso"
        titulo="Pulso del mes"
        bajada="Cada latido resume 6 horas de actividad del sistema médico y de la red. Las espigas de color son los incidentes detectados; toca una para ver el caso."
      >
        <Pulso pulso={e.pulso} historia={e.historia} onElegir={verCaso} />
      </Panel>

      <div className="rejilla rejilla--ejecutiva">
        <Panel titulo="Lo que pasó" bajada="En orden de fecha, contado sin tecnicismos.">
          <ol className="historia">
            {e.historia.map((h) => (
              <li key={h.id} className={`historia__item historia__item--${h.gravedad}`}>
                <div className="historia__fecha">{h.fecha}</div>
                <div className="historia__cuerpo">
                  <h3>
                    {h.titulo} <Gravedad g={h.gravedad} />
                    {h.avisoTelegram && (
                      <span className="etiqueta" title="Se avisó por Telegram al equipo de guardia">
                        <BellRing size={14} aria-hidden /> Aviso por Telegram
                      </span>
                    )}
                  </h3>
                  <p>{h.frase}</p>
                  <p className="historia__accion">
                    <strong>Qué hacer:</strong> {h.accion}
                  </p>
                  <p className="historia__estado">
                    Decisión del analista: <span className={`estado estado--${h.estado}`}>{ESTADO_CASO[h.estado]}</span>
                    {verCaso && (
                      <Link to={`/casos/${h.id}`} className="enlace">
                        Ver el caso {h.id} <ChevronRight size={14} aria-hidden />
                      </Link>
                    )}
                  </p>
                </div>
              </li>
            ))}
            {!e.historia.length && <li className="muted">No quedan incidentes vigentes en este análisis.</li>}
          </ol>
        </Panel>

        <div className="pila">
          <Panel titulo="Riesgos que más pesan" extra={<Link to="/riesgos" className="enlace">Ver la matriz</Link>}>
            <ul className="riesgos-top">
              {e.riesgosPrincipales.map((r) => (
                <li key={r.id}>
                  <span className={`nivel nivel--${r.nivel >= 20 ? 'critica' : r.nivel >= 12 ? 'alta' : r.nivel >= 6 ? 'media' : 'baja'}`}>
                    {r.nivel}
                  </span>
                  <div>
                    <strong>{r.nombre}</strong>
                    <p>{r.tratamiento}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="nota">
              Nivel = probabilidad × impacto, de 1 a 25. {plural(e.riesgosCriticos, 'riesgo está', 'riesgos están')} en zona crítica (20 o más).
            </p>
          </Panel>

          {e.extraccionesExitosas > 0 && (
            <div className="aviso aviso--critica">
              <ShieldAlert size={22} aria-hidden />
              <div>
                <strong>La información sí salió en {plural(e.extraccionesExitosas, 'ocasión', 'ocasiones')}.</strong>
                <p>
                  Hubo transferencias o descargas que se completaron. Conviene evaluar con el área legal la notificación que
                  exige la Ley de Protección de Datos Personales.
                </p>
              </div>
            </div>
          )}

          {e.agendamiento && (
            <Panel titulo={<><CalendarClock size={18} aria-hidden /> Citas del chatbot</>}>
              <p className="dato-grande">
                <strong>{num(e.agendamiento.origenesEnRevision)}</strong> orígenes reservan citas para muchos pacientes a la vez,
                como lo haría un tramitador.
              </p>
              <p>
                Conviene confirmar <strong>{num(e.agendamiento.citasAConfirmar)}</strong> de {num(e.agendamiento.reservas)} citas
                con el afiliado antes de la fecha. Ninguna se cancela de forma automática.
              </p>
              {e.agendamiento.explicadosLegitimos > 0 && (
                <p className="nota">
                  {plural(e.agendamiento.explicadosLegitimos, 'caso parecido era', 'casos parecidos eran')} de cuidadores u
                  operadores autorizados y no se marcó como sospechoso.
                </p>
              )}
              {puede('operativo') && (
                <Link to="/agendamiento" className="enlace">
                  Revisar los orígenes <ChevronRight size={14} aria-hidden />
                </Link>
              )}
            </Panel>
          )}

          <Panel titulo={<><Megaphone size={18} aria-hidden /> Denuncias de afiliados</>}>
            <p className="dato-grande">
              <strong>{num(e.denuncias.recibidas)}</strong> {e.denuncias.recibidas === 1 ? 'recibida' : 'recibidas'},{' '}
              {num(e.denuncias.abiertas)} sin cerrar.
            </p>
            <p className="nota">Llegan por el portal público, sin cédula ni nombre, y se cruzan con las citas del chatbot.</p>
            {puede('ver_denuncias') && (
              <Link to="/denuncias" className="enlace">
                Abrir la bandeja <ChevronRight size={14} aria-hidden />
              </Link>
            )}
          </Panel>
        </div>
      </div>
    </Pagina>
  )
}
